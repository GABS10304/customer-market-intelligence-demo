"""Tests für TERA-Ticket-Bearbeitungszeit aus HTML-Tickets."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.tera_scope import is_tera_hotline_cluster
from core.tera_ticket_duration import (
    aggregate_tera_ticket_durations,
    extract_phone_call_durations,
    format_tera_duration_evidence_markdown,
    is_tera_duration_question,
    iter_tera_ticket_durations,
)

SAMPLE_HTML = """
Telefonanruf: 10.03.2026 10:30 -->09621/10-1816 (Markus Willecke): Erfolgreich: (475 Sek.)
<p>Kundenanfrage</p>
Telefonanruf: 11.03.2026 11:22 -->09621/10-1816 (Markus Willecke): Erfolgreich: (56 Sek.)
"""

SAMPLE_HTML_ENTITY = (
    '<div class="richContent_froala">'
    "Telefonanruf: 18.03.2026 10:30 --&gt;0931 8003-5679 (J&ouml;rg Ei&szlig;ner): Erfolgreich: (1690 Sek.)"
    "</div>"
)

NON_TERA_HTML = """
Telefonanruf: 10.03.2026 10:15 -->0971/801-1161 (Sandro Schmitt): Erfolgreich: (949 Sek.)
"""


def test_extract_phone_call_durations_parses_seconds():
    calls = extract_phone_call_durations(SAMPLE_HTML)
    assert len(calls) == 2
    assert calls[0].seconds == 475
    assert calls[0].status == "Erfolgreich"
    assert calls[0].employee == "Markus Willecke"
    assert calls[1].seconds == 56


def test_extract_phone_call_durations_handles_html_entities():
    calls = extract_phone_call_durations(SAMPLE_HTML_ENTITY)
    assert len(calls) == 1
    assert calls[0].seconds == 1690


def test_is_tera_duration_question_positive():
    assert is_tera_duration_question("Wie viele Sekunden brauchten TERA Mitarbeiter für die Beantwortung?")
    assert is_tera_duration_question("TERA Bearbeitungszeit in Hotline-Tickets")


def test_is_tera_duration_question_negative_without_tera():
    assert not is_tera_duration_question("Wie viele Sekunden brauchten GIS Mitarbeiter?")


def test_iter_tera_ticket_durations_filters_scope(tmp_path: Path):
    root = tmp_path / "html"
    tera_dir = root / "teraWinData" / "alkis"
    riwa_dir = root / "riwaGisData" / "Modul - Verkehr"
    tera_dir.mkdir(parents=True)
    riwa_dir.mkdir(parents=True)

    (tera_dir / "4040001.html").write_text(SAMPLE_HTML, encoding="utf-8")
    (riwa_dir / "4040002.html").write_text(NON_TERA_HTML, encoding="utf-8")

    rows = list(iter_tera_ticket_durations(root))
    assert len(rows) == 1
    assert rows[0].ticket_id == "4040001"
    assert rows[0].total_seconds == 531
    assert rows[0].call_count == 2
    assert is_tera_hotline_cluster(rows[0].cluster)


def test_aggregate_tera_ticket_durations(tmp_path: Path):
    root = tmp_path / "html"
    tera_a = root / "teraWinData" / "alkis"
    tera_b = root / "teraWinData" / "vertragsmanager"
    riwa = root / "riwaGisData" / "Apps - Allgemein"
    for d in (tera_a, tera_b, riwa):
        d.mkdir(parents=True)

    (tera_a / "4040001.html").write_text(SAMPLE_HTML, encoding="utf-8")
    (tera_b / "4040002.html").write_text(
        "Telefonanruf: 26.03.2026 08:37 -->09471/7018-32 (Sebastian Schelchshorn): Erfolgreich: (147 Sek.)\n",
        encoding="utf-8",
    )
    (riwa / "4040003.html").write_text(NON_TERA_HTML, encoding="utf-8")

    summary = aggregate_tera_ticket_durations(root)
    assert summary.tickets_total == 2
    assert summary.tickets_with_calls == 2
    assert summary.calls_total == 3
    assert summary.seconds_total == 678
    assert summary.seconds_mean_per_call == pytest.approx(226.0)
    assert summary.status_counts.get("Erfolgreich") == 3
    assert summary.top_clusters[0][2] == 531


def test_format_tera_duration_evidence_markdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "html"
    tera_dir = root / "teraWinData" / "alkis"
    tera_dir.mkdir(parents=True)
    (tera_dir / "4040001.html").write_text(SAMPLE_HTML, encoding="utf-8")

    monkeypatch.setattr("core.ticket_duration.TICKETS_HTML_DIR", root)
    from core.tera_ticket_duration import clear_tera_duration_cache

    clear_tera_duration_cache()

    md = format_tera_duration_evidence_markdown(
        question="Wie viele Sekunden brauchten TERA Mitarbeiter?",
    )
    assert "TERA Bearbeitungszeit" in md
    assert "531" in md or "678" in md
    assert "Antwort (verbindlich)" in md
    assert "Telefonanruf" in md
