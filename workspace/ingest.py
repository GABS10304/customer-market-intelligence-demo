"""Upload → Verify → Inbox → Pipeline."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from config import INBOX_DIR, UPLOAD_DIR, ensure_data_dirs
from pipeline.runner import run_pipeline
from workspace.catalog import confirm_upload, register_pending_upload, update_source_freshness
from workspace.sources.detector import DetectionResult, detect_source
from workspace.sources.profiles import get_profile


def save_upload(file_bytes: bytes, filename: str) -> tuple[str, Path]:
    ensure_data_dirs()
    upload_id = f"pending_{uuid.uuid4().hex[:8]}"
    path = UPLOAD_DIR / f"{upload_id}_{filename}"
    path.write_bytes(file_bytes)
    return upload_id, path


def analyze_upload(path: Path) -> DetectionResult:
    profile = get_profile("survey_freetext_250")
    delimiter = profile.delimiter if profile else ";"
    df = pd.read_csv(path, sep=delimiter, encoding="utf-8-sig", on_bad_lines="skip")
    return detect_source(df, filename=path.name.split("_", 1)[-1])


def stage_for_verification(upload_id: str, path: Path, detection: DetectionResult) -> None:
    register_pending_upload(
        upload_id,
        path.name.split("_", 1)[-1],
        {
            "columns": detection.columns,
            "suggested_profile": detection.suggested_profile,
            "confidence": detection.confidence,
            "mapping": detection.mapping,
            "row_count": detection.row_count,
        },
    )


def confirm_and_ingest(
    upload_id: str,
    path: Path,
    profile_name: str,
    log=None,
    mapping: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Nach User-Bestätigung: Inbox + Meta + Pipeline."""
    ensure_data_dirs()
    original_name = path.name.split("_", 1)[-1]
    target = INBOX_DIR / original_name
    shutil.copy2(path, target)

    meta = {
        "source_profile": profile_name,
        "upload_id": upload_id,
        "confirmed": True,
    }
    if mapping:
        meta["mapping"] = mapping
    meta_path = target.with_suffix(".csv.meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    confirm_upload(upload_id, profile_name, original_name)

    logger = log or print
    results = run_pipeline(steps=("csv", "bq", "rag"), log=logger)
    update_source_freshness(profile_name, row_count=detection_row_count(target))

    path.unlink(missing_ok=True)
    return {"filename": original_name, "profile": profile_name, "pipeline": results}


def detection_row_count(path: Path) -> int:
    try:
        df = pd.read_csv(path, sep=";", encoding="utf-8-sig", on_bad_lines="skip")
        return len(df)
    except Exception:
        return 0
