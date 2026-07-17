"""
BigQuery Evidence Layer — gemeinsame Lese-Logik für Dashboard und RAG.
Single Source of Truth: BigQuery, nicht Markdown-Reports.
"""

from __future__ import annotations

import json
from typing import Literal

import pandas as pd
from google.cloud import bigquery
from langchain_core.documents import Document

from config import (
    BIGQUERY_FIELD_VISITS_TABLE,
    BIGQUERY_HTML_TABLE,
    BIGQUERY_TABLE,
    DATA_DIR,
    RAG_INDEX_DIR,
    RAG_META_PATH,
    setup_gcp_credentials,
)
from core.governance import scrub_pii
from core.source_dedup import adjust_survey_cluster_df

SourceKey = Literal["support", "surveys", "field_visits", "both"]

SOURCE_QUERIES: dict[str, dict[str, str]] = {
    "support": {
        "table": BIGQUERY_HTML_TABLE,
        "cluster_col": "Ordner___Modul",
        "label": "Support-Tickets",
    },
    "surveys": {
        "table": BIGQUERY_TABLE,
        "cluster_col": "Kategorie",
        "label": "Kundenumfragen",
    },
    "field_visits": {
        "table": BIGQUERY_FIELD_VISITS_TABLE,
        "cluster_col": "Modul_App_Verfahren",
        "label": "Weihnachtsbesuche",
    },
}

TEXT_COLUMNS = (
    "Original_Wortlaut_Freitext",
    "Original_Wortlaut__Freitext",
    "Original_Wortlaut_Freitext_",
    "Verbesserungsvorschlag___Kritik",
)


def _client() -> bigquery.Client:
    setup_gcp_credentials()
    return bigquery.Client()


def _pick_text_column(columns: list[str]) -> str | None:
    for candidate in TEXT_COLUMNS:
        if candidate in columns:
            return candidate
    for col in columns:
        lower = col.lower()
        if "freitext" in lower or "wortlaut" in lower:
            return col
    return None


def _query_df(client: bigquery.Client, query: str) -> pd.DataFrame:
    """BigQuery → DataFrame ohne db-dtypes Abhängigkeit."""
    job = client.query(query)
    rows = [dict(row) for row in job.result()]
    return pd.DataFrame(rows)


def _source_keys(source: SourceKey) -> list[str]:
    if source == "both":
        return list(SOURCE_QUERIES.keys())
    return [source]


def fetch_cluster_counts(source: SourceKey, limit: int = 15) -> pd.DataFrame:
    """Top-Cluster mit Häufigkeit aus BigQuery."""
    sources = _source_keys(source)
    frames: list[pd.DataFrame] = []

    client = _client()
    for key in sources:
        cfg = SOURCE_QUERIES[key]
        query = f"""
            SELECT
                '{cfg["label"]}' AS quelle,
                `{cfg['cluster_col']}` AS cluster,
                COUNT(*) AS anzahl
            FROM `{cfg['table']}`
            WHERE `{cfg['cluster_col']}` IS NOT NULL
            GROUP BY `{cfg['cluster_col']}`
            ORDER BY anzahl DESC
            LIMIT {int(limit)}
        """
        try:
            df = _query_df(client, query)
            if not df.empty:
                if key == "surveys":
                    df = adjust_survey_cluster_df(df)
                if not df.empty:
                    frames.append(df)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame(columns=["quelle", "cluster", "anzahl"])

    combined = pd.concat(frames, ignore_index=True)
    return combined.sort_values("anzahl", ascending=False).head(limit)


def fetch_sample_texts(
    source: SourceKey,
    cluster: str,
    cluster_col: str | None = None,
    table: str | None = None,
    limit: int = 3,
) -> list[str]:
    """Beispiel-Freitexte für einen Cluster."""
    if source == "both":
        return []

    cfg = SOURCE_QUERIES[source]
    table = table or cfg["table"]
    cluster_col = cluster_col or cfg["cluster_col"]

    client = _client()
    schema_query = f"SELECT * FROM `{table}` LIMIT 1"
    try:
        sample = _query_df(client, schema_query)
    except Exception:
        return []

    text_col = _pick_text_column(list(sample.columns))
    if not text_col:
        return []

    safe_cluster = cluster.replace("\\", "\\\\").replace("'", "\\'")
    query = f"""
        SELECT `{text_col}` AS text
        FROM `{table}`
        WHERE `{cluster_col}` = '{safe_cluster}'
          AND `{text_col}` IS NOT NULL
          AND TRIM(CAST(`{text_col}` AS STRING)) != ''
        LIMIT {int(limit)}
    """
    try:
        rows = _query_df(client, query)
        return [scrub_pii(str(row["text"])) for _, row in rows.iterrows()]
    except Exception:
        return []


def _key_from_quelle(quelle: str) -> SourceKey:
    q = quelle.lower()
    if "support" in q or "ticket" in q:
        return "support"
    if "weihnacht" in q or "besuch" in q or "feld" in q:
        return "field_visits"
    return "surveys"


def build_evidence_context(source: SourceKey, top_n: int = 5, samples_per_cluster: int = 3) -> str:
    """
    Erzeugt strukturierten Kontext-Text für Q&A (aus BigQuery, live).
    """
    counts = fetch_cluster_counts(source, limit=max(top_n, 10))
    if counts.empty:
        return f"(Keine Daten in BigQuery für Quelle: {source})"

    lines = [
        f"Datenquelle: {SOURCE_QUERIES[source]['label'] if source in SOURCE_QUERIES else source}",
        f"Stand: live aus BigQuery",
        "",
        "TOP CLUSTER (Häufigkeit):",
    ]

    seen = 0
    for row in counts.itertuples():
        if seen >= top_n:
            break
        cluster = str(row.cluster)
        quelle = getattr(row, "quelle", "")
        prefix = f"[{quelle}] " if source == "both" and quelle else ""
        lines.append(f"- {prefix}{cluster}: {int(row.anzahl)} Vorkommen")
        seen += 1

    lines.append("")
    lines.append("BEISPIEL-ZITATE (aus Rohdaten):")

    seen = 0
    for row in counts.itertuples():
        if seen >= top_n:
            break
        cluster = str(row.cluster)
        src_key: SourceKey = source if source != "both" else _key_from_quelle(str(getattr(row, "quelle", "")))
        if source == "both":
            cfg = SOURCE_QUERIES[src_key]
            samples = fetch_sample_texts(src_key, cluster, cfg["cluster_col"], cfg["table"], samples_per_cluster)
        else:
            samples = fetch_sample_texts(source, cluster, limit=samples_per_cluster)

        if samples:
            lines.append(f"\n### {cluster}")
            for i, sample in enumerate(samples, 1):
                lines.append(f"{i}. {sample[:500]}")

        seen += 1

    return "\n".join(lines)


def fetch_feedback_documents(
    source: SourceKey = "both",
    limit_per_table: int = 800,
) -> list[Document]:
    """Lädt Feedback-Zeilen aus BigQuery als LangChain Documents."""
    sources = _source_keys(source)
    documents: list[Document] = []
    client = _client()

    for key in sources:
        cfg = SOURCE_QUERIES[key]
        try:
            preview = _query_df(client, f"SELECT * FROM `{cfg['table']}` LIMIT 1")
        except Exception:
            continue

        text_col = _pick_text_column(list(preview.columns))
        if not text_col:
            continue

        cluster_col = cfg["cluster_col"]
        query = f"""
            SELECT `{cluster_col}` AS cluster, `{text_col}` AS text
            FROM `{cfg['table']}`
            WHERE `{text_col}` IS NOT NULL
              AND TRIM(CAST(`{text_col}` AS STRING)) != ''
            LIMIT {int(limit_per_table)}
        """
        try:
            df = _query_df(client, query)
        except Exception:
            continue

        for idx, row in df.iterrows():
            text = scrub_pii(str(row["text"]).strip())
            if len(text) < 10:
                continue
            cluster = str(row.get("cluster", "unknown"))
            page = f"[{cfg['label']} | {cluster}] {text}"
            documents.append(
                Document(
                    page_content=page,
                    metadata={
                        "source": key,
                        "cluster": cluster,
                        "row": str(idx),
                    },
                )
            )

    return documents


def load_rag_meta() -> dict:
    if not RAG_META_PATH.exists():
        return {}
    try:
        return json.loads(RAG_META_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_rag_meta(meta: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAG_META_PATH.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
