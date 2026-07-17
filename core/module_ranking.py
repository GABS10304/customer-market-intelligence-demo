"""
Modul-Ranking (Kunden/Reach pro Modul) → mapping_id.

Daten: data/module_ranking.csv
Mapping: product_module_mapping.json (ranking_aliases) + data/module_ranking_to_mapping.json
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from config import DATA_DIR, DELIMITER
from core.product_mapping import find_seed_mapping, load_mapping_entries, mapping_entry_by_id

RANKING_CSV = DATA_DIR / "module_ranking.csv"
RANKING_MAP_PATH = DATA_DIR / "module_ranking_to_mapping.json"
RANKING_ENRICHED_CSV = DATA_DIR / "module_ranking_enriched.csv"


def _norm_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _slug(text: str) -> str:
    s = _norm_key(text)
    s = re.sub(r"^modul\s+", "", s)
    s = re.sub(r"[^a-z0-9äöüß]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_") or "unbekannt"


@dataclass(frozen=True)
class RankingMatch:
    mapping_id: str
    mapping_label: str
    match_kind: str  # exact | alias | seed | label | manual | fallback


@lru_cache(maxsize=1)
def _load_ranking_map_raw() -> dict[str, Any]:
    if not RANKING_MAP_PATH.exists():
        return {}
    try:
        return json.loads(RANKING_MAP_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=1)
def _manual_exact_map() -> dict[str, str]:
    raw = _load_ranking_map_raw()
    out: dict[str, str] = {}
    for key, val in (raw.get("exact") or {}).items():
        if key and val:
            out[_norm_key(key)] = str(val)
    return out


@lru_cache(maxsize=1)
def _ranking_alias_lookup() -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in load_mapping_entries():
        out[_norm_key(entry.label)] = entry.id
        for alias in entry.ranking_aliases:
            out[_norm_key(alias)] = entry.id
    return out


def resolve_ranking_modul(modulname: str) -> RankingMatch:
    """Ordnet Modulranking-Modulname einer mapping_id zu."""
    name = (modulname or "").strip()
    key = _norm_key(name)
    if not key:
        return RankingMatch("ranking_unbekannt", "Unbekannt", "fallback")

    manual = _manual_exact_map()
    if key in manual:
        entry = mapping_entry_by_id(manual[key])
        label = entry.label if entry else name
        return RankingMatch(manual[key], label, "manual")

    aliases = _ranking_alias_lookup()
    if key in aliases:
        entry = mapping_entry_by_id(aliases[key])
        label = entry.label if entry else name
        return RankingMatch(aliases[key], label, "alias")

    seed = find_seed_mapping(name)
    if seed:
        return RankingMatch(seed.id, seed.label, "seed")

    name_compact = re.sub(r"[^a-z0-9äöüß]+", "", key)
    best: ProductMappingEntry | None = None
    best_len = 0
    for entry in load_mapping_entries():
        label_key = _norm_key(entry.label)
        label_compact = re.sub(r"[^a-z0-9äöüß]+", "", label_key)
        if label_compact and label_compact in name_compact and len(label_compact) > best_len:
            best = entry
            best_len = len(label_compact)
    if best:
        return RankingMatch(best.id, best.label, "label")

    fallback_id = f"ranking_{_slug(name)}"
    return RankingMatch(fallback_id, name, "fallback")


def load_module_ranking() -> pd.DataFrame:
    if not RANKING_CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(RANKING_CSV, sep=DELIMITER, encoding="utf-8-sig")


def enrich_module_ranking(df: pd.DataFrame | None = None) -> pd.DataFrame:
    work = df if df is not None else load_module_ranking()
    if work.empty:
        return work

    matches = [resolve_ranking_modul(str(n)) for n in work["Modulname"]]
    out = work.copy()
    out["mapping_id"] = [m.mapping_id for m in matches]
    out["mapping_label"] = [m.mapping_label for m in matches]
    out["match_kind"] = [m.match_kind for m in matches]
    return out


def aggregate_ranking_by_mapping(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Summiert Kunden/Umsatz pro mapping_id (dedupe Varianten im Ranking)."""
    enriched = enrich_module_ranking(df)
    if enriched.empty:
        return enriched

    agg = (
        enriched.groupby(["mapping_id", "mapping_label"], dropna=False)
        .agg(
            ranking_zeilen=("Modulname", "count"),
            kunden=("Kunden", "sum"),
            umsatz_eur=("umsatz_eur", "sum"),
            finaler_score=("finaler_score", "sum"),
            abc_ranking=("abc_ranking", lambda s: s.mode().iloc[0] if len(s) else ""),
            match_kinds=("match_kind", lambda s: ",".join(sorted(set(s)))),
        )
        .reset_index()
        .sort_values(["kunden", "umsatz_eur"], ascending=False)
    )
    return agg


def write_enriched_ranking() -> Path:
    enriched = enrich_module_ranking()
    enriched.to_csv(RANKING_ENRICHED_CSV, sep=DELIMITER, index=False, encoding="utf-8-sig")
    return RANKING_ENRICHED_CSV


def mapping_coverage_report(df: pd.DataFrame | None = None) -> dict[str, Any]:
    enriched = enrich_module_ranking(df)
    if enriched.empty:
        return {"rows": 0, "matched": 0, "fallback": 0}
    kinds = enriched["match_kind"].value_counts().to_dict()
    fallback_rows = enriched[enriched["match_kind"] == "fallback"]
    return {
        "rows": len(enriched),
        "kinds": kinds,
        "fallback_count": int(len(fallback_rows)),
        "fallback_modules": fallback_rows["Modulname"].drop_duplicates().tolist(),
        "mapped_kunden_pct": round(
            100.0
            * enriched.loc[enriched["match_kind"] != "fallback", "Kunden"].sum()
            / max(enriched["Kunden"].sum(), 1),
            1,
        ),
    }
