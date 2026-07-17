"""
Graylog event/dialogName → mapping_id (product_module_mapping.json).

Daten: data/graylog_event_mapping.json
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import GRAYLOG_EVENT_MAPPING_PATH

MAPPING_PATH = GRAYLOG_EVENT_MAPPING_PATH


@lru_cache(maxsize=1)
def _load_raw() -> dict[str, Any]:
    if not MAPPING_PATH.exists():
        return {}
    try:
        return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=1)
def _exact_map() -> dict[str, str]:
    raw = _load_raw()
    return {str(k).strip(): str(v).strip() for k, v in (raw.get("exact") or {}).items() if k and v}


@lru_cache(maxsize=1)
def _prefix_rules() -> list[tuple[str, str]]:
    raw = _load_raw()
    rules: list[tuple[str, str]] = []
    for prefix, mapping_id in (raw.get("prefix") or {}).items():
        p = str(prefix).strip()
        mid = str(mapping_id).strip()
        if p and mid:
            rules.append((p, mid))
    rules.sort(key=lambda item: len(item[0]), reverse=True)
    return rules


@lru_cache(maxsize=1)
def _skip_set() -> frozenset[str]:
    raw = _load_raw()
    return frozenset(str(x).strip() for x in (raw.get("skip") or []) if str(x).strip())


def is_graylog_skipped(label: str) -> bool:
    """True wenn Event/Dialog in skip-Liste (nicht in Usage zählen)."""
    text = (label or "").strip()
    return bool(text) and text in _skip_set()


def resolve_graylog_modul(label: str) -> str | None:
    """
    Ordnet Graylog-Event oder dialogName einer mapping_id zu.

    Reihenfolge: exact → längster Prefix-Match.
    None bei skip, unbekannt oder leerem Label.
    """
    text = (label or "").strip()
    if not text or is_graylog_skipped(text):
        return None

    exact = _exact_map()
    if text in exact:
        return exact[text]

    for prefix, mapping_id in _prefix_rules():
        if text.startswith(prefix):
            return mapping_id

    return None


def clear_graylog_mapping_cache() -> None:
    """Cache leeren (Tests)."""
    _load_raw.cache_clear()
    _exact_map.cache_clear()
    _prefix_rules.cache_clear()
    _skip_set.cache_clear()
