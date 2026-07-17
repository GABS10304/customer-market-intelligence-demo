"""Product Intelligence Assistent — eine Oberfläche auf der Übersicht."""

from __future__ import annotations

import importlib
import sys

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from config import DEMO_MODE
from core.evidence_orchestrator import build_snapshot_system_context
from core.graylog_analytics import is_graylog_usage_question
from core.llm import synthesis_setup_hint
from workspace.assistant_loader import ASSISTANT_ENGINE_REV, chat_system_message_supports_stale_kwargs
from workspace.chat import EXAMPLE_PROMPTS, run_chat
from workspace.snapshot import WorkspaceSnapshot


def _make_session_system_message(
    active: list[str],
    ws: WorkspaceSnapshot,
    *,
    stale: bool,
    stale_reason: str,
) -> SystemMessage:
    """Erzeugt die initiale System-Nachricht — nie workspace.chat.system_message."""
    return SystemMessage(
        content=build_snapshot_system_context(
            ws,
            active,
            snapshot_stale=stale,
            snapshot_stale_reason=stale_reason,
        )
    )


def _invoke_run_chat(
    messages,
    question,
    sources,
    *,
    ws: WorkspaceSnapshot,
    snapshot_stale: bool,
    snapshot_stale_reason: str,
    on_progress=None,
):
    try:
        return run_chat(
            messages,
            question,
            sources,
            ws=ws,
            snapshot_stale=snapshot_stale,
            snapshot_stale_reason=snapshot_stale_reason,
            on_graylog_progress=on_progress,
        )
    except TypeError:
        return run_chat(messages, question, sources, on_graylog_progress=on_progress)


def _invalidate_assistant_session() -> None:
    st.session_state.messages = []
    st.session_state.assistant_engine_rev = None
    st.session_state.last_selected_sources = None
    st.session_state.last_snapshot_fp = None


def _ensure_chat_system_message_compatible() -> None:
    """Alte gecachte chat.system_message ohne **kwargs → Session leeren + Reload."""
    if chat_system_message_supports_stale_kwargs():
        return
    if "workspace.chat" in sys.modules:
        importlib.reload(sys.modules["workspace.chat"])
    if chat_system_message_supports_stale_kwargs():
        return
    _invalidate_assistant_session()


def ensure_assistant_session(
    active: list[str],
    ws: WorkspaceSnapshot,
    *,
    snapshot_stale: bool = False,
    snapshot_stale_reason: str = "",
) -> None:
    _ensure_chat_system_message_compatible()

    if st.session_state.get("assistant_engine_rev") != ASSISTANT_ENGINE_REV:
        st.session_state.messages = []
        st.session_state.assistant_engine_rev = ASSISTANT_ENGINE_REV
        st.session_state.last_selected_sources = None
        st.session_state.last_snapshot_fp = None

    if st.session_state.get("last_selected_sources") != active:
        st.session_state.messages = [
            _make_session_system_message(
                active,
                ws,
                stale=snapshot_stale,
                stale_reason=snapshot_stale_reason,
            )
        ]
        st.session_state.last_selected_sources = list(active)
        st.session_state.last_snapshot_fp = ws.fingerprint

    if ws.fingerprint != st.session_state.get("last_snapshot_fp"):
        st.session_state.messages = [
            _make_session_system_message(
                active,
                ws,
                stale=snapshot_stale,
                stale_reason=snapshot_stale_reason,
            )
        ]
        st.session_state.last_snapshot_fp = ws.fingerprint

    if not st.session_state.messages:
        st.session_state.messages = [
            _make_session_system_message(
                active,
                ws,
                stale=snapshot_stale,
                stale_reason=snapshot_stale_reason,
            )
        ]


def render_assistant_panel(
    active: list[str],
    ws: WorkspaceSnapshot,
    *,
    can_synthesize: bool,
    snapshot_stale: bool = False,
    snapshot_stale_reason: str = "",
    compact: bool = False,
    key_prefix: str = "asst",
) -> None:
    """Zentraler Assistent — Chat-UI."""
    if not can_synthesize:
        st.info(synthesis_setup_hint())
        return

    ensure_assistant_session(
        active,
        ws,
        snapshot_stale=snapshot_stale,
        snapshot_stale_reason=snapshot_stale_reason,
    )

    caption = (
        "Product Intelligence Assistent — alle Evidenzquellen: "
        + (
            "Snapshot, GIS-Pain, Product Signals, Graylog (on-demand), RAG, Dauer, Strategie."
            if DEMO_MODE
            else "Snapshot, GIS-Pain, Product Signals, TERA, Graylog (on-demand), RAG, Dauer, Strategie."
        )
        + " Kernzahlen aus Evidenzblöcken sind verbindlich."
    )
    if snapshot_stale:
        caption += f" Snapshot veraltet: {snapshot_stale_reason}"
    st.caption(caption)

    if not compact:
        for msg in st.session_state.messages:
            if isinstance(msg, HumanMessage):
                with st.chat_message("user"):
                    st.write(msg.content.split("\n\n---\n")[0])
            elif isinstance(msg, AIMessage):
                with st.chat_message("assistant"):
                    st.write(msg.content)

    prompts = EXAMPLE_PROMPTS[:4 if compact else 6]
    cols = st.columns(min(3, len(prompts)))
    for i, prompt in enumerate(prompts):
        with cols[i % len(cols)]:
            if st.button(prompt, key=f"{key_prefix}_p_{i}", use_container_width=True):
                try:
                    _invoke_run_chat(
                        st.session_state.messages,
                        prompt,
                        active,
                        ws=ws,
                        snapshot_stale=snapshot_stale,
                        snapshot_stale_reason=snapshot_stale_reason,
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    placeholder = (
        "Frage zu Bedürfnissen, Product Signals, Graylog, Strategie…"
        if DEMO_MODE
        else "Frage zu Bedürfnissen, Product Signals, TERA, Graylog, Strategie…"
    )
    if user_q := st.chat_input(placeholder, key=f"{key_prefix}_input"):
        with st.chat_message("user"):
            st.write(user_q)
        try:
            with st.chat_message("assistant"):
                graylog_q = is_graylog_usage_question(user_q)
                status_box = st.empty()
                if graylog_q:
                    status_box.caption("Graylog-Nutzungsdaten werden geladen…")
                with st.spinner(
                    "Graylog-Abruf läuft (kann bei leerem Cache mehrere Minuten dauern)…"
                    if graylog_q
                    else "Antwort wird erstellt…"
                ):
                    result = _invoke_run_chat(
                        st.session_state.messages,
                        user_q,
                        active,
                        ws=ws,
                        snapshot_stale=snapshot_stale,
                        snapshot_stale_reason=snapshot_stale_reason,
                        on_progress=lambda msg: status_box.caption(msg),
                    )
                status_box.empty()
                st.write(result.text)
                meta = []
                if result.domains:
                    meta.append(" · ".join(result.domains))
                if result.graylog_used:
                    cache_note = "Cache" if result.graylog_from_cache else "Live"
                    meta.append(f"Graylog {result.graylog_events:,} ({cache_note})")
                if result.rag_hits:
                    meta.append(f"RAG {result.rag_hits}")
                if result.mode != "answer":
                    meta.append(f"Modus {result.mode}")
                if meta:
                    st.caption(" · ".join(meta))
        except Exception as exc:
            st.error(str(exc))
