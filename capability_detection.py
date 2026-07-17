"""
Regelbasierte Erkennung von Produkt-Capabilities (RAG, API).
Kein LLM.
"""

from __future__ import annotations

RAG_SIGNALS = (
    "chatgpt", "copilot", "ki chat", "wissensdatenbank", "dokumentation durchsuchen",
    "faq", "rag", "semantic", "halluzination", "wissen abfragen", "internes wiki",
    "q&a", "fragen beantworten", "knowledge base", "suchfunktion",
)

API_SIGNALS = (
    "api", "schnittstelle", "integration", "webhook", "rest", "anbindung",
    "sync", "synchron", "import automatisch", "export automatisch", "odata",
    "schnittstellen", "middleware", "fme",
)


def _detect_type(text: str, capability: str, signals: tuple[str, ...]) -> dict:
    lower = text.lower()
    hits = [s for s in signals if s in lower]
    detected = len(hits) > 0
    confidence = min(0.95, 0.4 + len(hits) * 0.15) if detected else 0.0
    return {
        "capability": capability,
        "detected": detected,
        "signals": hits,
        "confidence": round(confidence, 2),
    }


def detect_capabilities(text: str) -> list[dict]:
    """
    Erkennt RAG- und API-Bedarf in Freitext.

    Returns:
        Liste mit dicts: capability, detected, signals, confidence
    """
    text = (text or "").strip()
    if not text:
        return [
            {"capability": "RAG", "detected": False, "signals": [], "confidence": 0.0},
            {"capability": "API", "detected": False, "signals": [], "confidence": 0.0},
        ]

    return [
        _detect_type(text, "RAG", RAG_SIGNALS),
        _detect_type(text, "API", API_SIGNALS),
    ]


def detected_capabilities_summary(capabilities: list[dict]) -> str:
    """Kurztext für UI."""
    active = [c for c in capabilities if c["detected"]]
    if not active:
        return "Kein RAG- oder API-Bedarf erkannt."
    parts = [f"{c['capability']} ({', '.join(c['signals'][:2])})" for c in active]
    return "Erkannt: " + "; ".join(parts)
