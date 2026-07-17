"""KI-Strategie-Wizard — deterministische Evidenz + optional LLM-Synthese."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from workspace.snapshot import WorkspaceSnapshot


@dataclass(frozen=True)
class StrategyBrief:
    executive_summary: str
    top_needs: list[str]
    cross_source: list[str]
    actions: list[str]
    make_buy: list[str]
    confidence: str
    gaps: list[str]


def build_strategy_brief(ws: WorkspaceSnapshot, selected: list[str]) -> StrategyBrief:
    """Schritt 1–3: Evidenz → Strategie-Kern ohne LLM."""
    strat = ws.deterministic_strategy(selected)
    top = ws.top_needs(selected, limit=5)
    overlaps = ws.find_overlap(selected) if len(selected) >= 2 else []

    top_lines = []
    for row in top.itertuples():
        top_lines.append(f"{row.cluster} ({int(row.anzahl)}×, {row.quelle})")

    make_buy: list[str] = []
    if any("Make" in a or "RAG" in a for a in strat["actions"]):
        make_buy.append("Make: Internes RAG / In-App-Guidance vor externen Chat-Tools (Evidenz + DSGVO).")
    if len(selected) >= 2 and overlaps:
        make_buy.append("Buy nur punktuell — dort wo kein Overlap und kein Kern-Differentiator.")
    if not make_buy:
        make_buy.append("Zuerst Evidenz in Compare prüfen, dann Make/Buy pro Use Case entscheiden.")

    gaps = []
    if top.empty:
        gaps.append("Keine Cluster-Daten — Pipeline oder Quellen aktivieren.")
    if len(selected) < 2:
        gaps.append("Mindestens 2 Quellen für Quellenvergleich wählen.")
    if not overlaps:
        gaps.append("Kein starkes Theme-Overlap — ggf. Modul-Mapping verbessern.")

    summary = strat["summary"]
    if overlaps:
        summary += f" · {len([o for o in overlaps if '**' in o])} gemeinsame Themen."

    return StrategyBrief(
        executive_summary=summary,
        top_needs=top_lines[:5],
        cross_source=overlaps[:8],
        actions=list(strat["actions"]),
        make_buy=make_buy,
        confidence=str(strat.get("confidence", "medium")),
        gaps=gaps,
    )


def strategy_brief_to_markdown(brief: StrategyBrief, *, title: str = "KI-Strategie (Entwurf)") -> str:
    lines = [
        f"# {title}",
        "",
        "## Executive Summary",
        brief.executive_summary,
        "",
        "## Top Kundenbedürfnisse (Evidenz)",
    ]
    lines.extend(f"- {n}" for n in brief.top_needs) or lines.append("- (keine Daten)")
    lines.extend(["", "## Quellen-Overlap (Themen)"])
    lines.extend(f"- {o.replace('**', '')}" for o in brief.cross_source) or lines.append("- (kein Overlap)")
    lines.extend(["", "## Empfohlene Maßnahmen"])
    lines.extend(f"- {a}" for a in brief.actions)
    lines.extend(["", "## Make / Buy / Partner"])
    lines.extend(f"- {m}" for m in brief.make_buy)
    if brief.gaps:
        lines.extend(["", "## Lücken / Nächste Schritte"])
        lines.extend(f"- {g}" for g in brief.gaps)
    lines.append("")
    lines.append(f"*Confidence: {brief.confidence} · deterministisch aus Snapshot*")
    return "\n".join(lines)


def synthesize_strategy_document(
    brief: StrategyBrief,
    selected_sources: list[str],
    *,
    extra_context: str = "",
) -> str:
    """Optional: LLM poliert den Markdown-Entwurf (IONOS + Freigabe)."""
    from core.llm import get_ionos_llm, llm_text, synthesis_available, synthesis_setup_hint

    if not synthesis_available():
        raise RuntimeError(synthesis_setup_hint())

    draft = strategy_brief_to_markdown(brief)
    prompt = f"""Du bist Product Strategist für B2G-SaaS. Erstelle eine knappe KI-Strategie (max. 800 Wörter)
NUR auf Basis des Evidenz-Entwurfs unten. Keine erfundenen Zahlen. Struktur:
1. Ausgangslage
2. Priorisierte Use Cases für KI (max. 5)
3. Make vs Buy vs Partner
4. Risiken (DSGVO, Halluzination)
5. 90-Tage-Roadmap (3 Meilensteine)

Aktive Quellen: {', '.join(selected_sources) or 'keine'}
{extra_context}

EVIDENZ-ENTWURF:
{draft}
"""
    llm = get_ionos_llm()
    return llm_text(llm.invoke(prompt))
