"""
Freitext-Zeilen aus HTML-Tickets und CSV-Quellen für Intent-Auswertung.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from config import (
    DELIMITER,
    FIELD_VISITS_CSV,
    INBOX_DIR,
    INBOX_FIELD_VISITS_DIR,
    INBOX_SURVEYS_DIR,
    SURVEYS_NPS_CSV,
    TICKETS_BACKLOG_CSV,
)
from core.governance import scrub_pii
from core.hotline_scope import ticket_in_hotline_scope
from core.html_ticket_reader import iter_html_tickets
from workspace.sources.detector import build_mapping, detect_source
from workspace.sources.profiles import BUILTIN_PROFILES, get_profile

MIN_TEXT_LEN = 15
NO_FREETEXT_PROFILES = frozenset({"sales_product_penetration"})


@dataclass(frozen=True)
class FreetextRow:
    quelle: str
    quelle_technisch: str
    cluster: str
    freitext: str
    input_typ: str  # html_roh | csv
    bereich: str = ""


def _pipeline_csv_paths() -> list[Path]:
    return [p for p in (TICKETS_BACKLOG_CSV, SURVEYS_NPS_CSV, FIELD_VISITS_CSV) if p.exists()]


def _inbox_csv_paths() -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for root in (INBOX_DIR, INBOX_SURVEYS_DIR, INBOX_FIELD_VISITS_DIR):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.csv")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(path)
    return found


def discover_csv_files() -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for path in _pipeline_csv_paths() + _inbox_csv_paths():
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        paths.append(path)
    return paths


def _read_csv(path: Path):
    import pandas as pd

    profile = get_profile("survey_freetext_250")
    delimiter = profile.delimiter if profile else DELIMITER
    return pd.read_csv(path, sep=delimiter, encoding="utf-8-sig", on_bad_lines="skip")


def _resolve_profile(path: Path, df):
    meta_path = path.with_suffix(".csv.meta.json")
    if meta_path.exists():
        import json

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            name = meta.get("source_profile")
            if name and name in BUILTIN_PROFILES:
                mapping = meta.get("mapping") or build_mapping(BUILTIN_PROFILES[name], list(df.columns))
                return name, mapping
        except (OSError, json.JSONDecodeError):
            pass
    detection = detect_source(df, filename=path.name)
    return detection.suggested_profile, detection.mapping


@dataclass(frozen=True)
class FreetextInventory:
    """Auswertbare Freitextzeilen über alle Quellen (ohne Hotline-Doppelzählung HTML+CSV)."""

    total: int
    hotline: int
    feldbesuche: int
    umfrage_freitext: int
    extra: tuple[tuple[str, int], ...]

    @property
    def sonstige(self) -> int:
        return sum(n for _, n in self.extra)

    @property
    def breakdown(self) -> str:
        parts = [
            f"Hotline {self.hotline}",
            f"Feld {self.feldbesuche}",
            f"Umfrage-Freitext {self.umfrage_freitext}",
        ]
        for label, count in self.extra:
            parts.append(f"{label} {count}")
        return " · ".join(parts)


def _count_survey_freetext_rows() -> int:
    from core.survey_data import load_survey_frame, survey_column_map

    df = load_survey_frame()
    if df.empty:
        return 0
    cmap = survey_column_map(df)
    col = cmap.get("freitext") or ""
    if not col or col not in df.columns:
        return 0
    texts = df[col].dropna().astype(str).str.strip()
    return int(((texts.str.len() >= MIN_TEXT_LEN) & (texts.str.lower() != "nan")).sum())


_KNOWN_CSV_PROFILES = frozenset({"field_visits_weihnachtsbesuche"})


def freetext_inventory(*, include_html: bool = True, include_csv: bool = True) -> FreetextInventory:
    """
    Zählt Freitextzeilen je Quelle.

    Hotline nur aus HTML (Scraper-Scope) — tickets_backlog.csv wäre identisch und wird nicht addiert.
    """
    hotline = feldbesuche = 0
    extra_counts: Counter[str] = Counter()
    if include_html:
        for row in iter_freetext_rows(include_html=True, include_csv=False):
            if row.quelle_technisch == "support_tickets_html_roh":
                hotline += 1
    if include_csv:
        for row in iter_freetext_rows(include_html=False, include_csv=True):
            if row.quelle_technisch == "support_tickets_html":
                continue
            if row.quelle_technisch in _KNOWN_CSV_PROFILES:
                feldbesuche += 1
            else:
                label = row.quelle or row.quelle_technisch
                extra_counts[label] += 1
    umfrage = _count_survey_freetext_rows()
    extra = tuple(sorted(extra_counts.items(), key=lambda x: (-x[1], x[0])))
    sonstige = sum(extra_counts.values())
    total = hotline + feldbesuche + umfrage + sonstige
    return FreetextInventory(
        total=total,
        hotline=hotline,
        feldbesuche=feldbesuche,
        umfrage_freitext=umfrage,
        extra=extra,
    )


def iter_freetext_rows(*, include_html: bool = True, include_csv: bool = True) -> Iterator[FreetextRow]:
    if include_html:
        profile = get_profile("support_tickets_html")
        display = profile.display_name if profile else "Hotline Tickets RIWA"
        for ticket in iter_html_tickets():
            if not ticket_in_hotline_scope(ticket):
                continue
            yield FreetextRow(
                quelle=display,
                quelle_technisch="support_tickets_html_roh",
                cluster=ticket["cluster"],
                freitext=ticket["freitext"],
                input_typ="html_roh",
                bereich=ticket.get("bereich", ""),
            )

    if not include_csv:
        return

    for path in discover_csv_files():
        df = _read_csv(path)
        if df.empty:
            continue
        profile_name, mapping = _resolve_profile(path, df)
        if profile_name in NO_FREETEXT_PROFILES:
            continue
        text_col = mapping.get("text")
        if not text_col or text_col not in df.columns:
            continue
        cluster_col = mapping.get("cluster")
        profile = get_profile(profile_name)
        display_name = profile.display_name if profile else profile_name

        for _, row in df.iterrows():
            raw_text = row.get(text_col)
            if raw_text is None or str(raw_text).strip().lower() == "nan":
                continue
            text = scrub_pii(str(raw_text).strip())
            if len(text) < MIN_TEXT_LEN:
                continue
            cluster = ""
            if cluster_col and cluster_col in df.columns and row.get(cluster_col) is not None:
                cluster = str(row.get(cluster_col)).strip()
            yield FreetextRow(
                quelle=display_name,
                quelle_technisch=profile_name,
                cluster=cluster,
                freitext=text,
                input_typ="csv",
            )
