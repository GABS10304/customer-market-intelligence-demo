"""
Automatische Aktions-/Todo-Vorschläge aus Feldbesuchs-Feedback.

Regeln für PM-Follow-ups (Vertriebs-Klärung, …) — erweiterbar.
"""

from __future__ import annotations

import re


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def extract_aktion_todo(
    text: str,
    *,
    modul: str = "",
    bedarf: str = "",
    themen: tuple[str, ...] = (),
    request_thema: str = "",
    request_detail: str = "",
) -> str:
    """PM-Aktion / Todo-Vorschlag (z. B. Vertriebs-Klärung)."""
    lower = _normalize(text)
    modul_l = _normalize(modul)
    themen_l = " ".join(themen).lower()

    # Vertriebsversprechen vs. Produktrealität (S021: Kommuna Register / E-Akte KIC)
    vertrieb_signal = any(
        p in lower
        for p in (
            "vom kommuna vertrieb",
            "vom kommun vertrieb",
            "kommuna vertrieb",
            "kommun vertrieb",
            "vertrieb so kommuniziert",
            "wird so kommuniziert",
            "wird kommuniziert, dass",
            "wird kommuniziert dass",
        )
    )
    block_signal = any(
        p in lower
        for p in (
            "keine anbindung",
            "nicht möglich",
            "nicht moeglich",
            "geht nicht",
            "nicht umsetzbar",
        )
    )
    if vertrieb_signal and block_signal:
        if "kommuna" in lower or "kommuna" in themen_l or "kommuna" in modul_l:
            return "Klärung Kommunikation Vertrieb Kommuna/Komuna"
        return "Klärung Kommunikation Vertrieb"

    # Register-Anbindung E-Akte ohne expliziten Vertriebsbezug
    if (
        bedarf in ("Feature Request", "Service-Kritik")
        and request_thema.lower() in ("anbindung", "integration", "schnittstelle")
        and ("register" in lower or request_detail.lower() == "register")
        and ("e-akte" in lower or "kic" in lower or "e-akte" in themen_l or "kic" in themen_l)
    ):
        return "Klärung Anbindung Register (E-Akte KIC)"

    # Prozess-Vorschlag aus Feldbesuch (S030: Webinar bei Moduländerungen)
    if re.search(r"webinar", lower) and re.search(
        r"bestandskunden|bestandskunde", lower
    ):
        if re.search(r"vorschlag|anbieten|gr[öo]sseren|aenderungen|änderungen", lower):
            return "Webinar für Bestandskunden bei größeren Änderungen"

    return ""
