"""Trust status aggregation."""

from unittest.mock import patch

import pandas as pd

from core.hotline_inventory import HotlineInventory, clear_hotline_inventory_cache, hotline_inventory
from core.survey_inventory import SurveyInventory
from core.trust_status import build_trust_status
from workspace.product_signals_dashboard import load_signals_dataframe, prepare_signals_view


def test_trust_status_levels():
    view = prepare_signals_view(load_signals_dataframe())
    trust = build_trust_status(view)
    assert trust.level in ("hoch", "mittel", "niedrig")
    assert trust.matrix_rows == len(view)
    assert 0 <= trust.matrix_mapped_pct <= 100


def test_trust_status_hotline_aligned_excludes_tera_scope():
    """Product Signals (761) + TERA (271) = Scraper (1032) — kein falscher Mismatch."""
    clear_hotline_inventory_cache()
    view = prepare_signals_view(load_signals_dataframe())
    hotline_sum = int(view["hotline_tickets"].sum()) if not view.empty else 0
    inv = hotline_inventory(product_signals_sum=hotline_sum)
    if inv.scraper_scope_count and inv.tera_scope_count:
        assert inv.product_signals_scope_count == inv.scraper_scope_count - inv.tera_scope_count
        if hotline_sum == inv.product_signals_scope_count:
            assert inv.aligned is True
            trust = build_trust_status(view, hotline_sum=hotline_sum)
            assert trust.hotline_aligned is True
            assert "Hotline-Zählung nicht überall identisch" not in " ".join(trust.warnings)


def test_survey_match_does_not_block_portfolio_hoch():
    """Niedriger Umfrage-Match darf Portfolio-Vertrauen nicht auf mittel drücken."""
    df = pd.DataFrame(
        {
            "mapping_id": ["mod_a", "mod_b"],
            "modul": ["Mod A", "Mod B"],
            "hotline_tickets": [50, 50],
        }
    )
    inv = HotlineInventory(
        html_files=100,
        html_readable=100,
        html_skipped_short=0,
        scraper_scope_count=100,
        bigquery_rows=100,
        backlog_csv_rows=100,
        product_signals_sum=100,
        tera_scope_count=0,
    )
    survey = SurveyInventory("tickets_b.csv", raw_rows=543, matched_rows=383, product_attributions=400, products_with_survey=12)

    with (
        patch("core.hotline_inventory.hotline_inventory", return_value=inv),
        patch("core.survey_inventory.survey_inventory", return_value=survey),
        patch("core.product_mapping.load_mapping_entries", return_value=[{"id": "mod_a"}]),
        patch("core.runtime.rag_freshness", return_value=(True, "ok")),
        patch("core.trust_status.load_rag_meta", return_value={"documents": 100, "built_at": "2026-07-16T10:00:00"}),
    ):
        trust = build_trust_status(df, hotline_sum=100)

    assert trust.survey_match_pct == 70.5
    assert trust.level == "hoch"
    assert not any("Umfrage" in w for w in trust.warnings)
