"""Multi-Source Chat — Hybrid V2: BigQuery-Evidenz + Chonkie/Chroma-RAG + Graylog-Nutzung."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from config import DEMO_MODE
from core.sales_evidence import SALES_TECHNICAL_NAME
from core.llm import get_ionos_llm, synthesis_available, synthesis_setup_hint
from pipeline.rag_index import retrieve_rag_context
from workspace.compare import find_overlap
from workspace.snapshot import WorkspaceSnapshot
from workspace.sources.profiles import legacy_evidence_key

def assemble_assistant_context(*args, **kwargs):
    """Lazy-Wrapper — vermeidet ImportError bei partiellem Orchestrator in sys.modules."""
    from core.evidence_orchestrator import assemble_assistant_context as _impl

    return _impl(*args, **kwargs)


EXAMPLE_PROMPTS = [
    "Welche 5 Kundenbedürfnisse dominieren?",
    "Welche Themen sind in Tickets, Umfragen und Besuchen gleich?",
    "Welche Stellen im Produkt verursachen die meisten Anfragen?",
    "Top 10 Funktionen nach Aufrufzahl im GIS (letztes Jahr, Graylog)?",
    "Was sagen die Weihnachtsbesuche zu Export und Import?",
    "Erstelle mir auf Basis der vorhandenen Daten eine KI-Strategie und erkläre warum.",
    "Welche Quelle spricht gegen unsere Annahme?",
]


@dataclass(frozen=True)
class ChatResponse:
    text: str
    rag_hits: int = 0
    rag_stale: bool = False
    rag_stale_reason: str = ""
    graylog_used: bool = False
    graylog_from_cache: bool = False
    graylog_events: int = 0
    domains: tuple[str, ...] = ()
    mode: str = "answer"


def build_chat_context(selected_sources: list[str], ws: WorkspaceSnapshot | None = None) -> str:
    """Legacy-Fallback ohne Snapshot (Tests)."""
    if ws is not None:
        from core.evidence_orchestrator import build_snapshot_system_context

        return build_snapshot_system_context(ws, selected_sources)

    if not selected_sources:
        return "(Keine Quelle ausgewählt — bitte links im Data Catalog aktivieren.)"
    from core.bq_evidence import SOURCE_QUERIES, build_evidence_context
    from core.sales_evidence import build_sales_context

    parts = []
    for name in selected_sources:
        key = legacy_evidence_key(name)
        if name == SALES_TECHNICAL_NAME and not DEMO_MODE:
            parts.append(build_sales_context(top_n=10))
        elif key in SOURCE_QUERIES:
            parts.append(build_evidence_context(key, top_n=5))

    if len(parts) >= 2:
        parts.append("\n---\nVERGLEICH:\n")
        parts.extend(find_overlap(selected_sources))

    return "\n".join(parts)


def system_message(
    selected_sources: list[str],
    ws: WorkspaceSnapshot | None = None,
    **kwargs,
) -> SystemMessage:
    snapshot_stale = bool(kwargs.get("snapshot_stale", False))
    snapshot_stale_reason = str(kwargs.get("snapshot_stale_reason", ""))
    if ws is not None:
        from core.evidence_orchestrator import build_snapshot_system_context

        return SystemMessage(
            content=build_snapshot_system_context(
                ws,
                selected_sources,
                snapshot_stale=snapshot_stale,
                snapshot_stale_reason=snapshot_stale_reason,
            )
        )

    from config import WORKSPACE_VERSION

    context = build_chat_context(selected_sources)
    return SystemMessage(
        content=(
            f"Du bist ein Product Intelligence Assistent für RIWA (Workspace V{WORKSPACE_VERSION}). "
            "Antworte NUR auf Basis des Evidenz-Kontexts. "
            "Nur Zahlen aus den Evidenzblöcken verwenden — keine geschätzten Prozentanteile, "
            "«≈X% der Tickets», Reduktionsprognosen oder ROI erfinden. "
            "Themen-Ticket-Summen nicht als Anteil am Gesamtvolumen darstellen (Überlappung). "
            "Wenn etwas fehlt: explizit sagen, nicht erfinden. "
            f"Aktive Quellen: {', '.join(selected_sources) or 'keine'}\n\n{context}"
        )
    )


def run_chat(
    messages: list,
    user_input: str,
    selected_sources: list[str] | None = None,
    *,
    ws: WorkspaceSnapshot | None = None,
    snapshot_stale: bool = False,
    snapshot_stale_reason: str = "",
    on_graylog_progress: Callable[[str], None] | None = None,
) -> ChatResponse:
    if not synthesis_available():
        raise RuntimeError(synthesis_setup_hint())

    sources = selected_sources or []
    rag = retrieve_rag_context(user_input, sources)

    graylog_used = False
    graylog_from_cache = False
    graylog_events = 0
    domains: tuple[str, ...] = ()
    mode = "answer"
    evidence_blocks: tuple[str, ...] = ()

    if ws is not None:
        ctx = assemble_assistant_context(
            user_input,
            sources,
            ws,
            snapshot_stale=snapshot_stale,
            snapshot_stale_reason=snapshot_stale_reason,
            on_graylog_progress=on_graylog_progress,
        )
        graylog_used = ctx.graylog_used
        graylog_from_cache = ctx.graylog_from_cache
        graylog_events = ctx.graylog_events
        domains = ctx.domains
        mode = ctx.mode
        evidence_blocks = ctx.user_blocks

    sections = [user_input]
    if evidence_blocks:
        sections.extend(evidence_blocks)
    if rag.context:
        sections.append(rag.context)
    elif rag.stale and rag.stale_reason:
        sections.append(
            f"(Hinweis: RAG nicht verfügbar — {rag.stale_reason} "
            "Antwort nur aus Evidenz-Kontext.)"
        )

    user_content = "\n\n---\n".join(sections)

    llm = get_ionos_llm()
    messages.append(HumanMessage(content=user_content))
    response = llm.invoke(messages)
    text = response.content if hasattr(response, "content") else str(response)
    messages.append(AIMessage(content=text))
    return ChatResponse(
        text=text,
        rag_hits=rag.hits,
        rag_stale=rag.stale,
        rag_stale_reason=rag.stale_reason,
        graylog_used=graylog_used,
        graylog_from_cache=graylog_from_cache,
        graylog_events=graylog_events,
        domains=domains,
        mode=mode,
    )
