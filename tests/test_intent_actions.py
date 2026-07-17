"""Tests für PM-Aktions-/Todo-Vorschläge."""

from core.intent_actions import extract_aktion_todo


def test_webinar_bestandskunden_s030():
    text = (
        "Vorschlag: bei größeren Änderungen immer Webinar für Bestandskunden anbieten "
        "zur Vorstellung der Anpassungen und der neuen Workflows"
    )
    aktion = extract_aktion_todo(text, modul="Verkehr", bedarf="UX-Kritik")
    assert aktion == "Webinar für Bestandskunden bei größeren Änderungen"


def test_vertrieb_kommuna_register_s021():
    text = (
        "Keine Anbindung von Registern möglich. Großzahl der Kommunen arbeiten mit "
        "Registern bzw. wird vom Kommuna Vertrieb so kommuniziert, dass dies möglich ist"
    )
    aktion = extract_aktion_todo(
        text,
        modul="E-Akte KIC",
        bedarf="Feature Request",
        themen=("E-Akte", "KIC", "Kommuna"),
        request_thema="Anbindung",
        request_detail="Register",
    )
    assert aktion == "Klärung Kommunikation Vertrieb Kommuna/Komuna"
