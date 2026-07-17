"""
BigQuery-Upload — Staging → Validierung → Swap (sicher, kein blindes TRUNCATE).
"""

from __future__ import annotations

from typing import Any, Callable

from config import (
    BACKLOG_CSV,
    BIGQUERY_FIELD_VISITS_TABLE,
    BIGQUERY_HTML_TABLE,
    BIGQUERY_TABLE,
    FIELD_VISITS_CSV,
    HTML_OUTPUT_CSV,
    setup_gcp_credentials,
)
from core.bq_load import upload_csv_safe
from workspace.catalog import update_source_freshness

LogFn = Callable[[str], None]

# Pflichtspalten nach _normalize_columns (bq_load)
TABLE_RULES: dict[str, dict[str, Any]] = {
    BIGQUERY_TABLE: {
        "csv": BACKLOG_CSV,
        "required_columns": ("Kategorie",),
        "min_rows": 1,
    },
    BIGQUERY_HTML_TABLE: {
        "csv": HTML_OUTPUT_CSV,
        "required_columns": ("Ordner___Modul",),
        "min_rows": 1,
    },
    BIGQUERY_FIELD_VISITS_TABLE: {
        "csv": FIELD_VISITS_CSV,
        "required_columns": ("Modul_App_Verfahren",),
        "min_rows": 0,  # Quelle kann leer sein — dann skip, kein Swap
    },
}


def _default_log(message: str) -> None:
    print(message)


def upload_to_bigquery(log: LogFn = _default_log) -> dict[str, Any]:
    key = setup_gcp_credentials()
    if not key:
        log("🛑 gcp-key.json nicht gefunden.")
        return {"survey": False, "html": False, "field_visits": False, "skipped": True}

    log("🚀 BigQuery-Upload (Staging → Validierung → Swap)...")
    results: dict[str, Any] = {}

    for table_id, rules in TABLE_RULES.items():
        csv_path = rules["csv"]
        min_rows = int(rules.get("min_rows", 1))
        if min_rows == 0 and not csv_path.exists():
            log(f"⏭️ {csv_path.name} fehlt — {table_id} unverändert.")
            results[_result_key(table_id)] = None
            continue

        ok = upload_csv_safe(
            csv_path,
            table_id,
            required_columns=tuple(rules.get("required_columns", ())),
            min_rows=min_rows if min_rows > 0 else 1,
            log=log,
        )
        results[_result_key(table_id)] = ok
        if ok:
            _touch_catalog_source(table_id, csv_path)

    return results


def _touch_catalog_source(table_id: str, csv_path) -> None:
    import pandas as pd

    key = _result_key(table_id)
    profile_map = {
        "survey": "survey_freetext_250",
        "html": "support_tickets_html",
        "field_visits": "field_visits_weihnachtsbesuche",
    }
    profile = profile_map.get(key)
    if not profile:
        return
    try:
        row_count = len(pd.read_csv(csv_path, sep=";", encoding="utf-8-sig", on_bad_lines="skip"))
    except Exception:
        row_count = None
    update_source_freshness(profile, row_count=row_count)


def _result_key(table_id: str) -> str:
    if "anonymes_pm" in table_id or "backlog" in table_id:
        return "survey"
    if "html_tickets" in table_id:
        return "html"
    if "field_visits" in table_id:
        return "field_visits"
    return table_id
