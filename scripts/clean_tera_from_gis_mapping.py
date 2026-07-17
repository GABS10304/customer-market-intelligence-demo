#!/usr/bin/env python3
"""Entfernt teraWin-Cluster aus product_module_mapping.json (TERA = eigene Produktlinie)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.product_mapping import MAPPING_PATH
from core.tera_scope import is_tera_hotline_cluster

TERA_ONLY_ALIASES = frozenset(
    {
        "friedhofsverwaltung",
        "teraeakte",
        "teramobil",
        "beitragswesen",
        "mietundpachtobjekte",
        "gebaeudemanager",
        "auskunftsmoduleexpobjdat",
        "belegungsplan",
        "vertragsmanager",
        "liegenschaftsverwaltung",
        "adressabgleichfisewobaybis",
        "bauhofverwaltung  ressourcenmanager",
    }
)


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def clean_mapping_entries(entries: list[dict]) -> tuple[list[dict], int, int]:
    removed_entries = 0
    stripped_clusters = 0
    cleaned: list[dict] = []

    for raw in entries:
        entry = dict(raw)
        clusters = list(entry.get("ticket_clusters") or [])
        gis_clusters = [c for c in clusters if not is_tera_hotline_cluster(str(c))]
        stripped_clusters += len(clusters) - len(gis_clusters)

        if clusters and not gis_clusters:
            removed_entries += 1
            continue

        if gis_clusters != clusters:
            entry["ticket_clusters"] = gis_clusters

        aliases = list(entry.get("cluster_aliases") or [])
        kept_aliases = [a for a in aliases if _norm(str(a)) not in TERA_ONLY_ALIASES]
        if kept_aliases != aliases:
            if kept_aliases:
                entry["cluster_aliases"] = kept_aliases
            else:
                entry.pop("cluster_aliases", None)

        cleaned.append(entry)

    return cleaned, removed_entries, stripped_clusters


def main() -> None:
    if not MAPPING_PATH.exists():
        print(f"Fehlt: {MAPPING_PATH}", file=sys.stderr)
        raise SystemExit(1)

    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    entries = list(data.get("entries") or [])
    cleaned, removed, stripped = clean_mapping_entries(entries)
    data["entries"] = cleaned
    MAPPING_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Mapping bereinigt: {len(cleaned)} Einträge "
        f"({removed} TERA-only entfernt, {stripped} teraWin-Cluster gestrippt)"
    )


if __name__ == "__main__":
    main()
