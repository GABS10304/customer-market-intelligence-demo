#!/usr/bin/env python3
"""
Intent pro Business-Gruppe (ERP-Mapping) — CSV für Review und Priorität.

Usage:
    python extract_intent_by_business_group.py
    python extract_intent_by_business_group.py --output data/intent_by_business_group.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import DATA_DIR, DELIMITER
from core.intent_by_group import aggregate_intent_by_business_group

DEFAULT_OUTPUT = DATA_DIR / "intent_by_business_group.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Intent-Häufigkeiten pro ERP-Business-Gruppe.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    df = aggregate_intent_by_business_group()
    if df.empty:
        print("Keine gemappten Tickets gefunden.", file=sys.stderr)
        print("Prüfe data/Tickets_neu/html und data/product_module_mapping.json", file=sys.stderr)
        raise SystemExit(1)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, sep=DELIMITER, index=False, encoding="utf-8-sig")

    print(f"Intent pro Business-Gruppe: {len(df)} Gruppen -> {args.output}")
    show = df[
        ["business_gruppe", "summe_umsatz", "ticket_anzahl", "dominant_intent", "How-To", "Discovery", "Defekt"]
    ].head(12)
    print(show.to_string(index=False))


if __name__ == "__main__":
    main()
