"""TERA Hotline — Bearbeitungszeit aus HTML-Tickets (Backward-Compat-Wrapper)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from core.ticket_duration import (
    DURATION_QUESTION_PATTERNS,
    PhoneCallDuration,
    TicketDurationRow,
    TicketDurationSummary,
    aggregate_ticket_durations,
    extract_phone_call_durations,
    format_duration_evidence_markdown,
    iter_ticket_durations,
)

TERA_DURATION_QUESTION_PATTERNS = (
    *DURATION_QUESTION_PATTERNS,
    r"\b(tera|terawin)\b.*\b(sekunden?|bearbeitungszeit|beantwortung|antwortzeit|dauer)\b",
    r"\b(wie\s+lange|dauer|telefonanruf)\b.*\b(tera|terawin|hotline|ticket)\b",
)

TeraDurationSummary = TicketDurationSummary


def is_tera_duration_question(question: str) -> bool:
    lower = (question or "").lower()
    if not re.search(r"\b(tera|terawin)\b", lower):
        return False
    return any(re.search(p, lower) for p in TERA_DURATION_QUESTION_PATTERNS)


def iter_tera_ticket_durations(
    html_root: Path | None = None,
) -> Iterator[TicketDurationRow]:
    """Liefert TERA-Tickets (teraWinData) mit extrahierten Telefonanruf-Dauern."""
    return iter_ticket_durations(html_root, scope="tera")


def aggregate_tera_ticket_durations(
    html_root: Path | None = None,
) -> TeraDurationSummary:
    """Aggregiert Telefonanruf-Sekunden für TERA-Hotline-Tickets."""
    return aggregate_ticket_durations(html_root, scope="tera")


@lru_cache(maxsize=1)
def tera_duration_summary() -> TeraDurationSummary:
    return aggregate_tera_ticket_durations()


def clear_tera_duration_cache() -> None:
    tera_duration_summary.cache_clear()


def format_tera_duration_evidence_markdown(*, question: str = "", top_n: int = 5) -> str:
    """Markdown-Evidenzblock: Bearbeitungszeit = Telefonanruf-Sekunden aus TERA-HTML-Tickets."""
    return format_duration_evidence_markdown(scope="tera", question=question, top_n=top_n)
