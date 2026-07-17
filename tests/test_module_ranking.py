"""Tests für Modul-Ranking → mapping_id."""

from core.module_ranking import mapping_coverage_report, resolve_ranking_modul


def test_resolve_ranking_verkehr():
    m = resolve_ranking_modul("Modul Verkehr")
    assert m.mapping_id == "modul_verkehr"
    assert m.match_kind in ("alias", "seed", "manual", "label")


def test_resolve_ranking_wasser_edit():
    m = resolve_ranking_modul("Modul Wasser Edit")
    assert m.mapping_id == "modul_wasser"
    assert m.match_kind == "alias"


def test_resolve_ranking_kanal_barthauer():
    m = resolve_ranking_modul("Modul Kanal Autor - Barthauer Struktur")
    assert m.mapping_id == "modul_kanal"


def test_resolve_ranking_friedhof_tier():
    m = resolve_ranking_modul("Modul Friedhof bis 1.000 Grabstellen")
    assert m.mapping_id == "modul_friedhof"


def test_mapping_coverage_majority_not_fallback():
    report = mapping_coverage_report()
    assert report["rows"] == 121
    assert report.get("mapped_kunden_pct", 0) >= 85.0
