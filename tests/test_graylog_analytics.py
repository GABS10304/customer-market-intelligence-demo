"""Unit-Tests für Graylog-Nutzungsanalyse (Assistent, ohne Live-API)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from core.graylog_analytics import (
    GraylogUsageReport,
    FunctionRank,
    analyze_messages,
    build_graylog_usage_report,
    format_usage_report_markdown,
    is_alkis_focused_question,
    is_alkis_related,
    is_graylog_usage_question,
    parse_days_from_question,
    parse_top_n_from_question,
)


SAMPLE_MESSAGES = [
    {"event": "module.gis.query.desktop", "timestamp": "2026-01-01T10:00:00.000Z"},
    {"event": "module.gis.query.desktop", "timestamp": "2026-01-01T11:00:00.000Z"},
    {"event": "module.gis.query.mobile", "timestamp": "2026-01-01T12:00:00.000Z"},
    {"event": "module.dialog.alkis.flurstuecke", "dialogName": "Flurstücke", "timestamp": "2026-01-02T10:00:00.000Z"},
    {"event": "module.dialog.alkis.eigentuemer", "dialogName": "Eigentümer", "timestamp": "2026-01-02T11:00:00.000Z"},
]


def test_is_graylog_usage_question_detects_top10():
    assert is_graylog_usage_question("Top 10 Funktionen nach Aufrufzahl im GIS letztes Jahr")
    assert is_graylog_usage_question("Welche ALKIS Dialoge haben die meisten Aufrufe?")
    assert not is_graylog_usage_question("Welche Kundenbedürfnisse dominieren?")


def test_parse_days_and_top_n():
    assert parse_days_from_question("im letzten Jahr") == 365
    assert parse_days_from_question("letzten 30 Tage") == 30
    assert parse_top_n_from_question("Top 15 nach Nutzung") == 15
    assert parse_top_n_from_question("häufigste Funktionen") == 10


def test_is_alkis_related():
    assert is_alkis_related("Flurstücke")
    assert is_alkis_related("module.dialog.alkis")
    assert not is_alkis_related("module.gis.query.desktop")


def test_analyze_messages_counts_overall_and_alkis():
    overall, alkis, total = analyze_messages(SAMPLE_MESSAGES, module_field="event", top_n=10)
    assert total == 5
    assert overall[0][0] == "module.gis.query.desktop"
    assert overall[0][1] == 2
    alkis_labels = {name for name, _ in alkis}
    assert "Flurstücke" in alkis_labels
    assert "Eigentümer" in alkis_labels


def test_is_alkis_focused_question():
    assert is_alkis_focused_question("Welche ALKIS Dialoge haben die meisten Aufrufe?")
    assert is_alkis_focused_question("Eigentümerauskunft Nutzung letztes Jahr")
    assert not is_alkis_focused_question(
        "Top 10 Funktionen nach Aufrufzahl im GIS (letztes Jahr, Graylog)?"
    )


def test_format_usage_report_general_question_omits_alkis_section():
    report = GraylogUsageReport(
        days=365,
        stream_label="RGZ Statistik",
        messages_fetched=100,
        events_total=50,
        module_field="event",
        chunk_capped=False,
        top_overall=(
            FunctionRank(rank=1, label="module.gis.query.desktop", calls=40, mapping_id="rgz_basic"),
        ),
        top_alkis=(
            FunctionRank(rank=1, label="Flurstücke", calls=5, mapping_id="datenpflege_alkis"),
        ),
        built_at=datetime.now(timezone.utc).isoformat(),
    )
    question = "Top 10 Funktionen nach Aufrufzahl im GIS (letztes Jahr, Graylog)?"
    md = format_usage_report_markdown(report, top_n=10, question=question)
    assert "module.gis.query.desktop" in md
    assert "RGZ Statistik" in md
    assert "Top 10 ALKIS" not in md
    assert "module.gis.query.*" in md
    assert "Flurstücke" not in md


def test_format_usage_report_alkis_question_includes_subset():
    report = GraylogUsageReport(
        days=365,
        stream_label="RGZ Statistik",
        messages_fetched=100,
        events_total=50,
        module_field="event",
        chunk_capped=False,
        top_overall=(
            FunctionRank(rank=1, label="module.gis.query.desktop", calls=40, mapping_id=""),
        ),
        top_alkis=(
            FunctionRank(rank=1, label="Flurstücke", calls=5, mapping_id="modul_alkis"),
        ),
        built_at=datetime.now(timezone.utc).isoformat(),
    )
    md = format_usage_report_markdown(
        report,
        top_n=10,
        question="Welche ALKIS Dialoge haben die meisten Aufrufe?",
    )
    assert "Top 10 ALKIS" in md
    assert "Flurstücke" in md


@patch("core.graylog_analytics.fetch_messages_chunked")
@patch("core.graylog_analytics.resolve_stream_ids")
@patch("core.graylog_analytics.GraylogClient")
def test_build_graylog_usage_report_offline(mock_client_cls, mock_resolve, mock_fetch):
    mock_client = MagicMock()
    mock_client.base_url = "http://graylog.test"
    mock_client_cls.return_value = mock_client
    mock_resolve.return_value = (["stream1"], {"stream1": "RGZ Statistik"})
    mock_fetch.return_value = SAMPLE_MESSAGES

    report = build_graylog_usage_report(days=30, top_n=5, use_cache=False)
    assert report.ok
    assert report.stream_label == "RGZ Statistik"
    assert report.events_total == 5
    assert report.top_overall[0].label == "module.gis.query.desktop"
