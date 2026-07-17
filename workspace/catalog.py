"""Data Catalog — Quellen-Metadaten und Status."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from config import CATALOG_PATH, DEMO_EXCLUDED_SOURCE_KEYS, DEMO_MODE, ensure_data_dirs
from workspace.sources.detector import mapping_status
from workspace.sources.profiles import BUILTIN_PROFILES


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_catalog() -> dict[str, Any]:
    ensure_data_dirs()
    if not CATALOG_PATH.exists():
        return {"sources": {}, "updated_at": _now()}
    try:
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"sources": {}, "updated_at": _now()}


def save_catalog(catalog: dict[str, Any]) -> None:
    ensure_data_dirs()
    catalog["updated_at"] = _now()
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")


_DEMO_DISPLAY_NAMES: dict[str, str] = {
    "support_tickets_html": "Support-Tickets (Demo)",
    "survey_freetext_250": "Kundenumfragen (Demo)",
    "field_visits_weihnachtsbesuche": "Feldbesuche (Demo)",
    "sales_product_penetration": "Verträge / Penetration (Demo)",
}


def init_builtin_sources() -> dict[str, Any]:
    """Stellt Built-in-Quellen im Catalog sicher."""
    catalog = load_catalog()
    changed = False
    for name, profile in BUILTIN_PROFILES.items():
        if DEMO_MODE and name in DEMO_EXCLUDED_SOURCE_KEYS:
            if name in catalog["sources"]:
                del catalog["sources"][name]
                changed = True
            continue
        entry = catalog["sources"].get(name, {})
        display_name = (
            _DEMO_DISPLAY_NAMES.get(name, f"{profile.display_name} (Demo)")
            if DEMO_MODE
            else profile.display_name
        )
        new_entry = {
            "technical_name": name,
            "display_name": display_name,
            "status": entry.get("status", "active"),
            "last_updated": entry.get("last_updated"),
            "columns_detected": entry.get("columns_detected", list(profile.cluster_column_hints)),
            "mapping_status": entry.get("mapping_status", "confirmed"),
            "bq_table": None if DEMO_MODE else profile.bq_table,
            "source_type": "builtin",
            "description": profile.description if not DEMO_MODE else f"Synthetische Demo-Quelle: {display_name}",
        }
        if catalog["sources"].get(name) != new_entry:
            catalog["sources"][name] = new_entry
            changed = True
    if changed:
        save_catalog(catalog)
    return catalog


def register_pending_upload(
    upload_id: str,
    filename: str,
    detection: dict[str, Any],
) -> None:
    catalog = load_catalog()
    catalog["sources"][upload_id] = {
        "technical_name": upload_id,
        "display_name": f"Neu: {filename}",
        "status": "pending_verify",
        "last_updated": _now(),
        "columns_detected": detection.get("columns", []),
        "mapping_status": mapping_status(detection.get("mapping", {})),
        "bq_table": None,
        "source_type": "upload",
        "filename": filename,
        "suggested_profile": detection.get("suggested_profile"),
        "confidence": detection.get("confidence"),
        "mapping": detection.get("mapping"),
        "row_count": detection.get("row_count"),
    }
    save_catalog(catalog)


def confirm_upload(upload_id: str, profile_name: str, filename: str) -> None:
    catalog = load_catalog()
    pending = catalog["sources"].pop(upload_id, {})
    profile = BUILTIN_PROFILES.get(profile_name)
    if not profile:
        return
    catalog["sources"][profile_name] = {
        "technical_name": profile_name,
        "display_name": profile.display_name,
        "status": "active",
        "last_updated": _now(),
        "columns_detected": pending.get("columns_detected", []),
        "mapping_status": "confirmed",
        "bq_table": profile.bq_table,
        "source_type": "upload",
        "last_file": filename,
    }
    save_catalog(catalog)


def update_source_freshness(technical_name: str, row_count: int | None = None) -> None:
    catalog = load_catalog()
    if technical_name not in catalog["sources"]:
        init_builtin_sources()
        catalog = load_catalog()
    catalog["sources"][technical_name]["last_updated"] = _now()
    if row_count is not None:
        catalog["sources"][technical_name]["row_count"] = row_count
    save_catalog(catalog)


def mark_evidence_refreshed() -> None:
    """Nach Pipeline: Snapshot invalidieren (ohne catalog.updated_at zu bumpen)."""
    from workspace.snapshot import invalidate_workspace_snapshot

    invalidate_workspace_snapshot()


def list_catalog_sources() -> list[dict[str, Any]]:
    catalog = init_builtin_sources()
    items = list(catalog["sources"].values())
    if DEMO_MODE:
        items = [x for x in items if x.get("technical_name") not in DEMO_EXCLUDED_SOURCE_KEYS]
    order = {"active": 0, "pending_verify": 1, "error": 2}
    return sorted(items, key=lambda x: (order.get(x.get("status", ""), 9), x.get("display_name", "")))
