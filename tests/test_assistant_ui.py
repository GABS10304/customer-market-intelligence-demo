"""Smoke-Tests für assistant_ui — keine Streamlit-/LLM-Abhängigkeit."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

for _mod in (
    "google.cloud",
    "google.cloud.bigquery",
    "langchain_core",
    "langchain_core.documents",
    "langchain_core.messages",
    "langchain_openai",
    "streamlit",
    "pipeline.rag_index",
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

sys.modules["langchain_core.messages"].AIMessage = MagicMock
sys.modules["langchain_core.messages"].HumanMessage = MagicMock
sys.modules["langchain_core.messages"].SystemMessage = lambda content: {"role": "system", "content": content}

_llm_mock = MagicMock()
_llm_mock.synthesis_setup_hint.return_value = "LLM nicht konfiguriert"
sys.modules["core.llm"] = _llm_mock

import pytest

from workspace.snapshot import WorkspaceSnapshot


def _minimal_ws() -> WorkspaceSnapshot:
    return WorkspaceSnapshot.from_dict(
        {
            "fingerprint": "fp1",
            "built_at": "2026-07-16T08:00:00+00:00",
            "cluster_counts": {},
            "source_themes": {},
            "data_coverage": [],
        }
    )


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df")
def test_initial_system_message_never_calls_chat_system_message(mock_signals, mock_trust):
    import pandas as pd

    from core.trust_status import TrustStatus
    from workspace.assistant_loader import load_assistant_ui

    assistant_ui = load_assistant_ui()

    mock_signals.return_value = pd.DataFrame()
    mock_trust.return_value = TrustStatus(
        level="mittel",
        summary="ok",
        snapshot_at="",
        snapshot_source="",
        mapping_seed_entries=0,
        matrix_rows=0,
        matrix_mapped=0,
        matrix_mapped_pct=0.0,
        hotline_unmapped_pct=0.0,
        hotline_aligned=True,
        survey_match_pct=0.0,
        rag_fresh=True,
        rag_label="ok",
        rag_documents=0,
        product_signals_label="",
        warnings=(),
        actions=(),
        top_unmapped=(),
    )

    msg = assistant_ui._make_session_system_message(
        ["support_tickets_html"],
        _minimal_ws(),
        stale=True,
        stale_reason="test stale",
    )
    assert "Workspace-Snapshot" in msg["content"]
    assert "veraltet" in msg["content"]


def test_invoke_run_chat_falls_back_on_type_error():
    from workspace.assistant_loader import load_assistant_ui

    assistant_ui = load_assistant_ui()

    calls = []

    def _new_run_chat(*args, **kwargs):
        if kwargs.get("ws") is not None:
            raise TypeError("unexpected keyword argument 'ws'")
        calls.append("fallback")
        return MagicMock(text="ok", domains=(), mode="answer", graylog_used=False, graylog_from_cache=False, graylog_events=0, rag_hits=0)

    with patch.object(assistant_ui, "run_chat", side_effect=_new_run_chat):
        result = assistant_ui._invoke_run_chat(
            [],
            "test?",
            ["support_tickets_html"],
            ws=_minimal_ws(),
            snapshot_stale=False,
            snapshot_stale_reason="",
        )
    assert calls == ["fallback"]
    assert result.text == "ok"


def test_assistant_ui_import_line_excludes_system_message():
    text = open("workspace/assistant_ui.py", encoding="utf-8").read()
    import_line = next(line for line in text.splitlines() if line.startswith("from workspace.chat import"))
    assert "system_message" not in import_line
    assert "_make_session_system_message" in text
    assert "build_snapshot_system_context" in text


def test_chat_system_message_accepts_stale_kwargs():
    from workspace.chat import system_message

    msg = system_message(
        ["support_tickets_html"],
        _minimal_ws(),
        snapshot_stale=True,
        snapshot_stale_reason="stale reason",
    )
    content = msg.content if hasattr(msg, "content") else msg["content"]
    assert "Snapshot" in content or "Assistent" in content or "RIWA" in content


def test_chat_system_message_supports_stale_kwargs_probe():
    from workspace.assistant_loader import chat_system_message_supports_stale_kwargs, load_assistant_ui

    load_assistant_ui()
    assert chat_system_message_supports_stale_kwargs() is True


def test_invalidate_on_incompatible_system_message():
    from types import SimpleNamespace

    from workspace.assistant_loader import load_assistant_ui

    assistant_ui = load_assistant_ui()
    session = SimpleNamespace(
        messages=[{"role": "system", "content": "old"}],
        assistant_engine_rev="old-rev",
        last_selected_sources=["a"],
        last_snapshot_fp="fp",
    )

    with patch.object(assistant_ui, "chat_system_message_supports_stale_kwargs", return_value=False):
        with patch("workspace.assistant_ui.st") as mock_st:
            mock_st.session_state = session
            assistant_ui._ensure_chat_system_message_compatible()

    assert session.messages == []
    assert session.assistant_engine_rev is None
