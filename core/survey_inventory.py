"""
Umfrage-Bestand — Zählung und Buckets ohne Abhängigkeit zu product_signals.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import pandas as pd

from core.survey_data import (
    SURVEY_SOURCE_FILE,
    customer_product_mapping_ids,
    discover_survey_csv,
    load_survey_frame,
    match_landkreis_to_kunde,
    survey_column_map,
)


@dataclass(frozen=True)
class SurveyInventory:
    source_file: str
    raw_rows: int
    matched_rows: int
    product_attributions: int
    products_with_survey: int


@lru_cache(maxsize=1)
def build_survey_buckets() -> tuple[dict[str, dict[str, Any]], SurveyInventory]:
    df = load_survey_frame()
    empty_inv = SurveyInventory("", 0, 0, 0, 0)
    if df.empty:
        return {}, empty_inv

    src = discover_survey_csv()
    cmap = survey_column_map(df)
    cust_products = customer_product_mapping_ids()
    buckets: dict[str, dict[str, Any]] = {}
    matched_rows = 0
    product_attributions = 0

    for _, row in df.iterrows():
        lk = str(row.get(cmap["landkreis"]) or "").strip()
        kunde = match_landkreis_to_kunde(lk)
        product_ids = cust_products.get(kunde, []) if kunde else []
        if not product_ids:
            continue

        matched_rows += 1
        nps = pd.to_numeric(row.get(cmap["nps"]), errors="coerce")
        scores = {
            "ux": pd.to_numeric(row.get(cmap["ux"]), errors="coerce"),
            "stabilitaet": pd.to_numeric(row.get(cmap["stabilitaet"]), errors="coerce"),
            "support": pd.to_numeric(row.get(cmap["support"]), errors="coerce"),
            "fachmodule": pd.to_numeric(row.get(cmap["fachmodule"]), errors="coerce"),
        }

        for mid in product_ids:
            product_attributions += 1
            b = buckets.setdefault(
                mid,
                {
                    "umfrage_antworten": 0,
                    "nps_sum": 0.0,
                    "nps_n": 0,
                    "detractors": 0,
                    "ux_sum": 0.0,
                    "ux_n": 0,
                    "support_sum": 0.0,
                    "support_n": 0,
                },
            )
            b["umfrage_antworten"] += 1
            if pd.notna(nps):
                b["nps_sum"] += float(nps)
                b["nps_n"] += 1
                if float(nps) <= 2:
                    b["detractors"] += 1
            if pd.notna(scores["ux"]):
                b["ux_sum"] += float(scores["ux"])
                b["ux_n"] += 1
            if pd.notna(scores["support"]):
                b["support_sum"] += float(scores["support"])
                b["support_n"] += 1

    inv = SurveyInventory(
        source_file=src.name if src else SURVEY_SOURCE_FILE,
        raw_rows=len(df),
        matched_rows=matched_rows,
        product_attributions=product_attributions,
        products_with_survey=len(buckets),
    )
    return buckets, inv


@lru_cache(maxsize=1)
def survey_inventory() -> SurveyInventory:
    _, inv = build_survey_buckets()
    return inv


def clear_survey_inventory_cache() -> None:
    survey_inventory.cache_clear()
    build_survey_buckets.cache_clear()
