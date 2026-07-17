"""Tests fuer workspace.chat mit gemocktem LLM/RAG."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

for _mod in (
    "google.cloud",
    "google.cloud.bigquery",
    "langchain_openai",
    "langchain_ollama",
    "pipeline.rag_index",
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_llm_mod = MagicMock()
_llm_mod.synthesis_available.return_value = True
_llm_mod.synthesis_setup_hint.return_value = "hint"
_llm_mod.get_ionos_llm.return_value = MagicMock(
    invoke=MagicMock(return_value=MagicMock(content="Antwort aus Test"))
)
sys.modules["core.llm"] = _llm_mod

_rag_mod = MagicMock()
_rag_mod.retrieve_rag_context.return_value = MagicMock(
    context="RAG snippet", hits=2, stale=False, stale_reason=""
)
sys.modules["pipeline.rag_index"] = _rag_mod

from langchain_core.messages import HumanMessage, SystemMessage

from core.sales_evidence import SALES_TECHNICAL_NAME
from workspace.chat import build_chat_context, run_chat, system_message
from workspace.snapshot import WorkspaceSnapshot


def _ws() -> WorkspaceSnapshot:
    return WorkspaceSnapshot.from_dict(
        {
            "fingerprint": "fp",
            "built_at": "2026-07-16T08:00:00+00:00",
            "cluster_counts": {
                "support:30": [
                    {"quelle": "Support", "cluster": "riwaGisData\\Modul - Verkehr", "anzahl": 10}
                ]
            },
            "source_themes": {},
            "data_coverage": [],
        }
    )


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df")
@patch("core.evidence_orchestrator._format_tera_block", return_value="### TERA")
def test_system_message_with_snapshot(mock_tera, mock_signals, mock_trust):
    from core.trust_status import TrustStatus

    mock_signals.return_value = __import__("pandas").DataFrame()
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
    msg = system_message(["support_tickets_html"], _ws(), snapshot_stale=True, snapshot_stale_reason="stale")
    content = msg["content"] if isinstance(msg, dict) else msg.content
    assert "veraltet" in content
    assert "Assistent" in content or "RIWA" in content
    assert "Keine geschätzten Prozentanteile" in content


@patch("workspace.chat.build_chat_context", return_value="legacy context")
def test_system_message_legacy_forbids_invented_percentages(mock_ctx):
    msg = system_message(["support_tickets_html"], ws=None)
    content = msg["content"] if isinstance(msg, dict) else msg.content
    assert "Keine geschätzten Prozentanteile" in content or "keine geschätzten Prozentanteile" in content
    assert "Reduktionsprognosen" in content
    assert "nicht erfinden" in content
    assert "legacy context" in content


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df")
@patch("core.evidence_orchestrator._format_tera_block", return_value="### TERA")
@patch("workspace.chat.assemble_assistant_context")
def test_run_chat_with_orchestrator(mock_assemble, mock_tera, mock_signals, mock_trust):
    from core.evidence_orchestrator import AssistantContext

    mock_signals.return_value = __import__("pandas").DataFrame()
    mock_trust.return_value = MagicMock()
    mock_assemble.return_value = AssistantContext(
        mode="answer",
        system_markdown="sys",
        user_blocks=("block1",),
        domains=("Snapshot", "Trust"),
        graylog_used=False,
    )
    messages = [SystemMessage(content="init")]
    result = run_chat(messages, "Wie viele Tickets?", ["support_tickets_html"], ws=_ws())
    assert result.text == "Antwort aus Test"
    assert result.domains == ("Snapshot", "Trust")
    assert len(messages) == 3
    assert isinstance(messages[-2], HumanMessage)


@patch("workspace.compare.find_overlap", return_value=["overlap line"])
@patch("core.bq_evidence.build_evidence_context", return_value="evidence block")
def test_build_chat_context_legacy_multi_source(mock_evidence, mock_overlap):
    ctx = build_chat_context(["support_tickets_html", "survey_freetext_250"], ws=None)
    assert "evidence block" in ctx
    assert "VERGLEICH" in ctx
    assert mock_evidence.call_count >= 1


@patch("core.sales_evidence.build_sales_context", return_value="sales block")
def test_build_chat_context_legacy_sales(mock_sales):
    ctx = build_chat_context([SALES_TECHNICAL_NAME], ws=None)
    assert "sales block" in ctx


def test_build_chat_context_empty_sources():
    ctx = build_chat_context([], ws=None)
    assert "Keine Quelle" in ctx
