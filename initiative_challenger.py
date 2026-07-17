"""
Initiative Challenger – deterministische Analyse von Mitarbeiter-Initiativen.
Kombiniert Decision Engine + Capability Detection.
Kein LLM für Berechnungen.
"""

from __future__ import annotations

import re
import uuid

from capability_detection import detect_capabilities, detected_capabilities_summary
from decision_engine import evaluate_decision

CORE_KEYWORDS = ("kern", "differentiator", "strategisch", "wettbewerb", "proprietär")
MODULE_KEYWORDS = ("modul", "feature", "funktion", "app", "software")


def _build_challenges(text: str, capabilities: list[dict], frequency: int) -> list[str]:
    challenges = []
    lower = text.lower()

    if len(text.strip()) < 40:
        challenges.append("Initiative ist sehr kurz – welches konkrete Problem soll gelöst werden?")

    if any(kw in lower for kw in ("chatgpt", "copilot", "openai", "externe ki")):
        challenges.append("DSGVO-Check: Welche Daten dürfen in externe KI-Tools? Gibt es eine interne Alternative (RAG)?")

    if frequency == 0:
        challenges.append("Fehlt Evidenz: Wie oft tritt das Problem auf? Liegen Support-Tickets oder Umfragen vor?")

    if any(kw in lower for kw in ("neu", "bauen", "entwickeln")) and not any(kw in lower for kw in MODULE_KEYWORDS):
        challenges.append("Scope unklar: Was genau soll gebaut werden – und was bewusst nicht?")

    if any(c["capability"] == "API" and c["detected"] for c in capabilities):
        challenges.append("Integrations-Impact: Welche Systeme sind betroffen und wer wartet die Schnittstelle?")

    if any(c["capability"] == "RAG" and c["detected"] for c in capabilities):
        challenges.append("RAG-Bedarf: Welche Dokumente/Datenquellen sollen indexiert werden – und wer pflegt sie?")

    if "budget" not in lower and "kosten" not in lower and "aufwand" not in lower:
        challenges.append("Business Case fehlt: Was sind geschätzte Kosten und erwarteter Nutzen?")

    if not challenges:
        challenges.append("Priorisierung: Warum jetzt – und was wird bewusst depriorisiert?")

    return challenges[:5]


def _build_insight(text: str, frequency: int, decision: dict, capabilities: list[dict]) -> str:
    lower = text.lower()
    themes = []

    if frequency >= 15:
        themes.append(f"Hohe Datenlage ({frequency} Vorkommen) – starke Evidenz für Priorisierung.")
    elif frequency > 0:
        themes.append(f"Moderate Evidenz ({frequency} Vorkommen).")
    else:
        themes.append("Noch keine quantifizierte Evidenz aus BigQuery.")

    if any(kw in lower for kw in CORE_KEYWORDS):
        themes.append("Initiative berührt potenziell Kernprodukt – Make-Neigung erhöht.")

    cap_summary = detected_capabilities_summary(capabilities)
    if "Erkannt" in cap_summary:
        themes.append(cap_summary)

    themes.append(
        f"Decision Engine: {decision['recommendation']} "
        f"(Confidence {decision['confidence']:.0%})."
    )

    return " ".join(themes)


def analyze_initiative(
    text: str,
    frequency: int = 0,
    source: str = "initiative_challenger",
) -> dict:
    """
    Vollständige Challenger-Analyse.

    Returns:
        {
            "initiative_id": str,
            "input_text": str,
            "challenge": list[str],
            "insight": str,
            "empfehlung": dict,          # decision JSON
            "capabilities": list[dict],
            "source": str,
        }
    """
    text = (text or "").strip()
    initiative_id = str(uuid.uuid4())

    capabilities = detect_capabilities(text)
    has_module = any(kw in text.lower() for kw in MODULE_KEYWORDS)
    is_core = any(kw in text.lower() for kw in CORE_KEYWORDS)

    decision = evaluate_decision(
        problem=text,
        frequency=frequency,
        has_existing_module=has_module,
        is_core_differentiator=is_core,
    )

    challenges = _build_challenges(text, capabilities, frequency)
    insight = _build_insight(text, frequency, decision, capabilities)

    return {
        "initiative_id": initiative_id,
        "input_text": text,
        "challenge": challenges,
        "insight": insight,
        "empfehlung": decision,
        "capabilities": capabilities,
        "source": source,
    }


def slug_from_text(text: str, max_len: int = 40) -> str:
    """Erzeugt einen Dateinamen-Slug für Decision Memory."""
    cleaned = re.sub(r"[^a-zA-Z0-9äöüÄÖÜß]+", "-", text.lower()).strip("-")
    return cleaned[:max_len] or "initiative"
