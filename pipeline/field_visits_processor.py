"""
Feldfeedback (Weihnachtsbesuche etc.) — direktes Mapping, kein LLM.
"""

from __future__ import annotations

import csv
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from config import (
    DELIMITER,
    FIELD_VISITS_CSV,
    FIELD_VISITS_FIELDNAMES,
    INBOX_FIELD_VISITS_DIR,
    PROCESSED_DIR,
    ensure_data_dirs,
)
from core.governance import scrub_pii
from pipeline.inbox import mark_processed, pending_inbox_files
from workspace.sources.detector import build_mapping, detect_source
from workspace.sources.profiles import get_profile

LogFn = Callable[[str], None]


def _default_log(message: str) -> None:
    print(message)


def _move_to_processed(path: Path) -> Path:
    ensure_data_dirs()
    target = PROCESSED_DIR / path.name
    if target.exists():
        target.unlink()
    shutil.move(str(path), str(target))
    return target


def _find_ap_column(columns: list[str]) -> str | None:
    for col in columns:
        if col.strip().upper() == "AP":
            return col
    return None


def load_field_visits_rows() -> list[dict[str, str]]:
    if not FIELD_VISITS_CSV.exists():
        return []
    with open(FIELD_VISITS_CSV, encoding="utf-8-sig", errors="replace") as handle:
        return list(csv.DictReader(handle, delimiter=DELIMITER))


def write_field_visits(rows: list[dict[str, str]]) -> None:
    fieldnames = list(FIELD_VISITS_FIELDNAMES)
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with open(FIELD_VISITS_CSV, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)


def remove_rows_for_file(rows: list[dict[str, str]], filename: str) -> list[dict[str, str]]:
    return [row for row in rows if row.get("source_file") != filename]


def process_field_visits_csv(path: Path, *, log: LogFn = _default_log) -> list[dict[str, str]]:
    profile = get_profile("field_visits_weihnachtsbesuche")
    if profile is None:
        raise ValueError("Source Profile field_visits_weihnachtsbesuche fehlt.")

    df = pd.read_csv(path, sep=";", encoding="utf-8-sig", on_bad_lines="skip")
    if df.empty:
        return []

    detection = detect_source(df, filename=path.name)
    mapping = detection.mapping if detection.suggested_profile == profile.technical_name else build_mapping(
        profile, list(df.columns)
    )
    if not mapping.get("text") or not mapping.get("cluster"):
        mapping = build_mapping(profile, list(df.columns))

    text_col = mapping.get("text")
    cluster_col = mapping.get("cluster")
    customer_col = mapping.get("customer")
    ap_col = _find_ap_column(list(df.columns))

    if not text_col or not cluster_col:
        raise ValueError(
            f"Mapping unvollständig für {path.name} — "
            f"Text: {text_col}, Cluster: {cluster_col}"
        )

    processed_at = datetime.now(timezone.utc).isoformat()
    results: list[dict[str, str]] = []
    log(f"\n📋 Verarbeite Feldfeedback {path.name} (ohne LLM)...")

    for _, row in df.iterrows():
        text = scrub_pii(str(row.get(text_col, "")).strip())
        if not text or text.lower() in {"nan", "none", "-"}:
            continue
        cluster = str(row.get(cluster_col, "unknown")).strip()
        kunde = str(row.get(customer_col, "")).strip() if customer_col else ""
        ap = str(row.get(ap_col, "")).strip() if ap_col else ""

        results.append(
            {
                "Kunde": kunde,
                "AP": ap,
                "Modul_App_Verfahren": cluster,
                "Original_Wortlaut_Freitext": text,
                "Quelle": "Weihnachtsbesuche / Feldfeedback",
                "source_file": path.name,
                "processed_at": processed_at,
            }
        )

    log(f"   ✅ {len(results)} Zeilen normalisiert")
    return results


def process_field_visits_inbox(log: LogFn = _default_log) -> dict[str, Any]:
    ensure_data_dirs()
    field_visit_files = pending_inbox_files(INBOX_FIELD_VISITS_DIR)
    if not field_visit_files:
        return {"processed": 0, "rows_added": 0, "files": []}

    backlog = load_field_visits_rows()
    total_rows_added = 0
    processed_files: list[str] = []

    for path in field_visit_files:
        try:
            rows = process_field_visits_csv(path, log=log)
            backlog = remove_rows_for_file(backlog, path.name)
            backlog.extend(rows)
            total_rows_added += len(rows)
            mark_processed(path, rows=len(rows), status="done")
            _move_to_processed(path)
            processed_files.append(path.name)
        except Exception as exc:
            mark_processed(path, rows=0, status="error", error=str(exc))
            log(f"❌ Fehler bei {path.name}: {exc}")

    if processed_files:
        write_field_visits(backlog)
        log(f"\n🎉 Feldfeedback-Backlog: {len(backlog)} Zeilen gesamt (+{total_rows_added} neu).")

    return {
        "processed": len(processed_files),
        "rows_added": total_rows_added,
        "files": processed_files,
    }
