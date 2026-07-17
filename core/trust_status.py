"""
Vertrauens-Status — Transparenz für Mapping, Hotline, Umfrage, RAG, Snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import pandas as pd

from config import DEMO_MODE, PRODUCT_SIGNALS_CSV, SNAPSHOT_PATH
from core.bq_evidence import load_rag_meta

DEFAULT_OUTPUT = PRODUCT_SIGNALS_CSV


@dataclass(frozen=True)
class TrustStatus:
    level: str  # hoch | mittel | niedrig
    summary: str
    snapshot_at: str
    snapshot_source: str
    mapping_seed_entries: int
    matrix_rows: int
    matrix_mapped: int
    matrix_mapped_pct: float
    hotline_unmapped_pct: float
    hotline_aligned: bool
    survey_match_pct: float
    rag_fresh: bool
    rag_label: str
    rag_documents: int
    product_signals_label: str
    warnings: tuple[str, ...]
    actions: tuple[str, ...]
    top_unmapped: tuple[tuple[str, int], ...]


def _file_mtime_label(path: Path) -> str:
    if not path.exists():
        return "—"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def _matrix_stats(df: pd.DataFrame) -> tuple[int, int, float, float, tuple[tuple[str, int], ...]]:
    if df.empty or "mapping_id" not in df.columns:
        return 0, 0, 0.0, 0.0, ()
    mapped = ~df["mapping_id"].astype(str).str.startswith("unmapped:")
    rows = len(df)
    mapped_n = int(mapped.sum())
    mapped_pct = round(100.0 * mapped_n / rows, 1) if rows else 0.0
    hotline = pd.to_numeric(df.get("hotline_tickets"), errors="coerce").fillna(0)
    hotline_sum = float(hotline.sum())
    unmapped_hotline = float(hotline[~mapped].sum()) if hotline_sum else 0.0
    unmapped_pct = round(100.0 * unmapped_hotline / hotline_sum, 1) if hotline_sum else 0.0
    unmapped_df = df[~mapped].copy()
    if not unmapped_df.empty and "hotline_tickets" in unmapped_df.columns:
        top = (
            unmapped_df.sort_values("hotline_tickets", ascending=False)
            .head(5)[["modul", "hotline_tickets"]]
            .values.tolist()
        )
        top_tuples = tuple((str(m), int(h)) for m, h in top if int(h or 0) > 0)
    else:
        top_tuples = ()
    return rows, mapped_n, mapped_pct, unmapped_pct, top_tuples


def build_trust_status(
    df: pd.DataFrame | None = None,
    *,
    snapshot_at: str = "",
    snapshot_source: str = "",
    hotline_sum: int | None = None,
) -> TrustStatus:
    matrix_rows, matrix_mapped, mapped_pct, unmapped_hotline_pct, top_unmapped = _matrix_stats(
        df if df is not None else pd.DataFrame()
    )
    if hotline_sum is None and df is not None and "hotline_tickets" in df.columns:
        hotline_sum = int(pd.to_numeric(df["hotline_tickets"], errors="coerce").fillna(0).sum())

    from core.hotline_inventory import hotline_inventory
    from core.product_mapping import load_mapping_entries
    from core.runtime import rag_freshness
    from core.survey_inventory import survey_inventory

    inv = hotline_inventory(product_signals_sum=hotline_sum)
    survey = survey_inventory()
    survey_match_pct = round(100.0 * survey.matched_rows / survey.raw_rows, 1) if survey.raw_rows else 0.0
    rag_fresh, rag_reason = rag_freshness()
    rag_meta = load_rag_meta()
    rag_docs = int(rag_meta.get("documents") or 0)
    rag_built = (rag_meta.get("built_at") or "")[:16].replace("T", " ")

    warnings: list[str] = []
    actions: list[str] = []

    if unmapped_hotline_pct >= 50:
        warnings.append(f"{unmapped_hotline_pct:.0f}% Hotline-Tickets an unmapped Clustern")
        actions.append("`product_module_mapping.json` erweitern (Top-Cluster im Strip)")
    if not inv.aligned:
        # aligned vergleicht Product Signals nur mit RIWA/OTS (ohne teraWinData) — siehe hotline_inventory.
        warnings.append("Hotline-Zählung nicht überall identisch (RIWA/OTS vs. Scraper/BQ)")
        actions.append("`python scrape_html_tickets.py` + `python extract_product_signals.py`")
    # Umfrage-Match nur für Feel/NPS (Landkreis→ERP→Produkt) — kein Portfolio-Blocker;
    # domain-spezifische Verlässlichkeit: evidence_orchestrator „Feel“-Profil.
    if rag_meta and not rag_fresh:
        warnings.append(f"RAG: {rag_reason}")
        actions.append("Pipeline Schritt 5 (RAG) — Ollama muss laufen")
    elif rag_meta and inv.scraper_scope_count and rag_docs < inv.scraper_scope_count * 0.8:
        warnings.append(f"RAG nur {rag_docs} Docs — Hotline-Stand ~{inv.scraper_scope_count}")
        actions.append("RAG neu bauen für aktuellen BQ-Stand")
    if mapped_pct < 40 and matrix_rows:
        warnings.append(f"Nur {mapped_pct:.0f}% Matrix-Zeilen gemappt")
        actions.append("Mapping priorisieren vor Impact-Entscheidungen")

    if not warnings and inv.aligned and mapped_pct >= 40:
        level = "hoch"
        summary = "Say-Evidenz und Zählungen konsistent — Feel/Pay weiter mapping-abhängig."
    elif unmapped_hotline_pct >= 60 or not inv.aligned:
        level = "niedrig"
        summary = "Portfolio-Zahlen verzerrt — Mapping und Abgleich zuerst."
    else:
        level = "mittel"
        summary = "Exploration ok — produktgenaue Priorisierung mit Vorsicht."

    if DEMO_MODE:
        level = "mittel"
        summary = "Demo-Modus — synthetische Fixtures, keine Produktions-Evidenz."

    snap_label = snapshot_at or _file_mtime_label(SNAPSHOT_PATH)
    ps_label = _file_mtime_label(DEFAULT_OUTPUT)
    rag_label = f"{'aktuell' if rag_fresh else 'veraltet'} · {rag_docs} Docs · {rag_built or '—'}"

    return TrustStatus(
        level=level,
        summary=summary,
        snapshot_at=snap_label,
        snapshot_source=snapshot_source or ("disk" if SNAPSHOT_PATH.exists() else "—"),
        mapping_seed_entries=len(load_mapping_entries()),
        matrix_rows=matrix_rows,
        matrix_mapped=matrix_mapped,
        matrix_mapped_pct=mapped_pct,
        hotline_unmapped_pct=unmapped_hotline_pct,
        hotline_aligned=inv.aligned,
        survey_match_pct=survey_match_pct,
        rag_fresh=rag_fresh,
        rag_label=rag_label,
        rag_documents=rag_docs,
        product_signals_label=ps_label,
        warnings=tuple(warnings),
        actions=tuple(dict.fromkeys(actions)),
        top_unmapped=top_unmapped,
    )


@lru_cache(maxsize=1)
def trust_status_cached(_df_fingerprint: str, snapshot_at: str, snapshot_source: str) -> TrustStatus:
    """Fingerprint bustet Cache bei neuer CSV."""
    return build_trust_status(
        pd.read_csv(DEFAULT_OUTPUT, sep=";", encoding="utf-8-sig") if DEFAULT_OUTPUT.exists() else pd.DataFrame(),
        snapshot_at=snapshot_at,
        snapshot_source=snapshot_source,
    )


def trust_fingerprint() -> str:
    if not DEFAULT_OUTPUT.exists():
        return "missing"
    stat = DEFAULT_OUTPUT.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"
