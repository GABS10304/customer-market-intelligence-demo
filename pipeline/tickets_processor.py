"""
Hotline-Tickets aus data/Tickets_neu — Original-Text (.txt), ohne LLM.
"""

from __future__ import annotations

import csv
import html
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from config import TICKETS_BACKLOG_CSV, TICKETS_TEXT_DIR, ensure_data_dirs
from core.governance import scrub_pii

LogFn = Callable[[str], None]

MIN_TEXT_LEN = 20


def _default_log(message: str) -> None:
    print(message)


def _clean_ticket_text(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return scrub_pii(text)


def _module_label(filepath: Path) -> str:
    try:
        rel = filepath.relative_to(TICKETS_TEXT_DIR)
    except ValueError:
        return filepath.parent.name
    parts = rel.parts[:-1]
    if not parts:
        return "Hotline"
    return "\\".join(parts)


def build_tickets_from_source(log: LogFn = _default_log) -> dict[str, Any]:
    """Liest alle .txt unter Tickets_neu/Text → tickets_backlog.csv."""
    ensure_data_dirs()

    if not TICKETS_TEXT_DIR.exists():
        log(f"⚠️ Ticket-Ordner fehlt: {TICKETS_TEXT_DIR}")
        return {"rows": 0, "files_scanned": 0, "error": "missing_dir"}

    results: list[dict[str, str]] = []
    files_scanned = 0
    processed_at = datetime.now(timezone.utc).isoformat()

    log(f"\n🎫 Hotline-Tickets aus {TICKETS_TEXT_DIR} (Original-Text)…")

    for root, _, files in os.walk(TICKETS_TEXT_DIR):
        for filename in files:
            if not filename.lower().endswith(".txt"):
                continue

            filepath = Path(root) / filename
            files_scanned += 1

            try:
                raw = filepath.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                log(f"   ⚠️ {filename}: {exc}")
                continue

            text = _clean_ticket_text(raw)
            if len(text) < MIN_TEXT_LEN:
                continue

            ticket_id = filepath.stem
            module = _module_label(filepath)

            results.append(
                {
                    "Ordner / Modul": module,
                    "Quelle (Dateiname)": filename,
                    "ticket_id": ticket_id,
                    "Kategorie": "Hotline-Ticket",
                    "Original-Wortlaut (Freitext)": text,
                    "Quelle": "Hotline Tickets_neu",
                    "source_file": str(filepath.relative_to(TICKETS_TEXT_DIR.parent.parent)),
                    "processed_at": processed_at,
                }
            )

    if not results:
        log("⚠️ Keine Ticket-Texte gefunden.")
        return {"rows": 0, "files_scanned": files_scanned}

    fieldnames = list(results[0].keys())
    with open(TICKETS_BACKLOG_CSV, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(results)

    log(f"✅ {len(results)} Tickets → {TICKETS_BACKLOG_CSV.name} ({files_scanned} Dateien gescannt)")
    return {"rows": len(results), "files_scanned": files_scanned}


def run_html_shredder(log: LogFn = _default_log) -> dict[str, Any]:
    """Kompatibilitäts-Entry — delegiert an Original-Text-Pipeline."""
    return build_tickets_from_source(log=log)
