#!/usr/bin/env python3
"""
Intent-Stichprobe aus lokalen CSVs — für manuelle Challenge / Gold-Set.

Liest Pipeline-CSVs und Inbox-Dateien, klassifiziert Intent regelbasiert,
zieht stratifiziert N Zufallszeilen über verschiedene Quellen.

Usage:
    python extract_intent_sample.py
    python extract_intent_sample.py --limit 50 --seed 42
    python extract_intent_sample.py --output data/intent_review_sample.csv
    python extract_intent_sample.py --full
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from config import (
    DATA_DIR,
    DELIMITER,
    FIELD_VISITS_CSV,
    INBOX_DIR,
    INBOX_FIELD_VISITS_DIR,
    INBOX_SURVEYS_DIR,
    SURVEYS_NPS_CSV,
    TICKETS_BACKLOG_CSV,
)
from core.governance import scrub_pii
from core.intent_patterns import classify_intent
from core.intent_sample import (
    TESTER_CHALLENGE_FEEDBACK,
    finalize_sample,
    merge_challenge_fields,
    select_review_columns,
)
from workspace.sources.detector import build_mapping, detect_source
from workspace.sources.profiles import BUILTIN_PROFILES, get_profile

DEFAULT_OUTPUT = DATA_DIR / "intent_review_sample.csv"
MIN_TEXT_LEN = 15
NO_FREETEXT_PROFILES = frozenset({"sales_product_penetration"})


def _pipeline_csv_paths() -> list[Path]:
    return [
        p
        for p in (
            TICKETS_BACKLOG_CSV,
            SURVEYS_NPS_CSV,
            FIELD_VISITS_CSV,
        )
        if p.exists()
    ]


def _inbox_csv_paths() -> list[Path]:
    roots = [INBOX_DIR, INBOX_SURVEYS_DIR, INBOX_FIELD_VISITS_DIR]
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.csv")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(path)
    return found


def discover_csv_files(extra: list[Path] | None = None) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for path in _pipeline_csv_paths() + _inbox_csv_paths() + (extra or []):
        resolved = path.resolve()
        if resolved in seen or not path.exists():
            continue
        seen.add(resolved)
        paths.append(path)
    return paths


def _read_csv(path: Path) -> pd.DataFrame:
    profile = get_profile("survey_freetext_250")
    delimiter = profile.delimiter if profile else DELIMITER
    return pd.read_csv(path, sep=delimiter, encoding="utf-8-sig", on_bad_lines="skip")


def _resolve_profile(path: Path, df: pd.DataFrame) -> tuple[str, dict[str, str | None]]:
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


def _load_freetext_rows(path: Path) -> pd.DataFrame:
    df = _read_csv(path)
    if df.empty:
        return pd.DataFrame()

    profile_name, mapping = _resolve_profile(path, df)
    if profile_name in NO_FREETEXT_PROFILES:
        return pd.DataFrame()

    text_col = mapping.get("text")
    if not text_col or text_col not in df.columns:
        return pd.DataFrame()

    cluster_col = mapping.get("cluster")
    profile = get_profile(profile_name)
    display_name = profile.display_name if profile else profile_name

    rows: list[dict[str, str]] = []
    for idx, row in df.iterrows():
        raw_text = row.get(text_col)
        if pd.isna(raw_text):
            continue
        text = scrub_pii(str(raw_text).strip())
        if len(text) < MIN_TEXT_LEN:
            continue

        cluster = ""
        if cluster_col and cluster_col in df.columns and not pd.isna(row.get(cluster_col)):
            cluster = str(row.get(cluster_col)).strip()

        source_file_col = ""
        for candidate in ("source_file", "Quelle (Dateiname)", "Quelle"):
            if candidate in df.columns and not pd.isna(row.get(candidate)):
                source_file_col = str(row.get(candidate)).strip()
                break

        intent = classify_intent(text, modul=cluster)
        rows.append(
            {
                "quelle": display_name,
                "quelle_technisch": profile_name,
                "bereich": "",
                "cluster": cluster,
                "freitext": text,
                "intent_auto": intent.intent,
                "bedarf_auto": intent.bedarf,
                "geltung_auto": intent.geltung,
                "themen_auto": "|".join(intent.themen),
                "request_thema_auto": intent.request_thema,
                "request_detail_auto": intent.request_detail,
                "kontakt_angebot_auto": intent.kontakt_angebot,
                "ansprechpartner_auto": intent.ansprechpartner,
                "kontakt_zeitraum_auto": intent.kontakt_zeitraum,
                "aktion_todo_auto": intent.aktion_todo,
                "intent_confidence": intent.confidence,
                "matched_keywords": "|".join(intent.matched_keywords),
                "intent_manual": "",
                "challenge_ok": "",
                "challenge_notiz": "",
                "input_typ": "csv",
                "ticket_id": "",
                "ticket_datei": source_file_col,
                "csv_datei": path.name,
                "csv_pfad": str(path.resolve()),
                "html_pfad": "",
                "zeilen_index": str(idx),
            }
        )

    return pd.DataFrame(rows)


def _load_existing_output(output: Path) -> pd.DataFrame | None:
    if not output.exists():
        return None
    return pd.read_csv(output, sep=DELIMITER, encoding="utf-8-sig")


def run(limit: int, seed: int, output: Path, extra_csv: list[Path], *, full: bool = False) -> int:
    csv_files = discover_csv_files(extra_csv)
    if not csv_files:
        print("Keine CSV-Dateien gefunden.", file=sys.stderr)
        print("Erwartet u.a.:", file=sys.stderr)
        print(f"  - {TICKETS_BACKLOG_CSV}", file=sys.stderr)
        print(f"  - {SURVEYS_NPS_CSV}", file=sys.stderr)
        print(f"  - {FIELD_VISITS_CSV}", file=sys.stderr)
        print(f"  - CSVs unter {INBOX_DIR}", file=sys.stderr)
        return 1

    frames: list[pd.DataFrame] = []
    stats: list[str] = []
    for path in csv_files:
        part = _load_freetext_rows(path)
        if part.empty:
            stats.append(f"  {path.name}: 0 Freitext-Zeilen (übersprungen oder kein Mapping)")
            continue
        frames.append(part)
        by_source = part.groupby("quelle_technisch").size().to_dict()
        stats.append(f"  {path.name}: {len(part)} Zeilen — {by_source}")

    if not frames:
        print("CSV-Dateien gefunden, aber keine Freitext-Zeilen extrahierbar.", file=sys.stderr)
        for line in stats:
            print(line, file=sys.stderr)
        return 1

    pool = pd.concat(frames, ignore_index=True)
    sample = finalize_sample(pool, limit=limit, seed=seed, group_col="quelle_technisch")
    sample = merge_challenge_fields(
        sample,
        existing=_load_existing_output(output),
        feedback=TESTER_CHALLENGE_FEEDBACK,
    )
    export = select_review_columns(sample, full=full)

    output.parent.mkdir(parents=True, exist_ok=True)
    export.to_csv(output, sep=DELIMITER, index=False, encoding="utf-8-sig")

    print(f"Intent-Stichprobe: {len(sample)} Zeilen -> {output}")
    print(f"Gesamt-Pool: {len(pool)} Freitext-Zeilen aus {len(csv_files)} CSV(s)")
    print("Verteilung (auto):")
    for intent, count in sample["intent_auto"].value_counts().items():
        print(f"  {intent}: {count}")
    print("Quellen:")
    for quelle, count in sample["quelle"].value_counts().items():
        print(f"  {quelle}: {count}")
    print("\nDateien eingelesen:")
    for line in stats:
        print(line)
    cols = "alle Spalten (--full)" if full else "PM-Review-Spalten (default; --full für Debug)"
    print(f"\nManuelle Challenge ({cols}): challenge_ok (ja/nein/teilweise), challenge_notiz ausfüllen.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Intent-Stichprobe aus lokalen CSVs extrahieren.")
    parser.add_argument("--limit", type=int, default=50, help="Anzahl Zufallszeilen (default: 50)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed für reproduzierbare Stichprobe")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Ausgabe-CSV (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--csv",
        action="append",
        default=[],
        type=Path,
        help="Zusätzliche CSV-Datei (mehrfach möglich)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Alle Spalten exportieren (intent_auto, Metadaten, …); default ist schlankes PM-Review-Set",
    )
    args = parser.parse_args()
    raise SystemExit(run(args.limit, args.seed, args.output, args.csv, full=args.full))


if __name__ == "__main__":
    main()
