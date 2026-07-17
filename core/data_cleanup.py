"""
Datenbereinigung vor Pipeline-Lauf — Artefakte, Leerzeilen, Inbox-Sortierung.
"""

from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path
from typing import Callable

from config import (
    BACKLOG_CSV,
    DELIMITER,
    FIELD_VISITS_CSV,
    FIELD_VISITS_FIELDNAMES,
    INBOX_DIR,
    INBOX_FIELD_VISITS_DIR,
    INBOX_SURVEYS_DIR,
    OUTPUT_FIELDNAMES,
    PROCESSED_DIR,
    ensure_data_dirs,
)
from core.source_dedup import is_field_visits_csv, purge_survey_field_visit_duplicates
from pipeline.inbox import file_hash, mark_processed

LogFn = Callable[[str], None]

_KATEGORIE_LINE = re.compile(r"^\s*KATEGORIE:\s*.+$", re.IGNORECASE | re.MULTILINE)
_MOJIBAKE_FIXES = (
    ("Ã¼", "ü"),
    ("Ã¤", "ä"),
    ("Ã¶", "ö"),
    ("ÃŸ", "ß"),
    ("Ã„", "Ä"),
    ("Ã–", "Ö"),
    ("Ãœ", "Ü"),
    ("â€", "–"),
    ("ï¿½", ""),
)


def _default_log(message: str) -> None:
    print(message)


def fix_encoding(text: str) -> str:
    if not text:
        return text
    out = text
    for bad, good in _MOJIBAKE_FIXES:
        out = out.replace(bad, good)
    return out


def clean_llm_artifact_text(text: str) -> str:
    """Entfernt eingeschleuste Pipeline-Zeilen wie 'KATEGORIE: Feature-Wunsch'."""
    if not text:
        return text
    cleaned = _KATEGORIE_LINE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return fix_encoding(cleaned.strip())


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)


def clean_survey_backlog(log: LogFn = _default_log) -> dict[str, int]:
    """Bereinigt Umfragen-Backlog: LLM-Artefakte + Encoding."""
    if not BACKLOG_CSV.exists():
        return {"artifacts_fixed": 0, "rows": 0}

    with open(BACKLOG_CSV, encoding="utf-8-sig", errors="replace") as handle:
        rows = list(csv.DictReader(handle, delimiter=DELIMITER))

    if not rows:
        return {"artifacts_fixed": 0, "rows": 0}

    text_col = "Original-Wortlaut (Freitext)"
    fixed = 0
    for row in rows:
        raw = row.get(text_col, "") or ""
        cleaned = clean_llm_artifact_text(raw)
        if cleaned != raw:
            row[text_col] = cleaned
            fixed += 1
        else:
            row[text_col] = fix_encoding(raw)

    fieldnames = list(OUTPUT_FIELDNAMES)
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    _write_csv(BACKLOG_CSV, fieldnames, rows)
    if fixed:
        log(f"🧹 Umfragen: {fixed} Freitexte bereinigt (KATEGORIE-Artefakte / Encoding).")
    return {"artifacts_fixed": fixed, "rows": len(rows)}


def clean_field_visits_backlog(log: LogFn = _default_log) -> dict[str, int]:
    """Entfernt leere Feldfeedback-Zeilen."""
    if not FIELD_VISITS_CSV.exists():
        return {"removed": 0, "rows": 0}

    with open(FIELD_VISITS_CSV, encoding="utf-8-sig", errors="replace") as handle:
        rows = list(csv.DictReader(handle, delimiter=DELIMITER))

    kept: list[dict[str, str]] = []
    removed = 0
    for row in rows:
        text = (
            row.get("Original_Wortlaut_Freitext")
            or row.get("Verbesserungsvorschlag / Kritik")
            or ""
        ).strip()
        kunde = (row.get("Kunde") or "").strip()
        modul = (row.get("Modul_App_Verfahren") or "").strip()
        if len(text) < 5:
            removed += 1
            continue
        if not kunde and not modul:
            removed += 1
            continue
        row["Original_Wortlaut_Freitext"] = fix_encoding(text)
        kept.append(row)

    fieldnames = list(FIELD_VISITS_FIELDNAMES)
    for row in kept:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    _write_csv(FIELD_VISITS_CSV, fieldnames, kept)
    if removed:
        log(f"🧹 Feldbesuche: {removed} leere Zeilen entfernt ({len(kept)} verbleibend).")
    return {"removed": removed, "rows": len(kept)}


def _archive_inbox_file(path: Path, log: LogFn, *, rows: int = 0) -> None:
    dest = PROCESSED_DIR / path.name
    if dest.exists():
        dest.unlink()
    shutil.move(str(path), str(dest))
    mark_processed(dest, rows=rows, status="done")
    log(f"📁 {path.name} → processed/ (bereits verarbeitet / Duplikat).")


def _hash_already_processed(path: Path) -> bool:
    from pipeline.inbox import load_registry

    digest = file_hash(path)
    for entry in load_registry().get("files", {}).values():
        if entry.get("status") == "done" and entry.get("hash") == digest:
            return True
    return False


def _route_inbox_csv(path: Path, preview, log: LogFn, moved: list[str], archived: list[str]) -> None:
    if _hash_already_processed(path):
        _archive_inbox_file(path, log)
        archived.append(path.name)
        return

    if is_field_visits_csv(path, preview):
        target = INBOX_FIELD_VISITS_DIR / path.name
        if target.exists() or _hash_already_processed(path):
            _archive_inbox_file(path, log)
            archived.append(path.name)
        else:
            shutil.move(str(path), str(target))
            moved.append(f"{path.name} → weihnachtsbesuche/")
            log(f"📁 {path.name} → inbox/weihnachtsbesuche/")
        return

    target = INBOX_SURVEYS_DIR / path.name
    if target.exists():
        _archive_inbox_file(path, log)
        archived.append(path.name)
    else:
        shutil.move(str(path), str(target))
        moved.append(f"{path.name} → umfragen/")
        log(f"📁 {path.name} → inbox/umfragen/")


def sort_misplaced_inbox_files(log: LogFn = _default_log) -> dict[str, list[str]]:
    """
    Sortiert CSVs aus data/inbox/ (Root) in die richtigen Unterordner.
    Bereits verarbeitete Duplikate → processed/.
    """
    ensure_data_dirs()
    moved: list[str] = []
    archived: list[str] = []

    import pandas as pd

    for folder in (INBOX_DIR, INBOX_SURVEYS_DIR, INBOX_FIELD_VISITS_DIR):
        for path in sorted(folder.glob("*.csv")):
            if path.name.startswith("."):
                continue
            try:
                preview = pd.read_csv(path, sep=";", encoding="utf-8-sig", nrows=8, on_bad_lines="skip")
            except Exception:
                preview = pd.DataFrame()

            if folder == INBOX_DIR:
                _route_inbox_csv(path, preview, log, moved, archived)
            elif _hash_already_processed(path):
                _archive_inbox_file(path, log)
                archived.append(path.name)

    return {"moved": moved, "archived": archived}


def run_data_cleanup(log: LogFn = _default_log) -> dict[str, object]:
    """Vollständige Bereinigung vor dem Pipeline-Lauf."""
    log("\n--- Datenbereinigung ---")
    ensure_data_dirs()

    inbox = sort_misplaced_inbox_files(log=log)
    field = clean_field_visits_backlog(log=log)
    survey = clean_survey_backlog(log=log)
    dedup = purge_survey_field_visit_duplicates(log=log)

    log("✅ Datenbereinigung abgeschlossen.")
    return {
        "inbox": inbox,
        "field_visits": field,
        "surveys": survey,
        "dedup": dedup,
    }
