#!/usr/bin/env python3
"""
Graylog → data/module_usage.csv — aktive Nutzer pro Modul.

Usage:
    python import_module_usage_from_graylog.py
    python import_module_usage_from_graylog.py --probe
    python import_module_usage_from_graylog.py --dry-run --limit-messages 500
    python import_module_usage_from_graylog.py --streams "69e874cc69fe7d5951a9eaf0" --days 30
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import (
    DATA_DIR,
    GRAYLOG_DAYS,
    GRAYLOG_MODULE_FIELD,
    GRAYLOG_STREAMS,
    GRAYLOG_USER_FIELD,
    ROOT_DIR,
)
from core.graylog_client import (
    GraylogClient,
    GraylogConfigError,
    GraylogError,
    parse_stream_tokens,
    resolve_stream_ids,
)
from core.graylog_usage import (
    aggregate_usage_by_mapping,
    baum_related_label_counts,
    detect_fields,
    normalize_messages,
    top_module_values,
    usage_rows_with_mapping,
    write_module_usage_csv,
)
from core.module_usage import USAGE_CSV

DEFAULT_OUTPUT = USAGE_CSV


def _print_summary(out_df) -> None:
    print(f"\nZusammenfassung: {len(out_df)} Zeilen")
    if out_df.empty:
        return

    top = out_df.sort_values("aktive_nutzer", ascending=False).head(10)
    print("\nTop 10 Module:")
    for _, row in top.iterrows():
        print(f"  {row['modulname']}: {row['aktive_nutzer']} Nutzer ({row['mapping_id']})")

    unmapped = out_df[out_df["mapping_id"].astype(str).str.contains("unbekannt", case=False, na=False)]
    print(f"\nNicht gemappt: {len(unmapped)} von {len(out_df)}")


def run_probe(
    client: GraylogClient,
    stream_tokens: list[str],
    *,
    days: int,
    module_field: str | None,
    user_field: str | None,
    sample_per_stream: int = 20,
) -> int:
    print(f"Graylog: {client.base_url}")
    system = client.ping()
    version = system.get("version") or system.get("cluster_id") or "?"
    print(f"Ping OK — Version/Cluster: {version}")

    streams = client.list_streams()
    print(f"\nStreams ({len(streams)}):")
    for stream in streams:
        sid = stream.get("id", "")
        title = stream.get("title", "")
        print(f"  {sid}  {title}")

    stream_ids, labels = resolve_stream_ids(client, stream_tokens)
    if stream_ids:
        print(f"\nAusgewählte Streams: {', '.join(labels.get(s, s) for s in stream_ids)}")
        probe_targets = stream_ids
    else:
        probe_targets = [str(s.get("id", "")).strip() for s in streams if s.get("id")]
        labels = {str(s.get("id", "")).strip(): str(s.get("title") or s.get("id")) for s in streams}
        print(f"\nKeine Stream-Filter — alle {len(probe_targets)} Streams einzeln")

    all_samples: list[dict] = []
    for sid in probe_targets:
        label = labels.get(sid, sid)
        print(f"\n--- Probe: {label} (~{sample_per_stream} Nachrichten) ---")
        try:
            batch = client.fetch_messages(
                [sid],
                days,
                max_messages=sample_per_stream,
                page_size=sample_per_stream,
            )
        except GraylogError as exc:
            print(f"  Fehler: {exc}")
            continue
        print(f"  Empfangen: {len(batch)} Nachrichten")
        batch = normalize_messages(batch)
        if batch:
            keys = sorted({k for msg in batch for k in msg.keys()})
            print(f"  Felder ({len(keys)}): {', '.join(keys[:40])}{'…' if len(keys) > 40 else ''}")
            mod_f, _ = detect_fields(batch)
            if mod_f:
                print("  Top Modulwerte:")
                for name, count in top_module_values(batch, mod_f, limit=5):
                    print(f"    {name}: {count}")
        all_samples.extend(batch)

    all_samples = normalize_messages(all_samples)

    mod_field = module_field or None
    usr_field = user_field or None
    if not mod_field or not usr_field:
        detected_mod, detected_usr = detect_fields(all_samples)
        mod_field = mod_field or detected_mod
        usr_field = usr_field or detected_usr

    print(f"\nErkannte Felder: module={mod_field!r}, user={usr_field!r}")
    if mod_field:
        print("\nTop Modulwerte (gesamt):")
        for name, count in top_module_values(all_samples, mod_field, limit=10):
            print(f"  {name}: {count}")

    baum_labels = baum_related_label_counts(all_samples)
    print(f"\nBaum-bezogene dialogName/event ({len(baum_labels)} eindeutig):")
    if baum_labels:
        for label, count in baum_labels:
            print(f"  {label}: {count}")
    else:
        print("  (keine Treffer in den Stichproben)")
    return 0


def run_import(
    client: GraylogClient,
    stream_tokens: list[str],
    *,
    days: int,
    module_field: str | None,
    user_field: str | None,
    output: Path,
    dry_run: bool,
    max_messages: int,
) -> int:
    stream_ids, labels = resolve_stream_ids(client, stream_tokens)
    quelle = "graylog:" + ",".join(labels.get(s, s) for s in stream_ids) if stream_ids else "graylog"

    print(f"Lade Nachrichten ({days} Tage, max {max_messages}) …")
    messages = client.fetch_messages(stream_ids, days, max_messages=max_messages)
    print(f"Empfangen: {len(messages)} Nachrichten")
    messages = normalize_messages(messages)

    mod_field = module_field or None
    usr_field = user_field or None
    if not mod_field or not usr_field:
        detected_mod, detected_usr = detect_fields(messages)
        mod_field = mod_field or detected_mod
        usr_field = usr_field or detected_usr

    if not mod_field:
        print("Fehler: Kein Modul-Feld erkannt. --module-field setzen.", file=sys.stderr)
        return 1
    if not usr_field:
        print("Fehler: Kein Nutzer-Feld erkannt. --user-field setzen.", file=sys.stderr)
        return 1

    print(f"Felder: module={mod_field!r}, user={usr_field!r}")
    usage = aggregate_usage_by_mapping(messages, mod_field, usr_field)
    out_df = usage_rows_with_mapping(usage, quelle=quelle)

    if dry_run:
        print("\nDry-run — keine CSV geschrieben:")
        print(out_df.to_string(index=False))
    else:
        rows = write_module_usage_csv(out_df, output)
        print(f"\nGeschrieben: {rows} Zeilen → {output}")

    _print_summary(out_df)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Graylog-Nutzung → data/module_usage.csv importieren.",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Verbindung testen, Streams + Felder anzeigen (kein CSV-Schreiben).",
    )
    parser.add_argument(
        "--streams",
        default="",
        help="Komma-getrennte Stream-IDs oder -Namen (überschreibt GRAYLOG_STREAMS).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=int(GRAYLOG_DAYS or "30"),
        help=f"Tage zurück (Default: {GRAYLOG_DAYS}).",
    )
    parser.add_argument(
        "--module-field",
        default=GRAYLOG_MODULE_FIELD,
        help="Modul-Feld (Default: Auto-Erkennung).",
    )
    parser.add_argument(
        "--user-field",
        default=GRAYLOG_USER_FIELD,
        help="Nutzer-Feld (Default: Auto-Erkennung).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Ziel-CSV (Default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Aggregierte Tabelle ausgeben, nicht schreiben.",
    )
    parser.add_argument(
        "--limit-messages",
        type=int,
        default=10_000,
        help="Max. Nachrichten für Import/Probe (Default: 10000).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    stream_raw = args.streams.strip() or GRAYLOG_STREAMS
    stream_tokens = parse_stream_tokens(stream_raw)
    module_field = (args.module_field or "").strip() or None
    user_field = (args.user_field or "").strip() or None

    try:
        client = GraylogClient()
    except GraylogConfigError as exc:
        print(f"Konfiguration: {exc}", file=sys.stderr)
        print(f"Tipp: .env aus {ROOT_DIR / '.env.example'} anlegen.", file=sys.stderr)
        return 1

    try:
        if args.probe:
            return run_probe(
                client,
                stream_tokens,
                days=args.days,
                module_field=module_field,
                user_field=user_field,
                sample_per_stream=args.limit_messages,
            )
        return run_import(
            client,
            stream_tokens,
            days=args.days,
            module_field=module_field,
            user_field=user_field,
            output=args.output,
            dry_run=args.dry_run,
            max_messages=args.limit_messages,
        )
    except GraylogError as exc:
        print(f"Graylog-Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
