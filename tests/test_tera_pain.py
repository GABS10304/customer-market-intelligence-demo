"""Tests für TERA-scoped Pain-Point-Analyse."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

for _mod in ("google.cloud", "google.cloud.bigquery", "langchain_core", "langchain_core.documents"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pandas as pd

from core.tera_pain import (
    clear_tera_pain_cache,
    collect_tera_theme_scores,
    format_tera_pain_markdown,
    is_tera_focused_question,
    is_tera_pain_question,
)


SAMPLE_DETAIL = pd.DataFrame(
    [
        {
            "cluster": "teraWinData\\export-dienst",
            "cluster_leaf": "export-dienst",
            "tickets": 40,
            "tera_base": "TERA-FRI",
            "match_reason": "Mapping",
        },
        {
            "cluster": "teraWinData\\login-verwaltung",
            "cluster_leaf": "login-verwaltung",
            "tickets": 25,
            "tera_base": "TERA-RES",
            "match_reason": "Mapping",
        },
        {
            "cluster": "riwaGisData\\Modul - Friedhof (fh)",
            "cluster_leaf": "Modul - Friedhof (fh)",
            "tickets": 999,
            "tera_base": "—",
            "match_reason": "Kein TERA",
        },
    ]
)


def test_is_tera_pain_question_detection() -> None:
    assert is_tera_focused_question("Pain Points bei TERA Produkten")
    assert is_tera_pain_question("Was sind die 5 Haupt pain points bei den TERA Produkten?")
    assert not is_tera_pain_question("Welche Module haben die meisten Tickets?")
    assert not is_tera_pain_question("TERA Support-Druck für TERA-RES")


@patch("core.tera_pain.tera_hotline_detail", return_value=SAMPLE_DETAIL)
@patch("core.tera_pain._tera_freetext_samples", return_value={})
def test_collect_tera_theme_scores_ignores_riwa(mock_samples, mock_detail) -> None:
    clear_tera_pain_cache()
    scores = collect_tera_theme_scores()
    total = sum(int(data["score"]) for data in scores.values())
    assert total == 65
    assert total != 1064


@patch("core.tera_pain.tera_hotline_detail", return_value=SAMPLE_DETAIL)
@patch("core.tera_pain._tera_freetext_samples", return_value={})
def test_format_tera_pain_markdown_excludes_riwa(mock_samples, mock_detail) -> None:
    clear_tera_pain_cache()
    md = format_tera_pain_markdown(
        top_n=5,
        question="Was sind die 5 Haupt pain points bei den TERA Produkten?",
    )
    assert "teraWinData" in md
    assert "Modul - Friedhof" not in md
    assert "999" not in md
    assert "Export" in md or "Login" in md
    assert "nicht disjunkt" in md
    assert "Reduktionen schätzen" in md


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df")
@patch("core.evidence_orchestrator._format_tera_block", return_value="### TERA")
def test_orchestrator_uses_tera_pain_domain(mock_tera, mock_signals, mock_trust) -> None:
    import sys
    from unittest.mock import MagicMock

    for mod in ("google.cloud", "google.cloud.bigquery", "langchain_core", "langchain_core.documents"):
        sys.modules.setdefault(mod, MagicMock())

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

    with patch("core.tera_pain.tera_hotline_detail", return_value=SAMPLE_DETAIL):
        with patch("core.tera_pain._tera_freetext_samples", return_value={}):
            clear_tera_pain_cache()
            ctx = assemble_assistant_context(
                "Was sind die 5 Haupt pain points bei den TERA Produkten?",
                ["support_tickets_html", "survey_freetext_250"],
                ws,
            )

    assert "TERA Pain" in ctx.domains
    combined = "\n".join(ctx.user_blocks)
    assert "Quellen-Overlap (Themen)" not in combined
    assert "Modul - Friedhof" not in combined
    assert "TERA Pain Points" in combined
