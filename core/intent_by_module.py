"""
Intent-Auswertung pro Modul — alle Quellen (HTML, Feldbesuche, Umfragen).

Gruppiert nach normalisiertem Modul (product_module_mapping.json).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import pandas as pd

from core.intent_patterns import INTENT_LABELS, classify_intent
from core.intent_sources import iter_freetext_rows
from core.product_mapping import module_display_name, resolve_cluster_mapping, revenue_by_mapping_group
from core.tera_scope import is_tera_hotline_cluster


def aggregate_intent_by_module(*, min_count: int = 1) -> pd.DataFrame:
    """
    Intent + Bedarf pro Modul über HTML und CSV-Quellen.

    Modul = Mapping-Label (z. B. «Modul Verkehr») oder Cluster-Leaf.
    """
    stats: dict[str, dict[str, Any]] = {}

    for row in iter_freetext_rows():
        cluster = row.cluster
        if not cluster:
            continue
        if is_tera_hotline_cluster(cluster):
            continue

        mapping = resolve_cluster_mapping(cluster)
        module_key = mapping.id if mapping else module_display_name(cluster)
        module_label = mapping.label if mapping else module_display_name(cluster)

        intent = classify_intent(row.freitext, modul=cluster)
        bucket = stats.setdefault(
            module_key,
            {
                "modul_key": module_key,
                "modul": module_label,
                "mapping_id": mapping.id if mapping else "",
                "intent_counts": Counter(),
                "bedarf_counts": Counter(),
                "geltung_counts": Counter(),
                "quellen": Counter(),
                "beispiele": [],
                "total": 0,
            },
        )
        bucket["intent_counts"][intent.intent] += 1
        bucket["quellen"][row.quelle] += 1
        bucket["total"] += 1
        if intent.bedarf:
            bucket["bedarf_counts"][intent.bedarf] += 1
        if intent.geltung:
            bucket["geltung_counts"][intent.geltung] += 1
        if len(bucket["beispiele"]) < 3:
            bucket["beispiele"].append(row.freitext[:200])

    revenue = revenue_by_mapping_group()
    rows: list[dict[str, Any]] = []

    for key, data in stats.items():
        if data["total"] < min_count:
            continue
        total = data["total"]
        intents: Counter = data["intent_counts"]
        bedarf: Counter = data["bedarf_counts"]
        geltung: Counter = data["geltung_counts"]
        dominant = intents.most_common(1)[0][0] if intents else "Sonstiges"
        umsatz = revenue.get(key, 0.0)
        if not umsatz and data["mapping_id"]:
            umsatz = revenue.get(data["mapping_id"], 0.0)

        rec: dict[str, Any] = {
            "modul_key": key,
            "modul": data["modul"],
            "mapping_id": data["mapping_id"],
            "summe_umsatz": round(float(umsatz), 2),
            "eintraege": int(total),
            "dominant_intent": dominant,
            "top_bedarf": bedarf.most_common(1)[0][0] if bedarf else "",
            "top_geltung": geltung.most_common(1)[0][0] if geltung else "",
            "quellen": ", ".join(f"{q} ({n})" for q, n in data["quellen"].most_common(4)),
        }
        for label in INTENT_LABELS:
            count = int(intents.get(label, 0))
            rec[label] = count
            rec[f"pct_{label}"] = round(100.0 * count / total, 1) if total else 0.0
        for tag, count in bedarf.items():
            rec[f"bedarf_{tag}"] = int(count)
        rows.append(rec)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return df.sort_values(["eintraege", "summe_umsatz"], ascending=False).reset_index(drop=True)


def intent_by_module_records() -> list[dict[str, Any]]:
    df = aggregate_intent_by_module()
    if df.empty:
        return []
    return df.to_dict(orient="records")


def module_detail(module_key: str) -> pd.DataFrame:
    """Einzelzeilen für ein Modul (Drill-down)."""
    rows: list[dict[str, str]] = []
    for row in iter_freetext_rows():
        mapping = resolve_cluster_mapping(row.cluster)
        key = mapping.id if mapping else module_display_name(row.cluster)
        if key != module_key:
            continue
        intent = classify_intent(row.freitext, modul=row.cluster)
        rows.append(
            {
                "quelle": row.quelle,
                "cluster": row.cluster,
                "intent": intent.intent,
                "bedarf": intent.bedarf,
                "freitext": row.freitext[:300],
            }
        )
    return pd.DataFrame(rows)
