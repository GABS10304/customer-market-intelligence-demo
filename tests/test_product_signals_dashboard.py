"""Tests für Product Signals Dashboard."""

import pandas as pd

from workspace.product_signals_dashboard import prepare_signals_view


def test_prepare_signals_view_adds_produktlinie():
    df = pd.DataFrame(
        {
            "mapping_id": ["modul_verkehr"],
            "modul": ["Modul Verkehr"],
            "hotline_tickets": [10],
            "feldbesuche": [2],
            "signale_gesamt": [12],
            "reach_nutzer": [100],
        }
    )
    view = prepare_signals_view(df)
    assert view.iloc[0]["produktlinie"] == "Modul"
    assert bool(view.iloc[0]["is_mapped"])
    assert bool(view.iloc[0]["has_reach"])
