"""Tests für TERA-Vergleichsmatrix (ERP vs. Hotline)."""

from __future__ import annotations

import math
import sys
from unittest.mock import MagicMock

import pandas as pd

sys.modules.setdefault("streamlit", MagicMock())

from core.tera_compare import clear_tera_compare_cache, is_tera_request_question, tera_compare_matrix
from workspace.tera_dashboard import _format_support_druck


def test_tera_compare_matrix_has_support_druck_column() -> None:
    clear_tera_compare_cache()
    df = tera_compare_matrix()
    assert "hotline_pro_100_kunden" in df.columns

    if df.empty:
        return

    col = df["hotline_pro_100_kunden"]
    assert col.dtype == float
    has_erp = df["erp_kunden"] > 0
    assert col[has_erp].notna().all()
    assert col[~has_erp].isna().all()

    sample = df.loc[has_erp].iloc[0]
    expected = round(100.0 * sample["hotline_tickets"] / sample["erp_kunden"], 1)
    assert sample["hotline_pro_100_kunden"] == expected


def test_format_support_druck_german_percent() -> None:
    assert _format_support_druck(31.0) == "31,0 %"
    assert _format_support_druck(30.9) == "30,9 %"
    assert _format_support_druck(None) == "—"
    assert _format_support_druck(float("nan")) == "—"


def test_format_support_druck_on_matrix_values() -> None:
    clear_tera_compare_cache()
    df = tera_compare_matrix()
    if df.empty:
        return

    labels = df["hotline_pro_100_kunden"].map(_format_support_druck)
    assert labels.str.contains("%").any()
    assert (labels != "—").any()


def test_is_tera_request_question_detects_anfragen() -> None:
    assert is_tera_request_question("Welches TERA-Produkt produziert die meisten Anfragen?")
    assert is_tera_request_question("TERA mit den meisten Hotline-Tickets")
    assert not is_tera_request_question("Wie hoch ist der TERA Support-Druck?")


def test_format_tera_evidence_distinguishes_requests_from_erp() -> None:
    from core.tera_compare import format_tera_evidence_markdown

    clear_tera_compare_cache()
    md = format_tera_evidence_markdown(
        question="Welches TERA-Produkt produziert die meisten Anfragen?",
        top_n=5,
    )
    assert "Semantik" in md
    assert "keine Anfragen" in md
    assert "Antwort (verbindlich)" in md
    assert "Hotline" in md

    df = tera_compare_matrix()
    if df.empty:
        return

    top_by_tickets = df.sort_values("hotline_tickets", ascending=False).iloc[0]
    assert top_by_tickets["tera_base"] in md
    assert str(int(top_by_tickets["hotline_tickets"])) in md
