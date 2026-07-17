"""
Umfrage-Signale (NPS + Skalen) → mapping_id über Landkreis → ERP-Kunde → Produkte.

Daten: data/inbox/umfragen/tickets_b.csv (Kundenumfrage, Skalen + Freitext).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from core.survey_data import (
    SURVEY_SOURCE_FILE,
    SURVEY_SOURCE_LABEL,
    discover_survey_csv,
    load_survey_frame,
    match_landkreis_to_kunde,
    survey_column_map,
)
from core.survey_inventory import SurveyInventory, build_survey_buckets, clear_survey_inventory_cache, survey_inventory

SURVEY_CATEGORY_TO_BEDARF = {
    "bug/performance": "Bugmeldung",
    "usability": "UX-Kritik",
    "feature-wunsch": "Feature Request",
    "feature request": "Feature Request",
    "service/schulung": "Service-Kritik",
}


def _survey_column_map(df: pd.DataFrame) -> dict[str, str]:
    """Alias für Abwärtskompatibilität."""
    return survey_column_map(df)


def aggregate_survey_by_mapping() -> pd.DataFrame:
    buckets, _ = build_survey_buckets()
    if not buckets:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for mid, b in buckets.items():
        rows.append(
            {
                "mapping_id": mid,
                "umfrage_antworten": b["umfrage_antworten"],
                "umfrage_avg_nps": round(b["nps_sum"] / b["nps_n"], 2) if b["nps_n"] else None,
                "umfrage_detractors": b["detractors"],
                "umfrage_avg_ux": round(b["ux_sum"] / b["ux_n"], 2) if b["ux_n"] else None,
                "umfrage_avg_support": round(b["support_sum"] / b["support_n"], 2) if b["support_n"] else None,
            }
        )

    return pd.DataFrame(rows).sort_values("umfrage_antworten", ascending=False).reset_index(drop=True)


__all__ = [
    "SURVEY_SOURCE_LABEL",
    "SURVEY_SOURCE_FILE",
    "SurveyInventory",
    "aggregate_survey_by_mapping",
    "clear_survey_inventory_cache",
    "discover_survey_csv",
    "load_survey_frame",
    "match_landkreis_to_kunde",
    "survey_inventory",
]
