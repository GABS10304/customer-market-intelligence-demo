import os
import sys

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

PORTAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(PORTAL_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.bq_evidence import load_rag_meta
from decision_ui_helpers import setup_portal
from pipeline.rag_index import build_rag_index_from_bq, load_vectorstore

setup_portal()

st.set_page_config(page_title="RAG Workspace", layout="wide")
st.title("🔍 RAG Workspace (Deep Dive)")
st.caption("Index kommt aus **BigQuery** — aktualisiere über Admin → „Daten aktualisieren“.")

_SYSTEM_PROMPT = (
    "Du bist Senior Product Manager. Deine Antworten basieren AUSSCHLIESSLICH "
    "auf dem Kontext aus BigQuery. Erfinde absolut nichts."
)

_MODEL_OPTIONS = {
    "💻 LOKAL: qwen3.5:9b (Analyst)": "qwen3.5:9b",
    "💻 LOKAL: llama3.2 (Schnell)": "llama3.2",
    "💻 LOKAL: phi3 (Sehr schnell)": "phi3",
}

_RAG_SCORE_THRESHOLD = 0.42
_RAG_FETCH_K = 28
_RAG_CONTEXT_CAP = 12

if "messages" not in st.session_state:
    st.session_state.messages = [SystemMessage(content=_SYSTEM_PROMPT)]
if "vectorstore" not in st.session_state:
    st.session_state.vectorstore = load_vectorstore()

# --- Sidebar ---
with st.sidebar:
    st.header("📚 BigQuery-Index")

    meta = load_rag_meta()
    if meta:
        st.success(f"**{meta.get('documents', 0)}** Dokumente indexiert")
        st.caption(f"Stand: {meta.get('built_at', '?')[:19]} UTC")
        st.caption(f"Quelle: {meta.get('source', 'both')}")
    else:
        st.warning("Noch kein Index. Admin → „Daten aktualisieren“.")

    selected_model_label = st.selectbox(
        "KI-Motor",
        options=list(_MODEL_OPTIONS.keys()),
        index=0,
    )
    aktuelle_ki_wahl = _MODEL_OPTIONS[selected_model_label]

    if st.button("🔄 Index aus BigQuery neu laden", use_container_width=True):
        with st.spinner("Baue RAG-Index aus BigQuery..."):
            result = build_rag_index_from_bq()
        if result["success"]:
            st.session_state.vectorstore = load_vectorstore()
            st.session_state.messages = [
                SystemMessage(content=_SYSTEM_PROMPT),
                AIMessage(
                    content=f"✅ Index neu aufgebaut: {result['documents']} Dokumente aus BigQuery."
                ),
            ]
            st.rerun()
        else:
            st.error(result.get("error", "Index fehlgeschlagen"))

    if st.button("🧹 Chat leeren", use_container_width=True):
        st.session_state.messages = [SystemMessage(content=_SYSTEM_PROMPT)]
        st.rerun()

# --- Chat ---
for msg in st.session_state.messages:
    if isinstance(msg, HumanMessage) and "VERFÜGBARER KONTEXT:" not in msg.content:
        with st.chat_message("user"):
            st.write(msg.content)
    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            st.write(msg.content)

user_input = st.chat_input("Beispiel: Welche Pain Points gibt es im Modul XYZ?")

if user_input:
    with st.chat_message("user"):
        st.write(user_input)

    vectorstore = st.session_state.vectorstore
    if vectorstore is None:
        vectorstore = load_vectorstore()
        st.session_state.vectorstore = vectorstore

    context_text = ""
    if vectorstore is not None:
        retriever = vectorstore.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={
                "score_threshold": float(_RAG_SCORE_THRESHOLD),
                "k": _RAG_FETCH_K,
            },
        )
        relevante_zeilen = retriever.invoke(user_input)

        if not relevante_zeilen:
            st.warning(
                "Keine relevanten Daten gefunden. "
                "Bitte im **Admin** → **Daten aktualisieren** (Pipeline inkl. RAG-Index)."
            )
            st.stop()

        relevante_zeilen = relevante_zeilen[:_RAG_CONTEXT_CAP]
        context_text = "\nVERFÜGBARER KONTEXT (BigQuery → RAG-Index):\n"
        for i, doc in enumerate(relevante_zeilen):
            cluster = doc.metadata.get("cluster", "?")
            source = doc.metadata.get("source", "?")
            context_text += f"[{i + 1} | {source} | {cluster}]: {doc.page_content}\n"
    else:
        st.error(
            "Kein RAG-Index vorhanden. "
            "Admin → **Daten aktualisieren** oder Sidebar → **Index aus BigQuery neu laden**."
        )
        st.stop()

    hidden_prompt = f"{user_input}\n\n{context_text}"
    st.session_state.messages.append(HumanMessage(content=hidden_prompt))

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""

        llm = ChatOllama(model=aktuelle_ki_wahl, temperature=0.0, num_ctx=8192)

        for chunk in llm.stream(st.session_state.messages):
            full_response += chunk.content
            response_placeholder.markdown(full_response + "▌")

        response_placeholder.markdown(full_response)
        st.session_state.messages.append(AIMessage(content=full_response))
