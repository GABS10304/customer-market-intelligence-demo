"""
Inbox-Registry: trackt verarbeitete CSV-Dateien per Hash.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import REGISTRY_PATH, ensure_data_dirs


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_registry() -> dict[str, Any]:
    ensure_data_dirs()
    if not REGISTRY_PATH.exists():
        return {"files": {}}
    try:
        with open(REGISTRY_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {"files": {}}


def save_registry(registry: dict[str, Any]) -> None:
    ensure_data_dirs()
    with open(REGISTRY_PATH, "w", encoding="utf-8") as handle:
        json.dump(registry, handle, indent=2, ensure_ascii=False)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_file_entry(filename: str) -> dict[str, Any] | None:
    return load_registry().get("files", {}).get(filename)


def is_unchanged(path: Path) -> bool:
    entry = get_file_entry(path.name)
    if not entry or entry.get("status") != "done":
        return False
    return entry.get("hash") == file_hash(path)


def mark_processed(
    path: Path,
    *,
    rows: int,
    status: str = "done",
    error: str | None = None,
) -> None:
    registry = load_registry()
    registry.setdefault("files", {})[path.name] = {
        "hash": file_hash(path),
        "processed_at": _now_iso(),
        "rows": rows,
        "status": status,
        "error": error,
    }
    save_registry(registry)


def list_inbox_csvs(inbox_dir: Path) -> list[Path]:
    ensure_data_dirs()
    return sorted(inbox_dir.glob("*.csv"), key=lambda p: p.name.lower())


def pending_inbox_files(inbox_dir: Path) -> list[Path]:
    return [path for path in list_inbox_csvs(inbox_dir) if not is_unchanged(path)]
