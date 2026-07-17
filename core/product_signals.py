"""
Product Signals — Hotline + Feldbesuche + Umfrage + Reach (+ Usage wenn geliefert).

Hotline: riwaGis + otsBau (ohne teraWin — TERA = eigener Tab / Produktlinie).
Feldbesuche: Cluster + bedarf.
Reach: max(ranking_kunden, usage_nutzer) — Ranking als Lizenz-Reach, Graylog oft unvollständig.
Umfrage: NPS/Skalen via Landkreis → ERP → mapping_id.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from config import DELIMITER, PRODUCT_SIGNALS_CSV
from core.intent_patterns import INTENT_LABELS, classify_intent, ticket_routing_intent
from core.intent_sources import iter_freetext_rows
from core.module_ranking import aggregate_ranking_by_mapping
from core.module_usage import ensure_usage_template, load_usage_by_mapping
from core.product_mapping import (
    mapping_entry_by_id,
    module_display_name,
    resolve_cluster_mapping,
    revenue_by_mapping_group,
)
from core.tera_scope import is_tera_hotline_cluster
from core.survey_signals import aggregate_survey_by_mapping

HOTLINE_TECH = "support_tickets_html_roh"
FIELD_VISITS_TECH = "field_visits_weihnachtsbesuche"

DEFAULT_OUTPUT = PRODUCT_SIGNALS_CSV


def resolve_signal_mapping_id(cluster: str) -> tuple[str, str]:
    mapping = resolve_cluster_mapping(cluster)
    if mapping:
        return mapping.id, mapping.label
    label = module_display_name(cluster)
    return "", label


def _bucket_key(mapping_id: str, label: str) -> str:
    return mapping_id if mapping_id else f"unmapped:{label}"


def _collect_voice_signals() -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}

    for row in iter_freetext_rows(include_html=True, include_csv=True):
        if row.quelle_technisch not in (HOTLINE_TECH, FIELD_VISITS_TECH):
            continue
        cluster = (row.cluster or "").strip()
        if not cluster:
            continue
        if row.quelle_technisch == HOTLINE_TECH and is_tera_hotline_cluster(cluster):
            continue

        mapping_id, label = resolve_signal_mapping_id(cluster)
        key = _bucket_key(mapping_id, label)
        intent = classify_intent(row.freitext, modul=cluster)

        bucket = stats.setdefault(
            key,
            {
                "mapping_id": mapping_id,
                "modul": label,
                "intent_counts": Counter(),
                "bedarf_counts": Counter(),
                "routing_counts": Counter(),
                "hotline": 0,
                "feldbesuche": 0,
                "beispiele_hotline": [],
                "beispiele_feld": [],
            },
        )

        if row.quelle_technisch == HOTLINE_TECH:
            bucket["hotline"] += 1
            bucket["intent_counts"][intent.intent] += 1
            routing = ticket_routing_intent(intent.intent)
            if routing:
                bucket["routing_counts"][routing] += 1
            if len(bucket["beispiele_hotline"]) < 2:
                bucket["beispiele_hotline"].append(row.freitext[:160])
        else:
            bucket["feldbesuche"] += 1
            if intent.bedarf:
                bucket["bedarf_counts"][intent.bedarf] += 1
            if len(bucket["beispiele_feld"]) < 2:
                bucket["beispiele_feld"].append(row.freitext[:160])

    return stats


def _reach_nutzer(row: pd.Series) -> int:
    """Reach-Proxy: Maximum aus Graylog-Usage und Modul-Ranking (partielle Telemetrie)."""
    usage = pd.to_numeric(row.get("usage_nutzer"), errors="coerce")
    ranking = pd.to_numeric(row.get("ranking_kunden"), errors="coerce")
    u = int(usage) if pd.notna(usage) and int(usage) > 0 else 0
    r = int(ranking) if pd.notna(ranking) and int(ranking) > 0 else 0
    return max(u, r)


def aggregate_product_signals(*, min_count: int = 1) -> pd.DataFrame:
    stats = _collect_voice_signals()
    ranking = aggregate_ranking_by_mapping()
    ranking_idx = (
        ranking.set_index("mapping_id").to_dict(orient="index") if not ranking.empty else {}
    )
    revenue = revenue_by_mapping_group()

    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for key, data in stats.items():
        total = data["hotline"] + data["feldbesuche"]
        if total < min_count:
            continue

        mid = data["mapping_id"] or key
        seen_ids.add(mid if data["mapping_id"] else key)
        rank = ranking_idx.get(data["mapping_id"], {}) if data["mapping_id"] else {}
        kunden = int(rank.get("kunden", 0) or 0)
        ranking_umsatz = float(rank.get("umsatz_eur", 0) or 0)
        erp_umsatz = float(revenue.get(data["mapping_id"], 0) or 0) if data["mapping_id"] else 0.0

        intents: Counter = data["intent_counts"]
        bedarf: Counter = data["bedarf_counts"]
        routing: Counter = data["routing_counts"]

        rec: dict[str, Any] = {
            "mapping_id": mid,
            "modul": data["modul"],
            "hotline_tickets": int(data["hotline"]),
            "feldbesuche": int(data["feldbesuche"]),
            "signale_gesamt": int(total),
            "ranking_kunden": kunden,
            "ranking_umsatz_eur": round(ranking_umsatz, 2),
            "erp_umsatz_eur": round(erp_umsatz, 2),
            "dominant_intent": intents.most_common(1)[0][0] if intents else "",
            "top_ticket_routing": routing.most_common(1)[0][0] if routing else "",
            "top_bedarf": bedarf.most_common(1)[0][0] if bedarf else "",
            "beispiel_hotline": " | ".join(data["beispiele_hotline"]),
            "beispiel_feldbesuch": " | ".join(data["beispiele_feld"]),
        }

        for label in INTENT_LABELS:
            rec[f"intent_{label}"] = int(intents.get(label, 0))

        for tag, count in bedarf.items():
            safe = tag.replace(" ", "_").replace("/", "_")
            rec[f"bedarf_{safe}"] = int(count)

        rows.append(rec)

    df = pd.DataFrame(rows) if rows else pd.DataFrame()

    survey = aggregate_survey_by_mapping()
    usage = load_usage_by_mapping()
    ensure_usage_template()

    if not survey.empty:
        if df.empty:
            df = survey.rename(columns={"mapping_id": "mapping_id"}).copy()
            df["modul"] = df["mapping_id"].map(
                lambda mid: (mapping_entry_by_id(str(mid)).label if mapping_entry_by_id(str(mid)) else str(mid))
            )
            df["hotline_tickets"] = 0
            df["feldbesuche"] = 0
            df["signale_gesamt"] = 0
        else:
            df = df.merge(survey, on="mapping_id", how="outer")
            missing_modul = df["modul"].isna()
            if missing_modul.any():
                df.loc[missing_modul, "modul"] = df.loc[missing_modul, "mapping_id"].map(
                    lambda mid: (mapping_entry_by_id(str(mid)).label if mapping_entry_by_id(str(mid)) else str(mid))
                )
            for col, default in (
                ("hotline_tickets", 0),
                ("feldbesuche", 0),
                ("signale_gesamt", 0),
                ("ranking_kunden", 0),
                ("ranking_umsatz_eur", 0.0),
                ("erp_umsatz_eur", 0.0),
            ):
                if col in df.columns:
                    df[col] = df[col].fillna(default)
                else:
                    df[col] = default
    elif not df.empty:
        for col in (
            "umfrage_antworten",
            "umfrage_avg_nps",
            "umfrage_detractors",
            "umfrage_avg_ux",
            "umfrage_avg_support",
        ):
            df[col] = None

    if not usage.empty:
        df = df.merge(usage, on="mapping_id", how="left") if not df.empty else usage
    elif not df.empty:
        df["usage_nutzer"] = pd.NA
        df["usage_stichtag"] = ""
        df["usage_quelle"] = ""

    if df.empty:
        return df

    df["reach_nutzer"] = df.apply(_reach_nutzer, axis=1)
    df["impact_proxy"] = df.apply(
        lambda r: round(
            max(int(r.get("signale_gesamt") or 0), 1)
            * max(int(r.get("reach_nutzer") or 0), 1)
            * (
                1.0
                + float(r.get("erp_umsatz_eur") or 0) / 500_000.0
                + float(r.get("ranking_umsatz_eur") or 0) / 500_000.0
                + (2.0 if pd.notna(r.get("umfrage_avg_nps")) and float(r["umfrage_avg_nps"]) <= 2.5 else 0.0)
            ),
            1,
        ),
        axis=1,
    )

    return df.sort_values(
        ["impact_proxy", "signale_gesamt", "reach_nutzer"],
        ascending=False,
    ).reset_index(drop=True)


def write_product_signals(path: Path | None = None) -> pd.DataFrame:
    out_path = path or DEFAULT_OUTPUT
    df = aggregate_product_signals()
    if not df.empty:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, sep=DELIMITER, index=False, encoding="utf-8-sig")
    return df
