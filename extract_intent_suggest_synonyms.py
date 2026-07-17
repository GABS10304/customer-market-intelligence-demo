#!/usr/bin/env python3
"""
Synonym-Vorschläge aus manueller Challenge — Lern-Feedback-Schleife.

Liest intent_review_sample.csv: Zeilen mit abweichendem intent_manual / challenge_notiz
und schlägt neue Cluster-Terme vor (PM trägt bestätigte in intent_synonym_clusters.json ein).

Usage:
    python extract_intent_suggest_synonyms.py
    python extract_intent_suggest_synonyms.py --csv data/intent_review_sample.csv
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from config import DATA_DIR, DELIMITER
from core.intent_lexicon import all_terms_for_bedarf, load_clusters, suggest_terms_from_text

DEFAULT_CSV = DATA_DIR / "intent_review_sample.csv"

_BEDARF_MANUAL_MAP = {
    "feature-wunsch": "Feature Request",
    "feature wunsch": "Feature Request",
    "feature-request": "Feature Request",
    "feature request": "Feature Request",
    "ux-kritik": "UX-Kritik",
    "ux": "UX-Kritik",
    "service-kritik": "Service-Kritik",
    "dokumentations-wunsch": "Dokumentations-Wunsch",
    "update-kritik": "Update-Kritik",
}


def _resolve_manual_bedarf(row: pd.Series) -> str:
    manual = str(row.get("intent_manual") or row.get("bedarf_manual") or "").strip()
    if not manual or manual.lower() == "nan":
        return ""
    key = manual.lower()
    if key in _BEDARF_MANUAL_MAP:
        return _BEDARF_MANUAL_MAP[key]
    return manual


def _tokenize_notiz(notiz: str) -> list[str]:
    return re.findall(r"[a-zäöüß]{4,}", (notiz or "").lower())


def run(csv_path: Path) -> int:
    if not csv_path.exists():
        print(f"CSV nicht gefunden: {csv_path}", file=sys.stderr)
        return 1

    df = pd.read_csv(csv_path, sep=DELIMITER, encoding="utf-8-sig")
    candidates: Counter = Counter()

    for _, row in df.iterrows():
        ok = str(row.get("challenge_ok") or "").strip().lower()
        auto = str(row.get("bedarf_auto") or "").strip()
        manual_bedarf = _resolve_manual_bedarf(row)
        freitext = str(row.get("freitext") or "")

        needs_review = ok in ("nein", "no", "n") or (
            manual_bedarf and manual_bedarf != auto
        )
        if not needs_review or not manual_bedarf:
            continue

        for term in suggest_terms_from_text(freitext, bedarf=manual_bedarf):
            candidates[(manual_bedarf, term)] += 1
        for term in _tokenize_notiz(str(row.get("challenge_notiz") or "")):
            if term not in all_terms_for_bedarf(manual_bedarf):
                candidates[(manual_bedarf, term)] += 1

    if not candidates:
        print("Keine Synonym-Kandidaten (Challenge-Spalten leer oder alles konsistent).")
        return 0

    print("Synonym-Vorschläge (bestätigte Terme → data/intent_synonym_clusters.json):\n")
    by_bedarf: dict[str, list[tuple[str, int]]] = {}
    for (bedarf, term), count in candidates.most_common():
        by_bedarf.setdefault(bedarf, []).append((term, count))

    for bedarf, items in sorted(by_bedarf.items()):
        cluster_ids = [cid for cid, c in load_clusters().items() if c.get("bedarf") == bedarf]
        target = cluster_ids[0] if cluster_ids else "(neuer Cluster)"
        print(f"  {bedarf} → Cluster «{target}»:")
        for term, count in items[:12]:
            print(f"    - {term} ({count}×)")
        print()

    print(
        "Workflow: PM bestätigt Terme → eintragen unter "
        f"clusters.<id>.terms in {DATA_DIR / 'intent_synonym_clusters.json'}"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Synonym-Vorschläge aus Challenge-CSV.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    raise SystemExit(run(args.csv))


if __name__ == "__main__":
    main()
