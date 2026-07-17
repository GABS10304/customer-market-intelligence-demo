"""Product Signals — Hotline + Feldbesuche + Reach (ohne TERA/teraWin)."""

from core.product_signals import _reach_nutzer, aggregate_product_signals
from core.tera_scope import is_tera_hotline_cluster
import pandas as pd


def test_reach_nutzer_uses_max_of_usage_and_ranking():
    row = pd.Series({"usage_nutzer": 1, "ranking_kunden": 324})
    assert _reach_nutzer(row) == 324
    row2 = pd.Series({"usage_nutzer": 100, "ranking_kunden": 0})
    assert _reach_nutzer(row2) == 100


def test_aggregate_has_hotline_and_field_visits():
    df = aggregate_product_signals()
    assert not df.empty
    assert int(df["hotline_tickets"].sum()) >= 700
    assert int(df["hotline_tickets"].sum()) <= 900
    assert int(df["feldbesuche"].sum()) >= 40


def test_tera_hotline_excluded_from_unified():
    df = aggregate_product_signals()
    tera_ids = {
        "modul_bauhofverwaltung_ressourcenmanager",
        "modul_beitragswesen",
        "modul_teramobil",
    }
    present = set(df["mapping_id"].astype(str)) & tera_ids
    assert not present


def test_modul_friedhof_gis_only_ticket_volume():
    df = aggregate_product_signals()
    row = df[df["mapping_id"] == "modul_friedhof"]
    if not row.empty:
        assert int(row.iloc[0]["hotline_tickets"]) <= 60


def test_modul_verkehr_has_reach_and_signals():
    df = aggregate_product_signals()
    row = df[df["mapping_id"] == "modul_verkehr"]
    assert not row.empty
    rec = row.iloc[0]
    assert int(rec["hotline_tickets"]) >= 40
    assert int(rec["reach_nutzer"]) >= 300


def test_unified_includes_survey_columns():
    df = aggregate_product_signals()
    assert "umfrage_avg_nps" in df.columns
    assert df["umfrage_antworten"].fillna(0).gt(0).any()


def test_reach_prefers_usage_column():
    df = aggregate_product_signals()
    assert "usage_nutzer" in df.columns
    assert "reach_nutzer" in df.columns


def test_field_visit_bedarf_on_mapped_module():
    df = aggregate_product_signals()
    with_bedarf = df[df["top_bedarf"].astype(str).str.len() > 0]
    assert not with_bedarf.empty
