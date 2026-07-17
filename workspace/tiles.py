"""Dashboard-Kacheln — deterministisch aus BigQuery."""

from __future__ import annotations

from typing import Any

import pandas as pd

from core.bq_evidence import SOURCE_QUERIES, fetch_cluster_counts, load_rag_meta
from core.sales_evidence import SALES_TECHNICAL_NAME, sales_row_count
from core.time_display import format_berlin
from config import setup_gcp_credentials
from google.cloud import bigquery
from workspace.catalog import list_catalog_sources
from workspace.sources.profiles import BUILTIN_PROFILES, legacy_evidence_key


def _row_count(table: str) -> int:
    try:
        setup_gcp_credentials()
        client = bigquery.Client()
        return int(list(client.query(f"SELECT COUNT(*) AS n FROM `{table}`").result())[0].n)
    except Exception:
        return 0


def tile_top_needs(selected: list[str], limit: int = 5) -> pd.DataFrame:
    frames = []
    for name in selected:
        key = legacy_evidence_key(name)
        if key in SOURCE_QUERIES:
            df = fetch_cluster_counts(key, limit=limit)
            if not df.empty:
                profile = BUILTIN_PROFILES[name]
                df = df.copy()
                df["quelle"] = profile.display_name
                frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["quelle", "cluster", "anzahl"])
    return pd.concat(frames, ignore_index=True).sort_values("anzahl", ascending=False).head(limit)


def tile_hotline_frequency(selected: list[str]) -> pd.DataFrame:
    if "support_tickets_html" in selected:
        return fetch_cluster_counts("support", limit=10)
    return pd.DataFrame(columns=["quelle", "cluster", "anzahl"])


def tile_data_coverage() -> list[dict[str, Any]]:
    items = []
    for src in list_catalog_sources():
        if src.get("status") != "active":
            continue
        name = src["technical_name"]
        profile = BUILTIN_PROFILES.get(name)
        if name == SALES_TECHNICAL_NAME:
            rows = sales_row_count()
            backend = "CSV"
        else:
            rows = _row_count(profile.bq_table) if profile else 0
            backend = "BQ"
        items.append({
            "Quelle": src.get("display_name", name),
            "Status": src.get("status", "?"),
            "Zeilen": rows,
            "Backend": backend,
            "Mapping": src.get("mapping_status", "?"),
            "Aktualisiert": (src.get("last_updated") or "—")[:19],
        })
    rag = load_rag_meta()
    if rag:
        items.append({
            "Quelle": f"RAG-Index (V{rag.get('workspace_version', '2')})",
            "Status": "active",
            "Zeilen": rag.get("chunks", rag.get("documents", 0)),
            "Backend": "Chroma",
            "Mapping": rag.get("chunker", "index"),
            "Aktualisiert": format_berlin(rag.get("built_at")),
        })
    return items


def tile_strategic_opportunities(selected: list[str]) -> list[str]:
    """Deterministische Heuristiken — kein LLM."""
    hints: list[str] = []
    top = tile_top_needs(selected, limit=3)
    if top.empty:
        return ["Noch keine Evidenz in BigQuery — Pipeline oder Upload ausführen."]

    for row in top.itertuples():
        hints.append(
            f"**{row.cluster}** ({int(row.anzahl)}× in {row.quelle}): "
            "Kontextsensitive Hilfe / In-App-Guidance prüfen."
        )

    if len(selected) >= 2:
        hints.append(
            "Compare Mode: Quellen parallel wählen und wiederkehrende Cluster vergleichen."
        )
    return hints
