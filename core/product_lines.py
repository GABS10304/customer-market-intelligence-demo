"""
Produktlinien — Modul, App, Dienstleistung, Messstab, Plattform, Paket.

Ticket-Cluster (Ordner___Modul) und Sales-Artikelbezeichnungen werden
auf eine gemeinsame Linie gemappt — nicht alles ist ein «Modul».
"""

from __future__ import annotations

import re
from typing import Literal

from core.tera_scope import is_tera_hotline_cluster

ProductLine = Literal[
    "Modul",
    "TERA",
    "App",
    "Dienstleistung",
    "Messstab / Standard",
    "Plattform / Client",
    "Paket / Daten",
    "Sonstiges",
]

ALL_PRODUCT_LINES: tuple[str, ...] = (
    "Modul",
    "TERA",
    "App",
    "Dienstleistung",
    "Messstab / Standard",
    "Plattform / Client",
    "Paket / Daten",
    "Sonstiges",
)

PRODUCT_LINE_HINTS: dict[str, dict[str, str]] = {
    "Modul": {
        "kurz": "Fachmodule — was der Kunde fachlich nutzt (Verkehr, BauAV, Friedhof, …).",
        "abgrenzung": "Nicht Datenhaltung/Filehosting: «Modul Bebauungspläne» = Fachmodul, "
        "«Datenhaltung Modul Bebauungspläne» = Paket / Daten. Nicht TERA (eigene Linie).",
        "keywords": "Modul · Modul - … · Ticket-Pfad riwaGisData\\Modul - …",
    },
    "TERA": {
        "kurz": "TERA-Produktlinie — eigenständige Verwaltungssoftware (TERA-FRI, TERA-RES, …).",
        "abgrenzung": "Alles mit ERP-Präfix TERA-* und Hotline unter teraWinData\\… — "
        "nicht in der GIS-Modulliste mischen.",
        "keywords": "TERA-* · teraWinData\\ · tera.csv · TERA-Tab",
    },
    "App": {
        "kurz": "Mobile oder eigenständige Apps (KartenApp, Kontroll-App, …).",
        "abgrenzung": "Apps mit «Modul» im Pfadanfang werden weiter als Modul gezählt.",
        "keywords": "Apps · App · -app · kontroll-app · vermessungs-app",
    },
    "Dienstleistung": {
        "kurz": "Schulung, Beratung, Wartung, Support — kein Softwareprodukt.",
        "abgrenzung": "Oft nur in Verträgen sichtbar, selten in Hotline-Clustern.",
        "keywords": "Dienstleistung · Schulung · Beratung · Wartung · Hotline · Pflege",
    },
    "Messstab / Standard": {
        "kurz": "Messmittel, Kalibrierung, Prüfverfahren — explizit «Messstab», nicht Vermessung.",
        "abgrenzung": "«Modul Vermessungsdaten» bleibt Modul; «Messstab» ist eigene Linie.",
        "keywords": "Messstab · Messstandard · Kalibrier · Prüfverfahren",
    },
    "Plattform / Client": {
        "kurz": "RGZ Client, Einzelplatz/Netzwerk — Laufzeitumgebung, nicht Fachinhalt.",
        "abgrenzung": "Infrastruktur zum Starten der RIWA-Anwendungen.",
        "keywords": "RGZ Client · Client - · Einzelplatz · Netzwerkversion",
    },
    "Paket / Daten": {
        "kurz": "Daten-Infrastruktur: Hosting, WMS-Anbindung, Datenhaltung — nicht die Fachanwendung.",
        "abgrenzung": "«Wie werden Geodaten gehalten/angeliefert?» — nicht «Was kann der Kunde damit tun?».",
        "keywords": "datenhaltung · filehosting · anbindung wms · geobasis · fachdienstdaten · datenpflegepaket",
    },
    "Sonstiges": {
        "kurz": "Cluster/Artikel ohne passendes Keyword — heterogener Sammelbecken.",
        "abgrenzung": "Prüfen, ob Mapping oder Keyword-Regel fehlt.",
        "keywords": "Fallback, wenn keine andere Linie passt",
    },
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def classify_product_line_with_reason(label: str) -> tuple[str, str]:
    """
    Ordnet Cluster-Pfad oder Artikelbezeichnung einer Produktlinie zu.
    Gibt (Linie, Nachvollziehbarkeits-Hinweis) zurück.
    """
    raw = (label or "").strip()
    lower = _norm(raw)
    if not lower:
        return "Sonstiges", "Leerer Name"

    if is_tera_hotline_cluster(raw):
        bereich = raw.split("\\", 1)[0] if "\\" in raw else "teraWinData"
        return "TERA", f"Hotline-Bereich {bereich}"

    if lower.startswith("tera-") or lower.startswith("tera "):
        return "TERA", "ERP-Artikel TERA-*"
    if re.match(r"^tera[a-z]", lower) and "terawindata" not in lower:
        return "TERA", "TERA-Produktname im ERP"

    leaf = raw.rsplit("\\", 1)[-1].strip()
    prefix = leaf.split(" - ", 1)[0].strip().lower() if " - " in leaf else lower

    if prefix.startswith("apps") or prefix == "app" or re.search(r"\bapp\b", lower):
        if "modul" not in lower[:20]:
            return "App", f"App-Prefix «{leaf.split(' - ', 1)[0].strip()}»"
    if "-app" in lower or lower.endswith(" app") or "kontroll-app" in lower or "vermessungs-app" in lower:
        return "App", "Keyword «app» im Namen"

    if prefix.startswith("modul") or lower.startswith("modul ") or "modul -" in lower:
        return "Modul", f"Modul-Prefix «{leaf.split(' - ', 1)[0].strip() if ' - ' in leaf else 'Modul'}»"

    paket_keys = (
        "datenpflegepaket",
        "filehosting",
        "anbindung wms",
        "geobasis",
        "fachdienstdaten",
        "datenhaltung",
    )
    for key in paket_keys:
        if key in lower:
            return "Paket / Daten", f"Keyword «{key}» — Daten-Infrastruktur, kein Fachmodul"

    dienst_keys = (
        "dienstleist",
        "dienstleistungen",
        "schulung",
        "beratung",
        "implementierung",
        "support-paket",
        "hotline",
        "wartung",
        "instandhaltung",
        "pflege",
    )
    for key in dienst_keys:
        if key in lower:
            return "Dienstleistung", f"Keyword «{key}»"

    if "messstab" in lower or "mess stäb" in lower or "messsta" in lower:
        return "Messstab / Standard", "Keyword «messstab»"
    mess_keys = ("messstandard", "messmittel", " kalibrier", "prüfverfahren")
    for key in mess_keys:
        if key in lower:
            return "Messstab / Standard", f"Keyword «{key.strip()}»"

    plattform_keys = ("rgz client", "rgz allgemein", "client -", " rg z ", "einzelplatz", "netzwerkversion")
    for key in plattform_keys:
        if key in lower:
            return "Plattform / Client", f"Keyword «{key.strip()}»"

    if "modul" in lower:
        return "Modul", "Enthält «modul» (Fallback nach Paket/Daten-Prüfung)"

    return "Sonstiges", "Kein Produktlinien-Keyword erkannt"


def classify_product_line(label: str) -> str:
    """Ordnet Cluster-Pfad oder Artikelbezeichnung einer Produktlinie zu."""
    return classify_product_line_with_reason(label)[0]
