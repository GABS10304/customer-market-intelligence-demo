"""
Quellen-Vergleich — themenbasiert (deterministisch, kein LLM).

Brückt unterschiedliche Cluster-Namen (Modul-Pfade vs. Kategorien)
über gemeinsame Themen: Export, Login, Import, Verbindung, Installation.
"""

from __future__ import annotations

import re
from typing import Callable

import pandas as pd

from core.bq_evidence import SOURCE_QUERIES, fetch_cluster_counts, fetch_sample_texts
from workspace.sources.profiles import BUILTIN_PROFILES, legacy_evidence_key, source_short_label

THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Export": (
        "export", "csv", "excel", "pdf", "ausgabe", "download", "druck",
        "exportier", "ausspiel", "datei export",
    ),
    "Login": (
        "login", "anmeld", "benutzer", "nutzer", "account", "passwort",
        "single-user", "anmelden", "auth",
    ),
    "Import": (
        "import", "importier", "hochlad", "upload", "einlesen",
        "datenübertrag", "daten import", "anhang",
    ),
    "Verbindung": (
        "verbindung", "verbindungsfehler", "keine verbindung",
        "netzwerk", "offline", "sync", "synchron", "server", "internet",
    ),
    "Installation": (
        "installation", "installieren", "installiert", "installer",
        "neuinstallation", "deinstallation", "setup", "einrichten",
    ),
}

# Kurze/teils generische Keywords nur mit Wortgrenze (vermeidet z. B. „beschreibung“ → schreib)
_BOUNDARY_KEYWORDS = frozenset({
    "user", "sync", "csv", "pdf", "auth", "setup",
})

# Umfrage-Kategorien → wahrscheinliche Themen (nur Umfragen, nicht Ticket-Pfade)
SURVEY_CATEGORY_THEMES: dict[str, tuple[str, ...]] = {
    "Usability": ("Login", "Export", "Import"),
    "Feature Request": ("Export", "Import"),
    "Bug/Performance": ("Verbindung",),
    "Service/Schulung": ("Login",),
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _keyword_in_text(text: str, keyword: str) -> bool:
    kw = keyword.lower()
    if len(kw) <= 4 or kw in _BOUNDARY_KEYWORDS:
        return bool(re.search(rf"(?<![a-zäöüß0-9]){re.escape(kw)}", text))
    return kw in text


def _support_cluster_label(cluster: str) -> str:
    """Leaf-Segment aus Modul-Pfad — vermeidet Treffer auf „RGZ Client“ in jedem Pfad."""
    part = cluster.rsplit("\\", 1)[-1].strip()
    if " - " in part:
        return part.split(" - ", 1)[1].strip()
    return part


def themes_in_text(text: str, *, from_cluster: bool = False) -> set[str]:
    """Welche Themen kommen in einem Text/Cluster-Namen vor?"""
    if from_cluster:
        text = _support_cluster_label(text)
    lower = _normalize(text)
    if not lower:
        return set()
    matched: set[str] = set()
    for theme, keywords in THEME_KEYWORDS.items():
        if any(_keyword_in_text(lower, kw) for kw in keywords):
            matched.add(theme)
    return matched


def _survey_category_themes(category: str) -> set[str]:
    cat = (category or "").strip()
    for key, themes in SURVEY_CATEGORY_THEMES.items():
        if key.lower() in cat.lower():
            return set(themes)
    return set()


def _collect_theme_scores(
    source_key: str,
    technical_name: str,
    top_clusters: int = 20,
    *,
    cluster_df: pd.DataFrame | None = None,
    sample_fn: Callable[[str, str, int], list[str]] | None = None,
) -> dict[str, dict]:
    """
    Pro Thema: gewichtete Treffer, Beispiel-Cluster, Stichprobe.
    Returns: {theme: {score, clusters: [...], samples: [...]}}
    """
    df = cluster_df if cluster_df is not None else fetch_cluster_counts(source_key, limit=top_clusters)
    if df.empty:
        return {}

    get_samples = sample_fn or (
        lambda sk, cluster, limit: fetch_sample_texts(sk, cluster, limit=limit)
    )

    label = BUILTIN_PROFILES.get(technical_name)
    display = label.display_name if label else source_key

    scores: dict[str, dict] = {
        t: {"score": 0, "clusters": [], "samples": [], "quelle": display}
        for t in THEME_KEYWORDS
    }

    for row in df.itertuples():
        cluster = str(row.cluster)
        count = int(row.anzahl)
        from_cluster = source_key == "support"
        themes = themes_in_text(cluster, from_cluster=from_cluster)

        if source_key == "surveys":
            themes |= _survey_category_themes(cluster)
        elif source_key == "field_visits":
            pass

        # Freitext wenn Modul-Pfad kein Thema liefert (Keywords sind streng, kein RGZ/Client-Noise)
        if count >= 5 and not themes:
            samples = get_samples(source_key, cluster, 2)
            for sample in samples:
                themes |= themes_in_text(sample, from_cluster=False)
            if samples and themes:
                for theme in themes:
                    if sample := samples[0][:120]:
                        if sample not in scores[theme]["samples"]:
                            scores[theme]["samples"].append(sample)

        for theme in themes:
            scores[theme]["score"] += count
            entry = f"{cluster} ({count}×)"
            if entry not in scores[theme]["clusters"]:
                scores[theme]["clusters"].append(entry)

    return scores


def compare_themes_from_scores(per_source: dict[str, dict[str, dict]]) -> pd.DataFrame:
    """Themen-Matrix aus vorberechneten Quellen-Scores (kein BigQuery)."""
    if not per_source:
        return pd.DataFrame()

    rows = []
    for theme in THEME_KEYWORDS:
        row: dict = {"Thema": theme}
        scores_by_src = {}
        for name, theme_data in per_source.items():
            short = source_short_label(name)
            score = theme_data.get(theme, {}).get("score", 0)
            scores_by_src[name] = score
            row[f"{short} (Score)"] = score
            clusters = theme_data.get(theme, {}).get("clusters", [])[:2]
            row[f"{short} (Cluster)"] = "; ".join(clusters) if clusters else "—"

        active = [n for n, s in scores_by_src.items() if s > 0]
        total = sum(scores_by_src.values())
        row["Overlap"] = "✅" if len(active) >= 2 else ("—" if not active else "nur 1 Quelle")
        row["Gesamt_Score"] = total
        rows.append(row)

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values("Gesamt_Score", ascending=False).reset_index(drop=True)


def compare_themes(selected: list[str]) -> pd.DataFrame:
    """
    Themen-Matrix über alle gewählten Quellen.
    Spalten: Thema, je Quelle Score, Overlap, Top-Cluster pro Quelle.
    """
    if not selected:
        return pd.DataFrame()

    per_source: dict[str, dict[str, dict]] = {}
    for name in selected:
        key = legacy_evidence_key(name)
        if key not in SOURCE_QUERIES:
            continue
        per_source[name] = _collect_theme_scores(key, name)

    return compare_themes_from_scores(per_source)


def compare_sources(selected: list[str], top_n: int = 8) -> pd.DataFrame:
    """Top-Cluster je Quelle (unverändert für Rohvergleich)."""
    frames = []
    for name in selected:
        key = legacy_evidence_key(name)
        if key not in SOURCE_QUERIES:
            continue
        df = fetch_cluster_counts(key, limit=top_n)
        if df.empty:
            continue
        df = df.copy()
        df["source_id"] = name
        frames.append(df[["source_id", "quelle", "cluster", "anzahl"]])

    if not frames:
        return pd.DataFrame(columns=["source_id", "quelle", "cluster", "anzahl"])
    return pd.concat(frames, ignore_index=True)


def find_overlap_from_df(theme_df: pd.DataFrame, min_score: int = 5) -> list[str]:
    """Overlap-Zeilen aus vorberechneter Themen-Matrix."""
    if theme_df.empty:
        return ["Keine Themen-Daten verfügbar — BigQuery prüfen."]

    lines: list[str] = []
    overlaps = theme_df[theme_df["Overlap"] == "✅"]

    if overlaps.empty:
        return [
            "Keine gemeinsamen Themen mit ausreichend Signal in beiden Quellen.",
            "Tipp: Cluster-Namen unterscheiden sich (Modul vs. Kategorie) — Themen-Matrix unten prüfen.",
        ]

    for _, row in overlaps.iterrows():
        score_cols = [c for c in theme_df.columns if c.endswith("(Score)")]
        total = sum(int(row.get(c, 0) or 0) for c in score_cols)
        if total < min_score:
            continue
        theme = row["Thema"]
        parts = []
        for c in score_cols:
            val = int(row.get(c, 0) or 0)
            if val:
                label = c.replace(" (Score)", "")
                cluster_col = c.replace("(Score)", "(Cluster)")
                parts.append(f"{label} {val} ({row.get(cluster_col, '—')})")
        lines.append(f"**{theme}** — " + "; ".join(parts) + ".")

    if not lines:
        return ["Schwache Overlaps — Themen tauchen in beiden Quellen auf, aber mit geringer Häufigkeit."]

    return lines


def find_overlap(selected: list[str], min_score: int = 5) -> list[str]:
    """
    Themen, die in mindestens zwei Quellen vorkommen (gewichtet nach Ticket/Umfrage-Häufigkeit).
    """
    if len(selected) < 2:
        return []

    return find_overlap_from_df(compare_themes(selected), min_score=min_score)


# Öffentliche Aliase für andere Module
collect_theme_scores = _collect_theme_scores

__all__ = [
    "compare_themes",
    "compare_themes_from_scores",
    "compare_sources",
    "find_overlap",
    "find_overlap_from_df",
    "collect_theme_scores",
    "THEME_KEYWORDS",
]
