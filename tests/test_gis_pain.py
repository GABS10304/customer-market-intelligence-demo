"""Tests für GIS-scoped Pain-Point-Analyse (riwaGisData)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

for _mod in ("google.cloud", "google.cloud.bigquery", "langchain_core", "langchain_core.documents"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pandas as pd

from core.gis_pain import (
    clear_gis_pain_cache,
    collect_gis_theme_scores,
    format_gis_combined_evidence_markdown,
    format_gis_context_help_markdown,
    format_gis_module_prioritization_markdown,
    format_gis_pain_markdown,
    is_gis_context_help_question,
    is_gis_focused_question,
    is_gis_hotline_cluster,
    is_gis_module_view_requested,
    is_gis_pain_question,
    should_include_gis_module_view,
    should_include_gis_thematic_view,
    wants_gis_module_only_view,
)


SAMPLE_DETAIL = pd.DataFrame(
    [
        {
            "cluster": "riwaGisData\\Apps - KartenApp",
            "cluster_leaf": "Apps - KartenApp",
            "tickets": 112,
        },
        {
            "cluster": "riwaGisData\\Modul - Bebauungsplan (bp)",
            "cluster_leaf": "Modul - Bebauungsplan (bp)",
            "tickets": 89,
        },
        {
            "cluster": "riwaGisData\\RGZ Client - Installation",
            "cluster_leaf": "RGZ Client - Installation",
            "tickets": 76,
        },
        {
            "cluster": "riwaGisData\\verbindung-netzwerk",
            "cluster_leaf": "verbindung-netzwerk",
            "tickets": 168,
        },
        {
            "cluster": "riwaGisData\\login-verwaltung",
            "cluster_leaf": "login-verwaltung",
            "tickets": 151,
        },
        {
            "cluster": "riwaGisData\\export-daten",
            "cluster_leaf": "export-daten",
            "tickets": 146,
        },
        {
            "cluster": "teraWinData\\export-dienst",
            "cluster_leaf": "export-dienst",
            "tickets": 999,
        },
        {
            "cluster": "otsBauData\\Bauantrag",
            "cluster_leaf": "Bauantrag",
            "tickets": 500,
        },
    ]
)

SAMPLE_SIGNALS = pd.DataFrame(
    [
        {
            "mapping_id": "karten_app",
            "modul": "KartenApp",
            "hotline_tickets": 112,
            "feldbesuche": 2,
            "signale_gesamt": 114,
            "reach_nutzer": 450,
            "impact_proxy": 51300.0,
            "umfrage_avg_nps": 3.2,
        },
        {
            "mapping_id": "modul_bebauungsplan",
            "modul": "Modul Bebauungsplan",
            "hotline_tickets": 89,
            "feldbesuche": 1,
            "signale_gesamt": 90,
            "reach_nutzer": 320,
            "impact_proxy": 28800.0,
            "umfrage_avg_nps": 2.8,
        },
        {
            "mapping_id": "tera_fri",
            "modul": "TERA-FRI",
            "hotline_tickets": 500,
            "feldbesuche": 0,
            "signale_gesamt": 500,
            "reach_nutzer": 800,
            "impact_proxy": 400000.0,
            "umfrage_avg_nps": 3.0,
        },
    ]
)


def test_is_gis_hotline_cluster_scope() -> None:
    assert is_gis_hotline_cluster("riwaGisData\\Modul - Friedhof (fh)")
    assert is_gis_hotline_cluster("riwaGisData\\Modul - Verkehr (vk)")
    assert not is_gis_hotline_cluster("teraWinData\\export-dienst")
    assert not is_gis_hotline_cluster("otsBauData\\Bauantrag")
    assert not is_gis_hotline_cluster("")


EXACT_RIWA_CONTEXT_HELP_QUESTION = (
    "5 painpoints bei den kontexsensitive hilfe das hotline aufkommen reduzieren wird bei RIWA."
)


def test_is_gis_pain_question_detection() -> None:
    assert is_gis_focused_question("5 pain points RIWA GIS-Zentrum")
    assert is_gis_focused_question("5 painpoints bei RIWA")
    assert is_gis_focused_question(EXACT_RIWA_CONTEXT_HELP_QUESTION)
    assert is_gis_pain_question("Was sind die 5 Haupt pain points im RIWA GIS-Zentrum?")
    assert is_gis_pain_question("Hot spots kontextsensitive Hilfe riwaGis")
    assert is_gis_pain_question(EXACT_RIWA_CONTEXT_HELP_QUESTION)
    assert is_gis_context_help_question(EXACT_RIWA_CONTEXT_HELP_QUESTION)
    assert not is_gis_pain_question("Pain Points bei TERA Produkten")
    assert not is_gis_focused_question("Pain Points bei TERA Produkten")
    assert not is_gis_pain_question("Welche Module haben die meisten Tickets?")
    assert not is_gis_pain_question("TERA GIS-Schnittstelle pain points")


@patch("core.gis_pain.gis_hotline_detail", return_value=SAMPLE_DETAIL)
@patch("core.gis_pain._gis_freetext_samples", return_value={})
def test_collect_gis_theme_scores_ignores_tera_and_otsbau(mock_samples, mock_detail) -> None:
    clear_gis_pain_cache()
    scores = collect_gis_theme_scores()
    total = sum(int(data["score"]) for data in scores.values())
    assert total == 541
    assert total != 1499


@patch("core.gis_pain.gis_hotline_detail", return_value=SAMPLE_DETAIL)
@patch("core.gis_pain._gis_freetext_samples", return_value={})
def test_format_gis_pain_markdown_excludes_tera(mock_samples, mock_detail) -> None:
    clear_gis_pain_cache()
    md = format_gis_pain_markdown(
        top_n=5,
        question="Was sind die 5 Haupt pain points im RIWA GIS-Zentrum?",
    )
    assert "riwaGisData" in md
    assert "teraWinData" in md
    assert "Hotline HTML / riwaGisData (GIS Pain, live — kein Snapshot-Overlap)" in md
    assert "export-dienst" not in md
    assert "999" not in md
    assert "Bauantrag" not in md
    assert "Verbindung" in md or "Login" in md or "Export" in md


@patch("core.gis_pain.gis_hotline_detail", return_value=SAMPLE_DETAIL)
@patch("core.gis_pain._gis_freetext_samples", return_value={})
def test_format_gis_context_help_markdown_includes_suggestions(mock_samples, mock_detail) -> None:
    clear_gis_pain_cache()
    md = format_gis_context_help_markdown(top_n=5, question=EXACT_RIWA_CONTEXT_HELP_QUESTION)
    assert "Kontextsensitive Hilfe" in md
    assert "Kontext-Hilfe:" in md
    assert "Hotline HTML / riwaGisData (GIS Pain, live — kein Snapshot-Overlap)" in md
    assert "Sekundär — Top-GIS-Cluster" in md
    assert "999" not in md
    assert "export-dienst" not in md


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df")
@patch("core.evidence_orchestrator._format_tera_block", return_value="### TERA")
def test_orchestrator_uses_gis_pain_domain(mock_tera, mock_signals, mock_trust) -> None:
    from core.evidence_orchestrator import assemble_assistant_context
    from core.trust_status import TrustStatus
    from workspace.snapshot import WorkspaceSnapshot

    mock_signals.return_value = pd.DataFrame()
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
    ws = WorkspaceSnapshot.from_dict(
        {
            "fingerprint": "fp",
            "built_at": "2026-07-16T08:00:00+00:00",
            "cluster_counts": {},
            "source_themes": {},
            "data_coverage": [],
        }
    )

    with patch("core.gis_pain.gis_hotline_detail", return_value=SAMPLE_DETAIL):
        with patch("core.gis_pain._gis_freetext_samples", return_value={}):
            clear_gis_pain_cache()
            ctx = assemble_assistant_context(
                "5 pain points RIWA GIS-Zentrum",
                ["support_tickets_html", "survey_freetext_250"],
                ws,
            )

    assert "GIS Pain" in ctx.domains
    combined = "\n".join(ctx.user_blocks)
    assert "Quellen-Overlap (Themen)" not in combined
    assert "export-dienst" not in combined
    assert "GIS Pain" in combined
    assert "Sicht 1" in combined or "GIS Pain Points" in combined


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df")
@patch("core.evidence_orchestrator._format_tera_block", return_value="### TERA")
def test_orchestrator_routes_riwa_context_help_question(mock_tera, mock_signals, mock_trust) -> None:
    from core.evidence_orchestrator import assemble_assistant_context, build_assistant_system_prompt
    from core.trust_status import TrustStatus
    from workspace.snapshot import WorkspaceSnapshot

    mock_signals.return_value = pd.DataFrame()
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
    ws = WorkspaceSnapshot.from_dict(
        {
            "fingerprint": "fp",
            "built_at": "2026-07-16T08:00:00+00:00",
            "cluster_counts": {},
            "source_themes": {},
            "data_coverage": [],
        }
    )

    with patch("core.gis_pain.gis_hotline_detail", return_value=SAMPLE_DETAIL):
        with patch("core.gis_pain._gis_freetext_samples", return_value={}):
            clear_gis_pain_cache()
            ctx = assemble_assistant_context(
                EXACT_RIWA_CONTEXT_HELP_QUESTION,
                ["support_tickets_html", "survey_freetext_250", "field_visits"],
                ws,
            )

    assert "GIS Pain" in ctx.domains
    combined = "\n".join(ctx.user_blocks)
    assert "Quellen-Overlap (Themen)" not in combined
    assert "Top Bedürfnisse / Cluster (Snapshot)" not in combined
    assert "Kontextsensitive Hilfe" in combined
    assert "Kontext-Hilfe:" in combined

    system = build_assistant_system_prompt(
        selected_sources=["support_tickets_html"],
        question=EXACT_RIWA_CONTEXT_HELP_QUESTION,
    )
    assert "Top-5 ausschließlich" not in system
    assert "Sicht 1" in system
    assert "Sicht 2" in system
    assert "Feldbesuche" in system
    assert "Keine geschätzten Prozentanteile" in system
    assert "%-Anteile" in system
    assert "überlappen" in system


def test_gis_module_view_detection() -> None:
    assert is_gis_module_view_requested("RIWA Modul-Priorisierung nach Product Signals")
    assert is_gis_module_view_requested("Zweite Sicht Cluster bei RIWA GIS")
    assert should_include_gis_module_view(EXACT_RIWA_CONTEXT_HELP_QUESTION)
    assert should_include_gis_thematic_view(EXACT_RIWA_CONTEXT_HELP_QUESTION)
    assert not wants_gis_module_only_view(EXACT_RIWA_CONTEXT_HELP_QUESTION)
    assert wants_gis_module_only_view("Nur Modul-Priorisierung bei RIWA GIS ohne Themen")
    assert should_include_gis_module_view("Nur Modul-Priorisierung bei RIWA GIS ohne Themen")
    assert not should_include_gis_thematic_view("Nur Modul-Priorisierung bei RIWA GIS ohne Themen")


@patch("core.gis_pain._gis_mapping_ids_from_hotline", return_value={"karten_app", "modul_bebauungsplan"})
@patch("core.gis_pain.gis_hotline_detail", return_value=SAMPLE_DETAIL)
@patch("core.gis_pain._gis_freetext_samples", return_value={})
def test_format_gis_module_prioritization_markdown(mock_samples, mock_detail, mock_gis_ids) -> None:
    clear_gis_pain_cache()
    md = format_gis_module_prioritization_markdown(SAMPLE_SIGNALS, top_n=5)
    assert "Sicht 2" in md
    assert "Top-Cluster riwaGisData" in md
    assert "Product Signals CSV (ohne TERA)" in md
    assert "RGZ Client - Installation" in md or "RGZ-Modul" in md
    assert "KartenApp" in md
    assert "112" in md
    assert "Bebauungsplan" in md
    assert "Impact" in md
    assert "Reach" in md
    assert "TERA-FRI" not in md
    assert "999" not in md


@patch("core.gis_pain._gis_mapping_ids_from_hotline", return_value={"karten_app", "modul_bebauungsplan"})
@patch("core.gis_pain.gis_hotline_detail", return_value=SAMPLE_DETAIL)
@patch("core.gis_pain._gis_freetext_samples", return_value={})
def test_format_gis_combined_includes_both_views(mock_samples, mock_detail, mock_gis_ids) -> None:
    clear_gis_pain_cache()
    md = format_gis_combined_evidence_markdown(
        question=EXACT_RIWA_CONTEXT_HELP_QUESTION,
        signals_df=SAMPLE_SIGNALS,
        top_n=5,
    )
    assert "Zwei Sichten" in md
    assert "Sicht 1" in md
    assert "Sicht 2" in md
    assert "Kontext-Hilfe:" in md
    assert "Top-Themen" in md
    assert "Sekundär — Top-GIS-Cluster" not in md
    assert "Product Signals CSV (ohne TERA)" in md
    assert "**nicht** Snapshot oder Quellen-Overlap" in md
    assert "KartenApp" in md
    assert "nicht disjunkt" in md
    assert "%-Anteil" in md or "keine %-Anteil" in md
    assert "Reduktionen schätzen" in md


@patch("core.gis_pain._gis_mapping_ids_from_hotline", return_value={"karten_app", "modul_bebauungsplan"})
@patch("core.gis_pain.gis_hotline_detail", return_value=SAMPLE_DETAIL)
@patch("core.gis_pain._gis_freetext_samples", return_value={})
def test_format_gis_combined_module_only(mock_samples, mock_detail, mock_gis_ids) -> None:
    clear_gis_pain_cache()
    md = format_gis_combined_evidence_markdown(
        question="Nur Modul-Priorisierung bei RIWA GIS ohne Themen",
        signals_df=SAMPLE_SIGNALS,
    )
    assert "Sicht 2" in md
    assert "Sicht 1" not in md
    assert "Kontext-Hilfe:" not in md
    assert "Product Signals CSV (ohne TERA)" in md


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df")
@patch("core.evidence_orchestrator._format_tera_block", return_value="### TERA")
def test_orchestrator_combined_gis_context_help_includes_sicht2(
    mock_tera, mock_signals, mock_trust
) -> None:
    from core.evidence_orchestrator import assemble_assistant_context
    from core.trust_status import TrustStatus
    from workspace.snapshot import WorkspaceSnapshot

    mock_signals.return_value = SAMPLE_SIGNALS
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
    ws = WorkspaceSnapshot.from_dict(
        {
            "fingerprint": "fp",
            "built_at": "2026-07-16T08:00:00+00:00",
            "cluster_counts": {},
            "source_themes": {},
            "data_coverage": [],
        }
    )

    with patch("core.gis_pain.gis_hotline_detail", return_value=SAMPLE_DETAIL):
        with patch("core.gis_pain._gis_freetext_samples", return_value={}):
            with patch(
                "core.gis_pain._gis_mapping_ids_from_hotline",
                return_value={"karten_app", "modul_bebauungsplan"},
            ):
                clear_gis_pain_cache()
                ctx = assemble_assistant_context(
                    EXACT_RIWA_CONTEXT_HELP_QUESTION,
                    ["support_tickets_html"],
                    ws,
                )

    combined = "\n".join(ctx.user_blocks)
    assert "Sicht 1" in combined
    assert "Sicht 2" in combined
    assert "Kontext-Hilfe:" in combined
    assert "Product Signals CSV (ohne TERA)" in combined
    assert "Hotline HTML / riwaGisData (GIS Pain, live — kein Snapshot-Overlap)" in combined
    impact_section = combined.split("Product Signals CSV (ohne TERA)", 1)[1].split("###", 1)[0]
    assert "TERA-FRI" not in impact_section
