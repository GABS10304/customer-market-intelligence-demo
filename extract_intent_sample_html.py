#!/usr/bin/env python3
"""
Intent-Stichprobe aus rohen HTML-Hotline-Tickets — für manuelle Challenge.

Liest data/Tickets_neu/html (Original-HTML, kein LLM-Schredder),
klassifiziert Intent regelbasiert, zieht stratifiziert N Zeilen über Bereiche.

Usage:
    python extract_intent_sample_html.py
    python extract_intent_sample_html.py --limit 50 --seed 42
    python extract_intent_sample_html.py --generell
    python extract_intent_sample_html.py --output data/intent_review_sample_html.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from config import DATA_DIR, DELIMITER, TICKETS_HTML_DIR
from core.html_ticket_reader import iter_html_tickets
from core.intent_patterns import classify_intent
from core.intent_sample import finalize_sample
from workspace.sources.profiles import get_profile

DEFAULT_OUTPUT = DATA_DIR / "intent_review_sample_html.csv"
SOURCE_TECH = "support_tickets_html_roh"


def _load_html_pool(*, only_genereller_bereich: bool, html_root: Path) -> pd.DataFrame:
    profile = get_profile("support_tickets_html")
    display_name = profile.display_name if profile else "Hotline Tickets RIWA"

    rows: list[dict[str, str]] = []
    for ticket in iter_html_tickets(html_root, only_genereller_bereich=only_genereller_bereich):
        intent = classify_intent(ticket["freitext"], modul=ticket["cluster"])
        rows.append(
            {
                "quelle": display_name,
                "quelle_technisch": SOURCE_TECH,
                "bereich": ticket["bereich"],
                "cluster": ticket["cluster"],
                "freitext": ticket["freitext"],
                "intent_auto": intent.intent,
                "bedarf_auto": intent.bedarf,
                "geltung_auto": intent.geltung,
                "themen_auto": "|".join(intent.themen),
                "request_thema_auto": intent.request_thema,
                "request_detail_auto": intent.request_detail,
                "kontakt_angebot_auto": intent.kontakt_angebot,
                "ansprechpartner_auto": intent.ansprechpartner,
                "kontakt_zeitraum_auto": intent.kontakt_zeitraum,
                "aktion_todo_auto": intent.aktion_todo,
                "intent_confidence": intent.confidence,
                "matched_keywords": "|".join(intent.matched_keywords),
                "intent_manual": "",
                "challenge_ok": "",
                "challenge_notiz": "",
                "input_typ": "html_roh",
                "ticket_id": ticket["ticket_id"],
                "ticket_datei": ticket["ticket_datei"],
                "csv_datei": "",
                "csv_pfad": "",
                "html_pfad": ticket["html_pfad"],
                "zeilen_index": "",
            }
        )

    return pd.DataFrame(rows)


def run(
    limit: int,
    seed: int,
    output: Path,
    html_root: Path,
    only_genereller_bereich: bool,
    group_by: str,
) -> int:
    if not html_root.exists():
        print(f"HTML-Ordner nicht gefunden: {html_root}", file=sys.stderr)
        return 1

    pool = _load_html_pool(only_genereller_bereich=only_genereller_bereich, html_root=html_root)
    if pool.empty:
        scope = "Allgemein-Cluster" if only_genereller_bereich else "alle HTML-Tickets"
        print(f"Keine HTML-Tickets mit Freitext gefunden ({scope}).", file=sys.stderr)
        return 1

    group_col = "bereich" if group_by == "bereich" else "quelle_technisch"
    if group_by == "cluster":
        group_col = "cluster"

    sample = finalize_sample(pool, limit=limit, seed=seed, group_col=group_col)

    output.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(output, sep=DELIMITER, index=False, encoding="utf-8-sig")

    scope = "genereller Bereich (Allgemein-Cluster)" if only_genereller_bereich else "alle HTML-Roh-Tickets"
    print(f"Intent-Stichprobe HTML ({scope}): {len(sample)} Zeilen -> {output}")
    print(f"Gesamt-Pool: {len(pool)} Tickets aus {html_root}")
    print("Verteilung (auto):")
    for intent, count in sample["intent_auto"].value_counts().items():
        print(f"  {intent}: {count}")
    print("Bereiche in Stichprobe:")
    for bereich, count in sample["bereich"].value_counts().items():
        print(f"  {bereich}: {count}")
    print("\nManuelle Challenge: intent_manual, challenge_ok (ja/nein), challenge_notiz ausfuellen.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Intent-Stichprobe aus rohen HTML-Hotline-Tickets.")
    parser.add_argument("--limit", type=int, default=50, help="Anzahl Zufallszeilen (default: 50)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Ausgabe-CSV")
    parser.add_argument(
        "--html-root",
        type=Path,
        default=TICKETS_HTML_DIR,
        help=f"HTML-Wurzel (default: {TICKETS_HTML_DIR})",
    )
    parser.add_argument(
        "--generell",
        action="store_true",
        help="Nur «genereller Bereich»: Cluster mit Allgemein/Allg (RGZ Allgemein, gisAllgemein, …)",
    )
    parser.add_argument(
        "--group-by",
        choices=("bereich", "cluster", "quelle"),
        default="bereich",
        help="Stratifizierung der Stichprobe (default: bereich = riwaGisData, teraWinData, …)",
    )
    args = parser.parse_args()
    raise SystemExit(
        run(
            args.limit,
            args.seed,
            args.output,
            args.html_root,
            args.generell,
            args.group_by,
        )
    )


if __name__ == "__main__":
    main()
