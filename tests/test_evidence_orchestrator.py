"""Tests für Evidence Orchestrator (Phase 1, ohne LLM/Live-API)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

# BigQuery optional in Test-Umgebung — langchain_core nicht stubben (bricht andere Tests).
for _mod in ("google.cloud", "google.cloud.bigquery"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pandas as pd

from core.sales_evidence import SALES_TECHNICAL_NAME
from core.evidence_orchestrator import (
    assemble_assistant_context,
    detect_assistant_mode,
)
from workspace.snapshot import WorkspaceSnapshot


def _minimal_ws() -> WorkspaceSnapshot:
    return WorkspaceSnapshot.from_dict(
        {
            "fingerprint": "abc123",
            "built_at": "2026-07-16T08:00:00+00:00",
            "cluster_counts": {
                "support:30": [
                    {"quelle": "Support-Tickets", "cluster": "riwaGisData\\Modul - Verkehr", "anzahl": 42}
                ],
            },
            "source_themes": {},
            "data_coverage": [],
            "sales_top_products": [],
            "sales_top_revenue": [],
            "sales_total_revenue": 0.0,
            "priority_matrix": [],
            "intent_by_group": [],
            "intent_by_module": [],
        }
    )


SAMPLE_SIGNALS = pd.DataFrame(
    [
        {
            "mapping_id": "modul_verkehr",
            "modul": "Modul Verkehr",
            "hotline_tickets": 42,
            "feldbesuche": 3,
            "signale_gesamt": 45,
            "reach_nutzer": 300,
            "impact_proxy": 1200.0,
            "umfrage_avg_nps": 3.5,
            "umfrage_antworten": 10,
        }
    ]
)


def test_detect_assistant_mode_strategy():
    assert detect_assistant_mode("Erstelle eine KI-Strategie auf Basis der Daten") == "strategy"


def test_detect_assistant_mode_initiative():
    assert detect_assistant_mode("Initiative prüfen: ChatGPT für FAQ") == "initiative"


def test_detect_assistant_mode_answer_default():
    assert detect_assistant_mode("Welche Module haben die meisten Tickets?") == "answer"


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df", return_value=SAMPLE_SIGNALS)
@patch("core.evidence_orchestrator._format_tera_block", return_value="### TERA\n- TERA-RES")
@patch("core.evidence_orchestrator.is_graylog_usage_question", return_value=False)
def test_assemble_includes_core_domains(mock_graylog_q, mock_tera, mock_signals, mock_trust):
    from core.trust_status import TrustStatus

    mock_trust.return_value = TrustStatus(
        level="mittel",
        summary="ok",
        snapshot_at="",
        snapshot_source="",
        mapping_seed_entries=0,
        matrix_rows=1,
        matrix_mapped=1,
        matrix_mapped_pct=100.0,
        hotline_unmapped_pct=0.0,
        hotline_aligned=True,
        survey_match_pct=80.0,
        rag_fresh=True,
        rag_label="ok",
        rag_documents=100,
        product_signals_label="",
        warnings=(),
        actions=(),
        top_unmapped=(),
    )
    ctx = assemble_assistant_context(
        "Welche Module haben die meisten Hotline-Tickets?",
        ["support_tickets_html"],
        _minimal_ws(),
    )
    assert ctx.mode == "answer"
    assert "Snapshot" in ctx.domains
    assert "Product Signals" in ctx.domains
    assert "TERA" in ctx.domains
    assert "Trust" in ctx.domains
    combined = "\n".join(ctx.user_blocks)
    assert "Modul Verkehr" in combined
    assert mock_tera.called


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df", return_value=SAMPLE_SIGNALS)
def test_assemble_strategy_mode(mock_signals, mock_trust):
    from core.trust_status import TrustStatus

    mock_trust.return_value = TrustStatus(
        level="mittel",
        summary="ok",
        snapshot_at="",
        snapshot_source="",
        mapping_seed_entries=0,
        matrix_rows=0,
        matrix_mapped=0,
        matrix_mapped_pct=0.0,
        hotline_unmapped_pct=0.0,
        hotline_aligned=True,
        survey_match_pct=0.0,
        rag_fresh=True,
        rag_label="ok",
        rag_documents=0,
        product_signals_label="",
        warnings=(),
        actions=(),
        top_unmapped=(),
    )
    ctx = assemble_assistant_context(
        "Erstelle KI-Strategie",
        ["support_tickets_html"],
        _minimal_ws(),
    )
    assert ctx.mode == "strategy"
    assert "KI-Strategie" in ctx.domains
    assert any("KI-Strategie" in block for block in ctx.user_blocks)


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator.build_graylog_usage_report")
@patch("core.evidence_orchestrator._load_product_signals_df", return_value=SAMPLE_SIGNALS)
@patch("core.evidence_orchestrator._format_tera_block", return_value="### TERA")
def test_assemble_graylog_on_usage_question(mock_tera, mock_signals, mock_graylog, mock_trust):
    from core.trust_status import TrustStatus

    mock_trust.return_value = TrustStatus(
        level="mittel",
        summary="ok",
        snapshot_at="",
        snapshot_source="",
        mapping_seed_entries=0,
        matrix_rows=0,
        matrix_mapped=0,
        matrix_mapped_pct=0.0,
        hotline_unmapped_pct=0.0,
        hotline_aligned=True,
        survey_match_pct=0.0,
        rag_fresh=True,
        rag_label="ok",
        rag_documents=0,
        product_signals_label="",
        warnings=(),
        actions=(),
        top_unmapped=(),
    )
    from core.graylog_analytics import GraylogUsageReport

    mock_graylog.return_value = GraylogUsageReport(
        days=365,
        stream_label="RGZ Statistik",
        messages_fetched=100,
        events_total=100,
        module_field="event",
        chunk_capped=False,
        top_overall=(),
        top_alkis=(),
        built_at="2026-07-16T08:00:00+00:00",
    )
    ctx = assemble_assistant_context(
        "Top 10 Funktionen nach Aufrufzahl im GIS letztes Jahr",
        ["support_tickets_html"],
        _minimal_ws(),
    )
    assert ctx.graylog_used is True
    assert "Graylog" in ctx.domains
    mock_graylog.assert_called_once()


def _trust_status():
    from core.trust_status import TrustStatus

    return TrustStatus(
        level="mittel",
        summary="ok",
        snapshot_at="",
        snapshot_source="",
        mapping_seed_entries=0,
        matrix_rows=1,
        matrix_mapped=1,
        matrix_mapped_pct=100.0,
        hotline_unmapped_pct=0.0,
        hotline_aligned=True,
        survey_match_pct=80.0,
        rag_fresh=True,
        rag_label="ok",
        rag_documents=100,
        product_signals_label="",
        warnings=(),
        actions=(),
        top_unmapped=(),
    )


def _rich_ws() -> WorkspaceSnapshot:
    return WorkspaceSnapshot.from_dict(
        {
            "fingerprint": "abc123",
            "built_at": "2026-07-16T08:00:00+00:00",
            "cluster_counts": {
                "support:30": [
                    {"quelle": "Support-Tickets", "cluster": "riwaGisData\\Modul - Verkehr", "anzahl": 42}
                ],
            },
            "source_themes": {
                "support_tickets_html": {
                    "Export": {"score": 10, "clusters": ["c1"], "samples": []},
                }
            },
            "data_coverage": [],
            "sales_top_products": [],
            "sales_top_revenue": [{"cluster": "Modul Verkehr", "umsatz": 50000.0, "Kundentyp": "Behörde"}],
            "sales_total_revenue": 50000.0,
            "priority_matrix": [
                {
                    "produkt": "Modul Verkehr",
                    "produktlinie": "Modul",
                    "summe_umsatz": 50000.0,
                    "anzahl_kunden": 10,
                    "ticket_cluster": "riwaGisData\\Modul - Verkehr",
                    "ticket_anzahl": 42,
                    "match_score": 0.9,
                    "match_art": "exact",
                    "mapping_id": "modul_verkehr",
                    "prioritaet_score": 7.5,
                    "prioritaet_stufe": "hoch",
                }
            ],
            "intent_by_group": [],
            "intent_by_module": [
                {
                    "modul": "Modul Verkehr",
                    "summe_umsatz": 50000.0,
                    "eintraege": 42,
                    "dominant_intent": "How-To",
                    "top_bedarf": "Schulung",
                    "Defekt": 5,
                    "How-To": 20,
                    "Discovery": 3,
                    "quellen": "Hotline",
                }
            ],
        }
    )


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df", return_value=SAMPLE_SIGNALS)
@patch("core.evidence_orchestrator._format_tera_block", return_value="### TERA\n- full")
def test_assemble_initiative_mode(mock_tera, mock_signals, mock_trust):
    mock_trust.return_value = _trust_status()
    ctx = assemble_assistant_context(
        "Initiative prüfen: ChatGPT für FAQ",
        ["support_tickets_html"],
        _minimal_ws(),
    )
    assert ctx.mode == "initiative"
    assert "Initiative" in ctx.domains
    assert any("Phase 2" in block for block in ctx.user_blocks)


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df", return_value=SAMPLE_SIGNALS)
@patch("core.evidence_orchestrator._format_tera_block", return_value="### TERA\n- full")
def test_assemble_priority_intent_feel_domains(mock_tera, mock_signals, mock_trust):
    mock_trust.return_value = _trust_status()
    ctx = assemble_assistant_context(
        "Priorität Modul Verkehr: Umsatz vs Tickets und Intent How-To, NPS Feel?",
        ["support_tickets_html", SALES_TECHNICAL_NAME],
        _rich_ws(),
    )
    assert "Priorität" in ctx.domains
    assert "Intent" in ctx.domains
    assert "Feel" in ctx.domains
    combined = "\n".join(ctx.user_blocks)
    assert "Modul Verkehr" in combined


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df", return_value=SAMPLE_SIGNALS)
def test_assemble_tera_full_on_explicit_question(mock_signals, mock_trust):
    mock_trust.return_value = _trust_status()
    with patch("core.evidence_orchestrator._format_tera_block", return_value="### TERA\n- full") as mock_tera:
        assemble_assistant_context(
            "Wie hoch ist der TERA Support-Druck für teraWin?",
            ["support_tickets_html"],
            _minimal_ws(),
        )
        mock_tera.assert_called_once_with(
            top_n=10,
            full=True,
            question="Wie hoch ist der TERA Support-Druck für teraWin?",
        )


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df", return_value=SAMPLE_SIGNALS)
def test_build_snapshot_system_context_stale(mock_signals, mock_trust):
    from core.evidence_orchestrator import build_snapshot_system_context

    mock_trust.return_value = _trust_status()
    md = build_snapshot_system_context(
        _minimal_ws(),
        ["support_tickets_html"],
        snapshot_stale=True,
        snapshot_stale_reason="Rebuild nötig",
    )
    assert "veraltet" in md
    assert "Rebuild nötig" in md


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df", return_value=SAMPLE_SIGNALS)
@patch(
    "core.evidence_orchestrator._format_tera_duration_block",
    return_value="### TERA Bearbeitungszeit\n- 531 Sek.",
)
@patch("core.evidence_orchestrator._format_tera_block", return_value="### TERA\n- full")
def test_assemble_tera_duration_on_bearbeitungszeit_question(
    mock_tera, mock_duration, mock_signals, mock_trust
):
    mock_trust.return_value = _trust_status()
    ctx = assemble_assistant_context(
        "Wie viele Sekunden brauchten TERA Mitarbeiter für die Beantwortung?",
        ["support_tickets_html"],
        _minimal_ws(),
    )
    assert "TERA Bearbeitungszeit" in ctx.domains
    mock_duration.assert_called_once()
    combined = "\n".join(ctx.user_blocks)
    assert "TERA Bearbeitungszeit" in combined


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df", return_value=SAMPLE_SIGNALS)
@patch(
    "core.evidence_orchestrator._format_duration_block",
    return_value="### Hotline Bearbeitungszeit\n- 1600 Sek.",
)
@patch("core.evidence_orchestrator._format_tera_block", return_value="### TERA\n- full")
def test_assemble_all_duration_on_bearbeitungszeit_question(
    mock_tera, mock_duration, mock_signals, mock_trust
):
    mock_trust.return_value = _trust_status()
    ctx = assemble_assistant_context(
        "Wie viele Sekunden brauchten Hotline-Mitarbeiter für die Beantwortung?",
        ["support_tickets_html"],
        _minimal_ws(),
    )
    assert "Hotline Bearbeitungszeit" in ctx.domains
    assert "TERA Bearbeitungszeit" not in ctx.domains
    mock_duration.assert_called_once()
    combined = "\n".join(ctx.user_blocks)
    assert "Hotline Bearbeitungszeit" in combined


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df", return_value=SAMPLE_SIGNALS)
@patch(
    "core.evidence_orchestrator._format_duration_block",
    return_value="### Hotline Bearbeitungszeit\n- 1600 Sek.",
)
@patch("core.evidence_orchestrator._format_tera_block", return_value="### TERA\n- full")
def test_trust_block_scopes_reliability_for_duration(
    mock_tera, mock_duration, mock_signals, mock_trust
):
    from core.trust_status import TrustStatus

    mock_trust.return_value = TrustStatus(
        level="niedrig",
        summary="Portfolio verzerrt",
        snapshot_at="",
        snapshot_source="",
        mapping_seed_entries=0,
        matrix_rows=1,
        matrix_mapped=0,
        matrix_mapped_pct=20.0,
        hotline_unmapped_pct=60.0,
        hotline_aligned=False,
        survey_match_pct=70.0,
        rag_fresh=False,
        rag_label="veraltet",
        rag_documents=50,
        product_signals_label="",
        warnings=("Hotline-Zählung nicht überall identisch",),
        actions=(),
        top_unmapped=(),
    )
    ctx = assemble_assistant_context(
        "Wie viele Sekunden brauchten Hotline-Mitarbeiter für die Beantwortung?",
        ["support_tickets_html"],
        _minimal_ws(),
        snapshot_stale=True,
        snapshot_stale_reason="Rebuild nötig",
    )
    combined = "\n".join(ctx.user_blocks)
    assert "Portfolio-Level: **niedrig**" in combined
    assert "**Hotline Bearbeitungszeit:** hoch" in combined
    assert "unabhängig vom Snapshot" in combined


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator.build_graylog_usage_report")
@patch("core.evidence_orchestrator._load_product_signals_df", return_value=SAMPLE_SIGNALS)
@patch("core.evidence_orchestrator._format_tera_block", return_value="### TERA\n- full")
def test_trust_block_scope_hint_on_broad_question(mock_tera, mock_signals, mock_graylog, mock_trust):
    from core.graylog_analytics import GraylogUsageReport

    mock_graylog.return_value = GraylogUsageReport(
        days=365,
        stream_label="RGZ Statistik",
        messages_fetched=0,
        events_total=0,
        module_field="event",
        chunk_capped=False,
        top_overall=(),
        top_alkis=(),
        built_at="2026-07-16T08:00:00+00:00",
    )
    mock_trust.return_value = _trust_status()
    ctx = assemble_assistant_context(
        "Welche Module haben die meisten Tickets?",
        ["support_tickets_html"],
        _minimal_ws(),
    )
    combined = "\n".join(ctx.user_blocks)
    assert "Scope-Hinweis" in combined


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df", return_value=SAMPLE_SIGNALS)
@patch(
    "core.evidence_orchestrator._format_tera_duration_block",
    return_value="### TERA Bearbeitungszeit\n- 531 Sek.",
)
@patch("core.evidence_orchestrator._format_tera_block", return_value="### TERA\n- full")
def test_trust_block_no_scope_hint_when_specific(
    mock_tera, mock_duration, mock_signals, mock_trust
):
    mock_trust.return_value = _trust_status()
    ctx = assemble_assistant_context(
        "Wie viele Sekunden brauchten TERA Mitarbeiter für die Beantwortung?",
        ["support_tickets_html"],
        _minimal_ws(),
    )
    combined = "\n".join(ctx.user_blocks)
    assert "Scope-Hinweis" not in combined


def test_system_prompt_forbids_invented_percentages_and_reductions():
    from core.evidence_orchestrator import build_assistant_system_prompt

    system = build_assistant_system_prompt(
        selected_sources=["support_tickets_html"],
        question="Welche Module haben die meisten Tickets?",
    )
    assert "Keine geschätzten Prozentanteile" in system
    assert "≈X% der Tickets" in system
    assert "Reduktionsprognosen" in system
    assert "Themen-Ticket-Summen nicht als Anteil" in system
    assert "nicht disjunkt" in system or "überlappen" in system
    assert "nicht erfinden" in system


def test_system_prompt_gis_hint_forbids_percent_share_claims():
    from core.evidence_orchestrator import build_assistant_system_prompt

    system = build_assistant_system_prompt(
        selected_sources=["support_tickets_html"],
        question="Was sind die Pain Points im RIWA GIS Zentrum?",
    )
    assert "Themen-Ticket-Summen nicht als Anteil" in system
    assert "Snapshot oder Quellen-Overlap nicht als Herkunft nennen" in system
    assert "%-Anteile" in system
    assert "Reduktions" in system


def test_system_prompt_tera_hint_forbids_percent_share_claims():
    from core.evidence_orchestrator import build_assistant_system_prompt

    system = build_assistant_system_prompt(
        selected_sources=["support_tickets_html"],
        question="Was sind die 5 Haupt pain points bei den TERA Produkten?",
    )
    assert "keine %-Anteile am Gesamtvolumen" in system
    assert "Reduktionsprognosen" in system
