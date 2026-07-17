"""Signal overview — Stimmen vs. Feel vs. Reach."""

from core.signal_inventory import signal_overview


def test_signal_overview_lanes():
    ov = signal_overview()
    assert ov.stimmen_total > 0
    assert ov.feel_skalen_total >= ov.stimmen[2].count  # freitext <= skalen
    assert ov.reach.graylog_module_rows >= 0
    assert ov.reach.ranking_module_rows >= 0
    assert "Hotline" in ov.stimmen_breakdown()
