#!/usr/bin/env python3
"""Intent pro Modul (alle Quellen) — CSV-Export."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import DATA_DIR, DELIMITER
from core.intent_by_module import aggregate_intent_by_module

DEFAULT_OUTPUT = DATA_DIR / "intent_by_module.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Intent-Auswertung pro Modul (HTML + CSV).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    df = aggregate_intent_by_module()
    if df.empty:
        print("Keine modul-gemappten Eintraege.", file=sys.stderr)
        raise SystemExit(1)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, sep=DELIMITER, index=False, encoding="utf-8-sig")
    print(f"Intent pro Modul: {len(df)} Module -> {args.output}")

    cols = ["modul", "eintraege", "summe_umsatz", "dominant_intent", "top_bedarf", "Defekt", "quellen"]
    show = [c for c in cols if c in df.columns]
    print(df[show].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
