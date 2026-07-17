"""Gemeinsame Hilfsfunktionen für Intent-Stichproben."""

from __future__ import annotations

import pandas as pd

INTENT_REVIEW_COLUMNS = (
    "sample_id",
    "quelle",
    "cluster",
    "freitext",
    "bedarf_auto",
    "request_thema_auto",
    "request_detail_auto",
    "themen_auto",
    "challenge_ok",
    "challenge_notiz",
)

INTENT_REVIEW_COLUMNS_FULL = INTENT_REVIEW_COLUMNS + (
    "intent_auto",
    "geltung_auto",
    "kontakt_angebot_auto",
    "ansprechpartner_auto",
    "kontakt_zeitraum_auto",
    "aktion_todo_auto",
    "intent_confidence",
    "matched_keywords",
    "intent_manual",
    "bereich",
    "quelle_technisch",
    "input_typ",
    "ticket_id",
    "ticket_datei",
    "csv_datei",
    "csv_pfad",
    "html_pfad",
    "zeilen_index",
)

# Tester feedback from intent_review_tester_assignments.csv (merged into main review CSV).
TESTER_CHALLENGE_FEEDBACK: dict[str, tuple[str, str]] = {
    "S035": ("ja", "ok"),
    "S001": ("ja", "ok; tester noted modulübergreifend"),
    "S010": ("ja", "ok"),
    "S040": ("ja", "ok"),
    "S034": (
        "ja",
        "Update-Kritik (Verschlimmbesserung nach Release); intent Defekt vertretbar für Routing",
    ),
    "S003": ("ja", "ok"),
    "S039": (
        "ja",
        "Bugmeldung; intent Defekt ok; Cluster BOLL",
    ),
    "S020": ("ja", "ok"),
}


def select_review_columns(df: pd.DataFrame, *, full: bool = False) -> pd.DataFrame:
    columns = INTENT_REVIEW_COLUMNS_FULL if full else INTENT_REVIEW_COLUMNS
    present = [col for col in columns if col in df.columns]
    return df[present].copy()


def merge_challenge_fields(
    sample: pd.DataFrame,
    existing: pd.DataFrame | None = None,
    feedback: dict[str, tuple[str, str]] | None = None,
) -> pd.DataFrame:
    result = sample.copy()
    if existing is not None and not existing.empty and "sample_id" in existing.columns:
        for col in ("challenge_ok", "challenge_notiz"):
            if col not in existing.columns:
                continue
            by_id = existing.set_index("sample_id")[col].to_dict()
            for sid, value in by_id.items():
                if pd.isna(value) or not str(value).strip():
                    continue
                mask = result["sample_id"] == sid
                result.loc[mask, col] = value

    for sid, (ok, notiz) in (feedback or {}).items():
        mask = result["sample_id"] == sid
        if ok:
            result.loc[mask, "challenge_ok"] = ok
        if notiz:
            result.loc[mask, "challenge_notiz"] = notiz
    return result


def stratified_sample(pool: pd.DataFrame, limit: int, seed: int, *, group_col: str = "quelle_technisch") -> pd.DataFrame:
    if pool.empty:
        return pool

    work = pool.copy().reset_index(drop=True)
    work["_row_id"] = work.index

    sources = work[group_col].drop_duplicates().tolist()
    if not sources:
        return work.drop(columns=["_row_id"]).head(limit)

    base = limit // len(sources)
    remainder = limit % len(sources)
    picked_ids: list[int] = []

    for i, source in enumerate(sorted(sources)):
        subset = work[work[group_col] == source]
        take = min(len(subset), base + (1 if i < remainder else 0))
        if take <= 0:
            continue
        chosen = subset.sample(n=take, random_state=seed + i)
        picked_ids.extend(chosen["_row_id"].tolist())

    if len(picked_ids) < limit:
        remaining = work[~work["_row_id"].isin(picked_ids)]
        need = limit - len(picked_ids)
        if not remaining.empty and need > 0:
            extra = remaining.sample(n=min(need, len(remaining)), random_state=seed + 99)
            picked_ids.extend(extra["_row_id"].tolist())

    sample = work[work["_row_id"].isin(picked_ids)].drop(columns=["_row_id"])
    return sample.sample(frac=1, random_state=seed).reset_index(drop=True)


def finalize_sample(pool: pd.DataFrame, limit: int, seed: int, *, group_col: str = "quelle_technisch") -> pd.DataFrame:
    deduped = pool.drop_duplicates(subset=["freitext", "quelle_technisch", "cluster"], keep="first")
    sample = stratified_sample(deduped, limit=limit, seed=seed, group_col=group_col)
    sample.insert(0, "sample_id", [f"S{i + 1:03d}" for i in range(len(sample))])
    return sample
