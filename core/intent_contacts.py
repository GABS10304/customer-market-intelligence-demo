"""
Kontakt-Angebote aus Feldbesuchs-Freitext — Ansprechpartner für Verbesserungen.

Erkennt Formulierungen wie «kann man sich bei … melden» + optionale Zeiträume/Hinweise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


@dataclass(frozen=True)
class KontaktAngebot:
    ansprechpartner: str = ""
    zeitraum: str = ""
    hinweis: str = ""

    @property
    def has_offer(self) -> bool:
        return bool(self.ansprechpartner or self.hinweis)

    def summary(self) -> str:
        if not self.has_offer:
            return ""
        parts: list[str] = []
        if self.ansprechpartner:
            parts.append(self.ansprechpartner)
        if self.zeitraum:
            parts.append(f"ab {self.zeitraum}")
        if self.hinweis:
            parts.append(self.hinweis)
        return " — ".join(parts)


def _clean_contact_name(raw: str) -> str:
    name = re.sub(r"\s*\([^)]*\)", "", raw).strip(" .,;")
    if not name:
        return ""
    if name.isascii():
        return name.title()
    return name[0].upper() + name[1:] if len(name) > 1 else name


def _extract_zeitraum(parenthetical: str) -> str:
    inner = parenthetical.strip("()")
    for prefix in ("fängt im ", "faengt im ", "ab ", "start "):
        if inner.startswith(prefix):
            inner = inner[len(prefix) :].strip()
            break
    return re.sub(r"\s+an$", "", inner).strip()


def extract_kontakt_angebot(text: str) -> KontaktAngebot:
    """Ansprechpartner-Angebot für Produktverbesserung (Feldbesuche)."""
    lower = _normalize(text)
    if not lower:
        return KontaktAngebot()

    patterns = (
        r"kann man sich(?: gern)? bei (?:der |dem )?(.+?) melden",
        r"kann man sich(?: gern)? an (?:der |dem )?(.+?) wenden",
        r"melden sie sich(?: gern)? bei (?:der |dem )?(.+?)(?:\.|,|$)",
        r"kontakt(?:ieren)?(?: sie)?(?: gern)? (?:der |dem )?(.+?)(?:\.|,|$)",
    )

    ansprechpartner = ""
    zeitraum = ""
    for pattern in patterns:
        match = re.search(pattern, lower)
        if not match:
            continue
        raw = match.group(1).strip()
        paren = re.search(r"\(([^)]+)\)", raw)
        if paren:
            zeitraum = _extract_zeitraum(paren.group(1))
        ansprechpartner = _clean_contact_name(raw)
        break

    hinweis = ""
    if re.search(r"konkrete vorsch[lä]ge|konkrete verbesserung|was man vermisst|vermisst", lower):
        hinweis = "konkrete Verbesserungsvorschläge verfügbar"
    elif re.search(r"h[aä]tte vorschl[aä]ge|haette vorschlaege", lower):
        hinweis = "konkrete Verbesserungsvorschläge verfügbar"

    return KontaktAngebot(
        ansprechpartner=ansprechpartner,
        zeitraum=zeitraum,
        hinweis=hinweis,
    )
