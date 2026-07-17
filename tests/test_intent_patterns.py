"""Unit-Tests für regelbasierte Intent-Klassifikation."""

from core.intent_patterns import classify_intent


def test_discovery_geo_point():
    r = classify_intent("Wie finde ich alle Daten zu diesem Geo-Punkt in der Karte?")
    assert r.intent == "Discovery"


def test_how_to_menu():
    r = classify_intent("Wo finde ich den Menüpunkt für den CSV-Export?")
    assert r.intent == "How-To"


def test_defekt():
    r = classify_intent("Das Programm stürzt ab sobald ich den Bericht öffne.")
    assert r.intent == "Defekt"


def test_installation():
    r = classify_intent("Wie installiere ich das Update auf Version 2024?")
    assert r.intent == "Installation"


def test_feature_wunsch_s045_basisentwicklung_ebenen_editierbar():
    text = "Alle Module - Darstellung von Ebenen sollte selbst editierbar sein"
    r = classify_intent(text, modul="Basisentwicklung")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert r.geltung == "Alle Module"
    assert "Basisentwicklung" in r.themen
    assert r.request_thema == "Darstellung"
    assert r.request_detail == "Ebenen selbst editierbar"
    assert "feature-wunsch" in r.matched_keywords
    assert "alle-module" in r.matched_keywords


def test_discovery_feature_wunsch_s043_bauturbo_ebene():
    text = "Bauturbo - wird es eine eigene Ebene geben oder wie wird der dann dargestellt?"
    r = classify_intent(text, modul="BauAV")
    assert r.intent == "Discovery"
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert r.themen == ("BauAV", "BauTurbo")
    assert r.request_thema == "Ebene"
    assert "eigene Ebene" in r.request_detail
    assert "Darstellung BauTurbo" in r.request_detail
    assert "bauturbo-frage" in r.matched_keywords


def test_ux_kritik_s042_gruenflaechen_filter_handbuch():
    text = (
        "sehr komplexes und umständliches Modul; Filtereinschränkung auf 100 Datensätze "
        "sehr ärgerlich und einschränkend (Berichterstellung etc.); HAndbuch ist komplett "
        "unbrauchbar für die Praxis, passt nicht zu den Inhalten der Schulung,"
    )
    r = classify_intent(text, modul="Grünflächen")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "UX-Kritik"
    assert r.confidence == "hoch"
    assert "Grünflächen" in r.themen
    assert r.request_thema == "Grünflächen"
    assert "Modul komplex/umständlich" in r.request_detail
    assert "Filterlimit 100 Datensätze" in r.request_detail
    assert "Handbuch unbrauchbar" in r.request_detail
    assert "ux-kritik" in r.matched_keywords


def test_ux_kritik_s040_versorgungsleitungen_darstellung():
    text = (
        "Jeder Kunde hat irgendwo private Sparten liegen, die ganz einfach nur dargestellt "
        "werden sollen (vgl. Modul Testleitungen in Vertriebsdemo).\n"
        "Graphische Integrationen werden schnell unübersichtlich und können nicht vom "
        "Kunden nachgebessert werden.\n"
        "Das Modul Versorgungsleitungen ist hier schon viel zu komplex."
    )
    r = classify_intent(text, modul="Versorgungsleitungen / Modulbaukasten Versorgung")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "UX-Kritik"
    assert r.confidence == "hoch"
    assert "Versorgungsleitungen" in r.themen
    assert r.request_thema == "Darstellung"
    assert "private Sparten darstellen" in r.request_detail
    assert "Testleitungen" in r.request_detail
    assert "Integration unübersichtlich" in r.request_detail
    assert "keine Kunden-Anpassung" in r.request_detail
    assert "Modul zu komplex" in r.request_detail
    assert "ux-kritik" in r.matched_keywords
    assert r.request_thema != "Integration"


def test_defekt_s039_boll_schnittstelle_probleme():
    text = "anscheinend macht BOLL-Schnittstelle immer mal wieder Probleme"
    r = classify_intent(text, modul="BVL Schnittstelle BOLL")
    assert r.intent == "Defekt"
    assert r.bedarf == "Bugmeldung"
    assert r.confidence == "hoch"
    assert "Schnittstelle BOLL" in r.themen
    assert "BOLL" in r.themen
    assert r.request_thema == "Schnittstelle"
    assert "BOLL" in r.request_detail
    assert "wiederkehrend" in r.request_detail
    assert "schnittstelle-defekt" in r.matched_keywords
    assert "feature-wunsch" not in r.matched_keywords


def test_feature_wunsch_s038_bauav_berichtsvorlage_bauturbo():
    text = (
        'Anpassung Berichtsvorlage zur Stellungnahme muss angepasst werden '
        'nach den neuen Vorgaben "BauTurbo"'
    )
    r = classify_intent(text, modul="BauAV")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert r.themen == ("BauAV", "BauTurbo")
    assert r.request_thema == "Berichtsvorlage"
    assert "Stellungnahme" in r.request_detail
    assert "BauTurbo" in r.request_detail
    assert "feature-wunsch" in r.matched_keywords


def test_feature_wunsch_s037_verkehr_onlineformular():
    text = "Anbindung an Onlineformular"
    r = classify_intent(text, modul="Verkehr")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert "Modul Verkehr" in r.themen
    assert r.request_thema == "Anbindung"
    assert r.request_detail == "Onlineformular"
    assert "feature-wunsch" in r.matched_keywords
    assert "anbindung" in r.matched_keywords


def test_update_kritik_s036_basic_programmieroberflaeche():
    text = "Umstellung auf die neue Programmieroberfläche kommt nicht so gut beim Kunden an"
    r = classify_intent(text, modul="Basic")
    assert r.intent == "Defekt"
    assert r.bedarf == "Update-Kritik"
    assert r.confidence == "hoch"
    assert "RGZ Basic" in r.themen
    assert r.request_thema == "Update/UI"
    assert "Programmieroberfläche" in r.request_detail
    assert "Akzeptanz Kunde" in r.request_detail
    assert "update-kritik" in r.matched_keywords
    assert "flaeche" not in r.matched_keywords
    assert "fläche" not in r.matched_keywords


def test_feature_wunsch_s035_eakte_kic_stapelverarbeitung():
    text = (
        "wäre sehr interessant, wenn Stapelverarbeitung und ggf. Serienbrieffunktion "
        "in ER, BauAV, FH ... funktioniert, vorher nicht"
    )
    r = classify_intent(text, modul="eAkte zu KIC")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert r.geltung == "Querschnitt"
    assert "E-Akte KIC" in r.themen
    assert "E-Akte" in r.themen
    assert r.request_thema == "Stapelverarbeitung"
    assert "Serienbrief" in r.request_detail
    assert "ER" in r.request_detail
    assert "BauAV" in r.request_detail
    assert "FH" in r.request_detail
    assert "feature-wunsch" in r.matched_keywords
    assert "querschnitt" in r.matched_keywords


def test_update_kritik_s034_verkehr_modulumstellung():
    text = "Modulumstellung mit neuer Programmierung sehr unübersichtlich"
    r = classify_intent(text, modul="Verkehr")
    assert r.intent == "Defekt"
    assert r.bedarf == "Update-Kritik"
    assert r.confidence == "hoch"
    assert "Modul Verkehr" in r.themen
    assert r.request_thema == "Update/UI"
    assert "UI unübersichtlich" in r.request_detail
    assert "update-kritik" in r.matched_keywords
    assert "ux-kritik" not in r.matched_keywords


def test_update_kritik_s024_verkehr_modulupdate():
    text = (
        "Massive Kritik an Modulupdates, sehr unübersichtlich, viel zu viele Klicks, "
        "Ausblenden von VZ war früher einfacher, ... --> am Besten Update rückgängig machen"
    )
    r = classify_intent(text, modul="Verkehr")
    assert r.intent == "Defekt"
    assert r.bedarf == "Update-Kritik"
    assert r.confidence == "hoch"
    assert "Modul Verkehr" in r.themen
    assert r.request_thema == "Update/UI"
    assert "UI unübersichtlich" in r.request_detail
    assert "zu viele Klicks" in r.request_detail
    assert "Ausblenden VZ" in r.request_detail
    assert "Update rückgängig" in r.request_detail
    assert "update-kritik" in r.matched_keywords
    assert "update" not in r.matched_keywords


def test_feature_wunsch_s025_bauantrag_schnittstelle_eakte():
    text = (
        "Schnittstelle deckt nur 10% vom logisch notwendigen Umfang ab "
        "(das kam bei vielen Kunden sehr sehr oft), Stellungnahme geht nicht direkt "
        "in die eAkte, generell Funktionsumfang eAkte..."
    )
    r = classify_intent(text, modul="Bauantrag")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert "Bauantrag" in r.themen
    assert "E-Akte" in r.themen
    assert r.request_thema == "Schnittstelle"
    assert "Umfang ~10%" in r.request_detail
    assert "Stellungnahme → eAkte" in r.request_detail
    assert "Funktionsumfang eAkte" in r.request_detail
    assert "schnittstellen-luecke" in r.matched_keywords
    assert "geht nicht" not in r.matched_keywords


def test_feature_wunsch_s001_alle_module():
    text = (
        "Alle Module - Erstellung von individuellen Berichten aus RIWA "
        "mit Ansteuerung auf die Zusatzdaten"
    )
    r = classify_intent(text, modul="Basisentwicklung")
    assert r.bedarf == "Feature Request"
    assert r.geltung == "Alle Module"
    assert r.confidence == "hoch"
    assert "feature-wunsch" in r.matched_keywords


def test_feature_wunsch_s002_regisafe_eakte():
    text = "Interesse an eAkte für RegiSafe"
    r = classify_intent(text, modul="eAKte zu RegiSafe")
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert r.themen == ("E-Akte", "RegiSafe")
    assert "E-Akte" in r.matched_keywords
    assert "RegiSafe" in r.matched_keywords


def test_feature_wunsch_s003_prosoz_schnittstelle():
    text = (
        "leider keine Daten zu Entwurfsverfassen und auch Einzeldaten "
        "zum Bauherren fehlen (Te. Nr., ...)"
    )
    r = classify_intent(text, modul="BVL Schnittstelle Prosoz")
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert "Schnittstelle Prosoz" in r.themen
    assert "schnittstellen-luecke" in r.matched_keywords


def test_feature_wunsch_s004_kanal_app_filterung():
    text = "Filterung Endhydanten für Prüfung"
    r = classify_intent(text, modul="Kanal-App")
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert r.themen == ("Kanal-App",)
    assert r.request_thema == "Filterung"
    assert r.request_detail == "Endhydranten"
    assert "filterung" in r.matched_keywords
    assert "Endhydranten" in r.matched_keywords
    assert "Kanal-App" in r.matched_keywords


def test_feature_wunsch_s005_verkehr_kommuna_schnittstelle():
    text = "Schnittstelle zu Komuna bei dem Antrag"
    r = classify_intent(text, modul="Verkehr")
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert "Modul Verkehr" in r.themen
    assert "Kommuna" in r.themen
    assert r.request_thema == "Schnittstelle"
    assert r.request_detail == "Kommuna"
    assert "schnittstelle" in r.matched_keywords
    assert "Kommuna" in r.matched_keywords


def test_s006_basisentwicklung_rgz_ui():
    text = (
        'richtige Ebene wählen, wenn mehrere übereinander sind vereinfachen, '
        'Geländeschnitt bspw. "hängt" an der Maus (ESC für deaktivieren wäre sinnvoll), '
        'beenden der geteilten Karte mündet in schwarzen Bildschirm '
        '(geteilte Karte 3d, bewegen der Karte, geteilte karte beenden, '
        'dann neu starten - bleibt schwarz), '
        'Liste Kurzbefehle als Übersicht im Programm wäre sinnvoll'
    )
    r = classify_intent(text, modul="Basisentwicklung")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "Feature Request"
    assert r.geltung == "Querschnitt"
    assert r.confidence == "hoch"
    assert "feature-wunsch" in r.matched_keywords
    assert "querschnitt" in r.matched_keywords
    assert "RGZ" in r.themen
    assert "Basisentwicklung" in r.themen
    assert "kurzbefehl" in r.matched_keywords
    assert "ebene" in r.matched_keywords
    assert "geländeschnitt" in r.matched_keywords
    assert "hängt" not in r.matched_keywords


def test_feature_wunsch_s007_vermessungsdaten_pdf():
    text = (
        "bei den VM Punkten sollte es möglich sein, neben Fotos auch pdf "
        "Dokumente zu hinterlegen (für Zugriff im Außendienst)"
    )
    r = classify_intent(text, modul="Vermessungsdaten/-App")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert "Modul Vermessungsdaten" in r.themen
    assert r.request_thema == "Dokumente"
    assert r.request_detail == "VM Punkte"
    assert "feature-wunsch" in r.matched_keywords
    assert "pdf" in r.matched_keywords
    assert "VM Punkte" in r.matched_keywords


def test_feature_wunsch_s008_bauav_uebertragung():
    text = (
        "Übertragung von dig. BauAV-Dokumenten aus Genehmigungssoftware "
        "ins Modul unbedingt gewünscht"
    )
    r = classify_intent(text, modul="BauAV")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert r.themen == ("BauAV",)
    assert r.request_thema == "Übertragung"
    assert r.request_detail == "Genehmigungssoftware"
    assert "feature-wunsch" in r.matched_keywords
    assert "übertragung" in r.matched_keywords
    assert "Genehmigungssoftware" in r.matched_keywords


def test_service_kritik_s013_bauantrag_kommunikation():
    text = (
        "Problem mit Kommunikation, Wartezeit und RÜckmeldung "
        "zur Einbindung und Umsetzung"
    )
    r = classify_intent(text, modul="Bauantrag, Bebauungspläne, FPläne etc.")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "Service-Kritik"
    assert r.confidence == "hoch"
    assert "Bauantrag" in r.themen
    assert "service-kritik" in r.matched_keywords
    assert "kommunikation" in r.matched_keywords
    assert "wartezeit" in r.matched_keywords


def test_feature_wunsch_s009_baumkontroll_offline_pdf():
    text = (
        "Gut wäre es, auch pdfs im Offline Modus in der App bereitzustellen, "
        "nicht nur Bilder"
    )
    r = classify_intent(text, modul="Baumkontroll-App")
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert r.themen == ("Baumkontroll-App",)
    assert r.request_thema == "Dokumente"
    assert r.request_detail == "Offline-Modus"
    assert "pdf" in r.matched_keywords


def test_feature_wunsch_s010_geonotizen_nachtraeglich():
    text = (
        "bei Geonotizen sollte es möglich sein, nachträglich noch weitere "
        "Dokumente / Bilder zu ergänzen, auch wenn die Notiz schon mal als "
        "abgeschlossen gekennzeichnet wurde"
    )
    r = classify_intent(text, modul="Geonotizen")
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert r.themen == ("Geonotizen",)
    assert r.request_thema == "Dokumente"
    assert r.request_detail == "nachträglich ergänzen"
    assert "dokumente" in r.matched_keywords


def test_ux_kritik_discovery_s033_bauav_faehnchen_wunsch():
    text = (
        "Darstellung mit Einzelfähnchen extrem unübersichtlich, wenn alle gescannten "
        "Bauanträge integriert sind. Wunsch: ein Fähnchen pro Flurstück und dann "
        "Absprung zu den hinterlegten Bauanträgen, oder Flächendarstellung "
        "(wie bei den LRAs künftig) oder Auswahlmöglichkeit pro Kunde "
        "(1 Fähnchen oder viele Fähnchen)"
    )
    r = classify_intent(text, modul="BauAV")
    assert r.intent == "Discovery"
    assert r.bedarf == "UX-Kritik"
    assert r.confidence == "hoch"
    assert r.themen == ("BauAV",)
    assert r.request_thema == "Darstellung"
    assert "Einzelfähnchen unübersichtlich" in r.request_detail
    assert "1 Fähnchen pro Flurstück" in r.request_detail
    assert "Absprung zu Bauanträgen" in r.request_detail
    assert "Flächendarstellung" in r.request_detail
    assert "LRA Best Practice" in r.request_detail
    assert "Auswahl pro Kunde" in r.request_detail
    assert "ux-kritik" in r.matched_keywords
    assert "darstellung-wunsch" in r.matched_keywords


def test_ux_kritik_s011_bauav_faehnchen():
    text = "Darstellung mit Einzelfähnchen oft unübersichtlich"
    r = classify_intent(text, modul="BauAV")
    assert r.bedarf == "UX-Kritik"
    assert r.confidence == "hoch"
    assert r.themen == ("BauAV",)
    assert r.request_thema == "Darstellung"
    assert r.request_detail == "Einzelfähnchen"
    assert "ux-kritik" in r.matched_keywords


def test_feature_wunsch_s012_grosses_interesse_regisafe():
    text = "großes Interesse an eAkte für RegiSafe"
    r = classify_intent(text, modul="eAKte zu RegiSafe")
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert "E-Akte" in r.themen
    assert "RegiSafe" in r.themen


def test_service_kritik_s014_gekos_schnittstelle_nicht_erfuellt():
    text = (
        "Anforderungen an Schnittstelle noch nicht erfüllt (BVL), "
        "beim THema BP muss eine nachhaltige Lösung gefunden werden"
    )
    r = classify_intent(text, modul="Schnittstelle Gekos")
    assert r.bedarf == "Service-Kritik"
    assert r.confidence == "hoch"
    assert "Schnittstelle Gekos" in r.themen
    assert "service-kritik" in r.matched_keywords
    assert "schnittstellen-luecke" not in r.matched_keywords


def test_feature_wunsch_s015_basic_massendruck_qgis():
    text = (
        "Massendruck-Funktion gewünscht (z.B. für Karten zu Katastrophenschutzübungen), "
        "ähnlich Atlas-Funktion in QGIS"
    )
    r = classify_intent(text, modul="Basic")
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert r.geltung == "Querschnitt"
    assert r.themen == ("RGZ Basic",)
    assert r.request_thema == "Massendruck"
    assert r.request_detail == "Atlas-Funktion (QGIS)"
    assert "massendruck" in r.matched_keywords


def test_dokumentations_wunsch_s016_rgz_autor_ebenen():
    text = (
        "Bedienungsanleitung, wie selbst erstellte/gezeichnete Ebenen/Layer "
        "dauerhaft sichtbar gemacht werden können  für alle"
    )
    r = classify_intent(text, modul="RGZ Autor")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "Dokumentations-Wunsch"
    assert r.confidence == "hoch"
    assert r.geltung == "Alle Module"
    assert "RGZ Autor" in r.themen
    assert r.request_thema == "Bedienungsanleitung"
    assert r.request_detail == "Ebenen dauerhaft sichtbar"
    assert "dokumentations-wunsch" in r.matched_keywords


def test_ux_kritik_s017_qualitaetssicherung_detailmasken():
    text = "Qualitätssicherung in der Detailmasken, aktuell mühselig"
    r = classify_intent(text, modul="Basisentwicklung")
    assert r.bedarf == "UX-Kritik"
    assert r.confidence == "hoch"
    assert r.geltung == "Querschnitt"
    assert "Basisentwicklung" in r.themen
    assert r.request_thema == "Qualitätssicherung"
    assert r.request_detail == "Detailmasken"
    assert "mühselig" in r.matched_keywords or "muehsam" in r.matched_keywords


def test_lexicon_muehsam_matches_ux_reibung_cluster():
    from core.intent_lexicon import cluster_hits

    assert "mühselig" in cluster_hits("aktuell mühselig", "ux_reibung")
    assert "umständlich" in cluster_hits("sehr umständlich", "ux_reibung")


def test_produkt_luecke_s019_forst_kontakt():
    text = (
        "Ist weg von der Praxis, viel zu wenige Funktionen. "
        "MAcht deswegen keinen Sinn bedarf, kann man sich gern bei dem Forstamt Musterstadt "
        "(fängt im Feb 2026 an) melden. Diese hätte konkrete Vorschläge, was man vermisst."
    )
    r = classify_intent(text, modul="Forst")
    assert r.bedarf == "Produkt-Lücke"
    assert r.confidence == "hoch"
    assert r.themen == ("Modul Forst",)
    assert r.ansprechpartner == "Forstamt Musterstadt"
    assert "feb 2026" in r.kontakt_zeitraum.lower()
    assert "Verbesserungsvorschläge" in r.kontakt_angebot
    assert "kontakt-angebot" in r.matched_keywords


def test_feature_wunsch_s020_vm_wasser_uebertragung():
    text = (
        "Übertragung von VM-Daten ins jeweilige Edit-Modul leichter gestalten. "
        "Wenn VM-Punkte bspw. Code für Schieber hinterlegt haben, könnte sich dann "
        "nicht einfach die Sachdatenmaske zu Schiebern öffnen, sodass man die befüllen "
        "kann? + Möglichkeit erst zu zeichnen und dann erst die Sachdaten einzutragen?"
    )
    r = classify_intent(text, modul="VM/Wasser")
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert "VM/Wasser" in r.themen
    assert "Modul Vermessungsdaten" in r.themen
    assert r.request_thema == "Übertragung"
    assert "VM-Daten" in r.request_detail
    assert "Sachdatenmaske Schieber" in r.request_detail
    assert "zeichnen vor Sachdaten" in r.request_detail


def test_feature_wunsch_s021_e_akte_kic_register_aktion():
    text = (
        "Keine Anbindung von Registern möglich. Großzahl der Kommunen arbeiten mit "
        "Registern bzw. wird vom Kommuna Vertrieb so kommuniziert, dass dies möglich ist"
    )
    r = classify_intent(text, modul="E-Akte KIC")
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert "E-Akte KIC" in r.themen
    assert r.request_thema == "Anbindung"
    assert r.request_detail == "Register"
    assert r.aktion_todo == "Klärung Kommunikation Vertrieb Kommuna/Komuna"
    assert "aktion-todo" in r.matched_keywords


def test_feature_wunsch_s022_geonotizen_dokumentenanbindung():
    text = "Dokumentenanbindung"
    r = classify_intent(text, modul="Geonotizen")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert r.themen == ("Geonotizen",)
    assert r.request_thema == "Anbindung"
    assert r.request_detail == "Dokumente"
    assert "feature-wunsch" in r.matched_keywords
    assert "anbindung" in r.matched_keywords
    assert "Dokumente" in r.matched_keywords


def test_service_kritik_s023_bauleitplan_rueckmeldung():
    text = (
        "Rückmeldung und Erledigung, tlw. Wochen und Monate geht nichts vorran "
        "und es gibt keine Infos"
    )
    r = classify_intent(text, modul="Bebauungspläne / bauleitplan")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "Service-Kritik"
    assert r.confidence == "hoch"
    assert "Bauantrag" in r.themen
    assert r.request_thema == "Rückmeldung"
    assert "Wartezeit" in r.request_detail
    assert "fehlende Infos" in r.request_detail
    assert "service-kritik" in r.matched_keywords
    assert "geht nicht" not in r.matched_keywords


def test_themen_e_akte_hyphen():
    from core.intent_patterns import extract_request, extract_themen

    assert "E-Akte" in extract_themen("Anbindung E-Akte an KIC", modul="")


def test_extract_request_kommuna_spelling():
    from core.intent_patterns import extract_request

    assert extract_request("Schnittstelle zu Komuna bei dem Antrag") == ("Schnittstelle", "Kommuna")
    assert extract_request("Schnittstelle zu Kommuna beim Antrag") == ("Schnittstelle", "Kommuna")


def test_feature_wunsch_s032_tera_rgz_schnittstelle():
    text = (
        "kritisiert, dass es für GEB und (wo sinnvoll) RES und VER keine Schnittstelle "
        "ins RGZ gibt, zumindest für einfachen Wechsel zwischen den Systemen und "
        "kartografischen Überblick"
    )
    r = classify_intent(text, modul="TERA & RGZ")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert "TERA" in r.themen
    assert "RGZ" in r.themen
    assert r.request_thema == "Schnittstelle"
    assert "GEB" in r.request_detail
    assert "RES" in r.request_detail
    assert "VER" in r.request_detail
    assert "RGZ" in r.request_detail
    assert "Systemwechsel" in r.request_detail
    assert "kartografischer Überblick" in r.request_detail
    assert "feature-wunsch" in r.matched_keywords
    assert "schnittstellen-luecke" in r.matched_keywords


def test_discovery_feature_wunsch_s031_ki_auswertungen_erinnerungen():
    text = (
        "Auswertungen – bspw. Spülungen fehlen, willst du die machen? "
        "Dringende Sanierungen – erinnern… Baumkontrollen dran – erinnern… sowas"
    )
    r = classify_intent(text, modul="KI")
    assert r.intent == "Discovery"
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert "KI" in r.themen
    assert "Baumkontroll-App" in r.themen
    assert r.geltung == "Querschnitt"
    assert r.request_thema == "Auswertungen"
    assert "Spülungen" in r.request_detail
    assert "Sanierungen" in r.request_detail
    assert "Baumkontrollen" in r.request_detail
    assert "feature-wunsch" in r.matched_keywords
    assert "ki-assistenz" in r.matched_keywords


def test_ux_kritik_s030_verkehr_pdf_workflow_webinar():
    text = (
        "ganz schlecht: jede Anordnung bzw. jeder Bescheid muss erst als pdf erzeugt, "
        "lokal abgespeichert und dann wieder ins Modul importiert werden\n"
        "Vorschlag: bei größeren Änderungen immer WEbinar für Bestandskunden anbieten "
        "zur Vorstellung der ANpassungen und der neuen Workflows"
    )
    r = classify_intent(text, modul="Verkehr")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "UX-Kritik"
    assert r.confidence == "hoch"
    assert "Modul Verkehr" in r.themen
    assert r.request_thema == "Workflow"
    assert "PDF export → Re-Import" in r.request_detail
    assert r.aktion_todo == "Webinar für Bestandskunden bei größeren Änderungen"
    assert "ux-kritik" in r.matched_keywords
    assert "workflow-kritik" in r.matched_keywords
    assert "feature-wunsch" not in r.matched_keywords


def test_feature_wunsch_s029_boll_datenuebernahme_felder():
    text = (
        "Datenübernahme verbessern, nicht in eine Zeile sondern in die richtigen Felder"
    )
    r = classify_intent(text, modul="Schnittstelle zum dig. Bauantrag Boll")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert "Schnittstelle BOLL" in r.themen
    assert "BOLL" in r.themen
    assert r.request_thema == "Datenübernahme"
    assert r.request_detail == "Feldzuordnung statt Zeile"
    assert "feature-wunsch" in r.matched_keywords
    assert "schnittstellen-luecke" in r.matched_keywords


def test_feature_wunsch_s028_benutzerverwaltung_profil_und_anzeige_defekt():
    text = (
        "Möglichkeit ein Benutzerprofil (Berechtigungen) zu kopieren/duplizieren "
        "für neuen Mitarbeiter + Anzeige der berechtigten Module stimmt nicht mit "
        "Anzeige der Ebenen überein"
    )
    r = classify_intent(text, modul="Benutzerverwaltung")
    assert r.intent == "Defekt"
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert "Benutzerverwaltung" in r.themen
    assert r.request_thema == "Benutzerprofil"
    assert "Kopieren/Duplizieren" in r.request_detail
    assert "Anzeige Module vs Ebenen" in r.request_detail
    assert "feature-wunsch" in r.matched_keywords
    assert "anzeige-defekt" in r.matched_keywords


def test_feature_wunsch_s027_bauav_massenexport():
    text = "Massenexport von Dateien gewünscht"
    r = classify_intent(text, modul="BauAV")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "Feature Request"
    assert r.confidence == "hoch"
    assert r.themen == ("BauAV",)
    assert r.request_thema == "Massenexport"
    assert r.request_detail == "Dateien"
    assert "feature-wunsch" in r.matched_keywords
    assert "massenexport" in r.matched_keywords


def test_service_kritik_s026_projektplan_umstieg():
    text = (
        "kein Projektplan, tlw. ewige Wartezeiten auf Rückmeldung, keine Infos, "
        "Erledigung ohne Info etc."
    )
    r = classify_intent(text, modul="Projektplan Umstieg")
    assert r.intent == "Sonstiges"
    assert r.bedarf == "Service-Kritik"
    assert r.confidence == "hoch"
    assert "Projektplan Umstieg" in r.themen
    assert r.request_thema == "Kommunikation"
    assert "kein Projektplan" in r.request_detail
    assert "Wartezeit" in r.request_detail
    assert "fehlende Infos" in r.request_detail
    assert "Erledigung ohne Info" in r.request_detail
    assert "service-kritik" in r.matched_keywords


def test_ticket_routing_intent_hides_sonstiges():
    from core.intent_patterns import format_pm_category, ticket_routing_intent

    assert ticket_routing_intent("Sonstiges") == ""
    assert ticket_routing_intent("Defekt") == "Defekt"
    assert format_pm_category("Sonstiges", "Feature Request") == "Feature Request"
    assert format_pm_category("Defekt", "Feature Request") == "Feature Request · Defekt"


def test_short_text_sonstiges():
    r = classify_intent("kurz")
    assert r.intent == "Sonstiges"
