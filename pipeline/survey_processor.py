"""
Kundenumfrage (NPS) aus data/inbox/umfragen — vollständiger Export + Freitext.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from config import DELIMITER, INBOX_SURVEYS_DIR, SURVEYS_NPS_CSV, ensure_data_dirs
from core.data_cleanup import clean_llm_artifact_text, fix_encoding
from core.governance import scrub_pii

LogFn = Callable[[str], None]

FREITEXT_HINTS = ("anregungen", "wünsche", "wünsche", "verbesserung", "freitext", "kommentar")
LANDKREIS_HINTS = ("landkreis", "kreis", "region", "gemeinde")


def _default_log(message: str) -> None:
    print(message)


def _pick_column(columns: list[str], hints: tuple[str, ...]) -> str | None:
    for col in columns:
        lower = col.lower()
        if any(h in lower for h in hints):
            return col
    return None


def build_surveys_from_inbox(log: LogFn = _default_log) -> dict[str, Any]:
    """Exportiert alle CSV aus inbox/umfragen → surveys_nps.csv (Originalfelder)."""
    ensure_data_dirs()
    csv_files = sorted(INBOX_SURVEYS_DIR.glob("*.csv"))

    if not csv_files:
        log(f"⚠️ Keine Umfrage-CSV in {INBOX_SURVEYS_DIR}")
        return {"rows": 0, "files": [], "error": "no_files"}

    all_rows: list[dict[str, str]] = []
    processed_at = datetime.now(timezone.utc).isoformat()

    for path in csv_files:
        log(f"\n📊 Umfrage: {path.name}")
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            reader = csv.DictReader(handle, delimiter=DELIMITER)
            columns = list(reader.fieldnames or [])
            freitext_col = _pick_column(columns, FREITEXT_HINTS)
            landkreis_col = _pick_column(columns, LANDKREIS_HINTS)

            count = 0
            for row in reader:
                out = dict(row)
                if freitext_col and out.get(freitext_col):
                    cleaned = clean_llm_artifact_text(scrub_pii(str(out[freitext_col])))
                    out[freitext_col] = fix_encoding(cleaned)
                if landkreis_col and out.get(landkreis_col):
                    out[landkreis_col] = fix_encoding(str(out[landkreis_col]).strip())

                out["source_file"] = path.name
                out["processed_at"] = processed_at
                out["Quelle"] = "Kundenumfrage NPS"
                all_rows.append(out)
                count += 1

            log(f"   {count} Zeilen (Freitext-Spalte: {freitext_col or '—'})")

    if not all_rows:
        return {"rows": 0, "files": [p.name for p in csv_files]}

    fieldnames: list[str] = []
    for row in all_rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with open(SURVEYS_NPS_CSV, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(all_rows)

    freitext_col = _pick_column(fieldnames, FREITEXT_HINTS)
    with_text = 0
    if freitext_col:
        with_text = sum(1 for r in all_rows if len((r.get(freitext_col) or "").strip()) >= 5)

    log(f"✅ {len(all_rows)} Umfrage-Zeilen → {SURVEYS_NPS_CSV.name} ({with_text} mit Freitext)")
    return {
        "rows": len(all_rows),
        "freitext_rows": with_text,
        "files": [p.name for p in csv_files],
    }
