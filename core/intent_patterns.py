"""
Hotline-/Feedback-Intent — regelbasiert, deterministisch (kein LLM).

Trennt Frage-Art (How-To, Discovery, …) von Modul/Thema (Export, Login, …).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.intent_actions import extract_aktion_todo
from core.intent_contacts import KontaktAngebot, extract_kontakt_angebot
from core.intent_lexicon import any_cluster_hit, cluster_hits

INTENT_LABELS: tuple[str, ...] = (
    "Discovery",
    "Defekt",
    "Installation",
    "How-To",
    "Sonstiges",
)

TICKET_ROUTING_INTENTS: frozenset[str] = frozenset(
    {"Defekt", "Discovery", "How-To", "Installation"}
)


def ticket_routing_intent(intent: str) -> str:
    """Ticket-Routing (How-To/Defekt/…); leer wenn Sonstiges oder bedarf trägt die PM-Kategorie."""
    label = (intent or "").strip()
    return label if label in TICKET_ROUTING_INTENTS else ""


def format_pm_category(intent: str, bedarf: str = "") -> str:
    """PM-Anzeige: bedarf primär, Ticket-Routing nur wenn relevant (z. B. S028)."""
    bedarf_s = (bedarf or "").strip()
    routing = ticket_routing_intent(intent)
    if bedarf_s and routing:
        return f"{bedarf_s} · {routing}"
    if bedarf_s:
        return bedarf_s
    return routing or (intent or "").strip() or "—"

# Höhere Zahl = gewinnt bei Mehrfachtreffer
_INTENT_PRIORITY: dict[str, int] = {
    "Discovery": 50,
    "Defekt": 40,
    "Installation": 30,
    "How-To": 20,
    "Sonstiges": 0,
}

_PATTERN_GROUPS: dict[str, tuple[str, ...]] = {
    "Discovery": (
        "alle daten",
        "alle layer",
        "alle objekte",
        "an dieser stelle",
        "an dem punkt",
        "an diesem punkt",
        "geo punkt",
        "geo-punkt",
        "geopunkt",
        "koordinate",
        "koordinaten",
        "standort",
        "fläche",
        "flaeche",
        "polygon",
        "kartenpunkt",
        "kartenklick",
        "objektliste",
        "fachdaten",
        "was liegt",
        "welche daten",
        "daten zu diesem",
        "daten an der stelle",
        "daten am punkt",
        "zusammenstellung",
        "auskunft an",
        "informationsauskunft",
        "auswertung",
        "auswertungen",
        "erinnern",
        "wie wird",
    ),
    "Defekt": (
        "geht nicht",
        "funktioniert nicht",
        "fehler",
        "fehlermeldung",
        "absturz",
        "stürzt ab",
        "stuerzt ab",
        "hängt",
        "haengt",
        "blockiert",
        "kaputt",
        "bug",
        "defekt",
        "crash",
        "langsam",
        "performance",
        "reagiert nicht",
        "ohne wirkung",
        "probleme",
        "problem mit",
    ),
    "Installation": (
        "installation",
        "installieren",
        "installiert",
        "neuinstallation",
        "deinstallation",
        "update",
        "aktualisier",
        "upgrade",
        "setup",
        "einrichten",
        "einrichtung",
        "lizenz",
        "freischalt",
    ),
    "How-To": (
        "wie geht",
        "wie kann ich",
        "wie muss ich",
        "wie stelle ich",
        "wie finde ich",
        "wo finde ich",
        "wo klicke ich",
        "wo kann ich",
        "anleitung",
        "schritt für schritt",
        "schritt fuer schritt",
        "wo ist",
        "wo befindet sich",
        "wie exportier",
        "wie importier",
        "wie öffne",
        "wie oeffne",
        "wie erstelle",
        "wie lege ich",
        "hilfe bei",
        "können sie mir erklären",
        "koennen sie mir erklaeren",
    ),
}

_GEO_HINTS = frozenset(
    {
        "daten",
        "layer",
        "objekt",
        "punkt",
        "geo",
        "karte",
        "koordinate",
        "fläche",
        "flaeche",
        "standort",
        "fachdat",
        "vermess",
        "kataster",
        "grundstück",
        "grundstueck",
    }
)

_BOUNDARY_SHORT = frozenset({"bug", "geo"})


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _keyword_hits(text: str, keyword: str) -> bool:
    kw = keyword.lower()
    if kw in ("fläche", "flaeche"):
        return bool(re.search(rf"(?<![a-zäöüß]){re.escape(kw)}(?![a-zäöüß])", text))
    if len(kw) <= 4 or kw in _BOUNDARY_SHORT:
        return bool(re.search(rf"(?<![a-zäöüß0-9]){re.escape(kw)}", text))
    return kw in text


def _geo_term_in_text(text: str, term: str) -> bool:
    if term in ("geo", "bug"):
        return bool(re.search(rf"(?<![a-zäöüß0-9]){re.escape(term)}", text))
    if len(term) <= 5:
        return bool(re.search(rf"(?<![a-zäöüß0-9]){re.escape(term)}", text))
    return term in text


def _how_to_vs_discovery(text: str) -> str | None:
    """Disambiguiert «wo/wie finde ich …» — Menü vs. Geo-Daten."""
    if not any(
        p in text
        for p in (
            "wo finde ich",
            "wie finde ich",
            "wo kann ich",
            "wie kann ich",
        )
    ):
        return None
    window = text
    for anchor in ("wo finde ich", "wie finde ich", "wo kann ich", "wie kann ich"):
        idx = text.find(anchor)
        if idx >= 0:
            window = text[idx : idx + 120]
            break
    if any(_geo_term_in_text(window, h) for h in _GEO_HINTS):
        return "Discovery"
    return "How-To"


@dataclass(frozen=True)
class IntentResult:
    intent: str
    matched_keywords: tuple[str, ...]
    confidence: str
    bedarf: str = ""
    geltung: str = ""  # z. B. «Alle Module», «Querschnitt»
    themen: tuple[str, ...] = ()  # erkannte Produkt-/Feature-Keywords (E-Akte, RegiSafe, …)
    request_thema: str = ""  # z. B. Schnittstelle, Filterung
    request_detail: str = ""  # z. B. Kommuna, Endhydranten
    kontakt_angebot: str = ""  # zusammengefasstes Kontakt-Angebot
    ansprechpartner: str = ""
    kontakt_zeitraum: str = ""
    aktion_todo: str = ""  # PM-Follow-up (z. B. Vertriebs-Klärung)

    @property
    def is_confident(self) -> bool:
        return self.confidence == "hoch"


_SERVICE_KRITIK_PHRASES = (
    "kommunikation",
    "wartezeit",
    "rückmeldung",
    "rueckmeldung",
    "keine infos",
    "keine info",
    "erledigung",
    "erledigung ohne info",
    "antwortzeit",
    "keine rückmeldung",
    "keine rueckmeldung",
    "geht nichts vorran",
    "geht nichts voran",
    "noch nicht erfüllt",
    "noch nicht erfuellt",
    "anforderungen an schnittstelle",
    "kein projektplan",
    "projektplan",
)

_UX_KRITIK_PHRASES = (
    "unübersichtlich",
    "unuebersichtlich",
    "fähnchen",
    "faehnchen",
    "darstellung mit",
    "zu komplex",
    "umständlich",
    "umstaendlich",
    "unbrauchbar",
)

_DOKUMENTATIONS_WUNSCH_PHRASES = (
    "bedienungsanleitung",
    "bedienungsanleitung,",
    "handbuch wün",
    "handbuch wuens",
    "dokumentation wün",
    "dokumentation wuens",
)

_PRODUKT_LUECKE_PHRASES = (
    "zu wenige funktionen",
    "viel zu wenige funktionen",
    "weg von der praxis",
    "macht deswegen keinen sinn",
    "macht keinen sinn bedarf",
    "was man vermisst",
    "konkrete vorschläge, was man vermisst",
    "konkrete vorschlaege, was man vermisst",
)

_UPDATE_KRITIK_PHRASES = (
    "kritik an modulupdate",
    "modulupdates",
    "update rückgängig",
    "update rueckgaengig",
    "rückgängig machen",
    "rueckgaengig machen",
    "schlimmer",
    "unübersichtlich",
    "unuebersichtlich",
    "früher einfacher",
    "frueher einfacher",
    "zu viele klicks",
    "massive kritik",
    "war früher",
    "war frueher",
    "verschlechter",
    "kommt nicht so gut",
    "kommt nicht gut an",
    "nicht so gut beim kunden",
)

_UPDATE_CONTEXT_PHRASES = (
    "update",
    "modulupdate",
    "aktualisier",
    "modulumstellung",
    "neue programmierung",
    "neuer programmierung",
    "programmieroberfläche",
    "programmieroberflaeche",
    "neue programmieroberfläche",
    "neue programmieroberflaeche",
    "umstellung auf",
)

_FEATURE_WUNSCH_PHRASES = (
    "feature-wunsch",
    "feature wunsch",
    "wunschliste",
    "wäre schön",
    "waere schoen",
    "wäre sehr interessant",
    "waere sehr interessant",
    "großes interesse",
    "grosses interesse",
    "interesse an",
    "könnten sie ergänzen",
    "koennen sie ergaenzen",
    "sortier",
    "sortierung",
    "filterung",
    "usability",
    "gewünscht",
    "gewuenscht",
    " wunsch",
    "wunsch:",
    "vorschlag",
    "sollte möglich",
    "sollte moeglich",
    "sollte es möglich",
    "sollte es moeglich",
    "unbedingt gewünscht",
    "unbedingt gewuenscht",
    "hinterlegen",
    " pdf",
    "übertragung",
    "uebertragung",
    "gut wäre",
    "gut waere",
    "erstellung von",
    "individuell",
    "massendruck",
    "massenexport",
    "stapelverarbeitung",
    "serienbrief",
    "funktion gewünscht",
    "funktion gewuenscht",
    "anbindung an",
    "dokumentenanbindung",
    "leichter gestalten",
    "leichter gestalt",
    "editierbar",
    "bereitstellen",
    "verbesserung",
    "ausbaubar",
    "schnittstelle zu",
    "schnittstelle an",
    "schnittstelle für",
    "schnittstelle fuer",
    "wäre sinnvoll",
    "waere sinnvoll",
    "vereinfachen",
    "kurzbefehl",
    "kopieren",
    "duplizieren",
    "verbessern",
    "auswertung",
    "auswertungen",
    "erinnern",
    "berichtsvorlage",
    "muss angepasst",
    "bauturbo",
    "dargestellt werden sollen",
    "ganz einfach",
    "eigene ebene",
)

_INTEGRATION_GAP_PHRASES = (
    "keine daten zu",
    "keine daten für",
    "keine daten fuer",
    "daten fehlen",
    "einzeldaten",
    " fehlen",
    "fehlen (",
    "deckt nur",
    "notwendigen umfang",
    "datenübernahme",
    "datenuebernahme",
    "nicht übernommen",
    "nicht uebernommen",
    "keine schnittstelle ins",
    "keine schnittstelle zum",
    "keine schnittstelle in",
)

_SCHNITTSTELLE_HINTS = (
    "schnittstelle",
    "bvl",
    "prosoz",
    "boll",
    "gekos",
    "komuna",
    "tera",
)

# Erkennbare Request-Inhalte in Feature-Wünschen (Filterung, Anbindung, …)
_REQUEST_NOUNS: tuple[str, ...] = (
    "schnittstelle",
    "filterung",
    "sortierung",
    "anbindung",
    "dokumentenanbindung",
    "massendruck",
    "stapelverarbeitung",
    "serienbrief",
    "export",
    "import",
    "integration",
    "editierbar",
    "bereitstellen",
    "kurzbefehl",
    "ebene",
    "geländeschnitt",
    "gelandeschnitt",
    "dokumente",
    "pdf",
    "übertragung",
    "uebertragung",
    "hinterlegen",
)

_REQUEST_THEMA_ORDER: tuple[tuple[str, str], ...] = (
    ("Übertragung", "übertragung"),
    ("Übertragung", "uebertragung"),
    ("Schnittstelle", "schnittstelle"),
    ("Filterung", "filterung"),
    ("Anbindung", "anbindung"),
    ("Sortierung", "sortierung"),
    ("Integration", "integration"),
    ("Massendruck", "massendruck"),
    ("Stapelverarbeitung", "stapelverarbeitung"),
    ("Export", "export"),
    ("Import", "import"),
)

_DETAIL_ALIASES: dict[str, str] = {
    "komuna": "Kommuna",
    "kommuna": "Kommuna",
    "endhydranten": "Endhydranten",
    "endhydanten": "Endhydranten",
    "onlineformular": "Onlineformular",
    "regisafe": "RegiSafe",
    "kic": "KIC",
    "prosoz": "Prosoz",
    "boll": "BOLL",
    "gekos": "Gekos",
    "genehmigungssoftware": "Genehmigungssoftware",
}

_CROSS_MODULE_TEXT = (
    "alle module",
    "alle modul",
    "plattformweit",
    "querschnitt",
    "übergreifend",
    "uebergreifend",
    "modulübergreifend",
    "moduluebergreifend",
)

_CROSS_MODULE_CLUSTERS = frozenset(
    {
        "basisentwicklung",
        "generell",
        "allgemein",
        "basic",
        "einige kunden",
        "rgz autor",
    }
)

_CAPABILITY_HINTS = (
    "erstellung",
    "sollte",
    "möglich",
    "moeglich",
    "gewünscht",
    "gewuenscht",
    "interesse",
    "funktion",
    "anbindung",
    "übertragung",
    "uebertragung",
    "editierbar",
    "bereitstellen",
    "ergänzen",
    "ergaenzen",
    "integration",
    "schnittstelle",
    "darstellung",
    "filter",
    "export",
    "import",
    "bericht",
)

# Kanonisches Label → Regex (case-insensitive auf normalisiertem Text + Modul)
_TOPIC_RULES: tuple[tuple[str, str], ...] = (
    ("E-Akte", r"e[\-\s]?akte"),
    ("RegiSafe", r"regisafe"),
    ("KIC", r"\bkic\b"),
    ("BauAV", r"\bbauav\b|bauantragsverwaltung"),
    ("BauTurbo", r"bauturbo"),
    ("Modul Vermessungsdaten", r"vermessungsdaten|vermessungs[\s\-/]?app|vm[\s\-]?punkte|vm[\s\-]?daten"),
    ("Bauantrag", r"bauantrag|bebauungspl[aä]n[e]?|bauleitplan|f[\s\-]?pl[aä]ne"),
    ("Geonotizen", r"geonotiz"),
    ("Baumkontroll-App", r"baumkontroll[\s\-]?app|baumkontrollen"),
    ("Schnittstelle Prosoz", r"(?:bvl[\s\-]*)?schnittstelle[\s\-]*prosoz|prosoz[\s\-]*schnittstelle"),
    ("Schnittstelle BOLL", r"schnittstelle[\s\-]*boll|boll[\s\-]*schnittstelle|dig\.?\s*bauantrag[\s\-]*boll"),
    ("Schnittstelle Gekos", r"schnittstelle[\s\-]*gekos|gekos[\s\-]*schnittstelle"),
    ("Prosoz", r"prosoz"),
    ("BOLL", r"\bboll\b"),
    ("Gekos", r"gekos"),
    ("Kanal-App", r"kanal[\s\-]?app"),
    ("Modul Verkehr", r"(?:modul[\s\-]+)?verkehr\b|\bverkehr[\s\-]+modul"),
    ("Kommuna", r"komm?una"),
    ("RGZ", r"\brgz\b|geländeschnitt|gelandeschnitt|geteilte karte"),
    ("TERA", r"\btera\b"),
    ("Basisentwicklung", r"basisentwicklung"),
    ("Modul Forst", r"(?<![a-zäöüß])forst(?![a-zäöüß])"),
    ("Projektplan Umstieg", r"projektplan|umstieg"),
    ("Benutzerverwaltung", r"benutzerverwaltung|benutzerprofil|berechtigung"),
    ("KI", r"\bki\b|k[üu]nstliche intelligenz"),
    ("Versorgungsleitungen", r"versorgungsleitungen|modulbaukasten versorgung|testleitungen"),
    ("Grünflächen", r"gr[üu]nfl[aä]chen"),
)

# Feldbesuch-Cluster → Produktlabel (wenn nicht schon per Regex im Text)
_MODUL_PRODUCT_ALIASES: dict[str, str] = {
    "basic": "RGZ Basic",
    "basisentwicklung": "Basisentwicklung",
    "rgz autor": "RGZ Autor",
    "forst": "Modul Forst",
    "vm/wasser": "VM/Wasser",
    "e-akte kic": "E-Akte KIC",
    "eakte zu kic": "E-Akte KIC",
    "projektplan umstieg": "Projektplan Umstieg",
    "benutzerverwaltung": "Benutzerverwaltung",
    "ki": "KI",
    "tera & rgz": "TERA & RGZ",
    "versorgungsleitungen / modulbaukasten versorgung": "Versorgungsleitungen",
    "grünflächen": "Grünflächen",
}


def _ki_assistenz_request_details(lower: str) -> list[str]:
    """Compliance-/Fristen-Use-Cases für KI-Auswertungen & Erinnerungen."""
    details: list[str] = []
    if re.search(r"sp[üu]lung", lower):
        details.append("Spülungen")
    if re.search(r"sanierung", lower):
        details.append("Sanierungen")
    if re.search(r"baumkontroll", lower):
        details.append("Baumkontrollen")
    return details


def _is_ki_assistenz_wunsch(text: str, *, modul: str = "") -> bool:
    """Neues KI-Feature: Auswertungen + proaktive Erinnerungen (Compliance)."""
    lower = _normalize(text)
    modul_lower = _normalize(modul)
    ki_context = modul_lower == "ki" or modul_lower.startswith("ki ") or re.search(
        r"\bki\b", modul_lower
    )
    if not ki_context and not re.search(r"\bki\b", lower):
        return False
    if re.search(r"auswertung", lower):
        return True
    return bool(
        re.search(r"erinnern", lower)
        and re.search(r"fehlen|dran|willst du|sanierung|sp[üu]lung|baumkontroll", lower)
    )


def _cross_module_codes(lower: str) -> list[str]:
    """Kurzmodule in Stapelverarbeitungs-/Querschnitts-Wünschen (ER, BauAV, …)."""
    labels: list[str] = []
    for code, label in (
        ("er", "ER"),
        ("bauav", "BauAV"),
        ("fh", "FH"),
        ("vk", "VK"),
        ("vt", "VT"),
    ):
        if re.search(rf"\b{code}\b", lower):
            labels.append(label)
    return labels


def _stapelverarbeitung_request_details(lower: str) -> list[str]:
    details: list[str] = []
    if re.search(r"serienbrief", lower):
        details.append("Serienbrief")
    modules = _cross_module_codes(lower)
    if modules:
        details.extend(modules)
    return details


_BUGMELDUNG_RECURRING_PHRASES = (
    "immer mal wieder",
    "immer wieder",
    "wiederholt",
    "wiederkehrend",
    "ständig",
    "staendig",
    "macht probleme",
    "macht immer",
)

_BUGMELDUNG_DEFECT_PHRASES = (
    "fehlermeldung",
    "funktioniert nicht",
    "absturz",
    "stürzt ab",
    "stuerzt ab",
    "crash",
    "kaputt",
)


def _is_schnittstelle_defekt_report(text: str, *, modul: str = "") -> bool:
    """Wiederkehrende/fehlerhafte Schnittstelle (Bug, nicht Feature Request)."""
    lower = _normalize(text)
    if not _has_schnittstelle_context(text, modul):
        return False
    if _has_integration_gap(text):
        return False
    if re.search(r"geht nicht", lower) and not re.search(
        r"problem|fehler|immer mal wieder|wiederholt", lower
    ):
        return False
    return bool(
        re.search(
            r"probleme?|fehler|funktioniert nicht|geht nicht|macht.*probleme",
            lower,
        )
    )


def _is_bugmeldung(text: str, *, modul: str = "") -> bool:
    """Recurring defect / Schnittstelle-Stabilität — nicht Update-Kritik oder Feature Request."""
    lower = _normalize(text)
    if any(p in lower for p in _UPDATE_KRITIK_PHRASES) and _has_update_context(lower):
        return False
    if _has_integration_gap(lower):
        return False
    if _is_schnittstelle_defekt_report(text, modul=modul):
        return True
    if any(p in lower for p in _BUGMELDUNG_RECURRING_PHRASES) and re.search(
        r"problem|fehler|bug|defekt|funktioniert nicht", lower
    ):
        return True
    if re.search(r"\bbug\b", lower):
        return True
    if any(p in lower for p in _BUGMELDUNG_DEFECT_PHRASES):
        return True
    if re.search(r"\bfehler\b", lower) and not _has_capability_language(lower):
        return True
    if re.search(r"\bdefekt\b", lower) and not _has_update_context(lower):
        return True
    return False


def _schnittstelle_defekt_details(lower: str) -> list[str]:
    details: list[str] = []
    if re.search(r"\bboll\b", lower):
        details.append("BOLL")
    if re.search(r"immer mal wieder|wiederholt|immer wieder|st[äa]ndig", lower):
        details.append("wiederkehrend")
    return details


def _bauturbo_ebene_request_details(lower: str) -> list[str]:
    details: list[str] = []
    if re.search(r"eigene ebene", lower):
        details.append("eigene Ebene")
    if re.search(r"wie wird.*dargestellt|dargestellt", lower):
        details.append("Darstellung BauTurbo")
    return details


def _is_bauturbo_ebene_frage(text: str) -> bool:
    """BauTurbo: Frage nach Darstellung/Ebene (Discovery + Lösungsvorschlag)."""
    lower = _normalize(text)
    return bool(
        re.search(r"bauturbo", lower)
        and re.search(r"ebene|dargestellt", lower)
        and re.search(r"wird es|wird der|wie wird|\?", lower)
    )


def _gruenflaechen_kritik_details(lower: str) -> list[str]:
    """Mehrpunkt-Kritik Modul Grünflächen (UX, Filter, Handbuch)."""
    details: list[str] = []
    if re.search(r"komplex|umständlich|umstaendlich", lower):
        details.append("Modul komplex/umständlich")
    if re.search(r"filter.*100|100 datens", lower):
        details.append("Filterlimit 100 Datensätze")
    if re.search(r"handbuch", lower) and re.search(r"unbrauchbar|schulung|praxis", lower):
        details.append("Handbuch unbrauchbar")
    return details


def _versorgung_darstellung_details(lower: str) -> list[str]:
    """Versorgungsleitungen: einfache Darstellung vs. UX-Komplexität."""
    details: list[str] = []
    if re.search(r"private sparten|sparten liegen", lower):
        details.append("private Sparten darstellen")
    if re.search(r"testleitungen", lower):
        details.append("Vgl. Testleitungen (Demo)")
    if re.search(r"graphische integration|un[üu]bersichtlich", lower):
        details.append("Integration unübersichtlich")
    if re.search(r"nachgebessert|vom kunden", lower):
        details.append("keine Kunden-Anpassung")
    if re.search(r"viel zu komplex|zu komplex", lower):
        details.append("Modul zu komplex")
    return details


def _is_anzeige_defekt(text: str) -> bool:
    """Inkonsistente Anzeige (z. B. berechtigte Module vs. Ebenen)."""
    lower = _normalize(text)
    if not re.search(
        r"stimmt nicht|übereinstimm|uebereinstimm|nicht ueberein|weicht ab|inkonsistenz",
        lower,
    ):
        return False
    return bool(
        re.search(r"anzeige|modul|ebenen|berechtigt|layer|darstellung", lower)
    )


def _benutzerverwaltung_request_details(lower: str) -> list[str]:
    """Mehrpunkt-Feedback Benutzerverwaltung (Profil kopieren + Anzeige-Bug)."""
    details: list[str] = []
    if re.search(r"kopier|duplizier", lower) and re.search(
        r"benutzerprofil|berechtigung", lower
    ):
        details.append("Kopieren/Duplizieren")
    if _is_anzeige_defekt(lower):
        details.append("Anzeige Module vs Ebenen")
    return details


def _service_kritik_request_details(lower: str) -> list[str]:
    """Mehrpunkt-Details für Service-Kritik (Rückmeldung, Umstieg, …)."""
    details: list[str] = []
    if re.search(r"kein(?:en)?\s+projektplan|ohne\s+projektplan", lower):
        details.append("kein Projektplan")
    if any(
        p in lower
        for p in ("keine info", "keine infos", "keine rückmeldung", "keine rueckmeldung")
    ):
        details.append("fehlende Infos")
    if any(
        p in lower
        for p in (
            "woche",
            "monat",
            "wartezeit",
            "ewig",
            "geht nichts vorran",
            "geht nichts voran",
        )
    ):
        details.append("Wartezeit")
    if "erledigung ohne info" in lower:
        details.append("Erledigung ohne Info")
    return details


def _is_umstieg_service_context(lower: str, modul: str = "") -> bool:
    modul_lower = _normalize(modul)
    return bool(
        re.search(r"kein(?:en)?\s+projektplan|ohne\s+projektplan", lower)
        or "projektplan" in modul_lower
        or "umstieg" in modul_lower
    )


def _tera_rgz_schnittstelle_details(lower: str) -> list[str]:
    """TERA-Module (GEB/RES/VER) → RGZ Schnittstelle."""
    details: list[str] = []
    modules = [
        code.upper()
        for code in ("geb", "res", "ver")
        if re.search(rf"\b{code}\b", lower)
    ]
    if modules:
        details.append("; ".join(modules) + " → RGZ")
    elif re.search(r"\brgz\b", lower):
        details.append("TERA → RGZ")
    if re.search(r"wechsel zwischen", lower):
        details.append("Systemwechsel")
    if re.search(r"kartograf", lower):
        details.append("kartografischer Überblick")
    return details


def _darstellung_faehnchen_wunsch_details(lower: str) -> list[str]:
    """BauAV-Kartenkritik + Darstellungs-Wünsche (Fähnchen, Flurstück, Fläche)."""
    details: list[str] = []
    if re.search(r"einzel.*f[aäe]hnchen|extrem un[üu]bersichtlich", lower):
        details.append("Einzelfähnchen unübersichtlich")
    if re.search(r"wunsch:", lower) or re.search(r"flurst[üu]ck|fl[aäe]chendarstellung", lower):
        if re.search(r"f[aäe]hnchen pro flurst", lower):
            details.append("1 Fähnchen pro Flurstück")
        if re.search(r"absprung|hinterlegten bauantrag", lower):
            details.append("Absprung zu Bauanträgen")
        if re.search(r"fl[aäe]chendarstellung", lower):
            details.append("Flächendarstellung")
        if re.search(r"\blra", lower):
            details.append("LRA Best Practice")
        if re.search(r"auswahl.*kunde|1 f[aäe]hnchen oder viele", lower):
            details.append("Auswahl pro Kunde")
    return details


def _is_darstellung_discovery_wunsch(text: str) -> bool:
    """Mehrere Darstellungs-Optionen (Fähnchen/Fläche/Auswahl) — Discovery."""
    lower = _normalize(text)
    return bool(
        re.search(r"wunsch:", lower)
        and re.search(r"f[aäe]hnchen|fl[aäe]chendarstellung", lower)
        and len(re.findall(r"\boder\b", lower)) >= 2
    )


def extract_themen(text: str, *, modul: str = "") -> tuple[str, ...]:
    """Produkt-/Feature-Keywords aus Freitext und Cluster (z. B. E-Akte, RegiSafe)."""
    combined = f"{_normalize(text)} {_normalize(modul)}"
    found: list[str] = []
    seen: set[str] = set()
    for label, pattern in _TOPIC_RULES:
        if label in seen:
            continue
        if re.search(pattern, combined, re.IGNORECASE):
            found.append(label)
            seen.add(label)
    modul_key = _normalize(modul).strip()
    alias = _MODUL_PRODUCT_ALIASES.get(modul_key)
    if alias and alias not in seen:
        found.append(alias)
    return tuple(found)


def _has_update_context(text: str) -> bool:
    lower = _normalize(text)
    return any(p in lower for p in _UPDATE_CONTEXT_PHRASES)


def _canonical_detail(raw: str) -> str:
    token = re.sub(r"\s+", " ", (raw or "").strip()).strip(".,;()")
    if not token:
        return ""
    key = token.lower().split()[0]
    if key in _DETAIL_ALIASES:
        return _DETAIL_ALIASES[key]
    if len(token) <= 32 and token.isascii():
        return token.title()
    return token


def extract_request(text: str, *, modul: str = "") -> tuple[str, str]:
    """
    Strukturierter Feature-Request: Thema (Schnittstelle, Filterung, …)
    und Ziel/Detail (Kommuna, Endhydranten, …).
    """
    lower = _normalize(text)
    if not lower:
        return "", ""

    if re.search(r"dokumenten\s*anbindung|dokumentenanbindung", lower):
        return "Anbindung", "Dokumente"

    if re.search(r"massen\s*export|massenexport", lower):
        detail = "Dateien" if re.search(r"dateien?", lower) else ""
        return "Massenexport", detail

    if re.search(r"benutzerprofil|berechtigung", lower):
        admin_details = _benutzerverwaltung_request_details(lower)
        if admin_details:
            return "Benutzerprofil", "; ".join(admin_details)
        if re.search(r"kopier|duplizier", lower):
            return "Benutzerprofil", "Kopieren/Duplizieren"

    if re.search(r"daten[üu]bernahme|datenuebernahme", lower):
        detail = ""
        if re.search(r"richtigen?\s+felder", lower) and re.search(r"zeile", lower):
            detail = "Feldzuordnung statt Zeile"
        elif re.search(r"richtigen?\s+felder", lower):
            detail = "richtige Felder"
        elif re.search(r"zeile", lower):
            detail = "nicht in Zeile"
        return "Datenübernahme", detail

    if _is_workflow_kritik(lower):
        details = _workflow_kritik_details(lower)
        return "Workflow", "; ".join(details) if details else "PDF-Rundlauf"

    if _is_ki_assistenz_wunsch(lower, modul=modul):
        details = _ki_assistenz_request_details(lower)
        return "Auswertungen", "; ".join(details) if details else "Erinnerungen"

    if re.search(r"keine schnittstelle ins|schnittstelle ins rgz|schnittstelle.*\brgz\b", lower):
        tera_details = _tera_rgz_schnittstelle_details(lower)
        if tera_details:
            return "Schnittstelle", "; ".join(tera_details)

    if _has_schnittstelle_context(lower, modul) and re.search(r"problem", lower):
        defect_details = _schnittstelle_defekt_details(lower)
        return "Schnittstelle", "; ".join(defect_details) if defect_details else "Stabilität"

    if _has_update_context(lower) and any(p in lower for p in _UPDATE_KRITIK_PHRASES):
        update_details = _update_kritik_details(lower)
        if update_details:
            return "Update/UI", "; ".join(update_details)

    if re.search(r"stapelverarbeitung|serienbrief", lower):
        details = _stapelverarbeitung_request_details(lower)
        return "Stapelverarbeitung", "; ".join(details) if details else ""

    if re.search(r"bauturbo", lower) and re.search(r"ebene|dargestellt", lower):
        ebene_details = _bauturbo_ebene_request_details(lower)
        if ebene_details:
            return "Ebene", "; ".join(ebene_details)
        return "Ebene", "BauTurbo"

    if re.search(r"ebene", lower) and re.search(r"editierbar", lower):
        detail = "selbst editierbar" if re.search(r"selbst edit", lower) else "editierbar"
        if re.search(r"darstellung", lower):
            return "Darstellung", f"Ebenen {detail}"
        return "Ebenen", detail

    if re.search(r"berichtsvorlage|bericht.*vorlage", lower):
        details: list[str] = []
        if re.search(r"stellungnahme", lower):
            details.append("Stellungnahme")
        if re.search(r"bauturbo", lower):
            details.append("BauTurbo")
        if re.search(r"neuen vorgaben|neue vorgaben", lower) and "BauTurbo" not in details:
            details.append("neue Vorgaben")
        return "Berichtsvorlage", "; ".join(details) if details else "Anpassung"

    if re.search(
        r"versorgungsleitungen|private sparten|testleitungen|modulbaukasten versorgung",
        lower,
    ):
        versorgung_details = _versorgung_darstellung_details(lower)
        if versorgung_details:
            return "Darstellung", "; ".join(versorgung_details)

    modul_lower = _normalize(modul)
    if "grünfläch" in modul_lower or "gruenflaech" in modul_lower or re.search(
        r"gr[üu]nfl[aä]chen", lower
    ):
        gruen_details = _gruenflaechen_kritik_details(lower)
        if gruen_details:
            return "Grünflächen", "; ".join(gruen_details)

    for label, needle in _REQUEST_THEMA_ORDER:
        if needle not in lower:
            continue

        idx = lower.find(needle)
        after = lower[idx + len(needle) :].strip()

        zu_match = re.match(
            r"(?:zu|an|für|fuer)\s+([a-zäöüß][\w\-]*)",
            after,
            re.IGNORECASE,
        )
        if zu_match:
            return label, _canonical_detail(zu_match.group(1))

        if label == "Integration" and re.search(
            r"graphische integration|versorgungsleitungen", lower
        ):
            continue

        if label in ("Übertragung", "Integration"):
            if re.search(r"vm[\s\-]?daten|vm[\s\-]?punkte", lower):
                parts: list[str] = []
                if re.search(r"edit[\s\-]?modul|ins jeweilige", lower):
                    parts.append("VM-Daten → Edit-Modul")
                if re.search(r"sachdatenmaske|schieber", lower):
                    parts.append("Sachdatenmaske Schieber")
                if re.search(r"zeichnen", lower) and re.search(r"sachdaten", lower):
                    parts.append("zeichnen vor Sachdaten")
                detail = "; ".join(parts) if parts else "VM-Punkte"
                return label, detail
            ins_match = re.search(
                r"\bins\s+(?:das |dem |jeweilige )?([a-zäöüß][\w\-/ ]{2,30}?modul)",
                lower,
            )
            if ins_match:
                return label, _canonical_detail(ins_match.group(1).strip())
            aus_match = re.search(r"\baus\s+([a-zäöüß][\w\-]+)", lower)
            if aus_match:
                return label, _canonical_detail(aus_match.group(1))

        if label == "Filterung":
            noun_match = re.match(r"([a-zäöüß][\w\-]*)", after, re.IGNORECASE)
            if noun_match:
                return label, _canonical_detail(noun_match.group(1))

        if label == "Anbindung":
            if re.search(r"register", lower):
                return label, "Register"
            noun_match = re.match(r"([a-zäöüß][\w\-]*)", after, re.IGNORECASE)
            if noun_match:
                return label, _canonical_detail(noun_match.group(1))

        if label == "Massendruck":
            ref_match = re.search(
                r"ähnlich\s+([a-zäöüß0-9][\w\-\s]*funktion)(?:\s+in\s+qgis)?",
                lower,
                re.IGNORECASE,
            )
            if ref_match:
                detail = re.sub(r"\s+", " ", ref_match.group(1).strip())
                if "qgis" in lower:
                    return label, f"{detail.title()} (QGIS)"
                return label, detail
            if "qgis" in lower:
                return label, "Atlas-Funktion (QGIS)"
            if re.search(r"katastrophenschutz|\bkarten\b", lower):
                return label, "Karten"

        if label == "Schnittstelle" and _has_integration_gap(lower):
            gap_details = _integration_gap_details(lower)
            if gap_details:
                return label, "; ".join(gap_details)

        return label, ""

    if "darstellung" in lower and re.search(
        r"f[aäe]hnchen|einzelf[aäe]hnchen", lower
    ):
        details = _darstellung_faehnchen_wunsch_details(lower)
        if len(details) > 1:
            return "Darstellung", "; ".join(details)
        detail = "Einzelfähnchen" if "einzel" in lower else "Fähnchen"
        return "Darstellung", detail

    if "bedienungsanleitung" in lower or re.search(r"\bhandbuch\b.*\bwie\b", lower):
        detail = ""
        if re.search(r"ebenen|layer", lower) and re.search(r"sichtbar|dauerhaft", lower):
            detail = "Ebenen dauerhaft sichtbar"
        elif re.search(r"ebenen|layer", lower):
            detail = "Ebenen/Layer"
        return "Bedienungsanleitung", detail

    if re.search(r"qualit[aäe]tssicherung|qualitaetssicherung", lower):
        detail = "Detailmasken" if re.search(r"detailmask", lower) else ""
        return "Qualitätssicherung", detail

    if re.search(r"\bpdfs?\b|dokumente?\b", lower):
        detail = ""
        if re.search(r"vm[\s\-]?punkt", lower):
            detail = "VM Punkte"
        elif re.search(r"offline", lower):
            detail = "Offline-Modus"
        elif re.search(r"nachtr[aä]glich", lower) and re.search(r"erg[aä]nzen", lower):
            detail = "nachträglich ergänzen"
        return "Dokumente", detail

    service_details = _service_kritik_request_details(lower)
    if service_details and _is_umstieg_service_context(lower, modul):
        return "Kommunikation", "; ".join(service_details)

    for label, needles in (
        ("Rückmeldung", ("rückmeldung", "rueckmeldung")),
        ("Erledigung", ("erledigung",)),
        ("Kommunikation", ("kommunikation",)),
    ):
        if not any(n in lower for n in needles):
            continue
        details = _service_kritik_request_details(lower)
        if not details:
            continue
        return label, "; ".join(details)

    return "", ""


def _merge_matched(*parts: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for item in part:
            if item and item not in seen:
                out.append(item)
                seen.add(item)
    return tuple(out)


def _detect_geltung(text: str, modul: str = "") -> str:
    """Geltungsbereich — z. B. modulübergreifende Wünsche."""
    lower = _normalize(text)
    if any(p in lower for p in _CROSS_MODULE_TEXT):
        if "alle module" in lower or "alle modul" in lower:
            return "Alle Module"
        return "Querschnitt"
    if re.search(r"\bf[üu]r alle\b|\bfuer alle\b", lower):
        return "Alle Module"
    modul_lower = _normalize(modul)
    if modul_lower in _CROSS_MODULE_CLUSTERS:
        return "Querschnitt"
    return ""


def _has_capability_language(text: str) -> bool:
    return any(h in text for h in _CAPABILITY_HINTS)


def _has_schnittstelle_context(text: str, modul: str = "") -> bool:
    combined = f"{_normalize(text)} {_normalize(modul)}"
    return any(h in combined for h in _SCHNITTSTELLE_HINTS)


def _has_integration_gap(text: str) -> bool:
    lower = _normalize(text)
    return any(p in lower for p in _INTEGRATION_GAP_PHRASES)


def _integration_gap_details(lower: str) -> list[str]:
    """Mehrpunkt-Feedback bei Schnittstellen-/Integrationslücken."""
    details: list[str] = []
    if re.search(r"deckt nur", lower):
        pct = re.search(r"deckt nur\s+(\d+)\s*%", lower)
        details.append(f"Umfang ~{pct.group(1)}%" if pct else "Umfang unzureichend")
    if re.search(r"geht nicht.*e[\-\s]?akte|direkt in (?:die )?e[\-\s]?akte", lower):
        target = "Stellungnahme → eAkte" if "stellungnahme" in lower else "Direktübernahme eAkte"
        details.append(target)
    if re.search(r"funktionsumfang", lower):
        details.append("Funktionsumfang eAkte" if re.search(r"e[\-\s]?akte", lower) else "Funktionsumfang")
    return details


def _update_kritik_details(lower: str) -> list[str]:
    """UI-/Workflow-Kritik nach Modulupdate."""
    details: list[str] = []
    if re.search(r"un[üu]bersichtlich", lower):
        details.append("UI unübersichtlich")
    if re.search(r"(?:zu )?viele klicks|viel zu viele klicks", lower):
        details.append("zu viele Klicks")
    if re.search(r"ausblenden|\bvz\b", lower) and re.search(
        r"fr[üu]her einfacher|war fr[üu]her", lower
    ):
        details.append("Ausblenden VZ")
    if re.search(r"r[üu]ckg[äa]ngig", lower):
        details.append("Update rückgängig")
    if re.search(r"programmieroberfl[aäe]che", lower):
        details.append("Programmieroberfläche")
    if re.search(r"kommt nicht so gut|kommt nicht gut an|nicht so gut beim", lower):
        details.append("Akzeptanz Kunde")
    return details


def _request_keywords(text: str, *, request_thema: str = "") -> tuple[str, ...]:
    """Konkreter Wunsch-Inhalt (z. B. «filterung» bei «Filterung Endhydranten …»)."""
    lower = _normalize(text)
    hits = [n for n in _REQUEST_NOUNS if n in lower]
    if request_thema:
        key = request_thema.lower()
        if key not in hits:
            hits.insert(0, key)
    return tuple(hits)


def _is_ux_haengt(text: str) -> bool:
    """«hängt an der Maus» o. ä. — Werkzeugmodus, kein Defekt-Signal."""
    return bool(re.search(r"h[äa]ngt\s+an(\s+der|\s+dem|\s+)", text))


def _request_matched(request_thema: str, request_detail: str) -> tuple[str, ...]:
    parts: list[str] = []
    if request_thema:
        parts.append(request_thema.lower())
    if request_detail:
        parts.append(request_detail)
    return tuple(parts)


def _service_kritik_hits(text: str) -> tuple[str, ...]:
    return tuple(p for p in _SERVICE_KRITIK_PHRASES if p in text)


def _is_service_kritik(text: str, *, modul: str = "") -> bool:
    hits = _service_kritik_hits(text)
    if len(hits) >= 2:
        return True
    if "problem mit" in text and bool(hits):
        return True
    if _has_schnittstelle_context(text, modul) and any(
        p in text for p in ("noch nicht erfüllt", "noch nicht erfuellt", "anforderungen an schnittstelle")
    ):
        return True
    return False


def _ux_kritik_hits(text: str) -> tuple[str, ...]:
    hits: list[str] = [p for p in _UX_KRITIK_PHRASES if p in text]
    for cluster_id in ("ux_reibung", "ux_unuebersichtlich"):
        for term in cluster_hits(text, cluster_id):
            if term not in hits:
                hits.append(term)
    return tuple(hits)


def _is_workflow_kritik(text: str) -> bool:
    """Umständlicher Workflow (z. B. PDF erzeugen → speichern → Re-Import)."""
    lower = _normalize(text)
    pdf_roundtrip = bool(
        re.search(r"\bpdf", lower)
        and re.search(r"\bimport", lower)
        and re.search(r"speicher|abgespeichert|lokal|erzeugt", lower)
    )
    negative = any(
        p in lower
        for p in (
            "ganz schlecht",
            "sehr schlecht",
            "umständlich",
            "umstaendlich",
            "mühselig",
            "muehsam",
            "mühsam",
        )
    )
    return pdf_roundtrip and negative


def _workflow_kritik_details(lower: str) -> list[str]:
    details: list[str] = []
    if re.search(r"\bpdf", lower) and re.search(r"\bimport", lower):
        details.append("PDF export → Re-Import")
    return details


def _is_ux_kritik(text: str) -> bool:
    lower = _normalize(text)
    if _is_workflow_kritik(lower):
        return True
    if any(p in lower for p in _UPDATE_KRITIK_PHRASES):
        if "update" in lower or "modulupdate" in lower or "aktualisier" in lower:
            return False
    if any_cluster_hit(lower, "ux_reibung") or any_cluster_hit(lower, "ux_unuebersichtlich"):
        return True
    hits = _ux_kritik_hits(lower)
    if len(hits) >= 2:
        return True
    return "darstellung" in lower and bool(
        re.search(r"un[üu]bersichtlich|f[aä]hnchen", lower)
    )


def _is_dokumentations_wunsch(text: str) -> bool:
    lower = _normalize(text)
    return any(p in lower for p in _DOKUMENTATIONS_WUNSCH_PHRASES)


def _is_produkt_luecke(text: str, *, modul: str = "") -> bool:
    lower = _normalize(text)
    if not any(p in lower for p in _PRODUKT_LUECKE_PHRASES):
        return False
    return bool(_normalize(modul).strip() or extract_themen(text, modul=modul))


def _detect_bedarf(text: str, *, modul: str = "") -> str:
    """Feiner Bedarf-Typ — parallel zu Intent (Update-Kritik, Feature Request, …)."""
    if any(p in text for p in _UPDATE_KRITIK_PHRASES):
        if _has_update_context(text):
            return "Update-Kritik"
    if _is_service_kritik(text, modul=modul):
        return "Service-Kritik"
    if _is_ux_kritik(text):
        return "UX-Kritik"
    if _is_dokumentations_wunsch(text):
        return "Dokumentations-Wunsch"
    if _is_produkt_luecke(text, modul=modul):
        return "Produkt-Lücke"
    if _is_ki_assistenz_wunsch(text, modul=modul):
        return "Feature Request"
    if _is_bugmeldung(text, modul=modul):
        return "Bugmeldung"
    request_thema, request_detail = extract_request(text, modul=modul)
    if request_thema and (
        request_detail
        or request_thema
        in ("Filterung", "Anbindung", "Übertragung", "Dokumente", "Integration", "Schnittstelle", "Massenexport", "Benutzerprofil", "Datenübernahme", "Workflow", "Auswertungen", "Stapelverarbeitung", "Berichtsvorlage", "Ebene", "Darstellung", "Ebenen")
    ):
        return "Feature Request"
    if any(p in text for p in _FEATURE_WUNSCH_PHRASES):
        return "Feature Request"
    if _has_schnittstelle_context(text, modul) and _has_integration_gap(text):
        return "Feature Request"
    geltung = _detect_geltung(text, modul)
    if geltung and _has_capability_language(text):
        return "Feature Request"
    return ""


def _is_update_kritik(text: str, *, modul: str = "") -> bool:
    return _detect_bedarf(text, modul=modul) == "Update-Kritik"


def _is_feature_wunsch(text: str, *, modul: str = "") -> bool:
    return _detect_bedarf(text, modul=modul) == "Feature Request"


def _service_kritik_confidence(hits: tuple[str, ...]) -> str:
    if len(hits) >= 2:
        return "hoch"
    return "mittel"


def _finalize(
    intent: str,
    matched: tuple[str, ...],
    confidence: str,
    kontakt: KontaktAngebot,
    *,
    bedarf: str = "",
    geltung: str = "",
    themen: tuple[str, ...] = (),
    request_thema: str = "",
    request_detail: str = "",
    modul: str = "",
    source_text: str = "",
) -> IntentResult:
    aktion = extract_aktion_todo(
        source_text,
        modul=modul,
        bedarf=bedarf,
        themen=themen,
        request_thema=request_thema,
        request_detail=request_detail,
    )
    kw = matched
    if kontakt.has_offer:
        kw = _merge_matched(("kontakt-angebot",), kw)
        if kontakt.ansprechpartner:
            kw = _merge_matched(kw, (kontakt.ansprechpartner,))
    if aktion:
        kw = _merge_matched(("aktion-todo",), kw)
    return IntentResult(
        intent=intent,
        matched_keywords=kw,
        confidence=confidence,
        bedarf=bedarf,
        geltung=geltung,
        themen=themen,
        request_thema=request_thema,
        request_detail=request_detail,
        kontakt_angebot=kontakt.summary(),
        ansprechpartner=kontakt.ansprechpartner,
        kontakt_zeitraum=kontakt.zeitraum,
        aktion_todo=aktion,
    )


def classify_intent(text: str, *, modul: str = "") -> IntentResult:
    """
    Ordnet Freitext einem Intent zu.

    modul: optionaler Cluster/Modul-Pfad als schwaches Zusatzsignal.
    """
    lower = _normalize(text)
    kontakt = extract_kontakt_angebot(text)
    themen = extract_themen(text, modul=modul)
    request_thema, request_detail = extract_request(text, modul=modul)
    if len(lower) < 15:
        return _finalize(
            "Sonstiges",
            (),
            "niedrig",
            kontakt,
            themen=themen,
            request_thema=request_thema,
            request_detail=request_detail,
            modul=modul,
            source_text=text,
        )

    geltung = _detect_geltung(lower, modul)
    if _is_ki_assistenz_wunsch(lower, modul=modul) and len(_ki_assistenz_request_details(lower)) >= 2:
        geltung = geltung or "Querschnitt"
    if re.search(r"stapelverarbeitung|serienbrief", lower) and len(_cross_module_codes(lower)) >= 2:
        geltung = geltung or "Querschnitt"
    bedarf = _detect_bedarf(lower, modul=modul)
    if _is_update_kritik(lower, modul=modul):
        return _finalize(
            "Defekt",
            _merge_matched(
                ("update-kritik",),
                _request_matched(request_thema, request_detail),
                themen,
            ),
            "hoch",
            kontakt,
            bedarf="Update-Kritik",
            geltung=geltung,
            themen=themen,
            request_thema=request_thema,
            request_detail=request_detail,
            modul=modul,
            source_text=text,
        )

    if _is_bauturbo_ebene_frage(lower):
        return _finalize(
            "Discovery",
            _merge_matched(
                ("bauturbo-frage",),
                _request_matched(request_thema, request_detail),
                themen,
            ),
            "hoch",
            kontakt,
            bedarf="Feature Request",
            geltung=geltung,
            themen=themen,
            request_thema=request_thema,
            request_detail=request_detail,
            modul=modul,
            source_text=text,
        )

    if _is_service_kritik(lower, modul=modul):
        service_hits = _service_kritik_hits(lower)
        return _finalize(
            "Sonstiges",
            _merge_matched(("service-kritik",), service_hits, themen),
            _service_kritik_confidence(service_hits),
            kontakt,
            bedarf="Service-Kritik",
            geltung=geltung,
            themen=themen,
            request_thema=request_thema,
            request_detail=request_detail,
            modul=modul,
            source_text=text,
        )

    if bedarf == "UX-Kritik":
        ux_hits = _ux_kritik_hits(lower)
        workflow_kw = ("workflow-kritik",) if _is_workflow_kritik(lower) else ()
        discovery_kw = ("darstellung-wunsch",) if _is_darstellung_discovery_wunsch(lower) else ()
        intent_label = (
            "Discovery" if _is_darstellung_discovery_wunsch(lower) else "Sonstiges"
        )
        return _finalize(
            intent_label,
            _merge_matched(
                ("ux-kritik",),
                workflow_kw,
                discovery_kw,
                ux_hits,
                _request_matched(request_thema, request_detail),
                themen,
            ),
            "hoch",
            kontakt,
            bedarf="UX-Kritik",
            geltung=geltung,
            themen=themen,
            request_thema=request_thema,
            request_detail=request_detail,
            modul=modul,
            source_text=text,
        )

    if bedarf == "Dokumentations-Wunsch":
        return _finalize(
            "Sonstiges",
            _merge_matched(
                ("dokumentations-wunsch",),
                _request_matched(request_thema, request_detail),
                themen,
            ),
            "hoch",
            kontakt,
            bedarf="Dokumentations-Wunsch",
            geltung=geltung,
            themen=themen,
            request_thema=request_thema,
            request_detail=request_detail,
            modul=modul,
            source_text=text,
        )

    if bedarf == "Produkt-Lücke":
        detail = request_detail or "Funktionslücken"
        return _finalize(
            "Sonstiges",
            _merge_matched(("produkt-luecke",), _request_matched("Funktionsumfang", detail), themen),
            "hoch" if kontakt.has_offer else "mittel",
            kontakt,
            bedarf="Produkt-Lücke",
            geltung=geltung,
            themen=themen,
            request_thema="Funktionsumfang",
            request_detail=detail,
            modul=modul,
            source_text=text,
        )

    if _is_schnittstelle_defekt_report(lower, modul=modul):
        return _finalize(
            "Defekt",
            _merge_matched(
                ("schnittstelle-defekt",),
                _request_matched(request_thema, request_detail),
                themen,
            ),
            "hoch",
            kontakt,
            bedarf=bedarf or "Bugmeldung",
            geltung=geltung,
            themen=themen,
            request_thema=request_thema,
            request_detail=request_detail,
            modul=modul,
            source_text=text,
        )

    if _is_feature_wunsch(lower, modul=modul):
        kw: tuple[str, ...] = ("feature-wunsch",)
        if _has_schnittstelle_context(lower, modul) and _has_integration_gap(lower):
            kw = ("feature-wunsch", "schnittstellen-luecke")
        elif geltung == "Alle Module":
            kw = ("feature-wunsch", "alle-module")
        elif geltung:
            kw = ("feature-wunsch", "querschnitt")
        if _is_ki_assistenz_wunsch(lower, modul=modul):
            kw = _merge_matched(kw, ("ki-assistenz",))
        if _is_anzeige_defekt(lower):
            kw = _merge_matched(kw, ("anzeige-defekt",))
        intent_label = (
            "Discovery"
            if _is_ki_assistenz_wunsch(lower, modul=modul)
            else ("Defekt" if _is_anzeige_defekt(lower) else "Sonstiges")
        )
        return _finalize(
            intent_label,
            _merge_matched(
                kw,
                _request_keywords(lower, request_thema=request_thema),
                _request_matched(request_thema, request_detail),
                themen,
            ),
            "hoch",
            kontakt,
            bedarf="Feature Request",
            geltung=geltung,
            themen=themen,
            request_thema=request_thema,
            request_detail=request_detail,
            modul=modul,
            source_text=text,
        )

    scores: dict[str, list[str]] = {label: [] for label in INTENT_LABELS if label != "Sonstiges"}

    for intent, keywords in _PATTERN_GROUPS.items():
        for kw in keywords:
            if _keyword_hits(lower, kw):
                if intent == "Installation" and kw in ("update", "aktualisier", "upgrade") and _is_update_kritik(lower, modul=modul):
                    continue
                if intent == "Defekt" and kw in ("hängt", "haengt") and (
                    _is_ux_haengt(lower) or _is_feature_wunsch(lower, modul=modul)
                ):
                    continue
                if intent == "Defekt" and kw == "geht nicht" and (
                    "geht nichts vorran" in lower
                    or "geht nichts voran" in lower
                    or bedarf == "Feature Request"
                    or (
                        _has_integration_gap(lower)
                        and _has_schnittstelle_context(lower, modul)
                    )
                ):
                    continue
                scores[intent].append(kw)

    disambig = _how_to_vs_discovery(lower)
    if disambig:
        if disambig == "Discovery" and "How-To" in scores:
            scores["How-To"] = [k for k in scores["How-To"] if "finde ich" not in k and "kann ich" not in k]
        if disambig == "How-To" and "Discovery" in scores:
            scores["Discovery"] = [k for k in scores["Discovery"] if k not in ("alle daten", "welche daten")]
        scores.setdefault(disambig, []).append("disambiguation")

    modul_lower = _normalize(modul)
    if modul_lower and any(k in modul_lower for k in ("karten", "karte", "app", "geo")):
        if scores.get("Discovery"):
            scores["Discovery"].append("modul:karte/app")

    best_intent = "Sonstiges"
    best_score = 0
    for intent, hits in scores.items():
        if not hits:
            continue
        weighted = _INTENT_PRIORITY.get(intent, 0) + len(hits)
        if weighted > best_score:
            best_score = weighted
            best_intent = intent

    matched = _merge_matched(tuple(scores.get(best_intent, ())), themen)
    if kontakt.has_offer and not bedarf:
        confidence = "hoch"
    elif best_intent == "Sonstiges" or not scores.get(best_intent):
        confidence = "niedrig"
    elif len(matched) >= 2 or any(len(k) > 12 for k in matched):
        confidence = "hoch"
    else:
        confidence = "mittel"

    return _finalize(
        best_intent,
        matched,
        confidence,
        kontakt,
        bedarf=bedarf,
        geltung=geltung,
        themen=themen,
        request_thema=request_thema,
        request_detail=request_detail,
        modul=modul,
        source_text=text,
    )
