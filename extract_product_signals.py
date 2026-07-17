#!/usr/bin/env python3
"""Hotline + Feldbesuche → product_signals_unified.csv (mit Reach/Kunden)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import DATA_DIR, DELIMITER
from core.product_signals import DEFAULT_OUTPUT, aggregate_product_signals, write_product_signals
from core.survey_signals import survey_inventory


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Product Signals: Hotline (Cluster+intent) + Feldbesuche (bedarf) + Ranking-Kunden."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=20, help="Top-Zeilen auf stdout")
    args = parser.parse_args()

    df = write_product_signals(args.output)
    if df.empty:
        print("Keine Signale (Hotline/Feldbesuche).", file=sys.stderr)
        return 1

    print(f"Product Signals: {len(df)} mapping-Zeilen -> {args.output}")
    cols = [
        "modul",
        "hotline_tickets",
        "feldbesuche",
        "reach_nutzer",
        "ranking_kunden",
        "usage_nutzer",
        "umfrage_antworten",
        "umfrage_avg_nps",
        "dominant_intent",
        "top_bedarf",
        "impact_proxy",
    ]
    show = [c for c in cols if c in df.columns]
    print(df[show].head(args.limit).to_string(index=False))
    mapped = df[df["reach_nutzer"] > 0]
    survey_rows = df[df["umfrage_antworten"].fillna(0) > 0] if "umfrage_antworten" in df.columns else df.iloc[0:0]
    inv = survey_inventory()
    print(
        f"\nMit Reach (Nutzer/Kunden>0): {len(mapped)}/{len(df)} Zeilen, "
        f"Hotline gesamt {int(df['hotline_tickets'].sum())}, "
        f"Feldbesuche {int(df['feldbesuche'].sum())}, "
        f"Kundenumfrage {inv.raw_rows} Zeilen ({inv.matched_rows} ERP-gematcht, "
        f"{inv.product_attributions} Produkt-Zuordnungen auf {len(survey_rows)} Module)"
    )
    if not Path('data/module_usage.csv').exists():
        print("Usage: data/module_usage.csv noch nicht — Template: data/module_usage.template.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
