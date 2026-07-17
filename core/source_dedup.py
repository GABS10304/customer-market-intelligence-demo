"""
Deduplizierung: Weihnachtsbesuche/Feldfeedback nicht doppelt als Umfrage zählen.

Historisch wurden CSVs im Format „Kunde;AP;Modul;Kritik“ fälschlich über tickets_a.csv
als „Kundenumfrage (A)“ in den Umfragen-Backlog geschrieben.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Callable

import pandas as pd

from config import BACKLOG_CSV, DATA_DIR, DELIMITER, FIELD_VISITS_CSV
from workspace.sources.detector import detect_source
from workspace.sources.profiles import get_profile

LogFn = Callable[[str], None]

# Fehl geroutete Umfrage-Zeilen (Weihnachtsbesuche-Format via tickets_a.csv)
MISROUTED_SURVEY_LABEL = "Kundenumfrage (A)"
DEDUP_OFFSETS_PATH = DATA_DIR / "survey_dedup_offsets.json"


def _norm_key(text: str, *, max_len: int = 80) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", "", (text or "").lower())[:max_len]


def field_visit_customer_keys() -> set[str]:
    """Kunden-Schlüssel aus dem Feldfeedback-Backlog."""
    if not FIELD_VISITS_CSV.exists():
        return set()
    keys: set[str] = set()
    with open(FIELD_VISITS_CSV, encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.DictReader(handle, delimiter=DELIMITER):
            kunde = row.get("Kunde") or row.get("kunde") or ""
            text = (
                row.get("Original_Wortlaut_Freitext")
                or row.get("Verbesserungsvorschlag / Kritik")
                or row.get("Verbesserungsvorschlag___Kritik")
                or ""
            )
            if not kunde.strip() and not text.strip():
                continue
            keys.add(_norm_key(kunde))
    return keys


def is_misrouted_field_visit_survey_row(row: dict[str, str]) -> bool:
    """True wenn Umfrage-Zeile zum Feldfeedback-Backlog gehört (Doppelzählung)."""
    quelle = (row.get("Quelle") or "").strip()
    if quelle == MISROUTED_SURVEY_LABEL:
        return True

    fv_keys = field_visit_customer_keys()
    if not fv_keys:
        return False

    kunde = _norm_key(row.get("Kunde") or row.get("kunde") or "")
    if kunde and kunde in fv_keys:
        # Gleicher Kunde + typisches LLM-Summary-Muster aus Weihnachtsbesuch-Import
        if quelle in ("Kundenumfrage (A)", "Weihnachtsbesuche / Feldfeedback"):
            return True
    return False


def is_field_visits_csv(path: Path, df: pd.DataFrame | None = None) -> bool:
    """Erkennt Weihnachtsbesuche-CSV — darf nicht als Umfrage verarbeitet werden."""
    profile = get_profile("field_visits_weihnachtsbesuche")
    if profile is None:
        return False

    if df is None:
        try:
            df = pd.read_csv(path, sep=";", encoding="utf-8-sig", nrows=5, on_bad_lines="skip")
        except Exception:
            return False

    detection = detect_source(df, filename=path.name)
    return detection.suggested_profile == profile.technical_name and detection.confidence >= 0.5


def filter_survey_backlog_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    """Entfernt Feldfeedback-Duplikate aus Umfragen-Backlog."""
    kept: list[dict[str, str]] = []
    removed = 0
    for row in rows:
        if is_misrouted_field_visit_survey_row(row):
            removed += 1
            continue
        kept.append(row)
    return kept, removed


def survey_category_dedup_offsets() -> dict[str, int]:
    """Wie viele Umfrage-Zeilen pro Kategorie Feldfeedback-Duplikate sind."""
    if DEDUP_OFFSETS_PATH.exists():
        try:
            import json

            data = json.loads(DEDUP_OFFSETS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): int(v) for k, v in data.items()}
        except (json.JSONDecodeError, OSError, ValueError):
            pass

    if not BACKLOG_CSV.exists():
        return {}
    offsets: dict[str, int] = {}
    with open(BACKLOG_CSV, encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.DictReader(handle, delimiter=DELIMITER):
            if not is_misrouted_field_visit_survey_row(row):
                continue
            cat = (row.get("Kategorie") or "unknown").strip()
            offsets[cat] = offsets.get(cat, 0) + 1
    return offsets


def _save_dedup_offsets(offsets: dict[str, int]) -> None:
    if not offsets:
        return
    import json

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DEDUP_OFFSETS_PATH.write_text(json.dumps(offsets, ensure_ascii=False, indent=2), encoding="utf-8")


def adjust_survey_cluster_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Reduziert Umfragen-Cluster-Zähler um Feldfeedback-Duplikate.
    Nur wenn Feldfeedback-Backlog existiert und Duplikate erkannt wurden.
    """
    if df.empty:
        return df

    offsets = survey_category_dedup_offsets()
    if not offsets:
        return df

    out = df.copy()
    for idx, row in out.iterrows():
        cluster = str(row.get("cluster", ""))
        if cluster in offsets:
            new_val = max(0, int(row["anzahl"]) - offsets[cluster])
            out.at[idx, "anzahl"] = new_val
    return out[out["anzahl"] > 0].reset_index(drop=True)


def purge_survey_field_visit_duplicates(log: LogFn | None = None) -> dict[str, int]:
    """
    Schreibt bereinigten Umfragen-Backlog (ohne Weihnachtsbesuchs-Doppelungen).
    Returns: {"removed": n, "remaining": m}
    """
    if not BACKLOG_CSV.exists():
        return {"removed": 0, "remaining": 0}

    with open(BACKLOG_CSV, encoding="utf-8-sig", errors="replace") as handle:
        rows = list(csv.DictReader(handle, delimiter=DELIMITER))

    if not rows:
        return {"removed": 0, "remaining": 0}

    offsets: dict[str, int] = {}
    for row in rows:
        if not is_misrouted_field_visit_survey_row(row):
            continue
        cat = (row.get("Kategorie") or "unknown").strip()
        offsets[cat] = offsets.get(cat, 0) + 1

    kept, removed = filter_survey_backlog_rows(rows)
    if removed <= 0:
        return {"removed": 0, "remaining": len(rows)}

    _save_dedup_offsets(offsets)

    fieldnames = list(rows[0].keys())
    for row in kept:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with open(BACKLOG_CSV, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(kept)

    if log:
        log(
            f"🧹 Dedup: {removed} Weihnachtsbesuchs-Zeilen aus Umfragen-Backlog entfernt "
            f"(→ nur noch Feldfeedback-Quelle). Verbleibend: {len(kept)}."
        )

    return {"removed": removed, "remaining": len(kept)}
