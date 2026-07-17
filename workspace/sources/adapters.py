"""
Source Adapter — kanonisches Mapping pro Quelle (Normalization Layer).
Jede Quelle mappt auf: cluster, text, customer (+ Metadaten).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from workspace.sources.detector import build_mapping
from workspace.sources.profiles import SourceProfile, get_profile

CANONICAL_FIELDS = ("cluster", "text", "customer", "source_id", "source_file")


def resolve_mapping(profile: SourceProfile, columns: list[str]) -> dict[str, str | None]:
    return build_mapping(profile, columns)


def normalize_row(
    profile: SourceProfile,
    row: pd.Series,
    mapping: dict[str, str | None],
    *,
    source_file: str = "",
) -> dict[str, Any] | None:
    """Eine Rohzeile → kanonisches Dict. None wenn kein Text."""
    text_col = mapping.get("text")
    if not text_col or text_col not in row.index:
        return None
    text = str(row.get(text_col, "")).strip()
    if not text or text.lower() in ("nan", "none"):
        return None

    cluster_col = mapping.get("cluster")
    cluster = str(row.get(cluster_col, "unknown")).strip() if cluster_col else "unknown"
    customer_col = mapping.get("customer")
    customer = str(row.get(customer_col, "")).strip() if customer_col else ""

    return {
        "cluster": cluster,
        "text": text,
        "customer": customer,
        "source_id": profile.technical_name,
        "source_file": source_file,
    }


def preview_normalized(
    df: pd.DataFrame,
    profile_name: str,
    mapping: dict[str, str | None] | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    profile = get_profile(profile_name)
    if profile is None:
        return []
    mapping = mapping or resolve_mapping(profile, list(df.columns))
    rows: list[dict[str, Any]] = []
    for _, row in df.head(limit).iterrows():
        normalized = normalize_row(profile, row, mapping)
        if normalized:
            rows.append(normalized)
    return rows
