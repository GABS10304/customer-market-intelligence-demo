"""
Hotline-Rohdaten-Scope — gemeinsam für Scraper, Product Signals, Inventory.

Standard: riwaGisData + teraWinData + otsBauData, ohne «Allgemein»-Cluster.
"""

from __future__ import annotations

import os

from core.html_ticket_reader import is_genereller_bereich_cluster

DEFAULT_BEREICHE = ("riwaGisData", "teraWinData", "otsBauData")


def parse_bereiche(raw: str | None) -> tuple[str, ...] | None:
    """None = alle Bereiche."""
    if not raw or not str(raw).strip() or str(raw).strip() == "*":
        return None
    parts = tuple(b.strip() for b in str(raw).split(",") if b.strip())
    return parts or None


def hotline_scope_from_env() -> tuple[tuple[str, ...] | None, bool]:
    bereiche = parse_bereiche(os.getenv("HOTLINE_HTML_BEREICHE", ",".join(DEFAULT_BEREICHE)))
    exclude_gen = os.getenv("HOTLINE_EXCLUDE_ALLGEMEIN", "true").lower() not in ("0", "false", "no")
    return bereiche, exclude_gen


def ticket_in_hotline_scope(
    ticket: dict[str, str],
    *,
    bereiche: tuple[str, ...] | None = None,
    exclude_genereller_bereich: bool | None = None,
) -> bool:
    if bereiche is None or exclude_genereller_bereich is None:
        env_bereiche, env_exclude = hotline_scope_from_env()
        bereiche = env_bereiche if bereiche is None else bereiche
        exclude_genereller_bereich = (
            env_exclude if exclude_genereller_bereich is None else exclude_genereller_bereich
        )
    cluster = ticket.get("cluster") or ""
    bereich = ticket.get("bereich") or ""
    if bereiche is not None and bereich not in bereiche:
        return False
    if exclude_genereller_bereich and is_genereller_bereich_cluster(cluster):
        return False
    return True
