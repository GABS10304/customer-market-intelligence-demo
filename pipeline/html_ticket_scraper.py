"""
HTML-Ticket-Scraper V1 — data/Tickets_neu/html → tickets_backlog.csv (ohne LLM).

Ersetzt pipeline/html_processor.py (V0: Ollama-Schredder, IRRELEVANT-Filter → ~378 Zeilen BQ).

V1: Original-Freitext + Cluster aus Ordnerstruktur, PII-Scrub, optional Scope-Filter.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from typing import Any, Callable

from config import DELIMITER, TICKETS_BACKLOG_CSV, TICKETS_HTML_DIR, ensure_data_dirs
from core.hotline_scope import DEFAULT_BEREICHE, parse_bereiche, ticket_in_hotline_scope
from core.html_ticket_reader import iter_html_tickets

LogFn = Callable[[str], None]


def _default_log(message: str) -> None:
    print(message)


def _parse_bereiche(raw: str | None) -> tuple[str, ...] | None:
    return parse_bereiche(raw)


def scrape_html_tickets(
    *,
    html_root=None,
    output_csv=None,
    bereiche: tuple[str, ...] | None = DEFAULT_BEREICHE,
    exclude_genereller_bereich: bool = True,
    log: LogFn = _default_log,
) -> dict[str, Any]:
    """
    Liest HTML-Tickets und schreibt BQ-kompatibles CSV.

    Standard-Scope: riwaGisData + teraWinData + otsBauData, ohne «Allgemein»-Cluster.
    """
    ensure_data_dirs()
    root = html_root or TICKETS_HTML_DIR
    out_path = output_csv or TICKETS_BACKLOG_CSV

    if not root.exists():
        log(f"WARN HTML-Ordner fehlt: {root}")
        return {"rows": 0, "files_scanned": 0, "error": "missing_dir"}

    processed_at = datetime.now(timezone.utc).isoformat()
    results: list[dict[str, str]] = []
    stats: dict[str, int] = {
        "files_seen": 0,
        "skipped_bereich": 0,
        "skipped_generell": 0,
    }

    scope = f"bereiche={bereiche or 'alle'}"
    if exclude_genereller_bereich:
        scope += ", ohne Allgemein-Cluster"
    log(f"\nHTML-Scraper V1 ({scope})")
    log(f"   Quelle: {root}")

    for ticket in iter_html_tickets(root, only_genereller_bereich=False):
        stats["files_seen"] += 1
        bereich = ticket.get("bereich") or ""
        if not ticket_in_hotline_scope(
            ticket,
            bereiche=bereiche,
            exclude_genereller_bereich=exclude_genereller_bereich,
        ):
            if bereiche is not None and bereich not in bereiche:
                stats["skipped_bereich"] += 1
            else:
                stats["skipped_generell"] += 1
            continue

        results.append(
            {
                "Ordner / Modul": ticket.get("cluster") or "",
                "Quelle (Dateiname)": ticket.get("ticket_datei") or "",
                "ticket_id": ticket.get("ticket_id") or "",
                "Kategorie": "Hotline-Ticket",
                "Original-Wortlaut (Freitext)": ticket.get("freitext") or "",
                "Quelle": "Hotline HTML V1",
                "source_file": ticket.get("html_pfad") or "",
                "bereich": bereich,
                "processed_at": processed_at,
            }
        )

    if not results:
        log("WARN Keine Tickets nach Filter — CSV nicht überschrieben.")
        return {"rows": 0, **stats}

    fieldnames = list(results[0].keys())
    with open(out_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(results)

    log(f"OK {len(results)} Tickets -> {out_path.name}")
    log(
        f"   Gescannt: {stats['files_seen']}, "
        f"übersprungen Bereich: {stats['skipped_bereich']}, "
        f"übersprungen Allgemein: {stats['skipped_generell']}"
    )
    return {"rows": len(results), **stats}


def run_html_shredder(log: LogFn = _default_log) -> dict[str, Any]:
    """Pipeline-Entry — V1-Scraper (Name aus Kompatibilität zu runner.py)."""
    import os

    bereiche = parse_bereiche(os.getenv("HOTLINE_HTML_BEREICHE", "riwaGisData,teraWinData,otsBauData"))
    exclude_gen = os.getenv("HOTLINE_EXCLUDE_ALLGEMEIN", "true").lower() not in ("0", "false", "no")
    if bereiche is None and os.getenv("HOTLINE_HTML_BEREICHE", "").strip() == "*":
        bereiche = None
    return scrape_html_tickets(
        bereiche=bereiche,
        exclude_genereller_bereich=exclude_gen,
        log=log,
    )
