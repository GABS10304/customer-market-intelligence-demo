#!/usr/bin/env python3
"""Modul-Ranking anreichern (mapping_id) und aggregieren."""

from __future__ import annotations

import argparse
import sys

from core.module_ranking import (
    RANKING_ENRICHED_CSV,
    aggregate_ranking_by_mapping,
    mapping_coverage_report,
    write_enriched_ranking,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Modul-Ranking → mapping_id")
    parser.add_argument(
        "--aggregate",
        action="store_true",
        help="Aggregierte Tabelle pro mapping_id auf stdout",
    )
    args = parser.parse_args()

    path = write_enriched_ranking()
    report = mapping_coverage_report()
    print(f"Enriched: {path} ({report['rows']} Zeilen)")
    print(f"Match-Arten: {report.get('kinds', {})}")
    print(f"Kunden mit Mapping (nicht fallback): {report.get('mapped_kunden_pct', 0)}%")
    if report.get("fallback_count"):
        print(f"Fallback (noch prüfen): {report['fallback_count']} Zeilen")
        for name in report.get("fallback_modules", [])[:15]:
            print(f"  - {name}")
        if len(report.get("fallback_modules", [])) > 15:
            print(f"  ... +{len(report['fallback_modules']) - 15} weitere")

    if args.aggregate:
        agg = aggregate_ranking_by_mapping()
        cols = ["mapping_id", "mapping_label", "kunden", "umsatz_eur", "match_kinds"]
        print("\nAggregiert pro mapping_id:")
        print(agg[cols].head(20).to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
