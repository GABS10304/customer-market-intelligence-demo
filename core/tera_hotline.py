"""TERA Hotline-Tickets (teraWinData) — Cluster → Basis-Produktcode."""

from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache
from typing import Any

import pandas as pd

from config import TERA_HOTLINE_MAPPING_PATH
from core.demo_scope import TERA_WIN_BEREICH
from core.intent_sources import iter_freetext_rows
from core.tera_products import normalize_tera_product_code


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _cluster_leaf(cluster: str) -> str:
    raw = (cluster or "").strip()
    leaf = raw.rsplit("\\", 1)[-1].strip()
    return leaf


@lru_cache(maxsize=1)
def _load_mapping_doc() -> dict[str, Any]:
    if not TERA_HOTLINE_MAPPING_PATH.exists():
        return {"cluster_to_tera_base": {}, "keyword_rules": []}
    return json.loads(TERA_HOTLINE_MAPPING_PATH.read_text(encoding="utf-8"))


def map_hotline_cluster_to_tera_base(cluster: str) -> tuple[str, str]:
    """
    Ordnet Hotline-Cluster einem TERA-Basiscode zu.
    Returns: (tera_base, match_reason)
    """
    leaf = _cluster_leaf(cluster)
    leaf_n = _norm(leaf)
    if not leaf_n:
        return "", "leer"

    exact = _load_mapping_doc().get("cluster_to_tera_base") or {}
    if leaf_n in exact:
        return str(exact[leaf_n]), f"Mapping «{leaf}»"

    for key, base in exact.items():
        if key in leaf_n or leaf_n in key:
            return str(base), f"Mapping ~«{key}»"

    for rule in _load_mapping_doc().get("keyword_rules") or []:
        needle = str(rule.get("contains") or "")
        if needle and needle in leaf_n:
            return str(rule.get("tera_base") or ""), f"Keyword «{needle}»"

    if leaf.upper().startswith("TERA"):
        base = normalize_tera_product_code(leaf)
        return base, "TERA-Code im Cluster"

    return "", f"Kein TERA-Mapping für «{leaf}»"


def collect_tera_hotline_tickets() -> Counter[str]:
    """Roh-Cluster-Häufigkeit nur für teraWinData."""
    counts: Counter[str] = Counter()
    prefix = f"{TERA_WIN_BEREICH}\\".lower()
    for row in iter_freetext_rows(include_html=True, include_csv=False):
        cluster = row.cluster or ""
        if not cluster.lower().startswith(prefix):
            continue
        counts[cluster] += 1
    return counts


@lru_cache(maxsize=1)
def tera_hotline_by_product() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for cluster, tickets in collect_tera_hotline_tickets().items():
        tera_base, reason = map_hotline_cluster_to_tera_base(cluster)
        rows.append(
            {
                "cluster": cluster,
                "cluster_leaf": _cluster_leaf(cluster),
                "tickets": int(tickets),
                "tera_base": tera_base,
                "match_reason": reason,
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=["cluster", "cluster_leaf", "tickets", "tera_base", "match_reason"]
        )
    detail = pd.DataFrame(rows)
    summary = (
        detail.groupby("tera_base", dropna=False)
        .agg(
            tickets=("tickets", "sum"),
            cluster=("cluster", "nunique"),
            beispiel_cluster=("cluster_leaf", "first"),
        )
        .reset_index()
        .sort_values("tickets", ascending=False)
    )
    return summary


@lru_cache(maxsize=1)
def tera_hotline_detail() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for cluster, tickets in collect_tera_hotline_tickets().items():
        tera_base, reason = map_hotline_cluster_to_tera_base(cluster)
        rows.append(
            {
                "cluster": cluster,
                "cluster_leaf": _cluster_leaf(cluster),
                "tickets": int(tickets),
                "tera_base": tera_base or "—",
                "match_reason": reason,
            }
        )
    return pd.DataFrame(rows).sort_values("tickets", ascending=False)


def clear_tera_hotline_cache() -> None:
    _load_mapping_doc.cache_clear()
    tera_hotline_by_product.cache_clear()
    tera_hotline_detail.cache_clear()
