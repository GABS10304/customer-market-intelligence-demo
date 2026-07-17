#!/usr/bin/env python3
"""Graylog Top-Funktionen nach Aufrufzahl (Dialog/Event) — RIWA GIS-Zentrum."""

from __future__ import annotations

import argparse
import sys

from config import GRAYLOG_MODULE_FIELD, GRAYLOG_STREAMS
from core.graylog_analytics import build_graylog_usage_report
from core.graylog_event_mapping import resolve_graylog_modul


def _print_table(title: str, rows, *, limit: int = 10) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    if not rows:
        print("  (keine Daten)")
        return
    width = max(len(r.label) for r in rows[:limit])
    for row in rows[:limit]:
        mapping = row.mapping_id or resolve_graylog_modul(row.label) or "—"
        print(f"  {row.rank:2}. {row.label:<{width}}  {row.calls:>8,}  -> {mapping}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Top Graylog-Funktionen nach Aufrufzahl.")
    parser.add_argument("--days", type=int, default=365, help="Tage zurück (Default: 365).")
    parser.add_argument("--streams", default=GRAYLOG_STREAMS, help="Graylog-Stream(s).")
    parser.add_argument("--top", type=int, default=10, help="Top-N (Default: 10).")
    parser.add_argument(
        "--module-field",
        default=GRAYLOG_MODULE_FIELD or "",
        help="Modul-Feld (nur Info — Auto-Erkennung in Analytics).",
    )
    parser.add_argument("--chunk-days", type=int, default=30, help="Tage pro Graylog-Chunk.")
    parser.add_argument(
        "--max-per-chunk",
        type=int,
        default=10_000,
        help="Max. Nachrichten pro Chunk (Graylog-Limit ~10k).",
    )
    parser.add_argument("--no-cache", action="store_true", help="Disk-Cache ignorieren.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    def _progress(msg: str) -> None:
        print(f"  {msg}")

    report = build_graylog_usage_report(
        days=args.days,
        top_n=args.top,
        streams=args.streams.strip() if args.streams else None,
        chunk_days=args.chunk_days,
        max_per_chunk=args.max_per_chunk,
        use_cache=not args.no_cache,
        on_progress=_progress,
    )

    if report.error:
        print(f"Graylog-Fehler: {report.error}", file=sys.stderr)
        return 1

    print(f"Stream: {report.stream_label}")
    print(f"Zeitraum: letzte {report.days} Tage")
    print(f"Empfangen: {report.messages_fetched:,} Nachrichten")
    print(f"Zählfeld: {report.module_field!r}")
    print(f"\nAuswertbare Events gesamt: {report.events_total:,}")
    if report.chunk_capped:
        print(
            "Hinweis: Mindestens ein Chunk am Limit — absolute Aufrufzahlen sind Untergrenzen; "
            "Rangfolge der Top-Funktionen ist dennoch belastbar."
        )
    if report.from_cache:
        print(f"Cache: ja (Stand {report.built_at[:19].replace('T', ' ')})")

    _print_table(f"Top {args.top} Funktionen (Aufrufzahl, alle Bereiche)", report.top_overall, limit=args.top)
    _print_table(
        f"Top {args.top} ALKIS/Eigentümer/Flurstück (Teilmenge)",
        report.top_alkis,
        limit=args.top,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
