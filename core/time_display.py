"""Zeitformatierung für die UI — Europe/Berlin."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


def format_berlin(iso_timestamp: str | None) -> str:
    if not iso_timestamp or not str(iso_timestamp).strip():
        return "—"
    raw = str(iso_timestamp).strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw[:19]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(BERLIN).strftime("%d.%m.%Y %H:%M") + " Uhr (Berlin)"
