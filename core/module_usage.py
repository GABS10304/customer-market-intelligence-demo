"""
Usage-Daten pro Modul/App (aktive Nutzer) — Ergänzung zu Modul-Ranking Kunden.

Erwartete Datei: data/module_usage.csv
Spalten: mapping_id ODER modulname, aktive_nutzer, stichtag, quelle (metrik optional)

Wenn die Datei fehlt, bleibt usage leer — kein Fehler.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from config import DATA_DIR, DELIMITER
from core.module_ranking import resolve_ranking_modul

USAGE_CSV = DATA_DIR / "module_usage.csv"
USAGE_TEMPLATE_CSV = DATA_DIR / "module_usage.template.csv"


def ensure_usage_template() -> Path:
    if USAGE_TEMPLATE_CSV.exists():
        return USAGE_TEMPLATE_CSV
    USAGE_TEMPLATE_CSV.write_text(
        "mapping_id;modulname;aktive_nutzer;metrik;stichtag;quelle\n"
        "modul_verkehr;Modul Verkehr;;;aktive_nutzer;2026-01-14;beispiel\n"
        "karten_app;KartenApp;;;aktive_nutzer;2026-01-14;beispiel\n",
        encoding="utf-8-sig",
    )
    return USAGE_TEMPLATE_CSV


@lru_cache(maxsize=1)
def load_usage_by_mapping() -> pd.DataFrame:
    path = USAGE_CSV if USAGE_CSV.exists() else None
    if path is None:
        return pd.DataFrame()

    df = pd.read_csv(path, sep=DELIMITER, encoding="utf-8-sig")
    if df.empty:
        return df

    rows: list[dict[str, object]] = []
    for _, row in df.iterrows():
        mid = str(row.get("mapping_id") or "").strip()
        name = str(row.get("modulname") or "").strip()
        if not mid and name:
            mid = resolve_ranking_modul(name).mapping_id
        if not mid:
            continue
        nutzer = pd.to_numeric(row.get("aktive_nutzer"), errors="coerce")
        if pd.isna(nutzer):
            continue
        rows.append(
            {
                "mapping_id": mid,
                "usage_nutzer": int(nutzer),
                "usage_stichtag": str(row.get("stichtag") or "").strip(),
                "usage_quelle": str(row.get("quelle") or "").strip(),
            }
        )

    if not rows:
        return pd.DataFrame()

    agg = (
        pd.DataFrame(rows)
        .groupby("mapping_id", as_index=False)
        .agg(
            usage_nutzer=("usage_nutzer", "sum"),
            usage_stichtag=("usage_stichtag", "first"),
            usage_quelle=("usage_quelle", "first"),
        )
    )
    return agg
