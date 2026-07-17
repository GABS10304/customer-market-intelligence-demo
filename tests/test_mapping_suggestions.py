"""Mapping suggestion generation."""

from core.mapping_suggestions import collect_unmapped_clusters, suggest_all_unmapped, suggest_mappings


def test_suggest_top_unmapped_or_fully_mapped():
    unmapped = collect_unmapped_clusters(min_tickets=10)
    if unmapped:
        suggestions = suggest_mappings(limit=5, min_tickets=10)
        assert len(suggestions) <= 5
        assert all(s.tickets_covered >= 10 for s in suggestions)
    else:
        assert suggest_all_unmapped(min_tickets=1) == []


def test_beitraege_resolves_after_bulk_map():
    from core.product_mapping import load_mapping_entries, resolve_cluster_mapping

    load_mapping_entries.cache_clear()
    m = resolve_cluster_mapping("riwaGisData\\Modul - Beiträge (er)")
    assert m is not None
    assert m.id == "modul_beiträge_er"

def test_friedhof_resolves_after_extend():
    from core.product_mapping import load_mapping_entries, resolve_cluster_mapping

    load_mapping_entries.cache_clear()
    m = resolve_cluster_mapping("riwaGisData\\Modul - Friedhof (fh)")
    assert m is not None
    assert m.id == "modul_friedhof"
    assert resolve_cluster_mapping("teraWinData\\friedhofsverwaltung") is None
