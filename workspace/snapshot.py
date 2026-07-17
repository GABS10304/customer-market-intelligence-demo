"""
Persistierter Workspace-Snapshot — BigQuery-Evidenz einmal berechnen, wiederverwenden.

Invalidierung bei Pipeline-Lauf / Upload (catalog + RAG-Meta ändern den Fingerprint).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import pandas as pd

from config import DEMO_MODE, SNAPSHOT_PATH, ensure_data_dirs
from core.bq_evidence import SOURCE_QUERIES, fetch_cluster_counts, fetch_sample_texts, load_rag_meta
from core.product_lines import ALL_PRODUCT_LINES, classify_product_line, classify_product_line_with_reason
from core.intent_by_group import intent_by_group_records
from core.intent_by_module import intent_by_module_records
from core.product_priority import build_priority_matrix, priority_insights
from core.sales_evidence import (
    SALES_TECHNICAL_NAME,
    collect_sales_theme_scores,
    sales_fingerprint_token,
    top_products,
    top_products_by_revenue,
    total_revenue,
)
from core.source_dedup import DEDUP_OFFSETS_PATH
from workspace.catalog import load_catalog
from workspace.compare import THEME_KEYWORDS, _survey_category_themes, themes_in_text
from workspace.sources.profiles import BUILTIN_PROFILES, legacy_evidence_key, source_short_label
from workspace.tiles import tile_data_coverage

THEME_TOP_CLUSTERS = 30
COMPARE_TOP_N = 10


def _theme_matrix(per_source: dict[str, dict[str, dict]]) -> pd.DataFrame:
    """Themen-Matrix aus vorberechneten Quellen-Scores (kein BigQuery)."""
    if not per_source:
        return pd.DataFrame()

    rows = []
    for theme in THEME_KEYWORDS:
        row: dict = {"Thema": theme}
        scores_by_src = {}
        for name, theme_data in per_source.items():
            short = source_short_label(name)
            score = theme_data.get(theme, {}).get("score", 0)
            scores_by_src[name] = score
            row[f"{short} (Score)"] = score
            clusters = theme_data.get(theme, {}).get("clusters", [])[:2]
            row[f"{short} (Cluster)"] = "; ".join(clusters) if clusters else "—"

        active = [n for n, s in scores_by_src.items() if s > 0]
        total = sum(scores_by_src.values())
        row["Overlap"] = "✅" if len(active) >= 2 else ("—" if not active else "nur 1 Quelle")
        row["Gesamt_Score"] = total
        rows.append(row)

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values("Gesamt_Score", ascending=False).reset_index(drop=True)


def _overlap_lines(theme_df: pd.DataFrame, min_score: int = 5) -> list[str]:
    if theme_df.empty:
        return ["Keine Themen-Daten verfügbar — BigQuery prüfen."]

    lines: list[str] = []
    overlaps = theme_df[theme_df["Overlap"] == "✅"]
    if overlaps.empty:
        return [
            "Keine gemeinsamen Themen mit ausreichend Signal in beiden Quellen.",
            "Tipp: Cluster-Namen unterscheiden sich (Modul vs. Kategorie) — Themen-Matrix unten prüfen.",
        ]

    for _, row in overlaps.iterrows():
        score_cols = [c for c in theme_df.columns if c.endswith("(Score)")]
        total = sum(int(row.get(c, 0) or 0) for c in score_cols)
        if total < min_score:
            continue
        theme = row["Thema"]
        parts = []
        for c in score_cols:
            val = int(row.get(c, 0) or 0)
            if val:
                label = c.replace(" (Score)", "")
                cluster_col = c.replace("(Score)", "(Cluster)")
                parts.append(f"{label} {val} ({row.get(cluster_col, '—')})")
        lines.append(f"**{theme}** — " + "; ".join(parts) + ".")

    if not lines:
        return ["Schwache Overlaps — Themen tauchen in beiden Quellen auf, aber mit geringer Häufigkeit."]
    return lines


def _collect_theme_scores_from_df(
    source_key: str,
    technical_name: str,
    df: pd.DataFrame,
    sample_fn: Callable[[str, str, int], list[str]],
) -> dict[str, dict]:
    """Themen-Scores aus vorberechneten Cluster-Daten (kein extra BQ)."""
    if df.empty:
        return {}

    label = BUILTIN_PROFILES.get(technical_name)
    display = label.display_name if label else source_key

    scores: dict[str, dict] = {
        t: {"score": 0, "clusters": [], "samples": [], "quelle": display}
        for t in THEME_KEYWORDS
    }

    for row in df.itertuples():
        cluster = str(row.cluster)
        count = int(row.anzahl)
        from_cluster = source_key == "support"
        themes = themes_in_text(cluster, from_cluster=from_cluster)

        if source_key == "surveys":
            themes |= _survey_category_themes(cluster)

        if count >= 5 and not themes:
            samples = sample_fn(source_key, cluster, 2)
            for sample in samples:
                themes |= themes_in_text(sample, from_cluster=False)

        for theme in themes:
            scores[theme]["score"] += count
            entry = f"{cluster} ({count}×)"
            if entry not in scores[theme]["clusters"]:
                scores[theme]["clusters"].append(entry)

    return scores


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_fingerprint() -> str:
    """Stabil — nur RAG-Meta + Quellen-Zeitstempel, nicht catalog.updated_at."""
    catalog = load_catalog()
    rag = load_rag_meta()
    parts = [
        rag.get("built_at", "") or "",
        str(rag.get("documents", "") or ""),
        str(rag.get("chunks", "") or ""),
    ]
    if DEDUP_OFFSETS_PATH.exists():
        parts.append(DEDUP_OFFSETS_PATH.read_text(encoding="utf-8"))
    parts.append(sales_fingerprint_token())
    for name in sorted(BUILTIN_PROFILES.keys()):
        src = catalog.get("sources", {}).get(name, {})
        parts.append(f"{name}:{src.get('last_updated', '') or ''}:{src.get('row_count', '') or ''}")
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def invalidate_workspace_snapshot() -> None:
    if DEMO_MODE:
        return
    ensure_data_dirs()
    if SNAPSHOT_PATH.exists():
        SNAPSHOT_PATH.unlink()


def _df_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    return df.to_dict(orient="records")


def _records_to_df(records: list[dict[str, Any]], columns: list[str] | None = None) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=columns or [])
    return pd.DataFrame(records)


def _build_snapshot_data() -> dict[str, Any]:
    """Einmaliger BigQuery-Lauf — alle Dashboard-Daten."""
    cluster_counts: dict[str, list[dict[str, Any]]] = {}
    for key in SOURCE_QUERIES:
        for limit in (THEME_TOP_CLUSTERS, COMPARE_TOP_N, 5, 10):
            cache_key = f"{key}:{limit}"
            if cache_key not in cluster_counts:
                cluster_counts[cache_key] = _df_to_records(fetch_cluster_counts(key, limit=limit))

    sample_cache: dict[str, list[str]] = {}

    def sample_fn(source_key: str, cluster: str, limit: int = 2) -> list[str]:
        cache_key = f"{source_key}|{cluster}|{limit}"
        if cache_key not in sample_cache:
            sample_cache[cache_key] = fetch_sample_texts(source_key, cluster, limit=limit)
        return sample_cache[cache_key]

    source_themes: dict[str, dict[str, dict]] = {}
    for name in BUILTIN_PROFILES:
        key = legacy_evidence_key(name)
        if name == SALES_TECHNICAL_NAME:
            source_themes[name] = collect_sales_theme_scores(THEME_TOP_CLUSTERS)
            continue
        if key not in SOURCE_QUERIES:
            continue
        df = _records_to_df(cluster_counts[f"{key}:{THEME_TOP_CLUSTERS}"])
        source_themes[name] = _collect_theme_scores_from_df(
            key,
            name,
            df,
            sample_fn,
        )

    sales_top = _df_to_records(top_products(THEME_TOP_CLUSTERS))
    sales_revenue = _df_to_records(top_products_by_revenue(THEME_TOP_CLUSTERS))
    support_clusters = cluster_counts.get(f"support:{THEME_TOP_CLUSTERS}", [])
    priority_rows = _df_to_records(
        build_priority_matrix(support_clusters, limit=20)
    )
    intent_groups = intent_by_group_records(all_sources=True)
    intent_modules = intent_by_module_records()

    return {
        "fingerprint": build_fingerprint(),
        "built_at": _now(),
        "cluster_counts": cluster_counts,
        "source_themes": source_themes,
        "sales_top_products": sales_top,
        "sales_top_revenue": sales_revenue,
        "sales_total_revenue": total_revenue(),
        "priority_matrix": priority_rows,
        "intent_by_group": intent_groups,
        "intent_by_module": intent_modules,
        "data_coverage": tile_data_coverage(),
    }


def _save_snapshot(data: dict[str, Any]) -> None:
    ensure_data_dirs()
    SNAPSHOT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_snapshot_file() -> dict[str, Any] | None:
    if not SNAPSHOT_PATH.exists():
        return None
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


@dataclass
class WorkspaceSnapshot:
    fingerprint: str
    built_at: str
    cluster_counts: dict[str, list[dict[str, Any]]]
    source_themes: dict[str, dict[str, dict]]
    data_coverage: list[dict[str, Any]]
    sales_top_products: list[dict[str, Any]] | None = None
    sales_top_revenue: list[dict[str, Any]] | None = None
    sales_total_revenue: float = 0.0
    priority_matrix: list[dict[str, Any]] | None = None
    intent_by_group: list[dict[str, Any]] | None = None
    intent_module_rows: list[dict[str, Any]] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspaceSnapshot:
        return cls(
            fingerprint=data["fingerprint"],
            built_at=data["built_at"],
            cluster_counts=data["cluster_counts"],
            source_themes=data["source_themes"],
            data_coverage=data.get("data_coverage", []),
            sales_top_products=data.get("sales_top_products", []),
            sales_top_revenue=data.get("sales_top_revenue", []),
            sales_total_revenue=float(data.get("sales_total_revenue") or 0),
            priority_matrix=data.get("priority_matrix", []),
            intent_by_group=data.get("intent_by_group", []),
            intent_module_rows=data.get("intent_by_module", []),
        )

    def _clusters(self, source_key: str, limit: int) -> pd.DataFrame:
        return _records_to_df(
            self.cluster_counts.get(f"{source_key}:{limit}", []),
            columns=["quelle", "cluster", "anzahl"],
        )

    def top_needs(self, selected: list[str], limit: int = 5) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for name in selected:
            if name == SALES_TECHNICAL_NAME:
                df = _records_to_df(self.sales_top_products or []).head(limit).copy()
                if not df.empty:
                    profile = BUILTIN_PROFILES.get(name)
                    if profile:
                        df["quelle"] = profile.display_name
                    frames.append(df)
                continue
            key = legacy_evidence_key(name)
            if key not in SOURCE_QUERIES:
                continue
            df = self._clusters(key, THEME_TOP_CLUSTERS).head(limit).copy()
            if df.empty:
                continue
            profile = BUILTIN_PROFILES.get(name)
            if profile:
                df["quelle"] = profile.display_name
            frames.append(df)
        if not frames:
            return pd.DataFrame(columns=["quelle", "cluster", "anzahl"])
        return pd.concat(frames, ignore_index=True).sort_values("anzahl", ascending=False).head(limit)

    def sales_penetration(self, limit: int = 10) -> pd.DataFrame:
        return _records_to_df(self.sales_top_products or [], columns=["quelle", "cluster", "anzahl", "Kundentyp"]).head(
            limit
        )

    def sales_revenue(self, limit: int = 10) -> pd.DataFrame:
        return _records_to_df(
            self.sales_top_revenue or [],
            columns=["quelle", "cluster", "umsatz", "Kundentyp"],
        ).head(limit)

    def product_priority(self, limit: int = 15) -> pd.DataFrame:
        cols = [
            "produkt",
            "produktlinie",
            "summe_umsatz",
            "anzahl_kunden",
            "ticket_cluster",
            "ticket_anzahl",
            "match_score",
            "match_art",
            "mapping_id",
            "prioritaet_score",
            "prioritaet_stufe",
        ]
        df = _records_to_df(self.priority_matrix or [], columns=cols)
        if df.empty and self.sales_top_revenue:
            df = build_priority_matrix(
                self.cluster_counts.get(f"support:{THEME_TOP_CLUSTERS}", []),
                limit=limit,
            )
        return df.head(limit)

    def priority_summary(self, limit: int = 3) -> list[str]:
        return priority_insights(self.product_priority(limit=20), top_n=limit)

    def intent_by_business_group(self, limit: int = 15) -> pd.DataFrame:
        cols = [
            "business_gruppe",
            "summe_umsatz",
            "ticket_anzahl",
            "dominant_intent",
            "How-To",
            "Discovery",
            "Defekt",
            "Installation",
            "Sonstiges",
            "pct_How-To",
            "pct_Discovery",
        ]
        df = _records_to_df(self.intent_by_group or [], columns=cols)
        if df.empty:
            from core.intent_by_group import aggregate_intent_by_business_group

            return aggregate_intent_by_business_group(all_sources=True).head(limit)
        return df.head(limit)

    def module_intent_table(self, limit: int = 15) -> pd.DataFrame:
        """Intent/Bedarf pro Modul — Snapshot-Zeilen oder Live-Aggregation."""
        cols = [
            "modul",
            "summe_umsatz",
            "eintraege",
            "dominant_intent",
            "top_bedarf",
            "Defekt",
            "How-To",
            "Discovery",
            "quellen",
        ]
        df = _records_to_df(self.intent_module_rows or [], columns=cols)
        if df.empty:
            from core.intent_by_module import aggregate_intent_by_module

            return aggregate_intent_by_module().head(limit)
        return df.head(limit)

    def hotline_frequency(self, selected: list[str]) -> pd.DataFrame:
        if "support_tickets_html" not in selected:
            return pd.DataFrame(columns=["quelle", "cluster", "anzahl"])
        return self._clusters("support", 10)

    def _product_line_rows(self, selected: list[str], *, limit: int = 30) -> list[dict]:
        rows: list[dict] = []
        for name in selected:
            if name == SALES_TECHNICAL_NAME:
                for rec in (self.sales_top_products or [])[:limit]:
                    rows.append(
                        {
                            "Produktlinie": classify_product_line(str(rec.get("cluster", ""))),
                            "cluster": rec.get("cluster"),
                            "anzahl": int(rec.get("anzahl") or 0),
                            "quelle": rec.get("quelle", "Verträge"),
                            "kind": "erp",
                        }
                    )
                continue
            key = legacy_evidence_key(name)
            if key not in SOURCE_QUERIES:
                continue
            df = self._clusters(key, THEME_TOP_CLUSTERS)
            profile = BUILTIN_PROFILES.get(name)
            display = profile.display_name if profile else name
            for rec in df.to_dict(orient="records")[:limit]:
                cluster = str(rec.get("cluster", ""))
                rows.append(
                    {
                        "Produktlinie": classify_product_line(cluster),
                        "cluster": cluster,
                        "anzahl": int(rec.get("anzahl") or 0),
                        "quelle": display,
                        "kind": "signal",
                    }
                )
        return rows

    def product_line_breakdown(self, selected: list[str], *, limit: int = 30) -> pd.DataFrame:
        """Aggregiert Cluster/Artikel nach Produktlinie — Signale und ERP-Kunden getrennt."""
        rows = self._product_line_rows(selected, limit=limit)
        if not rows:
            return pd.DataFrame(
                columns=["Produktlinie", "signale", "kunden_erp", "Produkte", "quellen"]
            )
        detail = pd.DataFrame(rows)
        detail["signale"] = detail["anzahl"].where(detail["kind"] == "signal", 0)
        detail["kunden_erp"] = detail["anzahl"].where(detail["kind"] == "erp", 0)
        summary = (
            detail.groupby("Produktlinie", dropna=False)
            .agg(
                signale=("signale", "sum"),
                kunden_erp=("kunden_erp", "sum"),
                Produkte=("cluster", "nunique"),
                quellen=("quelle", "nunique"),
            )
            .reset_index()
        )
        order = {line: i for i, line in enumerate(ALL_PRODUCT_LINES)}
        summary["_ord"] = summary["Produktlinie"].map(lambda x: order.get(x, 99))
        summary["_rank"] = summary["signale"] + summary["kunden_erp"]
        return summary.sort_values(["_ord", "_rank"], ascending=[True, False]).drop(columns=["_ord", "_rank"])

    def product_line_detail(self, selected: list[str], product_line: str, *, limit: int = 10) -> pd.DataFrame:
        """Top-Cluster für eine Produktlinie."""
        rows = [
            {
                "cluster": rec["cluster"],
                "anzahl": rec["anzahl"],
                "quelle": rec["quelle"],
                "einheit": "Kunden (ERP)" if rec["kind"] == "erp" else "Signale",
                "zuordnung": classify_product_line_with_reason(str(rec["cluster"]))[1],
            }
            for rec in self._product_line_rows(selected, limit=THEME_TOP_CLUSTERS)
            if rec["Produktlinie"] == product_line
        ]
        if not rows:
            return pd.DataFrame(columns=["cluster", "anzahl", "einheit", "quelle", "zuordnung"])
        return pd.DataFrame(rows).sort_values("anzahl", ascending=False).head(limit)

    def compare_themes(self, selected: list[str]) -> pd.DataFrame:
        per_source = {name: self.source_themes[name] for name in selected if name in self.source_themes}
        return _theme_matrix(per_source)

    def compare_sources(self, selected: list[str], top_n: int = 8) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for name in selected:
            if name == SALES_TECHNICAL_NAME:
                df = self.sales_penetration(top_n).copy()
                if df.empty:
                    continue
                df["source_id"] = name
                frames.append(df[["source_id", "quelle", "cluster", "anzahl"]])
                continue
            key = legacy_evidence_key(name)
            if key not in SOURCE_QUERIES:
                continue
            df = self._clusters(key, max(top_n, COMPARE_TOP_N)).head(top_n).copy()
            if df.empty:
                continue
            df["source_id"] = name
            frames.append(df[["source_id", "quelle", "cluster", "anzahl"]])
        if not frames:
            return pd.DataFrame(columns=["source_id", "quelle", "cluster", "anzahl"])
        return pd.concat(frames, ignore_index=True)

    def find_overlap(self, selected: list[str]) -> list[str]:
        return _overlap_lines(self.compare_themes(selected))

    def strategic_opportunities(self, selected: list[str]) -> list[str]:
        hints: list[str] = []
        top = self.top_needs(selected, limit=3)
        if top.empty:
            return ["Noch keine Evidenz in BigQuery — Pipeline oder Upload ausführen."]
        for row in top.itertuples():
            hints.append(
                f"**{row.cluster}** ({int(row.anzahl)}× in {row.quelle}): "
                "Kontextsensitive Hilfe / In-App-Guidance prüfen."
            )
        if len(selected) >= 2:
            hints.append(
                "Compare Mode: Quellen parallel wählen und wiederkehrende Cluster vergleichen."
            )
        return hints

    def deterministic_strategy(self, selected: list[str]) -> dict[str, Any]:
        top = self.top_needs(selected, limit=5)
        compare_df = self.compare_sources(selected, top_n=5)
        actions: list[str] = []
        if top.empty:
            return {
                "summary": "Keine Evidenz — zuerst Daten ingestieren.",
                "actions": ["Pipeline ausführen oder CSV bestätigen."],
                "confidence": "low",
            }
        dominant = top.iloc[0]
        priority_df = self.product_priority(limit=5)
        revenue_hint = ""
        if not priority_df.empty:
            top_rev = priority_df.iloc[0]
            revenue_hint = (
                f" ERP-Top: **{top_rev['produkt']}** "
                f"(Umsatz {float(top_rev['summe_umsatz']):,.0f} €, Priorität {top_rev['prioritaet_stufe']})."
            ).replace(",", ".")
        actions.append(
            f"Priorität 1: **{dominant['cluster']}** ({int(dominant['anzahl'])} Vorkommen) — "
            "kontextsensitive Hilfe im Produkt verbessern."
            + revenue_hint
        )
        if len(selected) >= 2:
            overlap = self.find_overlap(selected)
            actions.append(f"Quellenvergleich: {overlap[0] if overlap else 'Kein klares Overlap'}")
        actions.append(
            "KI-Strategie (regelbasiert): Internes RAG über BigQuery vor externen Chat-Tools — "
            "DSGVO und Evidenzbindung."
        )
        if int(dominant["anzahl"]) >= 20:
            actions.append(
                "Hohe Ticket-/Feedback-Häufigkeit → Make (eigene UX-Hilfe) vor Buy (externes KI-Tool)."
            )
        return {
            "summary": f"Top Need: {dominant['cluster']} ({int(dominant['anzahl'])}×)",
            "actions": actions,
            "confidence": "high" if int(dominant["anzahl"]) >= 15 else "medium",
            "compare_rows": len(compare_df),
        }


def load_or_build_workspace_snapshot(*, force_rebuild: bool = False) -> WorkspaceSnapshot:
    """Legacy: lädt von Disk oder baut aus BQ (force_rebuild=True)."""
    return load_workspace_snapshot(force_rebuild=force_rebuild).snapshot


@dataclass(frozen=True)
class SnapshotLoadResult:
    snapshot: WorkspaceSnapshot
    stale: bool
    stale_reason: str
    source: str  # disk | bigquery | empty


def load_workspace_snapshot(*, force_rebuild: bool = False) -> SnapshotLoadResult:
    """
    Fast-boot: Snapshot von Disk wenn vorhanden (kein BQ beim Start).
    force_rebuild=True oder fehlende Datei → BigQuery-Lauf (nicht im Demo-Modus).
    """
    if DEMO_MODE:
        cached = _load_snapshot_file()
        if cached:
            return SnapshotLoadResult(
                snapshot=WorkspaceSnapshot.from_dict(cached),
                stale=False,
                stale_reason="",
                source="demo",
            )
        return SnapshotLoadResult(
            snapshot=WorkspaceSnapshot.from_dict(
                {
                    "fingerprint": "demo-empty",
                    "built_at": _now(),
                    "cluster_counts": {},
                    "source_themes": {},
                    "data_coverage": [],
                }
            ),
            stale=True,
            stale_reason="Demo-Snapshot fehlt — data/demo/workspace_snapshot.json prüfen.",
            source="demo",
        )

    cached = _load_snapshot_file()

    if not force_rebuild and cached:
        stale = cached.get("fingerprint") != build_fingerprint()
        reason = (
            "Rohdaten/RAG/Catalog geändert — «Evidenz aus BQ laden» oder Pipeline."
            if stale
            else ""
        )
        return SnapshotLoadResult(
            snapshot=WorkspaceSnapshot.from_dict(cached),
            stale=stale,
            stale_reason=reason,
            source="disk",
        )

    data = _build_snapshot_data()
    _save_snapshot(data)
    return SnapshotLoadResult(
        snapshot=WorkspaceSnapshot.from_dict(data),
        stale=False,
        stale_reason="",
        source="bigquery",
    )


def rebuild_workspace_snapshot() -> WorkspaceSnapshot:
    """Expliziter BQ-Refresh (Sidebar / nach Pipeline). Im Demo-Modus: Snapshot von Disk."""
    if DEMO_MODE:
        return load_workspace_snapshot(force_rebuild=False).snapshot
    return load_workspace_snapshot(force_rebuild=True).snapshot
