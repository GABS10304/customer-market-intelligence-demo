"""Survey signals aggregation."""

from core.survey_signals import aggregate_survey_by_mapping, match_landkreis_to_kunde, survey_inventory


def test_landkreis_match_kelheim():
    kunde = match_landkreis_to_kunde("Kelheim")
    assert "Kelheim" in kunde or "kelheim" in kunde.lower()


def test_survey_aggregation_not_empty():
    df = aggregate_survey_by_mapping()
    assert not df.empty
    assert int(df["umfrage_antworten"].sum()) > 0


def test_survey_inventory_raw_vs_attributions():
    inv = survey_inventory()
    assert inv.raw_rows > 0
    assert inv.product_attributions >= inv.matched_rows
    assert inv.raw_rows < inv.product_attributions
