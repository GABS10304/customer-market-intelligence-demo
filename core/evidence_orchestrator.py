"""
Evidence Orchestrator — zentraler Kontext für den Assistenten (Phase 1).

Deterministische Blöcke aus Snapshot, Product Signals, TERA, Trust, Graylog.
Modi vorbereitet: answer | strategy | initiative (Initiative Phase 2+).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Literal

import pandas as pd

from config import DATA_DIR, DELIMITER, DEMO_MODE
from core.graylog_analytics import (
    build_graylog_usage_report,
    format_usage_report_markdown,
    is_graylog_usage_question,
    parse_days_from_question,
    parse_top_n_from_question,
)
from core.product_signals import DEFAULT_OUTPUT, aggregate_product_signals
from core.sales_evidence import SALES_TECHNICAL_NAME
from core.tera_scope import is_tera_hotline_cluster
from core.ticket_duration import is_duration_question
from workspace.snapshot import WorkspaceSnapshot
from workspace.sources.profiles import legacy_evidence_key, source_short_label
from workspace.strategy_wizard import build_strategy_brief, strategy_brief_to_markdown

AssistantMode = Literal["answer", "strategy", "initiative"]


@lru_cache(maxsize=1)
def _gis_tera_api() -> tuple[Any, Any]:
    """Lazy-Load von gis_pain/tera_pain.

    Top-Level-Import kann bei parallelen GIS-Edits fehlschlagen und ein partielles
    evidence_orchestrator in sys.modules hinterlassen (ohne assemble_assistant_context).
    """
    from core import gis_pain, tera_pain

    return gis_pain, tera_pain

STRATEGY_PATTERNS = (
    r"\b(ki[\s-]?strategie|strategie\s+entwurf|make\s+vs\.?\s+buy|90[\s-]?tage|roadmap)\b",
    r"\b(erstell.*strategie|strategie\s+auf\s+basis)\b",
)

INITIATIVE_PATTERNS = (
    r"\b(initiative\s+prüfen|prüfe\s+(diese|meine)\s+initiative)\b",
    r"\b(make\s*/\s*buy\s*/\s*partner|partner\s+empfehlung)\b",
)

TERA_PATTERNS = (
    r"\b(tera|terawin|support[\s-]?druck)\b",
    r"\bTERA-[A-Z]{2,}\b",
)

TERA_DURATION_PATTERNS = (
    r"\b(sekunden?|bearbeitungszeit|bearbeitungsdauer|beantwortung|antwortzeit|reaktionszeit)\b",
    r"\b(wie\s+lange|dauer|telefonanruf)\b.*\b(tera|terawin|hotline|ticket)\b",
    r"\b(tera|terawin)\b.*\b(sekunden?|bearbeitungszeit|beantwortung|antwortzeit|dauer)\b",
)

DURATION_PATTERNS = (
    r"\b(sekunden?|bearbeitungszeit|bearbeitungsdauer|beantwortung|antwortzeit|reaktionszeit)\b",
    r"\b(wie\s+lange|dauer|telefonanruf)\b.*\b(hotline|ticket)\b",
    r"\b(bearbeitungszeit|telefonanruf).*\b(sekunden?|dauer)\b",
)

PRODUCT_SIGNALS_PATTERNS = (
    r"\b(product\s+signal|impact|pain|reach|say.*feel.*do)\b",
    r"\b(hotline.*modul|modul\s+\w+.*ticket|signale\s+gesamt)\b",
)

FEEL_PATTERNS = (
    r"\b(nps|detractor|ux[\s-]?skala|feel|umfrage.*skala)\b",
)

PRIORITY_PATTERNS = (
    r"\b(priorit[äa]t|umsatz.*ticket|ticket.*umsatz|produktpriorit)\b",
)

INTENT_PATTERNS = (
    r"\b(intent|how[\s-]?to|defekt.*modul|dominant_intent)\b",
)


@dataclass(frozen=True)
class AssistantContext:
    mode: AssistantMode
    system_markdown: str
    user_blocks: tuple[str, ...]
    domains: tuple[str, ...]
    graylog_used: bool = False
    graylog_from_cache: bool = False
    graylog_events: int = 0


def detect_assistant_mode(question: str) -> AssistantMode:
    lower = (question or "").lower()
    if any(re.search(p, lower) for p in INITIATIVE_PATTERNS):
        return "initiative"
    if any(re.search(p, lower) for p in STRATEGY_PATTERNS):
        return "strategy"
    return "answer"


def _matches(patterns: tuple[str, ...], text: str) -> bool:
    lower = (text or "").lower()
    return any(re.search(p, lower) for p in patterns)


def _load_product_signals_df() -> pd.DataFrame:
    if DEFAULT_OUTPUT.exists():
        try:
            df = pd.read_csv(DEFAULT_OUTPUT, sep=DELIMITER, encoding="utf-8-sig")
            if not df.empty:
                return df
        except (OSError, pd.errors.ParserError):
            pass
    return aggregate_product_signals()


def _format_snapshot_header(
    ws: WorkspaceSnapshot,
    *,
    snapshot_stale: bool,
    snapshot_stale_reason: str,
) -> str:
    built = (ws.built_at or "")[:19].replace("T", " ")
    lines = [
        "### Workspace-Snapshot (deterministisch, für Kernzahlen verbindlich)",
        f"- Stand: **{built or '—'}** · Fingerprint `{ws.fingerprint or '—'}`",
    ]
    if snapshot_stale:
        lines.append(f"- **Hinweis:** Snapshot veraltet — {snapshot_stale_reason or 'Rebuild empfohlen.'}")
    return "\n".join(lines)


def _detect_reliability_domains(question: str, mode: AssistantMode) -> tuple[str, ...]:
    """Domains, die für diese Frage voraussichtlich in den Evidenzblöcken landen."""
    if mode == "strategy":
        return ("Snapshot", "KI-Strategie")
    if mode == "initiative":
        return ("Initiative",)

    gis_pain, tera_pain = _gis_tera_api()
    domains: list[str] = ["Snapshot"]
    if not DEMO_MODE and tera_pain.is_tera_pain_question(question):
        domains.append("TERA Pain")
    elif gis_pain.is_gis_pain_question(question):
        domains.append("GIS Pain")
    else:
        domains.append("Feedback")
    domains.append("Product Signals")
    if not DEMO_MODE:
        domains.append("TERA")
        if _is_tera_duration_question(question):
            domains.append("TERA Bearbeitungszeit")
        elif _is_duration_question(question):
            domains.append("Hotline Bearbeitungszeit")
    elif _is_duration_question(question):
        domains.append("Hotline Bearbeitungszeit")
    if _matches(PRIORITY_PATTERNS, question) and not DEMO_MODE:
        domains.append("Priorität")
    if _matches(INTENT_PATTERNS, question):
        domains.append("Intent")
    if _matches(FEEL_PATTERNS, question):
        domains.append("Feel")
    if is_graylog_usage_question(question):
        domains.append("Graylog")
    return tuple(domains)


def _scope_clarification_hint(question: str, mode: AssistantMode) -> str | None:
    """Hinweis bei breiten Fragen — LLM soll Scope klären statt pauschal Feel zu mischen."""
    if mode != "answer":
        return None
    lower = (question or "").lower().strip()
    if len(lower) < 10:
        return None
    gis_pain, tera_pain = _gis_tera_api()
    skip_hint = (
        _matches(FEEL_PATTERNS, question)
        or _is_duration_question(question)
        or gis_pain.is_gis_pain_question(question)
        or gis_pain.is_gis_focused_question(question)
    )
    if not DEMO_MODE:
        skip_hint = skip_hint or (
            _is_tera_duration_question(question)
            or tera_pain.is_tera_pain_question(question)
            or _matches(TERA_PATTERNS, question)
        )
    if skip_hint:
        return None
    if is_graylog_usage_question(question) and not re.search(
        r"\b(ticket|hotline|bedürfnis|nps|umfrage|impact|pain|priorit)\w*\b", lower
    ):
        return None
    broad = (
        _matches(PRODUCT_SIGNALS_PATTERNS, question)
        or _matches(PRIORITY_PATTERNS, question)
        or (
            re.search(r"\b(welche|top|meist\w*|wichtigste|dominant)\b", lower)
            and re.search(r"\b(module?|produkte?|themen?|signale?|tickets?|bedürfnis)\b", lower)
        )
    )
    if not broad:
        return None
    if DEMO_MODE:
        return (
            "**Scope-Hinweis:** Frage ist breit — operational (Hotline/Graylog, ohne Umfrage-Match) "
            "oder Portfolio (inkl. NPS/Feel, mapping-abhängig)? "
            "Kurz nachfragen oder in der Antwort beide Linsen getrennt ausweisen."
        )
    return (
        "**Scope-Hinweis:** Frage ist breit — operational (Hotline/TERA/Graylog, ohne Umfrage-Match) "
        "oder Portfolio (inkl. NPS/Feel, mapping-abhängig)? "
        "Kurz nachfragen oder in der Antwort beide Linsen getrennt ausweisen."
    )


def _scoped_reliability_lines(
    domains: tuple[str, ...],
    *,
    snapshot_stale: bool,
    trust,
) -> list[str]:
    """Verlässlichkeit pro genutzter Domain — nicht pauschal vom Portfolio-Level."""
    from config import DEMO_MODE

    stale_snap = "Snapshot veraltet — BQ-Aggregate können abweichen" if snapshot_stale else ""
    gis_note = (
        "Demo-Fixture Hotline-CSV — synthetische Daten"
        if DEMO_MODE
        else "Live Hotline-HTML `riwaGisData` — unabhängig vom Snapshot; Keyword-Matching auf Cluster/Freitext"
    )
    profiles: dict[str, tuple[str, str]] = {
        "Hotline Bearbeitungszeit": (
            "hoch",
            "Live-HTML `Telefonanruf (XX Sek.)` — unabhängig vom Snapshot",
        ),
        "TERA Bearbeitungszeit": (
            "hoch",
            "Live TERA-HTML — unabhängig vom Snapshot",
        ),
        "TERA": (
            "mittel",
            "ERP-Lizenzen + HTML-Hotline; Anfragen ≠ ERP-Kunden (Semantik klar)",
        ),
        "TERA Pain": (
            "mittel",
            "Keyword-Matching auf Cluster/Freitext, nur `teraWinData`",
        ),
        "GIS Pain": (
            "mittel",
            gis_note,
        ),
        "Feedback": (
            "niedrig" if snapshot_stale else "mittel",
            f"Snapshot-Cluster{'; ' + stale_snap if stale_snap else ''}; Quellen-Overlap heuristisch",
        ),
        "Snapshot": (
            "niedrig" if snapshot_stale else "mittel",
            stale_snap or "BQ-Aggregate aus Snapshot — bei Rebuild aktuell",
        ),
        "Product Signals": (
            "niedrig" if not trust.hotline_aligned or trust.matrix_mapped_pct < 40 else "mittel",
            f"Mapping {trust.matrix_mapped_pct:.0f}%; Hotline-Abgleich "
            f"{'ok' if trust.hotline_aligned else 'inkonsistent'}",
        ),
        "Feel": (
            "niedrig" if trust.survey_match_pct < 75 else "mittel",
            f"Umfrage Landkreis→ERP {trust.survey_match_pct:.0f}% gematcht",
        ),
        "Priorität": (
            "niedrig" if snapshot_stale else "mittel",
            "Umsatz×Ticket-Matching; mapping-abhängig",
        ),
        "Intent": (
            "niedrig" if snapshot_stale else "mittel",
            "Intent-Klassifikation aus Freitext/Cluster",
        ),
        "Graylog": ("mittel", "Live-API oder Cache — Nutzungsdaten oft unvollständig"),
        "KI-Strategie": (
            "niedrig" if snapshot_stale else "mittel",
            "Regelbasiert aus Snapshot — kein LLM-Raten",
        ),
        "Initiative": ("niedrig", "Phase 2 — noch ohne Auto-Evidenz"),
        "Sales": ("mittel", "ERP-Umsatz aus Snapshot"),
    }

    lines: list[str] = []
    for domain in domains:
        level, note = profiles.get(domain, ("mittel", "Standard-Evidenz"))
        lines.append(f"- **{domain}:** {level} — {note}")
    return lines


def _format_trust_block(
    signals_df: pd.DataFrame,
    *,
    question: str = "",
    mode: AssistantMode = "answer",
    snapshot_stale: bool = False,
) -> str:
    from core.trust_status import build_trust_status
    from config import DEMO_MODE

    trust = build_trust_status(signals_df)
    lines = [
        "### Trust & Datenqualität",
    ]
    if DEMO_MODE:
        lines.append(
            "- **Demo-Modus:** Alle angezeigten Daten sind **synthetische Demo-Fixtures** — "
            "keine Produktions-Evidenz."
        )
    lines.extend([
        f"- Portfolio-Level: **{trust.level}** — {trust.summary}",
        f"- Matrix: {trust.matrix_mapped}/{trust.matrix_rows} gemappt ({trust.matrix_mapped_pct}%)",
        f"- RAG: {trust.rag_label}",
    ])
    if trust.warnings:
        lines.append("- Warnungen: " + "; ".join(trust.warnings[:3]))

    if question:
        rel_domains = _detect_reliability_domains(question, mode)
        scoped = _scoped_reliability_lines(rel_domains, snapshot_stale=snapshot_stale, trust=trust)
        if scoped:
            lines.append("\n**Verlässlichkeit für diese Frage (nach Domain):**")
            lines.extend(scoped)
        scope_hint = _scope_clarification_hint(question, mode)
        if scope_hint:
            lines.append(f"\n{scope_hint}")

    return "\n".join(lines)


def _format_feedback_block(
    ws: WorkspaceSnapshot,
    selected: list[str],
    *,
    top_n: int = 8,
    question: str = "",
    signals_df: pd.DataFrame | None = None,
) -> str:
    gis_pain, tera_pain = _gis_tera_api()
    if not DEMO_MODE and tera_pain.is_tera_pain_question(question):
        return tera_pain.format_tera_pain_markdown(top_n=5, question=question)

    if gis_pain.is_gis_pain_question(question) or (
        gis_pain.is_gis_focused_question(question)
        and gis_pain.should_include_gis_module_view(question)
    ):
        return gis_pain.format_gis_combined_evidence_markdown(
            question=question,
            signals_df=signals_df,
            top_n=5,
        )

    tera_focused = not DEMO_MODE and tera_pain.is_tera_focused_question(question)
    gis_focused = gis_pain.is_gis_focused_question(question)
    fetch_limit = top_n * 4 if (tera_focused or gis_focused) else top_n
    top = ws.top_needs(selected, limit=fetch_limit)

    if tera_focused:
        lines = [
            "### Top TERA-Cluster (teraWinData, Snapshot)",
            f"- Quellen: {', '.join(source_short_label(s) for s in selected) or 'keine'}",
            "- **Scope:** Nur `teraWinData\\…` — RIWA/GIS-Module (`riwaGisData`) ausgeschlossen.",
        ]
        if not top.empty:
            top = top[top["cluster"].astype(str).apply(is_tera_hotline_cluster)]
        top = top.head(top_n)
    elif gis_focused:
        lines = [
            "### Top GIS-Cluster (riwaGisData, Snapshot)",
            f"- Quellen: {', '.join(source_short_label(s) for s in selected) or 'keine'}",
            "- **Scope:** Nur `riwaGisData\\…` — TERA (`teraWinData`) und otsBau ausgeschlossen.",
        ]
        if not top.empty:
            top = top[top["cluster"].astype(str).apply(gis_pain.is_gis_hotline_cluster)]
        top = top.head(top_n)
    else:
        lines = [
            "### Top Bedürfnisse / Cluster (Snapshot)",
            f"- Quellen: {', '.join(source_short_label(s) for s in selected) or 'keine'}",
        ]

    if top.empty:
        lines.append("- (keine Cluster in Snapshot)")
        return "\n".join(lines)

    for row in top.itertuples():
        lines.append(f"- **{row.cluster}** — {int(row.anzahl)}× ({row.quelle})")

    if len(selected) >= 2 and not tera_focused and not gis_focused:
        overlap = ws.find_overlap(selected)
        if overlap:
            lines.append("\n**Quellen-Overlap (Themen):**")
            lines.extend(f"- {o.replace('**', '')}" for o in overlap[:5])

    return "\n".join(lines)


def _format_product_signals_block(
    df: pd.DataFrame,
    *,
    top_n: int = 10,
    module_filter: str | None = None,
) -> str:
    if df.empty:
        return "### Product Signals\n- (keine Daten — `extract_product_signals.py` ausführen)"
    view = df.copy()
    if module_filter:
        needle = module_filter.lower()
        view = view[view["modul"].astype(str).str.lower().str.contains(needle, na=False)]
    sort_col = "impact_proxy" if "impact_proxy" in view.columns else "signale_gesamt"
    view = view.sort_values(sort_col, ascending=False).head(top_n)
    lines = [f"### Product Signals (Top {min(top_n, len(view))} nach Impact)"]
    for row in view.itertuples():
        hotline = int(getattr(row, "hotline_tickets", 0) or 0)
        reach = int(getattr(row, "reach_nutzer", 0) or 0)
        impact = getattr(row, "impact_proxy", "")
        nps = getattr(row, "umfrage_avg_nps", None)
        nps_s = f", NPS Ø {nps}" if pd.notna(nps) else ""
        lines.append(
            f"- **{row.modul}** — Hotline {hotline}, Reach {reach}, Impact {impact}{nps_s} "
            f"(`{getattr(row, 'mapping_id', '')}`)"
        )
    return "\n".join(lines)


def _format_tera_block(*, top_n: int = 8, full: bool = False, question: str = "") -> str:
    from core.tera_compare import format_tera_evidence_markdown

    return format_tera_evidence_markdown(question=question, top_n=top_n, full=full)


def _format_tera_duration_block(*, question: str = "", top_n: int = 5) -> str:
    from core.tera_ticket_duration import format_tera_duration_evidence_markdown

    return format_tera_duration_evidence_markdown(question=question, top_n=top_n)


def _format_duration_block(*, question: str = "", top_n: int = 5) -> str:
    from core.ticket_duration import format_duration_evidence_markdown

    return format_duration_evidence_markdown(scope="all", question=question, top_n=top_n)


def _is_tera_duration_question(question: str) -> bool:
    lower = (question or "").lower()
    if not _matches(TERA_PATTERNS, question) and not re.search(r"\b(tera|terawin)\b", lower):
        return False
    return _matches(TERA_DURATION_PATTERNS, question)


def _is_duration_question(question: str) -> bool:
    if _is_tera_duration_question(question):
        return False
    return is_duration_question(question) or _matches(DURATION_PATTERNS, question)


def _format_priority_block(ws: WorkspaceSnapshot, *, top_n: int = 8) -> str:
    df = ws.product_priority(limit=top_n)
    lines = ["### Produkt-Priorität (Umsatz × Tickets, Snapshot)"]
    if df.empty:
        lines.append("- (keine Prioritäts-Matrix)")
        return "\n".join(lines)
    for row in df.itertuples():
        umsatz = float(row.summe_umsatz)
        lines.append(
            f"- **{row.produkt}** — Umsatz {umsatz:,.0f} €, "
            f"Tickets {int(row.ticket_anzahl)}, Stufe {row.prioritaet_stufe} "
            f"(Score {float(row.prioritaet_score):.2f})".replace(",", ".")
        )
    return "\n".join(lines)


def _format_intent_block(ws: WorkspaceSnapshot, *, top_n: int = 8) -> str:
    df = ws.module_intent_table(limit=top_n)
    lines = ["### Intent pro Modul (Snapshot)"]
    if df.empty:
        lines.append("- (keine Intent-Daten)")
        return "\n".join(lines)
    for row in df.itertuples():
        lines.append(
            f"- **{row.modul}** — {int(row.eintraege)} Einträge, "
            f"Intent: {row.dominant_intent}, Bedarf: {getattr(row, 'top_bedarf', '—')}"
        )
    return "\n".join(lines)


def _format_feel_block(df: pd.DataFrame, *, top_n: int = 8) -> str:
    if df.empty or "umfrage_antworten" not in df.columns:
        return "### Feel (Umfrage-Skalen)\n- (keine Skalen-Daten)"
    feel = df[pd.to_numeric(df["umfrage_antworten"], errors="coerce").fillna(0) > 0].copy()
    feel = feel.sort_values("umfrage_antworten", ascending=False).head(top_n)
    if feel.empty:
        return "### Feel (Umfrage-Skalen)\n- (keine Skalen-Daten)"
    lines = ["### Feel — NPS / UX / Support (Product Signals)"]
    for row in feel.itertuples():
        nps = getattr(row, "umfrage_avg_nps", None)
        ux = getattr(row, "umfrage_avg_ux", None)
        parts = [f"Antworten {int(row.umfrage_antworten)}"]
        if pd.notna(nps):
            parts.append(f"NPS Ø {nps}")
        if pd.notna(ux):
            parts.append(f"UX Ø {ux}")
        lines.append(f"- **{row.modul}** — " + ", ".join(parts))
    return "\n".join(lines)


def _format_sales_block(ws: WorkspaceSnapshot, *, top_n: int = 8) -> str:
    rev = ws.sales_revenue(limit=top_n)
    lines = ["### Sales / Pay (Snapshot)"]
    if rev.empty:
        lines.append("- (keine Umsatzdaten)")
        return "\n".join(lines)
    total = ws.sales_total_revenue
    lines.append(f"- Gesamtumsatz (Snapshot): **{total:,.0f} €**".replace(",", "."))
    for row in rev.itertuples():
        umsatz = float(row.umsatz)
        lines.append(
            f"- **{row.cluster}** — {umsatz:,.0f} € ({getattr(row, 'Kundentyp', '—')})".replace(",", ".")
        )
    return "\n".join(lines)


def _format_strategy_block(ws: WorkspaceSnapshot, selected: list[str]) -> str:
    brief = build_strategy_brief(ws, selected)
    return strategy_brief_to_markdown(brief, title="KI-Strategie (Evidenz-Kern)")


def _format_initiative_stub(question: str) -> str:
    return (
        "### Initiative prüfen (Phase 2)\n"
        "Für Make/Buy/Partner-Analysen nutze den Tab **Initiative prüfen** "
        "oder formuliere: «Prüfe Initiative: …» (Auto-Evidenz folgt Phase 3).\n"
        f"- Eingabe erkannt aus: «{(question or '')[:120]}»"
    )


def _parse_module_filter(question: str) -> str | None:
    m = re.search(r"\bmodul\s+([\w\s\-]+?)(?:\?|$|\s+(?:ticket|hotline|pain|reach))", question, re.I)
    if m:
        return m.group(1).strip()
    return None


def build_snapshot_system_context(
    ws: WorkspaceSnapshot,
    selected_sources: list[str],
    *,
    snapshot_stale: bool = False,
    snapshot_stale_reason: str = "",
) -> str:
    """Kurzer System-Kontext aus Snapshot (Start-Session)."""
    parts = [
        build_assistant_system_prompt(selected_sources=selected_sources, mode="answer"),
        _format_snapshot_header(ws, snapshot_stale=snapshot_stale, snapshot_stale_reason=snapshot_stale_reason),
        _format_feedback_block(ws, selected_sources, top_n=5),
    ]
    return "\n\n".join(parts)


def build_assistant_system_prompt(
    *,
    selected_sources: list[str],
    mode: AssistantMode = "answer",
    question: str = "",
) -> str:
    from config import DEMO_MODE, WORKSPACE_VERSION

    demo_prefix = ""
    if DEMO_MODE:
        demo_prefix = (
            "**DEMO-MODUS:** Alle Zahlen stammen aus **synthetischen Demo-Fixtures** "
            "(data/demo/) — keine echten Kunden-, Produkt- oder Hotline-Daten. "
            "Produktnamen sind fiktional (GeoSuite, GeoClient, ERP Suite Demo, MapApp Demo).\n\n"
        )

    mode_hint = {
        "answer": "Beantworte Produkt-, Markt- und Evidenzfragen sachlich.",
        "strategy": "Erstelle eine KI-Strategie NUR aus dem Strategie-Evidenzblock.",
        "initiative": "Hilf bei der Einordnung von Initiativen — keine erfundenen Häufigkeiten.",
    }[mode]
    gis_pain, tera_pain = _gis_tera_api()
    gis_context_hint = ""
    if (
        gis_pain.is_gis_pain_question(question)
        or gis_pain.is_gis_context_help_question(question)
        or (
            gis_pain.is_gis_focused_question(question)
            and gis_pain.is_gis_module_view_requested(question)
        )
    ):
        gis_context_hint = (
            "Bei RIWA-Pain- oder kontextsensitiver-Hilfe-Fragen: **Sicht 1 (Themen-Top-5) aus dem Block "
            "«Sicht 1 — Themen» bzw. «GIS Pain Points» ist verbindlich** — Quelle ist Hotline HTML / "
            "riwaGisData (GIS Pain, live); **Snapshot oder Quellen-Overlap nicht als Herkunft nennen**. "
            "Keine Portfolio-Snapshot-Zahlen (Login/Import/Export gesamt), "
            "keine Umfrage-/Quellen-Overlap-Mischung. "
            "**Sicht 2 (Module & Impact)** ergänzt Top-Cluster riwaGisData und Product Signals CSV — "
            "beide Sichten zusammen nutzen; Sicht 2 ersetzt Sicht 1 nicht. "
            "Themen-Ticket-Summen nicht als Anteil am Gesamtvolumen darstellen (Themen überlappen). "
            "Keine geschätzten %-Anteile, Ticket-Reduktionen oder ROI aus Sicht 1/2 ableiten. "
            "Feldbesuche/Umfrage-NPS nicht als Hotline-Reduktion via In-App-Hilfe nennen, "
            "außer explizit danach gefragt. RAG-Zitate nur als Beispiele, nicht für die Rangfolge.\n"
        )
    tera_context_hint = ""
    if not DEMO_MODE and tera_pain.is_tera_pain_question(question):
        tera_context_hint = (
            "Bei TERA-Pain-Fragen: Themen-Ticket-Zahlen nur wie im Evidenzblock — "
            "keine %-Anteile am Gesamtvolumen (Themen überlappen), keine Reduktionsprognosen.\n"
        )
    evidence_sources = (
        "Snapshot, Product Signals, Graylog"
        if DEMO_MODE
        else "Snapshot, Product Signals, TERA, Graylog"
    )
    tera_rules = (
        ""
        if DEMO_MODE
        else (
            "Bei TERA: **Anfragen** = nur Hotline-Tickets; **ERP-Kunden** = Lizenzbasis — niemals als Anfragen addieren. "
            "Bei TERA-Fragen nur `teraWinData`/TERA-* — **niemals** `riwaGisData`/RIWA-Module oder Umfrage-Overlap mischen. "
        )
    )
    duration_rules = (
        "Bei Bearbeitungszeit/Sekunden: nutze **Hotline Bearbeitungszeit** (alle HTML-Tickets). "
        if DEMO_MODE
        else (
            "Bei Bearbeitungszeit/Sekunden: nutze **Hotline Bearbeitungszeit** (alle HTML-Tickets) "
            "oder **TERA Bearbeitungszeit** (nur `teraWinData`) — je nach Frage-Scope. "
        )
    )
    return (
        demo_prefix
        + f"Du bist der zentrale Product Intelligence Assistent für RIWA (Workspace V{WORKSPACE_VERSION}). "
        f"{mode_hint} "
        f"Antworte NUR auf Basis der deterministischen Evidenzblöcke ({evidence_sources}) "
        "und RAG-Zitaten. **Kernzahlen aus den Markdown-Blöcken sind verbindlich** — nicht schätzen oder mischen. "
        "**Zahlen-Disziplin:** Nur Zahlen verwenden, die explizit in den Evidenzblöcken stehen. "
        "Keine geschätzten Prozentanteile, «≈X% der Tickets», Reduktionsprognosen, ROI- oder Impact-Prozentzahlen erfinden. "
        "Themen-Ticket-Summen nicht als Anteil am Gesamtvolumen darstellen (Themen überlappen / sind nicht disjunkt). "
        "Wenn etwas fehlt: explizit sagen, nicht erfinden. "
        f"{tera_rules}"
        "Bei GIS-Zentrum/RIWA-GIS-Fragen nur `riwaGisData` — **niemals** TERA (`teraWinData`) oder otsBau mischen; "
        "TERA-Friedhof und GIS-Modul Friedhof sind getrennte Produktlinien. "
        "«Bei RIWA» im PM-Kontext = riwaGisData-Portfolio, nicht TERA.\n"
        f"{gis_context_hint}"
        f"{tera_context_hint}"
        f"{duration_rules}"
        "Wenn Informationen fehlen, sage das explizit.\n\n"
        f"Aktive Feedback-Quellen: {', '.join(selected_sources) or 'alle'}\n"
    )


def assemble_assistant_context(
    question: str,
    selected_sources: list[str],
    ws: WorkspaceSnapshot,
    *,
    snapshot_stale: bool = False,
    snapshot_stale_reason: str = "",
    on_graylog_progress: Callable[[str], None] | None = None,
) -> AssistantContext:
    """Baut deterministische Kontextblöcke für eine Assistenten-Anfrage."""
    mode = detect_assistant_mode(question)
    signals_df = _load_product_signals_df()
    domains: list[str] = []
    user_blocks: list[str] = []

    graylog_used = False
    graylog_from_cache = False
    graylog_events = 0

    user_blocks.append(
        _format_snapshot_header(ws, snapshot_stale=snapshot_stale, snapshot_stale_reason=snapshot_stale_reason)
    )
    domains.append("Snapshot")

    user_blocks.append(
        _format_trust_block(
            signals_df,
            question=question,
            mode=mode,
            snapshot_stale=snapshot_stale,
        )
    )
    domains.append("Trust")

    if mode == "strategy":
        user_blocks.append(_format_strategy_block(ws, selected_sources))
        domains.append("KI-Strategie")
    elif mode == "initiative":
        user_blocks.append(_format_initiative_stub(question))
        domains.append("Initiative")
    else:
        user_blocks.append(
            _format_feedback_block(
                ws,
                selected_sources,
                question=question,
                signals_df=signals_df,
            )
        )
        gis_pain, tera_pain = _gis_tera_api()
        if not DEMO_MODE and tera_pain.is_tera_pain_question(question):
            domains.append("TERA Pain")
        elif gis_pain.is_gis_pain_question(question):
            domains.append("GIS Pain")
        else:
            domains.append("Feedback")

        ps_top = (
            10
            if _matches(PRODUCT_SIGNALS_PATTERNS, question)
            and not gis_pain.is_gis_pain_question(question)
            and not (not DEMO_MODE and tera_pain.is_tera_pain_question(question))
            else 8
        )
        mod_filter = _parse_module_filter(question)
        user_blocks.append(_format_product_signals_block(signals_df, top_n=ps_top, module_filter=mod_filter))
        domains.append("Product Signals")

        if not DEMO_MODE:
            tera_full = _matches(TERA_PATTERNS, question)
            user_blocks.append(_format_tera_block(top_n=10, full=tera_full, question=question))
            domains.append("TERA")

            if _is_tera_duration_question(question):
                user_blocks.append(_format_tera_duration_block(question=question))
                domains.append("TERA Bearbeitungszeit")
            elif _is_duration_question(question):
                user_blocks.append(_format_duration_block(question=question))
                domains.append("Hotline Bearbeitungszeit")
        elif _is_duration_question(question):
            user_blocks.append(_format_duration_block(question=question))
            domains.append("Hotline Bearbeitungszeit")

        if _matches(PRIORITY_PATTERNS, question) and not DEMO_MODE:
            user_blocks.append(_format_priority_block(ws))
            domains.append("Priorität")

        selected_keys = {legacy_evidence_key(s) for s in selected_sources}
        if not DEMO_MODE and (SALES_TECHNICAL_NAME in selected_sources or "sales" in selected_keys):
            user_blocks.append(_format_sales_block(ws))
            domains.append("Sales")

        if _matches(INTENT_PATTERNS, question):
            user_blocks.append(_format_intent_block(ws))
            domains.append("Intent")

        if _matches(FEEL_PATTERNS, question):
            user_blocks.append(_format_feel_block(signals_df))
            domains.append("Feel")

        if is_graylog_usage_question(question):
            days = parse_days_from_question(question)
            top_n = parse_top_n_from_question(question)
            report = build_graylog_usage_report(
                days=days,
                top_n=top_n,
                use_cache=True,
                on_progress=on_graylog_progress,
            )
            graylog_used = True
            graylog_from_cache = report.from_cache
            graylog_events = report.events_total
            user_blocks.append(format_usage_report_markdown(report, top_n=top_n, question=question))
            domains.append("Graylog")

    system_md = build_assistant_system_prompt(
        selected_sources=selected_sources,
        mode=mode,
        question=question,
    )

    return AssistantContext(
        mode=mode,
        system_markdown=system_md,
        user_blocks=tuple(user_blocks),
        domains=tuple(domains),
        graylog_used=graylog_used,
        graylog_from_cache=graylog_from_cache,
        graylog_events=graylog_events,
    )
