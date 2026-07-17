"""Tests für workspace.snapshot (ohne Live-BigQuery)."""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

for _mod in ("google.cloud", "google.cloud.bigquery", "langchain_core", "langchain_core.documents"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from core.sales_evidence import SALES_TECHNICAL_NAME
from workspace.snapshot import (
    SnapshotLoadResult,
    WorkspaceSnapshot,
    _overlap_lines,
    _theme_matrix,
    invalidate_workspace_snapshot,
    load_workspace_snapshot,
)


def _rich_snapshot_dict() -> dict:
    return {
        "fingerprint": "fp-test",
        "built_at": "2026-07-16T08:00:00+00:00",
        "cluster_counts": {
            "support:30": [
                {"quelle": "Support-Tickets", "cluster": "riwaGisData\\Modul - Verkehr", "anzahl": 42},
                {"quelle": "Support-Tickets", "cluster": "riwaGisData\\Modul - Friedhof", "anzahl": 18},
            ],
            "support:10": [
                {"quelle": "Support-Tickets", "cluster": "riwaGisData\\Modul - Verkehr", "anzahl": 42},
            ],
            "surveys:30": [
                {"quelle": "Kundenumfragen", "cluster": "Export", "anzahl": 12},
            ],
            "surveys:10": [
                {"quelle": "Kundenumfragen", "cluster": "Export", "anzahl": 12},
            ],
        },
        "source_themes": {
            "support_tickets_html": {
                "Export": {"score": 10, "clusters": ["riwaGisData\\Modul - Verkehr (42×)"], "samples": []},
                "Performance": {"score": 3, "clusters": [], "samples": []},
            },
            "survey_freetext_250": {
                "Export": {"score": 8, "clusters": ["Export (12×)"], "samples": []},
            },
        },
        "data_coverage": [{"source": "support", "rows": 100}],
        "sales_top_products": [
            {"cluster": "Modul Verkehr", "anzahl": 50, "Kundentyp": "Behörde"},
        ],
        "sales_top_revenue": [
            {"cluster": "Modul Verkehr", "umsatz": 120000.0, "Kundentyp": "Behörde"},
        ],
        "sales_total_revenue": 500000.0,
        "priority_matrix": [
            {
                "produkt": "Modul Verkehr",
                "produktlinie": "Modul",
                "summe_umsatz": 120000.0,
                "anzahl_kunden": 50,
                "ticket_cluster": "riwaGisData\\Modul - Verkehr",
                "ticket_anzahl": 42,
                "match_score": 0.9,
                "match_art": "exact",
                "mapping_id": "modul_verkehr",
                "prioritaet_score": 8.5,
                "prioritaet_stufe": "hoch",
            }
        ],
        "intent_by_group": [],
        "intent_by_module": [
            {
                "modul": "Modul Verkehr",
                "summe_umsatz": 120000.0,
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


@pytest.fixture
def ws() -> WorkspaceSnapshot:
    return WorkspaceSnapshot.from_dict(_rich_snapshot_dict())


def test_top_needs_and_hotline_frequency(ws: WorkspaceSnapshot):
    top = ws.top_needs(["support_tickets_html"], limit=5)
    assert not top.empty
    assert int(top.iloc[0]["anzahl"]) == 42

    hotline = ws.hotline_frequency(["support_tickets_html"])
    assert len(hotline) == 1

    empty = ws.hotline_frequency(["survey_freetext_250"])
    assert empty.empty


def test_compare_sources_and_overlap(ws: WorkspaceSnapshot):
    selected = ["support_tickets_html", "survey_freetext_250"]
    cmp_df = ws.compare_sources(selected, top_n=5)
    assert len(cmp_df) >= 2

    themes = ws.compare_themes(selected)
    assert not themes.empty
    assert "Export" in set(themes["Thema"])

    overlap = ws.find_overlap(selected)
    assert overlap
    assert any("Export" in line for line in overlap)


def test_product_line_breakdown(ws: WorkspaceSnapshot):
    selected = ["support_tickets_html", SALES_TECHNICAL_NAME]
    breakdown = ws.product_line_breakdown(selected)
    assert not breakdown.empty
    assert "signale" in breakdown.columns
    assert breakdown["signale"].sum() > 0


def test_sales_and_priority(ws: WorkspaceSnapshot):
    rev = ws.sales_revenue(limit=5)
    assert float(rev.iloc[0]["umsatz"]) == 120000.0
    assert ws.sales_total_revenue == 500000.0

    prio = ws.product_priority(limit=5)
    assert prio.iloc[0]["produkt"] == "Modul Verkehr"
    summary = ws.priority_summary(limit=2)
    assert summary


def test_module_intent_table(ws: WorkspaceSnapshot):
    table = ws.module_intent_table(limit=5)
    assert table.iloc[0]["modul"] == "Modul Verkehr"
    assert table.iloc[0]["dominant_intent"] == "How-To"


def test_deterministic_strategy(ws: WorkspaceSnapshot):
    strat = ws.deterministic_strategy(["support_tickets_html", "survey_freetext_250"])
    assert strat["confidence"] in ("high", "medium", "low")
    assert strat["actions"]


def test_theme_matrix_and_overlap_helpers():
    per_source = {
        "a": {
            "Export": {"score": 10, "clusters": ["c1"], "samples": []},
            "Performance": {"score": 0, "clusters": [], "samples": []},
        },
        "b": {
            "Export": {"score": 6, "clusters": ["c2"], "samples": []},
        },
    }
    matrix = _theme_matrix(per_source)
    assert not matrix.empty
    export_row = matrix[matrix["Thema"] == "Export"].iloc[0]
    assert export_row["Overlap"] == "\u2705"

    lines = _overlap_lines(matrix, min_score=5)
    assert any("Export" in line for line in lines)

    empty_lines = _overlap_lines(pd.DataFrame(), min_score=5)
    assert "Keine Themen-Daten" in empty_lines[0]


@patch("workspace.snapshot.DEMO_MODE", False)
@patch("workspace.snapshot.build_fingerprint", return_value="fp-test")
@patch("workspace.snapshot._load_snapshot_file")
def test_load_workspace_snapshot_from_disk(mock_load, mock_fp):
    mock_load.return_value = _rich_snapshot_dict()
    result = load_workspace_snapshot(force_rebuild=False)
    assert isinstance(result, SnapshotLoadResult)
    assert result.source == "disk"
    assert not result.stale
    assert result.snapshot.fingerprint == "fp-test"


@patch("workspace.snapshot.DEMO_MODE", False)
@patch("workspace.snapshot.build_fingerprint", return_value="new-fp")
@patch("workspace.snapshot._load_snapshot_file")
def test_load_workspace_snapshot_marks_stale(mock_load, mock_fp):
    mock_load.return_value = _rich_snapshot_dict()
    result = load_workspace_snapshot(force_rebuild=False)
    assert result.stale
    assert "Rohdaten" in result.stale_reason


@patch("workspace.snapshot.DEMO_MODE", False)
@patch("workspace.snapshot._build_snapshot_data")
@patch("workspace.snapshot._save_snapshot")
@patch("workspace.snapshot._load_snapshot_file", return_value=None)
def test_load_workspace_snapshot_rebuilds_when_missing(mock_load, mock_save, mock_build):
    mock_build.return_value = _rich_snapshot_dict()
    result = load_workspace_snapshot(force_rebuild=False)
    assert result.source == "bigquery"
    mock_save.assert_called_once()


@patch("workspace.snapshot.DEMO_MODE", False)
@patch("workspace.snapshot.SNAPSHOT_PATH")
def test_invalidate_workspace_snapshot(mock_path):
    mock_path.exists.return_value = True
    invalidate_workspace_snapshot()
    mock_path.unlink.assert_called_once()
