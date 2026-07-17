"""
BigQuery-Schreibfunktionen für Decision Layer.
Trennung: Data Layer (keine UI, keine Entscheidungslogik).
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone

import pandas as pd
from google.cloud import bigquery

from config import BQ_DATASET, BQ_PROJECT, GCP_KEY_PATH, setup_gcp_credentials

PROJECT = BQ_PROJECT
DATASET = BQ_DATASET
DECISION_TABLE = f"{PROJECT}.{DATASET}.decision_results"
CAPABILITY_TABLE = f"{PROJECT}.{DATASET}.capability_results"


def _client() -> bigquery.Client:
    setup_gcp_credentials()
    if GCP_KEY_PATH.exists():
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(GCP_KEY_PATH))
    return bigquery.Client()


def _parse_frequency_from_text(text: str) -> int:
    match = re.search(r"(\d+)\s+Vorkommen", text or "")
    return int(match.group(1)) if match else 0


def _derive_initiative_name(input_text: str, initiative_name: str | None) -> str:
    if initiative_name:
        return initiative_name[:200]
    text = (input_text or "").strip()
    return text[:80] if text else "unbenannt"


def _derive_problem_cluster(input_text: str, problem_cluster: str | None) -> str:
    if problem_cluster:
        return problem_cluster[:200]
    text = (input_text or "").strip()
    for prefix in ("Modul:", "Problem_Kategorie:", "Kategorie:"):
        if prefix in text:
            part = text.split(prefix, 1)[1].strip()
            cluster = part.split("(", 1)[0].strip()
            if cluster:
                return cluster[:200]
    return text[:120] if text else "unknown"


def _derive_priority_score(confidence: float, frequency: int) -> float:
    score = confidence * 100
    if frequency >= 50:
        score += 30
    elif frequency >= 15:
        score += 15
    elif frequency > 0:
        score += 5
    return round(min(100.0, score), 2)


def _derive_signal_quality(confidence: float, frequency: int) -> str:
    if confidence >= 0.75 and frequency >= 15:
        return "high"
    if confidence >= 0.5 and frequency > 0:
        return "medium"
    if confidence >= 0.5 or frequency > 0:
        return "low"
    return "insufficient"


def write_decision_to_bq(
    recommendation: str,
    reason: str,
    risk: str,
    confidence: float,
    source: str = "decision_hub",
    input_text: str = "",
    initiative_id: str | None = None,
    initiative_name: str | None = None,
    problem_cluster: str | None = None,
    decision_type: str | None = None,
    priority_score: float | None = None,
    signal_quality: str | None = None,
    frequency: int | None = None,
) -> dict:
    """
    Speichert ein Entscheidungsergebnis in decision_results.

    Returns:
        {"success": bool, "id": str, "error": str | None}
    """
    record_id = initiative_id or str(uuid.uuid4())
    text = (input_text or "").strip()
    freq = frequency if frequency is not None else _parse_frequency_from_text(text)

    row = {
        "id": record_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "input_text": text[:4000],
        "recommendation": recommendation,
        "reason": reason,
        "risk": risk,
        "confidence": float(confidence),
        "initiative_name": _derive_initiative_name(text, initiative_name),
        "problem_cluster": _derive_problem_cluster(text, problem_cluster),
        "decision_type": decision_type or recommendation,
        "priority_score": priority_score if priority_score is not None else _derive_priority_score(confidence, freq),
        "signal_quality": signal_quality or _derive_signal_quality(confidence, freq),
    }

    try:
        client = _client()
        errors = client.insert_rows_json(DECISION_TABLE, [row])
        if errors:
            return {"success": False, "id": record_id, "error": str(errors)}
        return {"success": True, "id": record_id, "error": None}
    except Exception as exc:
        return {"success": False, "id": record_id, "error": str(exc)}


def write_capability_to_bq(
    capabilities: list[dict],
    source: str = "decision_hub",
    input_text: str = "",
    initiative_id: str | None = None,
) -> dict:
    """
    Speichert Capability-Erkennungsergebnisse in capability_results.

    Returns:
        {"success": bool, "count": int, "error": str | None}
    """
    if not capabilities:
        return {"success": True, "count": 0, "error": None}

    parent_id = initiative_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    rows = []

    for cap in capabilities:
        rows.append({
            "id": str(uuid.uuid4()),
            "initiative_id": parent_id,
            "created_at": now,
            "source": source,
            "input_text": (input_text or "")[:4000],
            "capability_type": cap.get("capability", "unknown"),
            "detected": bool(cap.get("detected", False)),
            "signals": ", ".join(cap.get("signals", [])),
            "confidence": float(cap.get("confidence", 0.0)),
        })

    try:
        client = _client()
        errors = client.insert_rows_json(CAPABILITY_TABLE, rows)
        if errors:
            return {"success": False, "count": 0, "error": str(errors)}
        return {"success": True, "count": len(rows), "error": None}
    except Exception as exc:
        return {"success": False, "count": 0, "error": str(exc)}


def load_recent_decisions(limit: int = 20) -> pd.DataFrame:
    """Liest letzte Entscheidungen aus BigQuery (für Dashboard)."""
    query = f"""
        SELECT
            id,
            created_at,
            source,
            initiative_name,
            problem_cluster,
            recommendation,
            decision_type,
            reason,
            risk,
            confidence,
            priority_score,
            signal_quality,
            input_text
        FROM `{DECISION_TABLE}`
        ORDER BY created_at DESC
        LIMIT {int(limit)}
    """
    try:
        client = _client()
        return client.query(query).to_dataframe()
    except Exception:
        return pd.DataFrame()
