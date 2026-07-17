"""Datenschutz-Hilfsfunktionen — vor jeder LLM-Verarbeitung."""

from __future__ import annotations

import re


def scrub_pii(text: str) -> str:
    text = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "[EMAIL ENTFERNT]", text)
    text = re.sub(r"(?:\+49|0)[1-9][0-9\s\-\/]{7,}", "[TELEFON ENTFERNT]", text)
    text = re.sub(
        r"DE\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{2}",
        "[IBAN ENTFERNT]",
        text,
    )
    return text
