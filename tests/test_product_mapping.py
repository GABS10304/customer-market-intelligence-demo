"""Tests für ERP ↔ Ticket Seed-Mapping."""

from core.product_mapping import find_seed_mapping, resolve_product_tickets


def test_seed_datenpflege():
    m = find_seed_mapping("Datenpflegepaket  Geobasis-u. Fachdienstdaten RGZ")
    assert m is not None
    assert m.id == "datenpflege_geobasis_rgz"
    assert any("Datenintegration" in c for c in m.ticket_clusters)


def test_seed_landkreis_prefix():
    m = find_seed_mapping("Landkreis-GIS Ostallgäu - ab 01.01.2026")
    assert m is not None
    assert m.id == "landkreis_gis"


def test_seed_modul_bauav():
    m = find_seed_mapping("Modul Bauantragsverwaltung (BauAV)")
    assert m is not None
    assert m.id == "modul_bauav"


def test_seed_modul_vermessung():
    m = find_seed_mapping("Modul Vermessungsdaten")
    assert m is not None
    assert m.id == "modul_vermessungsdaten"


def test_seed_karten_app():
    m = find_seed_mapping("KartenApp - 10 Nutzerlizenzen")
    assert m is not None
    assert m.id == "karten_app"
    assert find_seed_mapping("Baumkontroll-App").id == "baumkontroll_app"


def test_cluster_alias_basisentwicklung():
    from core.product_mapping import resolve_cluster_mapping

    m = resolve_cluster_mapping("Basisentwicklung")
    assert m is not None
    assert m.id == "basisentwicklung_querschnitt"


def test_cluster_alias_regisafe_eakte():
    from core.product_mapping import resolve_cluster_mapping

    m = resolve_cluster_mapping("eAKte zu RegiSafe")
    assert m is not None
    assert m.id == "regisafe_eakte"


def test_cluster_alias_prosoz_schnittstelle():
    from core.product_mapping import resolve_cluster_mapping

    m = resolve_cluster_mapping("BVL Schnittstelle Prosoz")
    assert m is not None
    assert m.id == "schnittstelle_prosoz"


def test_cluster_alias_kanal_app():
    from core.product_mapping import resolve_cluster_mapping

    m = resolve_cluster_mapping("Kanal-App")
    assert m is not None
    assert m.id == "kanal_app"


def test_cluster_alias_geonotizen():
    from core.product_mapping import resolve_cluster_mapping

    m = resolve_cluster_mapping("Geonotizen")
    assert m is not None
    assert m.id == "geonotizen"


def test_cluster_alias_bebauungsplaene_bauleitplan():
    from core.product_mapping import resolve_cluster_mapping

    m = resolve_cluster_mapping("Bebauungspläne / bauleitplan")
    assert m is not None
    assert m.id == "modul_bebauungsplaene"


def test_cluster_alias_baumkontroll_app():
    from core.product_mapping import resolve_cluster_mapping

    m = resolve_cluster_mapping("Baumkontroll-App")
    assert m is not None
    assert m.id == "baumkontroll_app"


def test_cluster_alias_modul_forst():
    from core.product_mapping import resolve_cluster_mapping

    m = resolve_cluster_mapping("Forst")
    assert m is not None
    assert m.id == "modul_forst"


def test_resolve_aggregates_mapped_clusters():
    ticket_idx = {
        "riwaGisData\\RGZ Allgemein - Datenintegration": 12,
        "riwaGisData\\Datenabgabe - Geodaten": 5,
    }
    cluster, total, score, art, mid = resolve_product_tickets(
        "Datenpflegepaket Geobasis-u. Fachdienstdaten RGZ",
        ticket_idx,
        heuristic_match_fn=lambda a, t: ("", 0, 0.0),
    )
    assert art == "seed"
    assert mid == "datenpflege_geobasis_rgz"
    assert total == 17
    assert score == 1.0
    assert "Datenintegration" in cluster
