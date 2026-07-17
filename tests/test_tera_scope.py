"""TERA-Produktlinie und Scope-Trennung."""

from core.product_lines import classify_product_line, classify_product_line_with_reason
from core.tera_scope import is_riwa_portfolio_hotline_cluster, is_tera_hotline_cluster


def test_tera_hotline_cluster():
    assert is_tera_hotline_cluster("teraWinData\\friedhofsverwaltung")
    assert is_tera_hotline_cluster("teraWinData\\Bauhofverwaltung  Ressourcenmanager")
    assert not is_tera_hotline_cluster("riwaGisData\\Modul - Friedhof (fh)")


def test_riwa_portfolio_hotline_cluster():
    assert is_riwa_portfolio_hotline_cluster("riwaGisData\\Modul - Verkehr (vk)")
    assert is_riwa_portfolio_hotline_cluster("otsBauData\\eAkte")
    assert not is_riwa_portfolio_hotline_cluster("teraWinData\\beitragswesen")


def test_classify_tera_product_line():
    line, reason = classify_product_line_with_reason("teraWinData\\friedhofsverwaltung")
    assert line == "TERA"
    assert "teraWin" in reason

    assert classify_product_line("TERA-FRI") == "TERA"
    assert classify_product_line("TERA RES Technik") == "TERA"
    assert classify_product_line("riwaGisData\\Modul - Friedhof (fh)") == "Modul"


def test_friedhof_gis_still_maps():
    from core.product_mapping import load_mapping_entries, resolve_cluster_mapping

    load_mapping_entries.cache_clear()
    m = resolve_cluster_mapping("riwaGisData\\Modul - Friedhof (fh)")
    assert m is not None
    assert m.id == "modul_friedhof"

    tera = resolve_cluster_mapping("teraWinData\\friedhofsverwaltung")
    assert tera is None or tera.id != "modul_friedhof"
