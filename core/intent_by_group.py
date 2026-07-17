"""
Intent-Auswertung pro Business-Gruppe (ERP-Mapping).

Liest Freitext-Quellen, ordnet Cluster → mapping_id, zählt Intents pro Gruppe.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import pandas as pd

from core.intent_patterns import INTENT_LABELS, classify_intent
from core.intent_sources import iter_freetext_rows
from core.product_mapping import mapping_entry_by_id, resolve_cluster_mapping, revenue_by_mapping_group
from core.tera_scope import is_tera_hotline_cluster


def _dominant_intent(counter: Counter) -> str:
    if not counter:
        return "Sonstiges"
    intent, _ = counter.most_common(1)[0]
    return intent


def aggregate_intent_by_business_group(
    *,
    all_sources: bool = False,
    ticket_rows: list[dict[str, Any]] | None = None,
) -> pd.DataFrame:
    """
    Intent-Häufigkeiten pro ERP-Business-Gruppe (product_module_mapping.json).

    all_sources: HTML + CSV (Feldbesuche, Umfragen). Default nur HTML.
    """
    revenue = revenue_by_mapping_group()
    intent_counts: dict[str, Counter] = defaultdict(Counter)
    bedarf_counts: dict[str, Counter] = defaultdict(Counter)
    ticket_totals: Counter = Counter()

    if ticket_rows:
        for row in ticket_rows:
            cluster = str(row.get("cluster", "")).strip()
            mapping = resolve_cluster_mapping(cluster)
            if not mapping:
                continue
            gid = mapping.id
            weight = max(1, int(row.get("anzahl") or 1))
            intent = classify_intent(cluster, modul=cluster)
            intent_counts[gid][intent.intent] += weight
            if intent.bedarf:
                bedarf_counts[gid][intent.bedarf] += weight
            ticket_totals[gid] += weight
    else:
        for item in iter_freetext_rows(include_html=True, include_csv=all_sources):
            if is_tera_hotline_cluster(item.cluster):
                continue
            mapping = resolve_cluster_mapping(item.cluster)
            if not mapping:
                continue
            gid = mapping.id
            intent = classify_intent(item.freitext, modul=item.cluster)
            intent_counts[gid][intent.intent] += 1
            if intent.bedarf:
                bedarf_counts[gid][intent.bedarf] += 1
            ticket_totals[gid] += 1

    rows: list[dict[str, Any]] = []
    for gid, counter in intent_counts.items():
        entry = mapping_entry_by_id(gid)
        total = ticket_totals[gid] or sum(counter.values())
        row: dict[str, Any] = {
            "mapping_id": gid,
            "business_gruppe": entry.label if entry else gid,
            "ticket_anzahl": int(total),
            "summe_umsatz": round(revenue.get(gid, 0.0), 2),
            "dominant_intent": _dominant_intent(counter),
            "top_bedarf": bedarf_counts[gid].most_common(1)[0][0] if bedarf_counts.get(gid) else "",
        }
        for label in INTENT_LABELS:
            count = int(counter.get(label, 0))
            row[label] = count
            row[f"pct_{label}"] = round(100.0 * count / total, 1) if total else 0.0
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return df.sort_values(["summe_umsatz", "ticket_anzahl"], ascending=False).reset_index(drop=True)


def intent_by_group_records(*, all_sources: bool = False) -> list[dict[str, Any]]:
    df = aggregate_intent_by_business_group(all_sources=all_sources)
    if df.empty:
        return []
    return df.to_dict(orient="records")
