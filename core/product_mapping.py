"""
ERP-Artikel ↔ Hotline-Cluster — Seed-Mapping + Fallback-Heuristik.

Mapping-Datei: data/product_module_mapping.json (manuell erweiterbar).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from config import PRODUCT_MODULE_MAPPING_PATH

MAPPING_PATH = PRODUCT_MODULE_MAPPING_PATH


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


@dataclass(frozen=True)
class ProductMappingEntry:
    id: str
    label: str
    ticket_clusters: tuple[str, ...]
    cluster_aliases: tuple[str, ...] = ()
    ranking_aliases: tuple[str, ...] = ()
    notes: str = ""


def _entry_matches(artikel_norm: str, raw: dict[str, Any]) -> bool:
    excludes = [_norm(x) for x in raw.get("artikel_excludes") or []]
    if any(ex in artikel_norm for ex in excludes if ex):
        return False

    prefix = raw.get("artikel_prefix")
    if prefix and artikel_norm.startswith(_norm(prefix)):
        return True

    exact_list = raw.get("artikel_exact") or []
    for exact in exact_list:
        if artikel_norm == _norm(exact):
            return True

    contains_all = [_norm(x) for x in raw.get("artikel_contains_all") or []]
    if contains_all and all(token in artikel_norm for token in contains_all if token):
        return True

    contains_any = [_norm(x) for x in raw.get("artikel_contains_any") or []]
    if contains_any and any(token in artikel_norm for token in contains_any if token):
        return True

    return False


@lru_cache(maxsize=1)
def load_mapping_entries() -> tuple[ProductMappingEntry, ...]:
    if not MAPPING_PATH.exists():
        return ()

    try:
        data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()

    entries: list[ProductMappingEntry] = []
    for raw in data.get("entries") or []:
        clusters = tuple(str(c) for c in raw.get("ticket_clusters") or [] if str(c).strip())
        aliases = tuple(str(a) for a in raw.get("cluster_aliases") or [] if str(a).strip())
        ranking = tuple(str(a) for a in raw.get("ranking_aliases") or [] if str(a).strip())
        if not clusters and not aliases and not ranking:
            continue
        entries.append(
            ProductMappingEntry(
                id=str(raw.get("id") or raw.get("label") or "mapping"),
                label=str(raw.get("label") or raw.get("id") or "Mapping"),
                ticket_clusters=clusters,
                cluster_aliases=aliases,
                ranking_aliases=ranking,
                notes=str(raw.get("notes") or ""),
            )
        )
    return tuple(entries)


def _raw_entries() -> list[dict[str, Any]]:
    if not MAPPING_PATH.exists():
        return []
    try:
        data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return list(data.get("entries") or [])


def find_seed_mapping(artikel: str) -> ProductMappingEntry | None:
    artikel_norm = _norm(artikel)
    if not artikel_norm:
        return None
    for raw, entry in zip(_raw_entries(), load_mapping_entries()):
        if _entry_matches(artikel_norm, raw):
            return entry
    return None


def ticket_count_for_clusters(
    clusters: tuple[str, ...],
    ticket_idx: dict[str, int],
) -> tuple[int, str]:
    """Summiert Tickets über gemappte Cluster; liefert Top-Cluster für Anzeige."""
    total = 0
    best_cluster = ""
    best_count = 0
    for cluster in clusters:
        count = ticket_idx.get(cluster, 0)
        total += count
        if count > best_count:
            best_count = count
            best_cluster = cluster
    if total > 0 and not best_cluster:
        best_cluster = clusters[0]
    return total, best_cluster


def resolve_product_tickets(
    artikel: str,
    ticket_idx: dict[str, int],
    *,
    heuristic_match_fn,
) -> tuple[str, int, float, str, str]:
    """
    Returns: cluster_label, ticket_count, match_score, match_art, mapping_id

    match_art: seed | heuristisch | —
    """
    seed = find_seed_mapping(artikel)
    if seed:
        total, top_cluster = ticket_count_for_clusters(seed.ticket_clusters, ticket_idx)
        label = top_cluster if top_cluster else (seed.ticket_clusters[0] if seed.ticket_clusters else "")
        if total > 0:
            return label, total, 1.0, "seed", seed.id
        # Seed definiert, aber keine Tickets in BQ — Cluster trotzdem anzeigen
        return label, 0, 1.0, "seed", seed.id

    cluster, count, score = heuristic_match_fn(artikel, ticket_idx)
    if cluster:
        return cluster, count, score, "heuristisch", ""
    return "", 0, 0.0, "—", ""


@lru_cache(maxsize=1)
def cluster_to_primary_group() -> dict[str, str]:
    """Cluster/Alias → mapping_id. Spätere Einträge überschreiben."""
    out: dict[str, str] = {}
    for entry in load_mapping_entries():
        for cluster in entry.ticket_clusters:
            out[_norm(cluster)] = entry.id
        for alias in entry.cluster_aliases:
            out[_norm(alias)] = entry.id
    return out


def resolve_cluster_mapping(cluster: str) -> ProductMappingEntry | None:
    """Ordnet Ticket- oder Feldbesuch-Cluster einer Business-Gruppe zu."""
    raw = (cluster or "").strip()
    if not raw:
        return None

    lookup = cluster_to_primary_group()
    key = _norm(raw)
    if key in lookup:
        return mapping_entry_by_id(lookup[key])

    leaf = raw.rsplit("\\", 1)[-1].strip()
    if " - " in leaf:
        leaf = leaf.split(" - ", 1)[1].strip()
    leaf_key = _norm(leaf)
    if leaf_key in lookup:
        return mapping_entry_by_id(lookup[leaf_key])

    for entry in load_mapping_entries():
        for ticket_cluster in entry.ticket_clusters:
            tc_norm = _norm(ticket_cluster)
            if leaf_key and leaf_key in tc_norm:
                return entry
            if key and key in tc_norm:
                return entry
    return None


def module_display_name(cluster: str) -> str:
    """Anzeigename für Modul-Auswertung (Mapping-Label oder Cluster-Leaf)."""
    entry = resolve_cluster_mapping(cluster)
    if entry:
        return entry.label
    raw = (cluster or "").strip()
    leaf = raw.rsplit("\\", 1)[-1].strip()
    if " - " in leaf:
        return leaf.split(" - ", 1)[1].strip()
    return leaf or raw or "Unbekannt"


def groups_for_cluster(cluster: str) -> tuple[str, ...]:
    cid = cluster_to_primary_group().get((cluster or "").strip())
    return (cid,) if cid else ()


def revenue_by_mapping_group() -> dict[str, float]:
    """Summe_Umsatz pro mapping_id über alle passenden ERP-Artikel."""
    from core.sales_evidence import load_sales_revenue_by_product

    out: dict[str, float] = {}
    rev = load_sales_revenue_by_product()
    if rev.empty:
        return out
    for row in rev.itertuples():
        entry = find_seed_mapping(str(row.artikelbezeichnung))
        if not entry:
            continue
        out[entry.id] = out.get(entry.id, 0.0) + float(row.summe_umsatz)
    return out


def mapping_entry_by_id(mapping_id: str) -> ProductMappingEntry | None:
    for entry in load_mapping_entries():
        if entry.id == mapping_id:
            return entry
    return None
