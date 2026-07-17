"""TERA Pain Points — Themen nur aus teraWinData-Hotline (ohne RIWA/GIS-Mix)."""

from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache
from typing import Any

from core.intent_sources import iter_freetext_rows
from core.tera_hotline import tera_hotline_detail
from core.tera_scope import is_tera_hotline_cluster
from workspace.compare import THEME_KEYWORDS, themes_in_text

TERA_FOCUS_PATTERNS = (
    r"\b(tera|terawin|support[\s-]?druck)\b",
    r"\bTERA-[A-Z]{2,}\b",
)

TERA_PAIN_PATTERNS = (
    r"\b(pain[\s-]?point|schmerz|problem|hauptproblem|engpass|schwachstelle|bedürfnis)\b",
    r"\b(häufigste|top|haupt|wichtigste)\b.*\b(problem|themen|pain|bedürfnisse|pain[\s-]?point)\b",
)


def is_tera_focused_question(question: str) -> bool:
    """True wenn die Frage sich auf die TERA-Produktlinie bezieht."""
    lower = (question or "").lower()
    return any(re.search(p, lower) for p in TERA_FOCUS_PATTERNS)


def is_tera_pain_question(question: str) -> bool:
    """True wenn nach Pain Points / Hauptproblemen bei TERA gefragt wird."""
    if not is_tera_focused_question(question):
        return False
    lower = (question or "").lower()
    return any(re.search(p, lower) for p in TERA_PAIN_PATTERNS)


def _tera_freetext_samples(*, per_cluster: int = 2) -> dict[str, list[str]]:
    by_cluster: dict[str, list[str]] = defaultdict(list)
    for row in iter_freetext_rows(include_html=True, include_csv=False):
        cluster = row.cluster or ""
        if not is_tera_hotline_cluster(cluster):
            continue
        if len(by_cluster[cluster]) >= per_cluster:
            continue
        text = (row.freitext or "").strip()
        if text:
            by_cluster[cluster].append(text)
    return by_cluster


@lru_cache(maxsize=1)
def collect_tera_theme_scores() -> dict[str, dict[str, Any]]:
    """Themen-Scores nur aus teraWinData-Hotline-Clustern."""
    detail = tera_hotline_detail()
    scores: dict[str, dict[str, Any]] = {
        theme: {"score": 0, "clusters": [], "tera_bases": set()}
        for theme in THEME_KEYWORDS
    }
    if detail.empty:
        return scores

    samples = _tera_freetext_samples()

    for row in detail.itertuples():
        cluster = str(row.cluster)
        if not is_tera_hotline_cluster(cluster):
            continue
        count = int(row.tickets)
        matched = themes_in_text(cluster, from_cluster=True)
        if count >= 5 and not matched:
            for sample in samples.get(cluster, []):
                matched |= themes_in_text(sample, from_cluster=False)
        if not matched:
            continue

        tera_base = str(getattr(row, "tera_base", "") or "").strip()
        entry = f"{cluster} ({count}×)"
        for theme in matched:
            scores[theme]["score"] += count
            if entry not in scores[theme]["clusters"]:
                scores[theme]["clusters"].append(entry)
            if tera_base and tera_base != "—":
                scores[theme]["tera_bases"].add(tera_base)

    return scores


def clear_tera_pain_cache() -> None:
    collect_tera_theme_scores.cache_clear()


def _top_tera_clusters(*, top_n: int = 5) -> list[tuple[str, int, str]]:
    """Top-TERA-Cluster nach Ticket-Häufigkeit (nur teraWinData)."""
    detail = tera_hotline_detail()
    rows: list[tuple[str, int, str]] = []
    for row in detail.itertuples():
        cluster = str(row.cluster)
        if not is_tera_hotline_cluster(cluster):
            continue
        rows.append(
            (
                cluster,
                int(row.tickets),
                str(getattr(row, "tera_base", "") or "—"),
            )
        )
    rows.sort(key=lambda item: item[1], reverse=True)
    return rows[:top_n]


def format_tera_pain_markdown(*, top_n: int = 5, question: str = "") -> str:
    """Deterministischer Evidenzblock — Top-Pain-Points nur aus TERA-Hotline."""
    scores = collect_tera_theme_scores()
    ranked = sorted(
        [(theme, data) for theme, data in scores.items() if int(data.get("score") or 0) > 0],
        key=lambda item: int(item[1]["score"]),
        reverse=True,
    )

    lines = [
        "### TERA Pain Points (nur teraWinData)",
        "**Scope:** Nur Hotline-Cluster `teraWinData\\…` — **ohne** `riwaGisData`/`otsBauData` "
        "und **ohne** Umfrage-Quellen-Overlap.",
        "**Ranking:** Hotline-Ticket-Häufigkeit pro Thema (deterministisch, verbindlich).",
        "**Hinweis:** Themen-Scores sind nicht disjunkt — keine %-Anteil-Aussagen / Reduktionen schätzen.",
    ]

    if not ranked:
        clusters = _top_tera_clusters(top_n=top_n)
        if not clusters:
            lines.append("- (keine TERA-Hotline-Daten für Themen-Analyse)")
            return "\n".join(lines)
        lines.append("\n**Top-Cluster nach Hotline-Tickets (kein Themen-Match im Cluster-Namen):**")
        for index, (cluster, tickets, tera_base) in enumerate(clusters, start=1):
            lines.append(f"{index}. **{cluster}** — {tickets} Tickets (TERA-Basis: {tera_base})")
        return "\n".join(lines)

    show = ranked[:top_n]
    for index, (theme, data) in enumerate(show, start=1):
        cluster_hint = ", ".join(data["clusters"][:2]) or "—"
        bases = ", ".join(sorted(data["tera_bases"])[:4]) if data["tera_bases"] else "—"
        lines.append(
            f"{index}. **{theme}** — {int(data['score'])} Hotline-Tickets "
            f"(TERA-Basis: {bases}; z. B. {cluster_hint})"
        )

    if len(ranked) > top_n:
        lines.append(f"- … {len(ranked) - top_n} weitere TERA-Themen mit Signal")

    return "\n".join(lines)
