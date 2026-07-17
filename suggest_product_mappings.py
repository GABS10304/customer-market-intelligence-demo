#!/usr/bin/env python3
"""Top-unmapped Hotline-Cluster → Mapping-Vorschläge generieren und optional anwenden."""

from __future__ import annotations

import argparse
import sys

from core.mapping_suggestions import apply_suggestions, suggest_all_unmapped, suggest_mappings, write_suggestions_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Mapping-Vorschläge für product_module_mapping.json")
    parser.add_argument("--limit", type=int, default=5, help="Anzahl Top-Cluster")
    parser.add_argument("--min-tickets", type=int, default=10, help="Min. Hotline-Tickets pro Cluster")
    parser.add_argument("--all", action="store_true", help="Alle unmapped Cluster mappen (nicht nur Top-N)")
    parser.add_argument("--apply", action="store_true", help="Vorschläge in product_module_mapping.json schreiben")
    args = parser.parse_args()

    if args.all:
        suggestions = suggest_all_unmapped(min_tickets=args.min_tickets)
    else:
        suggestions = suggest_mappings(limit=args.limit, min_tickets=args.min_tickets)
    if not suggestions:
        print("Keine unmapped Cluster über Schwelle.", file=sys.stderr)
        return 1

    write_suggestions_file(suggestions)
    print(f"Mapping-Vorschläge ({len(suggestions)}) → data/mapping_suggestions.json\n")
    for s in suggestions:
        print(f"  [{s.action}] {s.target_id} — {s.label} ({s.tickets_covered} Tickets)")
        print(f"       cluster: {s.ticket_clusters[0]}")

    if args.apply:
        result = apply_suggestions(suggestions)
        print(f"\nAngewendet: {', '.join(result['applied'])}")
        print("Bitte: python extract_product_signals.py")
    else:
        print("\nAnwenden: python suggest_product_mappings.py --apply")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
