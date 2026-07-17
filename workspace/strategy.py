"""KI-Strategie — deterministische Basis + optionale LLM-Synthese."""

from __future__ import annotations

from workspace.compare import compare_sources, find_overlap
from workspace.tiles import tile_top_needs


def deterministic_strategy(selected: list[str]) -> dict:
    """Regelbasierte Strategie-Empfehlungen ohne LLM."""
    top = tile_top_needs(selected, limit=5)
    compare_df = compare_sources(selected, top_n=5)

    actions = []
    if top.empty:
        return {
            "summary": "Keine Evidenz — zuerst Daten ingestieren.",
            "actions": ["Pipeline ausführen oder CSV bestätigen."],
            "confidence": "low",
        }

    dominant = top.iloc[0]
    actions.append(
        f"Priorität 1: **{dominant['cluster']}** ({int(dominant['anzahl'])} Vorkommen) — "
        "kontextsensitive Hilfe im Produkt verbessern."
    )

    if len(selected) >= 2:
        overlap = find_overlap(selected)
        actions.append(f"Quellenvergleich: {overlap[0] if overlap else 'Kein klares Overlap'}")

    actions.append(
        "KI-Strategie (regelbasiert): Internes RAG über BigQuery vor externen Chat-Tools — "
        "DSGVO und Evidenzbindung."
    )
    if int(dominant["anzahl"]) >= 20:
        actions.append("Hohe Ticket-/Feedback-Häufigkeit → Make (eigene UX-Hilfe) vor Buy (externes KI-Tool).")

    return {
        "summary": f"Top Need: {dominant['cluster']} ({int(dominant['anzahl'])}×)",
        "actions": actions,
        "confidence": "high" if int(dominant["anzahl"]) >= 15 else "medium",
        "compare_rows": len(compare_df),
    }
