"""Pending-Dateien in quellenspezifischen Inbox-Ordnern."""

from __future__ import annotations

from pathlib import Path

from config import INBOX_DIR, INBOX_FIELD_VISITS_DIR, INBOX_SURVEYS_DIR, ensure_data_dirs
from pipeline.inbox import list_inbox_csvs, pending_inbox_files

SOURCE_INBOX_DIRS: dict[str, Path] = {
    "survey_freetext_250": INBOX_SURVEYS_DIR,
    "field_visits_weihnachtsbesuche": INBOX_FIELD_VISITS_DIR,
}


def pending_for_profile(profile_name: str) -> list[Path]:
    ensure_data_dirs()
    folder = SOURCE_INBOX_DIRS.get(profile_name, INBOX_DIR)
    return pending_inbox_files(folder)


def pending_all_backend_csvs() -> dict[str, list[Path]]:
    ensure_data_dirs()
    return {
        profile: pending_for_profile(profile)
        for profile in SOURCE_INBOX_DIRS
    }
