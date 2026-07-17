"""Tests für Kontakt-Angebote aus Feldbesuchs-Freitext."""

from core.intent_contacts import extract_kontakt_angebot


def test_kontakt_demo_ansprechpartnerin_feb_2026():
    text = (
        "kann man sich gern bei der Demo-Ansprechpartnerin Mueller (fängt im Feb 2026 an) melden. "
        "Diese hätte konkrete Vorschläge, was man vermisst."
    )
    k = extract_kontakt_angebot(text)
    assert k.ansprechpartner == "Demo-Ansprechpartnerin Mueller"
    assert "feb 2026" in k.zeitraum.lower()
    assert "Verbesserungsvorschläge" in k.hinweis
    assert "Demo-Ansprechpartnerin Mueller" in k.summary()


def test_no_kontakt_when_absent():
    k = extract_kontakt_angebot("Massendruck-Funktion gewünscht")
    assert not k.has_offer
