"""Tests für Synonym-Cluster (Intent-Lexikon)."""

from core.intent_lexicon import (
    any_cluster_hit,
    cluster_hits,
    load_clusters,
    suggest_terms_from_text,
)


def test_ux_reibung_cluster_muehsam_umstaendlich():
    assert any_cluster_hit("aktuell mühselig", "ux_reibung")
    assert any_cluster_hit("sehr umständlich", "ux_reibung")
    assert not any_cluster_hit("Massendruck gewünscht", "ux_reibung")


def test_cluster_hits_returns_matched_term():
    hits = cluster_hits("mühselig und lang", "ux_reibung")
    assert "mühselig" in hits


def test_suggest_unknown_terms_for_bedarf():
    unknown = suggest_terms_from_text("Qualitätssicherung mühselig", bedarf="UX-Kritik")
    assert "qualitätssicherung" in unknown
    assert "mühselig" not in unknown


def test_load_clusters_has_builtins():
    clusters = load_clusters()
    assert "ux_reibung" in clusters
    assert "mühselig" in clusters["ux_reibung"]["terms"]
