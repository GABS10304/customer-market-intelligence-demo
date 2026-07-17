"""Schema-Erkennung und Spalten-Mapping — deterministisch, kein LLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from workspace.sources.profiles import BUILTIN_PROFILES, SourceProfile


@dataclass
class DetectionResult:
    suggested_profile: str
    confidence: float
    columns: list[str]
    row_count: int
    mapping: dict[str, str | None]
    summary: str
    alternatives: list[tuple[str, float]]


def _norm(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_").replace("/", "_")


def _find_column(columns: list[str], hints: tuple[str, ...]) -> str | None:
    normalized = {_norm(c): c for c in columns}
    for hint in hints:
        if hint in columns:
            return hint
        nh = _norm(hint)
        if nh in normalized:
            return normalized[nh]
    for col in columns:
        nc = _norm(col)
        for hint in hints:
            if _norm(hint) in nc or nc in _norm(hint):
                return col
    return None


def _score_profile(profile: SourceProfile, columns: list[str], filename: str) -> float:
    score = 0.0
    fname = filename.lower()
    for kw in profile.detection_keywords:
        if kw in fname:
            score += 2.0
    if _find_column(columns, profile.text_column_hints):
        score += 3.0
    if _find_column(columns, profile.cluster_column_hints):
        score += 2.5
    if _find_column(columns, profile.customer_column_hints):
        score += 0.5
    for col in columns:
        nc = _norm(col)
        for kw in profile.detection_keywords:
            if kw in nc:
                score += 0.5
    return score


def build_mapping(profile: SourceProfile, columns: list[str]) -> dict[str, str | None]:
    return {
        "text": _find_column(columns, profile.text_column_hints),
        "cluster": _find_column(columns, profile.cluster_column_hints),
        "customer": _find_column(columns, profile.customer_column_hints),
    }


def detect_source(df: pd.DataFrame, filename: str = "upload.csv") -> DetectionResult:
    """Schätzt Source Profile anhand von Spalten und Dateiname."""
    columns = [str(c) for c in df.columns]
    scores: list[tuple[str, float]] = []

    for name, profile in BUILTIN_PROFILES.items():
        scores.append((name, _score_profile(profile, columns, filename)))

    scores.sort(key=lambda x: x[1], reverse=True)
    best_name, best_score = scores[0]
    second_score = scores[1][1] if len(scores) > 1 else 0.0
    confidence = min(0.95, 0.35 + best_score * 0.08 + max(0, best_score - second_score) * 0.05)

    profile = BUILTIN_PROFILES[best_name]
    mapping = build_mapping(profile, columns)
    missing = [k for k, v in mapping.items() if k in ("text", "cluster") and not v]

    summary_parts = [
        f"Datei: **{filename}**",
        f"Zeilen: **{len(df)}**",
        f"Spalten ({len(columns)}): `{', '.join(columns[:8])}{'…' if len(columns) > 8 else ''}`",
        f"Vermutete Quelle: **{profile.display_name}** (`{best_name}`)",
        f"Confidence: **{confidence:.0%}**",
    ]
    if mapping.get("text"):
        summary_parts.append(f"Freitext-Spalte: `{mapping['text']}`")
    if mapping.get("cluster"):
        summary_parts.append(f"Cluster-Spalte: `{mapping['cluster']}`")
    if missing:
        summary_parts.append(f"⚠️ Unklares Mapping für: {', '.join(missing)}")

    return DetectionResult(
        suggested_profile=best_name,
        confidence=confidence,
        columns=columns,
        row_count=len(df),
        mapping=mapping,
        summary="\n".join(summary_parts),
        alternatives=scores[1:4],
    )


def mapping_status(mapping: dict[str, str | None]) -> str:
    if mapping.get("text") and mapping.get("cluster"):
        return "confirmed"
    if mapping.get("text"):
        return "partial"
    return "unclear"
