"""
Deterministische Make / Buy / Partner Entscheidungslogik.
Kein LLM – rein regelbasiertes Scoring.
"""

from __future__ import annotations

MAKE_KEYWORDS = (
    "kern", "differentiator", "strategisch", "wettbewerb", "proprietär",
    "stabilität", "bug", "fehler", "absturz", "performance", "usability",
    "modul", "feature", "funktion",
)

BUY_KEYWORDS = (
    "chatgpt", "copilot", "office", "microsoft", "google", "saas",
    "standard", "fertig", "markt", "lizenz", "cloud dienst", "extern",
)

PARTNER_KEYWORDS = (
    "partner", "outsourcing", "berater", "dienstleister", "white label",
    "gemeinsam", "kooperation",
)

INTEGRATION_KEYWORDS = (
    "schnittstelle", "api", "integration", "anbindung", "import", "export",
    "sync", "synchron", "webhook", "rest",
)


def _count_keyword_hits(text: str, keywords: tuple[str, ...]) -> list[str]:
    lower = text.lower()
    return [kw for kw in keywords if kw in lower]


def evaluate_decision(
    problem: str,
    frequency: int = 0,
    has_existing_module: bool = False,
    is_core_differentiator: bool = False,
) -> dict:
    """
    Liefert strukturiertes Entscheidungs-JSON.

    Returns:
        {
            "recommendation": "Make" | "Buy" | "Partner",
            "reason": str,
            "risk": str,
            "confidence": float,
        }
    """
    text = (problem or "").strip()
    if not text:
        return {
            "recommendation": "Make",
            "reason": "Kein Input – manuelle Klärung erforderlich.",
            "risk": "Entscheidung ohne Evidenz getroffen.",
            "confidence": 0.2,
        }

    make_hits = _count_keyword_hits(text, MAKE_KEYWORDS)
    buy_hits = _count_keyword_hits(text, BUY_KEYWORDS)
    partner_hits = _count_keyword_hits(text, PARTNER_KEYWORDS)
    integration_hits = _count_keyword_hits(text, INTEGRATION_KEYWORDS)

    score_make = len(make_hits) * 2.0
    score_buy = len(buy_hits) * 2.5
    score_partner = len(partner_hits) * 2.0

    if frequency >= 50:
        score_make += 3.0
    elif frequency >= 15:
        score_make += 1.5
    elif 0 < frequency < 5:
        score_buy += 2.0

    if has_existing_module:
        score_make += 2.0

    if is_core_differentiator:
        score_make += 3.0

    if len(integration_hits) >= 2:
        score_partner += 2.0
        score_buy += 1.0

    scores = {
        "Make": score_make,
        "Buy": score_buy,
        "Partner": score_partner,
    }
    recommendation = max(scores, key=scores.get)
    top = scores[recommendation]
    sorted_scores = sorted(scores.values(), reverse=True)
    margin = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else sorted_scores[0]
    confidence = min(0.95, 0.45 + margin * 0.08 + (0.1 if frequency > 0 else 0))

    reason_parts = []
    if frequency > 0:
        reason_parts.append(f"Häufigkeit: {frequency} Vorkommen in den Daten.")
    if make_hits:
        reason_parts.append(f"Make-Signale: {', '.join(make_hits[:3])}.")
    if buy_hits:
        reason_parts.append(f"Buy-Signale: {', '.join(buy_hits[:3])}.")
    if partner_hits:
        reason_parts.append(f"Partner-Signale: {', '.join(partner_hits[:3])}.")
    if integration_hits:
        reason_parts.append(f"Integrationsbedarf: {', '.join(integration_hits[:3])}.")

    reason = " ".join(reason_parts) if reason_parts else f"Scoring: Make={score_make:.1f}, Buy={score_buy:.1f}, Partner={score_partner:.1f}."

    risk_map = {
        "Make": "Hoher Entwicklungsaufwand und Wartungslast im eigenen Team.",
        "Buy": "Vendor-Lock-in, laufende Lizenzkosten und eingeschränkte Anpassbarkeit.",
        "Partner": "Abhängigkeit vom Partner und Koordinationsaufwand.",
    }
    if frequency < 5 and frequency > 0:
        risk_map[recommendation] += " Geringe Datenbasis – Entscheidung könnte sich bei mehr Evidenz ändern."

    return {
        "recommendation": recommendation,
        "reason": reason,
        "risk": risk_map[recommendation],
        "confidence": round(confidence, 2),
    }
