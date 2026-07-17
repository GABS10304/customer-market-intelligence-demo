"""TERA-Produktlinie — Hotline-Bereich teraWinData vs. RIWA/GIS-Portfolio."""

from __future__ import annotations

from core.demo_scope import BUILD_BEREICH, GIS_BEREICH, TERA_WIN_BEREICH


def is_tera_hotline_cluster(cluster: str) -> bool:
    """True für Hotline-Cluster unter teraWinData (eigenständige TERA-Produktlinie)."""
    raw = (cluster or "").strip()
    if not raw:
        return False
    prefix = f"{TERA_WIN_BEREICH}\\"
    lower = raw.lower()
    return lower.startswith(prefix.lower()) or lower == TERA_WIN_BEREICH.lower()


def is_riwa_portfolio_hotline_cluster(cluster: str) -> bool:
    """Hotline-Cluster für Product Signals (riwaGis + otsBau, ohne teraWin)."""
    raw = (cluster or "").strip()
    if not raw or is_tera_hotline_cluster(raw):
        return False
    lower = raw.lower()
    gis_prefix = f"{GIS_BEREICH}\\".lower()
    build_prefix = f"{BUILD_BEREICH}\\".lower()
    return lower.startswith(gis_prefix) or lower.startswith(build_prefix)
