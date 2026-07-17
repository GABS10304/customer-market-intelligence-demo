#!/usr/bin/env python3
"""CLI: HTML-Tickets scrapen (V1) → data/tickets_backlog.csv → BigQuery."""

from __future__ import annotations

import argparse
import sys

from pipeline.html_ticket_scraper import scrape_html_tickets, _parse_bereiche


def main() -> int:
    parser = argparse.ArgumentParser(description="HTML-Ticket-Scraper V1 (ohne LLM)")
    parser.add_argument(
        "--bereiche",
        default="riwaGisData,teraWinData,otsBauData",
        help="Komma-Liste oder * für alle Bereiche",
    )
    parser.add_argument(
        "--include-allgemein",
        action="store_true",
        help="«Allgemein»-Cluster nicht ausschließen",
    )
    parser.add_argument(
        "--all-bereiche",
        action="store_true",
        help="Alle Bereiche (riwaGis, teraWin, otsBau, …)",
    )
    args = parser.parse_args()

    if args.all_bereiche:
        bereiche = None
    else:
        bereiche = _parse_bereiche("*" if args.bereiche.strip() == "*" else args.bereiche)

    result = scrape_html_tickets(
        bereiche=bereiche,
        exclude_genereller_bereich=not args.include_allgemein,
    )
    if result.get("error"):
        return 1
    if result.get("rows", 0) == 0:
        return 1
    print(f"Fertig: {result['rows']} Zeilen (gescannt {result.get('files_seen', 0)})")
    print("Nächster Schritt: Pipeline Schritt bq oder Sidebar «Pipeline starten» (Schritt bq).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
