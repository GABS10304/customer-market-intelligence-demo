"""Sicherer BigQuery-Upload: Staging → Validierung → Swap."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

from config import BQ_MAX_ROW_DROP_PCT, BQ_MIN_ROWS, BQ_USE_STAGING, setup_gcp_credentials

LogFn = Callable[[str], None]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = (
        df.columns.str.replace(" ", "_")
        .str.replace("-", "_")
        .str.replace("(", "")
        .str.replace(")", "")
        .str.replace("/", "_")
        .str.replace("?", "")
    )
    return df


def _table_row_count(client: bigquery.Client, table_id: str) -> int | None:
    try:
        query = f"SELECT COUNT(*) AS n FROM `{table_id}`"
        return int(list(client.query(query).result())[0].n)
    except NotFound:
        return None
    except Exception:
        return None


def _validate_staging(
    client: bigquery.Client,
    staging_id: str,
    prod_id: str,
    *,
    min_rows: int,
    required_columns: tuple[str, ...],
    max_drop_pct: float,
    log: LogFn,
) -> bool:
    staging_count = _table_row_count(client, staging_id)
    if staging_count is None:
        log(f"🛑 Staging-Tabelle {staging_id} nicht lesbar.")
        return False

    if staging_count < min_rows:
        log(f"🛑 Staging hat nur {staging_count} Zeilen (Minimum: {min_rows}) — Prod unverändert.")
        return False

    try:
        staging_table = client.get_table(staging_id)
        cols = {field.name for field in staging_table.schema}
    except Exception as exc:
        log(f"🛑 Staging-Schema nicht lesbar: {exc}")
        return False

    missing = [c for c in required_columns if c not in cols]
    if missing:
        log(f"🛑 Pflichtspalten fehlen in Staging: {', '.join(missing)} — Prod unverändert.")
        return False

    prod_count = _table_row_count(client, prod_id)
    if prod_count is not None and prod_count > 0:
        drop_ratio = 1.0 - (staging_count / prod_count)
        if drop_ratio > max_drop_pct:
            log(
                f"🛑 Row-Count-Drop zu groß: {prod_count} → {staging_count} "
                f"({drop_ratio:.0%} Verlust, Limit {max_drop_pct:.0%}) — Prod unverändert."
            )
            return False

    log(f"✅ Staging OK: {staging_count} Zeilen, Schema geprüft.")
    return True


def _swap_staging_to_prod(client: bigquery.Client, staging_id: str, prod_id: str, log: LogFn) -> None:
    query = f"CREATE OR REPLACE TABLE `{prod_id}` AS SELECT * FROM `{staging_id}`"
    log(f"🔄 Swap Staging → Prod: `{prod_id}` …")
    client.query(query, location="EU").result()
    log(f"✅ Prod-Tabelle aktualisiert: {prod_id}")


def upload_csv_safe(
    csv_path: Path,
    table_id: str,
    *,
    required_columns: tuple[str, ...] = (),
    min_rows: int | None = None,
    max_drop_pct: float | None = None,
    use_staging: bool | None = None,
    log: LogFn = print,
) -> bool:
    """
    Lädt CSV sicher nach BigQuery.

    Mit Staging (Standard): Load → `_staging` → Validierung → CREATE OR REPLACE Swap.
    Ohne Staging (Fallback): direkter Load nur wenn Prod-Tabelle noch nicht existiert.
    """
    if not csv_path.exists():
        log(f"⚠️ Datei nicht gefunden: {csv_path.name} — übersprungen.")
        return False

    if setup_gcp_credentials() is None:
        log("🛑 gcp-key.json nicht gefunden.")
        return False

    df = pd.read_csv(csv_path, sep=";", encoding="utf-8-sig", on_bad_lines="skip")
    if df.empty:
        log(f"🛑 {csv_path.name} ist leer — Prod-Tabelle wird nicht angetastet.")
        return False

    df = _normalize_columns(df)
    min_rows = BQ_MIN_ROWS if min_rows is None else min_rows
    max_drop_pct = BQ_MAX_ROW_DROP_PCT if max_drop_pct is None else max_drop_pct
    use_staging = BQ_USE_STAGING if use_staging is None else use_staging

    client = bigquery.Client()
    staging_id = f"{table_id}_staging"

    if use_staging:
        job_config = bigquery.LoadJobConfig(
            write_disposition="WRITE_TRUNCATE",
            autodetect=True,
        )
        log(f"☁️ Staging-Load: {len(df)} Zeilen → `{staging_id}` …")
        job = client.load_table_from_dataframe(df, staging_id, job_config=job_config, location="EU")
        job.result()

        if not _validate_staging(
            client,
            staging_id,
            table_id,
            min_rows=min_rows,
            required_columns=required_columns,
            max_drop_pct=max_drop_pct,
            log=log,
        ):
            return False

        _swap_staging_to_prod(client, staging_id, table_id, log)
        return True

    # Fallback: direkter Load nur bei Erst-Anlage
    prod_exists = _table_row_count(client, table_id) is not None
    if prod_exists:
        log(f"🛑 Prod `{table_id}` existiert — Staging erforderlich (BQ_USE_STAGING=true).")
        return False

    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE", autodetect=True)
    log(f"☁️ Erst-Load: {len(df)} Zeilen → `{table_id}` …")
    job = client.load_table_from_dataframe(df, table_id, job_config=job_config, location="EU")
    job.result()
    log(f"✅ Erst-Load OK: {table_id}")
    return True
