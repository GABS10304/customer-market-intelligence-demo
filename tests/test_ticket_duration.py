"""Tests für Hotline-Ticket-Bearbeitungszeit (alle HTML-Bereiche)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.ticket_duration import (
    aggregate_ticket_durations,
    format_duration_evidence_markdown,
    is_duration_question,
    iter_ticket_durations,
    normalize_bereich,
)

SAMPLE_HTML = """
Telefonanruf: 10.03.2026 10:30 -->09621/10-1816 (Markus Willecke): Erfolgreich: (475 Sek.)
<p>Kundenanfrage</p>
Telefonanruf: 11.03.2026 11:22 -->09621/10-1816 (Markus Willecke): Erfolgreich: (56 Sek.)
"""

RIWA_HTML = """
Telefonanruf: 10.03.2026 10:15 -->0971/801-1161 (Sandro Schmitt): Erfolgreich: (949 Sek.)
"""

OTS_HTML = """
Telefonanruf: 12.03.2026 09:00 -->0931/123-456 (Anna Test): Erfolgreich: (120 Sek.)
"""


def test_is_duration_question_positive_without_tera():
    assert is_duration_question("Wie viele Sekunden brauchten Hotline-Mitarbeiter?")
    assert is_duration_question("Bearbeitungszeit in Hotline-Tickets")
    assert is_duration_question("Telefonanruf Dauer pro Ticket?")


def test_is_duration_question_negative():
    assert not is_duration_question("Wie viele TERA Tickets gibt es?")


def test_normalize_bereich_groups_unknown():
    assert normalize_bereich("riwaGisData") == "riwaGisData"
    assert normalize_bereich("gisData") == "Sonstiges"


def test_iter_ticket_durations_all_scope(tmp_path: Path):
    root = tmp_path / "html"
    tera_dir = root / "teraWinData" / "alkis"
    riwa_dir = root / "riwaGisData" / "Modul - Verkehr"
    ots_dir = root / "otsBauData" / "Bau"
    for d in (tera_dir, riwa_dir, ots_dir):
        d.mkdir(parents=True)

    (tera_dir / "4040001.html").write_text(SAMPLE_HTML, encoding="utf-8")
    (riwa_dir / "4040002.html").write_text(RIWA_HTML, encoding="utf-8")
    (ots_dir / "4040003.html").write_text(OTS_HTML, encoding="utf-8")

    rows = list(iter_ticket_durations(root, scope="all"))
    assert len(rows) == 3
    bereiche = {r.bereich for r in rows}
    assert bereiche == {"teraWinData", "riwaGisData", "otsBauData"}
    riwa_row = next(r for r in rows if r.bereich == "riwaGisData")
    assert riwa_row.total_seconds == 949


def test_iter_ticket_durations_riwa_bereich_scope(tmp_path: Path):
    root = tmp_path / "html"
    tera_dir = root / "teraWinData" / "alkis"
    riwa_dir = root / "riwaGisData" / "Modul - Verkehr"
    tera_dir.mkdir(parents=True)
    riwa_dir.mkdir(parents=True)

    (tera_dir / "4040001.html").write_text(SAMPLE_HTML, encoding="utf-8")
    (riwa_dir / "4040002.html").write_text(RIWA_HTML, encoding="utf-8")

    rows = list(iter_ticket_durations(root, scope="bereich", bereich="riwaGisData"))
    assert len(rows) == 1
    assert rows[0].bereich == "riwaGisData"
    assert rows[0].total_seconds == 949


def test_aggregate_ticket_durations_all_scope_with_bereich_breakdown(tmp_path: Path):
    root = tmp_path / "html"
    tera_dir = root / "teraWinData" / "alkis"
    riwa_dir = root / "riwaGisData" / "Modul - Verkehr"
    ots_dir = root / "otsBauData" / "Bau"
    for d in (tera_dir, riwa_dir, ots_dir):
        d.mkdir(parents=True)

    (tera_dir / "4040001.html").write_text(SAMPLE_HTML, encoding="utf-8")
    (riwa_dir / "4040002.html").write_text(RIWA_HTML, encoding="utf-8")
    (ots_dir / "4040003.html").write_text(OTS_HTML, encoding="utf-8")

    summary = aggregate_ticket_durations(root, scope="all")
    assert summary.tickets_total == 3
    assert summary.tickets_with_calls == 3
    assert summary.calls_total == 4
    assert summary.seconds_total == 1600
    assert summary.bereich_stats["teraWinData"].seconds_total == 531
    assert summary.bereich_stats["riwaGisData"].seconds_total == 949
    assert summary.bereich_stats["otsBauData"].seconds_total == 120


def test_format_duration_evidence_markdown_all_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "html"
    riwa_dir = root / "riwaGisData" / "Modul - Verkehr"
    riwa_dir.mkdir(parents=True)
    (riwa_dir / "4040002.html").write_text(RIWA_HTML, encoding="utf-8")

    monkeypatch.setattr("core.ticket_duration.TICKETS_HTML_DIR", root)

    md = format_duration_evidence_markdown(
        scope="all",
        question="Wie viele Sekunden in Hotline-Tickets?",
    )
    assert "Hotline Bearbeitungszeit" in md
    assert "riwaGisData" in md
    assert "949" in md
    assert "Antwort (verbindlich)" in md
