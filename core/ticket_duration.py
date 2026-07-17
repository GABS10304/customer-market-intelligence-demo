"""Hotline — Bearbeitungszeit aus HTML-Tickets (Telefonanruf-Sekunden, alle Bereiche)."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Literal

from config import TICKETS_HTML_DIR
from core.html_ticket_reader import bereich_label, module_label
from core.tera_scope import is_tera_hotline_cluster

DurationScope = Literal["all", "tera", "bereich"]

KNOWN_BEREICHE = ("teraWinData", "riwaGisData", "otsBauData")

DURATION_QUESTION_PATTERNS = (
    r"\b(sekunden?|bearbeitungszeit|bearbeitungsdauer|beantwortung|antwortzeit|reaktionszeit)\b",
    r"\b(wie\s+lange|dauer|telefonanruf)\b.*\b(hotline|ticket)\b",
    r"\b(bearbeitungszeit|telefonanruf).*\b(sekunden?|dauer)\b",
)

# Telefonanruf: 17.03.2026 13:20 -->09471/8097-19 (Stefan Graf): Erfolgreich: (65 Sek.)
_TELEFON_LINE_RE = re.compile(
    r"Telefonanruf:\s*(?P<datetime>\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})\s*-->\s*"
    r"(?P<phone>[^:(]+?)\s*\((?P<employee>[^)]+)\):\s*"
    r"(?P<status>[^:]+):\s*\((?P<seconds>\d+)\s*Sek\.?\)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PhoneCallDuration:
    datetime: str
    phone: str
    employee: str
    status: str
    seconds: int


@dataclass(frozen=True)
class TicketDurationRow:
    ticket_id: str
    cluster: str
    bereich: str
    calls: tuple[PhoneCallDuration, ...]

    @property
    def total_seconds(self) -> int:
        return sum(c.seconds for c in self.calls)

    @property
    def call_count(self) -> int:
        return len(self.calls)


@dataclass
class BereichDurationStats:
    tickets_total: int = 0
    tickets_with_calls: int = 0
    calls_total: int = 0
    seconds_total: int = 0


@dataclass
class TicketDurationSummary:
    scope: str = "all"
    tickets_total: int = 0
    tickets_with_calls: int = 0
    calls_total: int = 0
    seconds_total: int = 0
    seconds_mean_per_call: float = 0.0
    seconds_median_per_call: float = 0.0
    seconds_mean_per_ticket: float = 0.0
    seconds_median_per_ticket: float = 0.0
    status_counts: dict[str, int] = field(default_factory=dict)
    bereich_stats: dict[str, BereichDurationStats] = field(default_factory=dict)
    top_clusters: list[tuple[str, int, int]] = field(default_factory=list)


def normalize_bereich(bereich: str) -> str:
    """Gruppiert unbekannte Bereiche unter «Sonstiges»."""
    return bereich if bereich in KNOWN_BEREICHE else "Sonstiges"


def is_duration_question(question: str) -> bool:
    lower = (question or "").lower()
    return any(re.search(p, lower) for p in DURATION_QUESTION_PATTERNS)


def extract_phone_call_durations(raw_html: str) -> list[PhoneCallDuration]:
    """Extrahiert Telefonanruf-Dauern aus rohem Ticket-HTML."""
    text = (raw_html or "").replace("&gt;", ">")
    calls: list[PhoneCallDuration] = []
    for match in _TELEFON_LINE_RE.finditer(text):
        calls.append(
            PhoneCallDuration(
                datetime=match.group("datetime").strip(),
                phone=match.group("phone").strip(),
                employee=match.group("employee").strip(),
                status=match.group("status").strip(),
                seconds=int(match.group("seconds")),
            )
        )
    return calls


def _scope_matches(
    cluster: str,
    bereich: str,
    *,
    scope: DurationScope,
    filter_bereich: str | None,
) -> bool:
    if scope == "all":
        return True
    if scope == "tera":
        return is_tera_hotline_cluster(cluster)
    if scope == "bereich":
        return bereich == filter_bereich
    raise ValueError(f"Unbekannter Scope: {scope}")


def iter_ticket_durations(
    html_root: Path | None = None,
    *,
    scope: DurationScope = "all",
    bereich: str | None = None,
) -> Iterator[TicketDurationRow]:
    """Liefert HTML-Tickets mit extrahierten Telefonanruf-Dauern (Scope-filterbar)."""
    root = html_root or TICKETS_HTML_DIR
    if not root.exists():
        return

    for path in sorted(root.rglob("*.html")):
        cluster = module_label(root, path)
        ticket_bereich = bereich_label(root, path)
        if not _scope_matches(cluster, ticket_bereich, scope=scope, filter_bereich=bereich):
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        calls = extract_phone_call_durations(raw)
        if not calls:
            continue
        yield TicketDurationRow(
            ticket_id=path.stem,
            cluster=cluster,
            bereich=ticket_bereich,
            calls=tuple(calls),
        )


def aggregate_ticket_durations(
    html_root: Path | None = None,
    *,
    scope: DurationScope = "all",
    bereich: str | None = None,
) -> TicketDurationSummary:
    """Aggregiert Telefonanruf-Sekunden für HTML-Hotline-Tickets."""
    root = html_root or TICKETS_HTML_DIR
    summary = TicketDurationSummary(scope=scope if scope != "bereich" else f"bereich:{bereich}")

    if not root.exists():
        return summary

    all_call_seconds: list[int] = []
    ticket_totals: list[int] = []
    cluster_seconds: dict[str, int] = {}
    cluster_calls: dict[str, int] = {}

    for path in root.rglob("*.html"):
        cluster = module_label(root, path)
        ticket_bereich = bereich_label(root, path)
        if not _scope_matches(cluster, ticket_bereich, scope=scope, filter_bereich=bereich):
            continue

        summary.tickets_total += 1
        bereich_key = normalize_bereich(ticket_bereich)
        bereich_stat = summary.bereich_stats.setdefault(bereich_key, BereichDurationStats())
        bereich_stat.tickets_total += 1

        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        calls = extract_phone_call_durations(raw)
        if not calls:
            continue

        summary.tickets_with_calls += 1
        bereich_stat.tickets_with_calls += 1
        summary.calls_total += len(calls)
        bereich_stat.calls_total += len(calls)

        ticket_sec = 0
        for call in calls:
            summary.seconds_total += call.seconds
            bereich_stat.seconds_total += call.seconds
            all_call_seconds.append(call.seconds)
            ticket_sec += call.seconds
            status = call.status or "unbekannt"
            summary.status_counts[status] = summary.status_counts.get(status, 0) + 1
            cluster_seconds[cluster] = cluster_seconds.get(cluster, 0) + call.seconds
            cluster_calls[cluster] = cluster_calls.get(cluster, 0) + 1
        ticket_totals.append(ticket_sec)

    if all_call_seconds:
        summary.seconds_mean_per_call = round(statistics.mean(all_call_seconds), 1)
        summary.seconds_median_per_call = round(statistics.median(all_call_seconds), 1)
    if ticket_totals:
        summary.seconds_mean_per_ticket = round(statistics.mean(ticket_totals), 1)
        summary.seconds_median_per_ticket = round(statistics.median(ticket_totals), 1)

    summary.top_clusters = sorted(
        (
            (cluster, cluster_calls.get(cluster, 0), cluster_seconds.get(cluster, 0))
            for cluster in cluster_seconds
        ),
        key=lambda row: row[2],
        reverse=True,
    )
    return summary


@lru_cache(maxsize=2)
def duration_summary(scope: str = "all") -> TicketDurationSummary:
    if scope == "tera":
        return aggregate_ticket_durations(scope="tera")
    return aggregate_ticket_durations(scope="all")


def clear_duration_cache() -> None:
    duration_summary.cache_clear()


def _format_number(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def format_duration_evidence_markdown(
    *,
    scope: DurationScope = "all",
    question: str = "",
    top_n: int = 5,
) -> str:
    """Markdown-Evidenzblock: Bearbeitungszeit = Telefonanruf-Sekunden aus HTML-Tickets."""
    summary = (
        aggregate_ticket_durations(scope="tera")
        if scope == "tera"
        else aggregate_ticket_durations(scope="all")
    )

    if summary.tickets_total == 0:
        scope_hint = "TERA (`teraWinData`)" if scope == "tera" else "HTML-Hotline"
        return (
            f"### Bearbeitungszeit ({scope_hint})\n"
            "- (keine HTML-Tickets im Scope gefunden)"
        )

    if scope == "tera":
        title = "### TERA Bearbeitungszeit — Telefonanruf-Sekunden (HTML-Tickets, verbindlich)"
        source = "**Quelle:** `Telefonanruf: … (XX Sek.)` in Hotline-HTML unter `teraWinData`."
        scope_line = f"- TERA-Tickets gesamt: **{summary.tickets_total}**"
        answer_prefix = "TERA-Mitarbeiter"
    else:
        title = "### Hotline Bearbeitungszeit — Telefonanruf-Sekunden (alle HTML-Tickets, verbindlich)"
        source = (
            "**Quelle:** `Telefonanruf: … (XX Sek.)` in Hotline-HTML "
            "(`teraWinData`, `riwaGisData`, `otsBauData`, …)."
        )
        scope_line = f"- HTML-Tickets gesamt: **{summary.tickets_total}**"
        answer_prefix = "Hotline-Mitarbeiter"

    lines = [
        title,
        source,
        "**Semantik:** Sekunden = Dauer pro dokumentiertem Telefonkontakt (RIWA-Mitarbeiter ↔ Kunde), "
        "nicht ERP-Lizenzen und nicht Ticket-Anzahl.",
        scope_line,
        f"- Tickets mit Telefonanruf-Dauer: **{summary.tickets_with_calls}** "
        f"({round(100.0 * summary.tickets_with_calls / summary.tickets_total, 1)} %)",
        f"- Telefonanrufe gesamt: **{summary.calls_total}**",
        f"- Summe Sekunden: **{_format_number(summary.seconds_total)}**",
        f"- Ø pro Anruf: **{summary.seconds_mean_per_call}** Sek. "
        f"(Median **{summary.seconds_median_per_call}** Sek.)",
        f"- Ø pro Ticket (nur mit Anrufen): **{summary.seconds_mean_per_ticket}** Sek. "
        f"(Median **{summary.seconds_median_per_ticket}** Sek.)",
    ]

    if is_duration_question(question) and summary.calls_total:
        lines.append(
            f"- **Antwort (verbindlich):** {answer_prefix} haben in **{summary.calls_total}** "
            f"dokumentierten Telefonanrufen insgesamt **{_format_number(summary.seconds_total)}** Sekunden "
            f"({summary.seconds_total / 3600:.1f} h) bearbeitet; "
            f"Ø **{summary.seconds_mean_per_call}** Sek. pro Anruf."
        )

    if summary.bereich_stats and scope != "tera":
        lines.append("\n**Nach Bereich/Produktlinie:**")
        order = (*KNOWN_BEREICHE, "Sonstiges")
        for key in order:
            stat = summary.bereich_stats.get(key)
            if not stat or stat.tickets_total == 0:
                continue
            pct = round(100.0 * stat.tickets_with_calls / stat.tickets_total, 1) if stat.tickets_total else 0
            lines.append(
                f"- **{key}** — {stat.tickets_total} Tickets, "
                f"{stat.tickets_with_calls} mit Anruf ({pct} %), "
                f"{stat.calls_total} Anrufe, {_format_number(stat.seconds_total)} Sek."
            )

    if summary.status_counts:
        top_status = sorted(summary.status_counts.items(), key=lambda kv: kv[1], reverse=True)[:4]
        status_s = ", ".join(f"{name} {count}×" for name, count in top_status)
        lines.append(f"- Anruf-Status (Top): {status_s}")

    if summary.top_clusters:
        lines.append(f"\n**Top {min(top_n, len(summary.top_clusters))} Cluster nach Telefon-Sekunden:**")
        for cluster, calls, seconds in summary.top_clusters[:top_n]:
            leaf = cluster.rsplit("\\", 1)[-1]
            lines.append(f"- **{leaf}** — {_format_number(seconds)} Sek. ({calls} Anrufe)")

    return "\n".join(lines)
