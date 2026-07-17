"""
RAG-Index aus BigQuery — Chonkie V2 (Semantic + Overlap) + Chroma (Ollama Embeddings).
https://github.com/chonkie-inc/chonkie
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings

from config import OLLAMA_URL, WORKSPACE_VERSION, _env, ensure_data_dirs, setup_gcp_credentials
from core.bq_evidence import (
    RAG_INDEX_DIR,
    SOURCE_QUERIES,
    fetch_feedback_documents,
    save_rag_meta,
)
from core.chunking import RAG_CHUNK_SIZE, chunk_documents, chunker_info
from core.ollama_runtime import is_ollama_running
from core.runtime import rag_freshness
from workspace.sources.profiles import legacy_evidence_key

LogFn = Callable[[str], None]

EMBED_MODEL = "nomic-embed-text"
RAG_EMBED_BATCH = int(_env("RAG_EMBED_BATCH", "64") or "64")
RAG_SCORE_THRESHOLD = 0.38
RAG_FETCH_K = 20
RAG_CONTEXT_CAP = 12


@dataclass(frozen=True)
class RagRetrieval:
    context: str
    hits: int
    stale: bool = False
    stale_reason: str = ""


def _default_log(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", errors="replace").decode("ascii"))


def _ollama_embeddings() -> OllamaEmbeddings:
    """Explizite base_url — vermeidet falsche Dynamic-Ports bei großen Batches (Windows)."""
    return OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_URL)


def load_vectorstore():
    """Lädt persistierten Chroma-Index (oder None)."""
    if not RAG_INDEX_DIR.exists():
        return None
    if not any(RAG_INDEX_DIR.iterdir()):
        return None

    setup_gcp_credentials()
    embeddings = _ollama_embeddings()
    return Chroma(persist_directory=str(RAG_INDEX_DIR), embedding_function=embeddings)


def retrieve_rag_context(
    query: str,
    selected_sources: list[str],
    *,
    k: int = RAG_FETCH_K,
    score_threshold: float = RAG_SCORE_THRESHOLD,
    cap: int = RAG_CONTEXT_CAP,
) -> RagRetrieval:
    """Semantische Treffer aus Chroma — gefiltert nach aktiven Quellen."""
    if not is_ollama_running():
        return RagRetrieval(
            context="",
            hits=0,
            stale=True,
            stale_reason="Ollama offline — RAG deaktiviert.",
        )

    fresh, reason = rag_freshness()
    if not fresh:
        return RagRetrieval(context="", hits=0, stale=True, stale_reason=reason)

    vectorstore = load_vectorstore()
    if not vectorstore or not query.strip():
        return RagRetrieval(context="", hits=0)

    legacy_keys = {
        legacy_evidence_key(name)
        for name in selected_sources
        if legacy_evidence_key(name) in SOURCE_QUERIES
    }
    if not legacy_keys:
        return RagRetrieval(context="", hits=0)

    retriever = vectorstore.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={
            "score_threshold": float(score_threshold),
            "k": int(k),
            "filter": {"source": {"$in": sorted(legacy_keys)}},
        },
    )

    try:
        hits: list[Document] = retriever.invoke(query)
    except Exception:
        hits = vectorstore.similarity_search(query, k=k)

    if not hits:
        return RagRetrieval(context="", hits=0)

    capped = hits[:cap]
    info = chunker_info()
    lines = [f"RELEVANTE TEXTSTELLEN (RAG V{WORKSPACE_VERSION} · {info.label}):"]
    for i, doc in enumerate(capped, 1):
        src = doc.metadata.get("source", "?")
        cluster = doc.metadata.get("cluster", "?")
        lines.append(f"{i}. [{src} | {cluster}] {doc.page_content[:600]}")
    return RagRetrieval(context="\n".join(lines), hits=len(capped))


def build_rag_index_from_bq(
    source: str = "both",
    limit_per_table: int = 1500,
    log: LogFn = _default_log,
) -> dict[str, Any]:
    """
    Baut den Vektor-Index aus BigQuery neu auf (Chonkie V2).

    Returns:
        {"success": bool, "documents": int, "chunks": int, "error": str | None}
    """
    ensure_data_dirs()
    key = setup_gcp_credentials()
    if not key:
        log("🛑 gcp-key.json nicht gefunden — RAG-Index übersprungen.")
        return {"success": False, "documents": 0, "chunks": 0, "error": "no_gcp_key", "skipped": True}

    if not is_ollama_running():
        log("⏭️ Ollama offline — RAG-Index übersprungen (degraded mode).")
        return {"success": False, "documents": 0, "chunks": 0, "error": "ollama_offline", "skipped": True}

    valid = {"support", "surveys", "field_visits", "both", "all"}
    src: str = source if source in valid else "both"
    if src in ("both", "all"):
        src = "both"

    info = chunker_info()
    log(f"📚 Lade Feedback aus BigQuery (Quellen: {src})...")

    try:
        documents = fetch_feedback_documents(source=src, limit_per_table=limit_per_table)  # type: ignore[arg-type]
    except Exception as exc:
        log(f"❌ BigQuery-Lesen fehlgeschlagen: {exc}")
        return {"success": False, "documents": 0, "chunks": 0, "error": str(exc)}

    if not documents:
        log("⚠️ Keine Dokumente in BigQuery — Index nicht erstellt.")
        return {"success": False, "documents": 0, "chunks": 0, "error": "no_documents"}

    by_source: dict[str, int] = {}
    for doc in documents:
        key_name = str(doc.metadata.get("source", "?"))
        by_source[key_name] = by_source.get(key_name, 0) + 1
    breakdown = ", ".join(f"{k}={v}" for k, v in sorted(by_source.items()))
    log(f"   Zeilen: {len(documents)} ({breakdown})")

    log(f"✂️ Chonkie V2 — {info.label} (chunk_size={RAG_CHUNK_SIZE})…")
    chunks = chunk_documents(documents)
    log(f"   {len(documents)} Zeilen → {len(chunks)} Chunks")

    if RAG_INDEX_DIR.exists():
        shutil.rmtree(RAG_INDEX_DIR)
    RAG_INDEX_DIR.mkdir(parents=True, exist_ok=True)

    log(
        f"🔨 Indexiere {len(chunks)} Chunks (Ollama/{EMBED_MODEL}, "
        f"batch={RAG_EMBED_BATCH})..."
    )

    try:
        embeddings = _ollama_embeddings()
        vectorstore = Chroma(
            persist_directory=str(RAG_INDEX_DIR),
            embedding_function=embeddings,
        )
        for start in range(0, len(chunks), RAG_EMBED_BATCH):
            batch = chunks[start : start + RAG_EMBED_BATCH]
            vectorstore.add_documents(batch)
            done = min(start + RAG_EMBED_BATCH, len(chunks))
            if done == len(chunks) or done % (RAG_EMBED_BATCH * 4) == 0:
                log(f"   … {done}/{len(chunks)} Chunks indexiert")
    except Exception as exc:
        log(f"❌ Index-Erstellung fehlgeschlagen: {exc}")
        return {"success": False, "documents": len(documents), "chunks": 0, "error": str(exc)}

    meta = {
        "workspace_version": WORKSPACE_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "documents": len(documents),
        "chunks": len(chunks),
        "source": src,
        "sources_indexed": sorted(by_source.keys()),
        "embed_model": EMBED_MODEL,
        "chunker": info.label,
        "chunker_mode": info.mode,
        "chunk_size": RAG_CHUNK_SIZE,
        "overlap_context": info.overlap_context,
    }
    if info.semantic_model:
        meta["semantic_model"] = info.semantic_model
        meta["semantic_threshold"] = info.semantic_threshold
    save_rag_meta(meta)
    log(f"✅ RAG-Index V{WORKSPACE_VERSION} bereit: {len(chunks)} Chunks → {RAG_INDEX_DIR}")

    return {
        "success": True,
        "documents": len(documents),
        "chunks": len(chunks),
        "error": None,
    }
