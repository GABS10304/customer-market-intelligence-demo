"""
Graylog-Nutzungsanalyse — Top-Funktionen nach Aufrufzahl für Assistent & CLI.

Quelle: Stream «RGZ Statistik» (dialogName/event aus RIWA-Statistik-Logs).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable

from config import GRAYLOG_CACHE_PATH, GRAYLOG_MODULE_FIELD, GRAYLOG_STREAMS
from core.graylog_client import (
    GraylogClient,
    GraylogConfigError,
    GraylogError,
    parse_stream_tokens,
    resolve_stream_ids,
)
from core.graylog_event_mapping import resolve_graylog_modul
from core.graylog_usage import _module_label_from_message, detect_fields, normalize_messages

CACHE_PATH = GRAYLOG_CACHE_PATH
CACHE_TTL_HOURS = 12

ALKIS_KEYWORDS = (
    "alkis",
    "flurstück",
    "flurstueck",
    "flurstücks",
    "eigentümer",
    "eigentümernachweis",
    "eigentümerauskunft",
    "eigentümerzusatz",
    "eigentuemer",
)

USAGE_QUESTION_PATTERNS = (
    r"\b(top[\s-]?10|häufigst|meistgenutzt|meist genutzt|aufruf|nutzung|nutzungs)\w*\b",
    r"\b(graylog|systemnutzung|funktionen?\s+im\s+gis)\b",
    r"\b(welche\s+funktion|welche\s+module|was\s+wird\s+am\s+häufigsten)\b",
)

ALKIS_QUESTION_PATTERNS = (
    r"\b(alkis|eigentümer|eigentümerauskunft|flurstück|flurstücke)\b",
)


@dataclass(frozen=True)
class FunctionRank:
    rank: int
    label: str
    calls: int
    mapping_id: str


@dataclass(frozen=True)
class GraylogUsageReport:
    days: int
    stream_label: str
    messages_fetched: int
    events_total: int
    module_field: str
    chunk_capped: bool
    top_overall: tuple[FunctionRank, ...]
    top_alkis: tuple[FunctionRank, ...]
    built_at: str
    from_cache: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.events_total > 0


def is_alkis_related(label: str) -> bool:
    text = (label or "").lower()
    return any(k in text for k in ALKIS_KEYWORDS)


def is_alkis_focused_question(text: str) -> bool:
    """True nur wenn die Frage explizit ALKIS/Eigentümer/Flurstück thematisiert."""
    lower = (text or "").lower()
    return any(re.search(p, lower) for p in ALKIS_QUESTION_PATTERNS)


def is_graylog_usage_question(text: str) -> bool:
    lower = (text or "").lower()
    if not lower.strip():
        return False
    if any(re.search(p, lower) for p in USAGE_QUESTION_PATTERNS):
        return True
    if any(re.search(p, lower) for p in ALKIS_QUESTION_PATTERNS) and re.search(
        r"\b(nutz|aufruf|häufig|top|funktion|dialog)\w*\b", lower
    ):
        return True
    return False


def parse_days_from_question(text: str, *, default: int = 365) -> int:
    lower = (text or "").lower()
    if re.search(r"\b(letztes?\s+jahr|12\s+monate|365\s+tage)\b", lower):
        return 365
    if re.search(r"\b(letzten?\s+quartal|90\s+tage|3\s+monate)\b", lower):
        return 90
    if re.search(r"\b(letzten?\s+monat|30\s+tage)\b", lower):
        return 30
    m = re.search(r"\b(\d{1,3})\s+tage\b", lower)
    if m:
        return max(1, min(int(m.group(1)), 730))
    return default


def parse_top_n_from_question(text: str, *, default: int = 10) -> int:
    lower = (text or "").lower()
    m = re.search(r"\btop[\s-]?(\d{1,2})\b", lower)
    if m:
        return max(3, min(int(m.group(1)), 25))
    return default


def analyze_messages(
    messages: list[dict],
    *,
    module_field: str,
    top_n: int,
) -> tuple[list[tuple[str, int]], list[tuple[str, int]], int]:
    event_counts: Counter[str] = Counter()
    alkis_counts: Counter[str] = Counter()

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        label = _module_label_from_message(msg, module_field).strip()
        if not label:
            continue
        event_counts[label] += 1
        if is_alkis_related(label):
            alkis_counts[label] += 1

    overall = event_counts.most_common(top_n)
    alkis = alkis_counts.most_common(top_n)
    return overall, alkis, sum(event_counts.values())


def fetch_messages_chunked(
    client: GraylogClient,
    stream_ids: list[str],
    *,
    days: int,
    chunk_days: int = 30,
    max_per_chunk: int = 10_000,
    on_chunk: Callable[[str], None] | None = None,
) -> list[dict]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    cursor = start
    collected: list[dict] = []

    while cursor < now:
        window_end = min(cursor + timedelta(days=chunk_days), now)
        batch = client.fetch_messages_between(
            stream_ids,
            cursor,
            window_end,
            max_messages=max_per_chunk,
        )
        collected.extend(batch)
        if on_chunk:
            on_chunk(
                f"{cursor.date()} .. {window_end.date()}: {len(batch):,} Nachrichten "
                f"(Summe {len(collected):,})"
            )
        cursor = window_end

    return collected


def _to_ranks(ranked: list[tuple[str, int]]) -> tuple[FunctionRank, ...]:
    out: list[FunctionRank] = []
    for idx, (label, count) in enumerate(ranked, start=1):
        out.append(
            FunctionRank(
                rank=idx,
                label=label,
                calls=int(count),
                mapping_id=resolve_graylog_modul(label) or "",
            )
        )
    return tuple(out)


def _cache_key(
    *,
    days: int,
    streams: str,
    chunk_days: int,
    max_per_chunk: int,
    top_n: int,
) -> str:
    return f"d{days}|s{streams}|c{chunk_days}|m{max_per_chunk}|t{top_n}"


def _load_cache(key: str) -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        doc = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entry = (doc.get("entries") or {}).get(key)
    if not entry:
        return None
    built = datetime.fromisoformat(str(entry["built_at"]).replace("Z", "+00:00"))
    age_h = (datetime.now(timezone.utc) - built).total_seconds() / 3600
    if age_h > CACHE_TTL_HOURS:
        return None
    return entry


def _save_cache(key: str, report: GraylogUsageReport) -> None:
    doc: dict = {"version": 1, "entries": {}}
    if CACHE_PATH.exists():
        try:
            doc = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            doc = {"version": 1, "entries": {}}
    doc.setdefault("entries", {})[key] = {
        "built_at": report.built_at,
        "days": report.days,
        "stream_label": report.stream_label,
        "messages_fetched": report.messages_fetched,
        "events_total": report.events_total,
        "module_field": report.module_field,
        "chunk_capped": report.chunk_capped,
        "top_overall": [
            {"rank": r.rank, "label": r.label, "calls": r.calls, "mapping_id": r.mapping_id}
            for r in report.top_overall
        ],
        "top_alkis": [
            {"rank": r.rank, "label": r.label, "calls": r.calls, "mapping_id": r.mapping_id}
            for r in report.top_alkis
        ],
    }
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _report_from_cache(entry: dict) -> GraylogUsageReport:
    def _rows(key: str) -> tuple[FunctionRank, ...]:
        return tuple(
            FunctionRank(
                rank=int(r["rank"]),
                label=str(r["label"]),
                calls=int(r["calls"]),
                mapping_id=str(r.get("mapping_id") or ""),
            )
            for r in entry.get(key) or []
        )

    return GraylogUsageReport(
        days=int(entry["days"]),
        stream_label=str(entry.get("stream_label") or ""),
        messages_fetched=int(entry.get("messages_fetched") or 0),
        events_total=int(entry.get("events_total") or 0),
        module_field=str(entry.get("module_field") or "event"),
        chunk_capped=bool(entry.get("chunk_capped")),
        top_overall=_rows("top_overall"),
        top_alkis=_rows("top_alkis"),
        built_at=str(entry.get("built_at") or ""),
        from_cache=True,
    )


def build_graylog_usage_report(
    *,
    days: int = 365,
    top_n: int = 10,
    streams: str | None = None,
    chunk_days: int = 30,
    max_per_chunk: int = 10_000,
    use_cache: bool = True,
    on_progress: Callable[[str], None] | None = None,
) -> GraylogUsageReport:
    stream_raw = (streams or GRAYLOG_STREAMS or "").strip()
    cache_key = _cache_key(
        days=days,
        streams=stream_raw,
        chunk_days=chunk_days,
        max_per_chunk=max_per_chunk,
        top_n=top_n,
    )
    if use_cache:
        cached = _load_cache(cache_key)
        if cached:
            return _report_from_cache(cached)

    try:
        client = GraylogClient()
    except GraylogConfigError as exc:
        return GraylogUsageReport(
            days=days,
            stream_label="",
            messages_fetched=0,
            events_total=0,
            module_field="",
            chunk_capped=False,
            top_overall=(),
            top_alkis=(),
            built_at=datetime.now(timezone.utc).isoformat(),
            error=str(exc),
        )

    try:
        stream_ids, labels = resolve_stream_ids(client, parse_stream_tokens(stream_raw))
        stream_label = ", ".join(labels.get(s, s) for s in stream_ids) if stream_ids else "alle"
        messages = fetch_messages_chunked(
            client,
            stream_ids,
            days=days,
            chunk_days=chunk_days,
            max_per_chunk=max_per_chunk,
            on_chunk=on_progress,
        )
    except GraylogError as exc:
        return GraylogUsageReport(
            days=days,
            stream_label="",
            messages_fetched=0,
            events_total=0,
            module_field="",
            chunk_capped=False,
            top_overall=(),
            top_alkis=(),
            built_at=datetime.now(timezone.utc).isoformat(),
            error=str(exc),
        )

    messages = normalize_messages(messages)
    module_field = (GRAYLOG_MODULE_FIELD or "").strip() or None
    if not module_field and messages:
        module_field, _ = detect_fields(messages)
    module_field = module_field or "event"

    overall, alkis, total = analyze_messages(messages, module_field=module_field, top_n=top_n)
    chunk_count = max(1, (days + chunk_days - 1) // chunk_days)
    chunk_capped = len(messages) >= max_per_chunk * chunk_count

    report = GraylogUsageReport(
        days=days,
        stream_label=stream_label,
        messages_fetched=len(messages),
        events_total=total,
        module_field=module_field,
        chunk_capped=chunk_capped,
        top_overall=_to_ranks(overall),
        top_alkis=_to_ranks(alkis),
        built_at=datetime.now(timezone.utc).isoformat(),
    )
    if use_cache and report.ok:
        _save_cache(cache_key, report)
    return report


def format_usage_report_markdown(
    report: GraylogUsageReport,
    *,
    top_n: int = 10,
    question: str | None = None,
) -> str:
    if report.error:
        return (
            "### Graylog-Nutzungsanalyse (nicht verfügbar)\n"
            f"- Fehler: {report.error}\n"
            "- Prüfe `.env`: `GRAYLOG_URL`, `GRAYLOG_TOKEN`, `GRAYLOG_STREAMS`"
        )

    alkis_focus = is_alkis_focused_question(question or "")

    lines = [
        "### Graylog-Nutzungsanalyse (deterministisch, für Zahlenantworten verbindlich)",
        f"- Stream: **{report.stream_label}**",
        f"- Zeitraum: letzte **{report.days}** Tage",
        f"- Nachrichten ausgewertet: **{report.messages_fetched:,}** · Events: **{report.events_total:,}**",
        f"- Zählfeld: `{report.module_field}` (bei module.dialog.* → dialogName)",
    ]
    if report.from_cache:
        lines.append(f"- Cache: ja (Stand {report.built_at[:19].replace('T', ' ')})")
    if report.chunk_capped:
        lines.append(
            "- **Hinweis:** Chunk-Limit erreicht — absolute Aufrufzahlen sind Untergrenzen; "
            "Rangfolge der Top-Funktionen ist dennoch belastbar."
        )

    lines.append(f"\n**Top {top_n} Funktionen (Aufrufzahl gesamt):**")
    if not report.top_overall:
        lines.append("- (keine Events)")
    else:
        for row in report.top_overall[:top_n]:
            mid = f" → `{row.mapping_id}`" if row.mapping_id else ""
            lines.append(f"{row.rank}. **{row.label}** — {row.calls:,} Aufrufe{mid}")

    if alkis_focus:
        lines.append(f"\n**Top {top_n} ALKIS / Eigentümer / Flurstück (Teilmenge):**")
        if not report.top_alkis:
            lines.append("- (keine ALKIS-bezogenen Dialoge im Sample)")
        else:
            for row in report.top_alkis[:top_n]:
                mid = f" → `{row.mapping_id}`" if row.mapping_id else ""
                lines.append(f"{row.rank}. **{row.label}** — {row.calls:,} Aufrufe{mid}")
        lines.append(
            "\n**Interpretation:** ALKIS-Dialoge sind eine Teilmenge; "
            "Kartenabfragen (`module.gis.query.*`) haben typischerweise deutlich höhere Aufrufzahlen."
        )
    else:
        lines.append(
            "\n**Interpretation:** Die Top-Plätze werden von Kartenabfragen "
            "(`module.gis.query.*`) und Server-Sessions (Login/Logout) dominiert."
        )
    return "\n".join(lines)


@lru_cache(maxsize=8)
def build_graylog_context_for_question(question: str) -> str:
    """Kontextblock für den Assistenten — cached pro Frage-Parameter."""
    if not is_graylog_usage_question(question):
        return ""
    days = parse_days_from_question(question)
    top_n = parse_top_n_from_question(question)
    report = build_graylog_usage_report(days=days, top_n=top_n, use_cache=True)
    return format_usage_report_markdown(report, top_n=top_n, question=question)


def clear_graylog_usage_cache() -> None:
    build_graylog_context_for_question.cache_clear()
    if CACHE_PATH.exists():
        CACHE_PATH.unlink(missing_ok=True)
