"""Source Profiles — technische + menschliche Namen, BQ-Mapping."""

from __future__ import annotations

from dataclasses import dataclass

from config import BIGQUERY_FIELD_VISITS_TABLE, BIGQUERY_HTML_TABLE, BIGQUERY_SALES_TABLE, BIGQUERY_TABLE


@dataclass(frozen=True)
class SourceProfile:
    technical_name: str
    display_name: str
    bq_table: str
    cluster_column: str
    text_column_hints: tuple[str, ...]
    cluster_column_hints: tuple[str, ...]
    customer_column_hints: tuple[str, ...] = ()
    delimiter: str = ";"
    description: str = ""
    detection_keywords: tuple[str, ...] = ()


BUILTIN_PROFILES: dict[str, SourceProfile] = {
    "support_tickets_html": SourceProfile(
        technical_name="support_tickets_html",
        display_name="Hotline Tickets RIWA",
        bq_table=BIGQUERY_HTML_TABLE,
        cluster_column="Ordner___Modul",
        text_column_hints=("Original_Wortlaut_Freitext", "Original-Wortlaut (Freitext)"),
        cluster_column_hints=("Ordner___Modul", "Ordner / Modul", "Modul"),
        customer_column_hints=("Kunde",),
        description="Support- und Hotline-Tickets (HTML-Pipeline → BigQuery)",
        detection_keywords=("ordner", "modul", "ticket", "hotline", "support"),
    ),
    "survey_freetext_250": SourceProfile(
        technical_name="survey_freetext_250",
        display_name="Kundenumfragen Freitext",
        bq_table=BIGQUERY_TABLE,
        cluster_column="Kategorie",
        text_column_hints=(
            "Original_Wortlaut_Freitext",
            "Original-Wortlaut (Freitext)",
        ),
        cluster_column_hints=("Kategorie", "Category", "Problem_Kategorie"),
        customer_column_hints=("Kunde", "Customer"),
        description="NPS / Umfrage-Freitexte (~250 Einträge)",
        detection_keywords=("kategorie", "nps", "umfrage", "survey", "freitext"),
    ),
    "field_visits_weihnachtsbesuche": SourceProfile(
        technical_name="field_visits_weihnachtsbesuche",
        display_name="Weihnachtsbesuche / Feldfeedback",
        bq_table=BIGQUERY_FIELD_VISITS_TABLE,
        cluster_column="Modul_App_Verfahren",
        text_column_hints=(
            "Verbesserungsvorschlag / Kritik",
            "Verbesserungsvorschlag___Kritik",
            "Original_Wortlaut_Freitext",
            "Original-Wortlaut (Freitext)",
            "Verbesserungsvorschlag",
            "Kritik",
        ),
        cluster_column_hints=(
            "Modul/App/Verfahren",
            "Modul_App_Verfahren",
            "Modul",
            "Verfahren",
        ),
        customer_column_hints=("Kunde",),
        description="Verbesserungsvorschläge aus Kundenbesuchen (Weihnachtsbesuche etc.)",
        detection_keywords=(
            "verbesserung",
            "kritik",
            "besuch",
            "weihnacht",
            "feld",
            "vorschlag",
        ),
    ),
    "sales_product_penetration": SourceProfile(
        technical_name="sales_product_penetration",
        display_name="Verträge / Produkt-Penetration",
        bq_table=BIGQUERY_SALES_TABLE,
        cluster_column="artikelbezeichnung",
        text_column_hints=(),
        cluster_column_hints=("artikelbezeichnung", "Artikelbezeichnung", "artikel"),
        customer_column_hints=("Kundentyp",),
        description="Anonyme Modul-Penetration und ERP-Umsatz aus Vertragsdaten (Kundentyp × Produkt × Umsatz)",
        detection_keywords=("kundentyp", "artikelbezeichnung", "anzahl_kunden", "penetration", "vertrag"),
    ),
}

LEGACY_KEY_MAP = {
    "support_tickets_html": "support",
    "survey_freetext_250": "surveys",
    "field_visits_weihnachtsbesuche": "field_visits",
    "sales_product_penetration": "sales",
}


def get_profile(technical_name: str) -> SourceProfile | None:
    return BUILTIN_PROFILES.get(technical_name)


def legacy_evidence_key(technical_name: str) -> str:
    return LEGACY_KEY_MAP.get(technical_name, technical_name)


def source_short_label(technical_name: str) -> str:
    key = legacy_evidence_key(technical_name)
    return {
        "support": "Tickets",
        "surveys": "Umfragen",
        "field_visits": "Besuche",
        "sales": "Verträge",
    }.get(key, technical_name)
