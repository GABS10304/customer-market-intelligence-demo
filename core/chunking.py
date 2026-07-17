"""Text-Chunking für RAG — Chonkie V2 (Semantic + Overlap, Fallback Recursive)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from langchain_core.documents import Document

from config import _env

# Windows: HuggingFace-Cache ohne Symlinks (Developer Mode oft aus)
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

try:
    from chonkie import RecursiveChunker, SemanticChunker
except ImportError:  # pragma: no cover
    RecursiveChunker = None  # type: ignore[misc, assignment]
    SemanticChunker = None  # type: ignore[misc, assignment]

try:
    from chonkie.refinery import OverlapRefinery
except ImportError:  # pragma: no cover
    OverlapRefinery = None  # type: ignore[misc, assignment]

RAG_CHUNK_SIZE = int(_env("RAG_CHUNK_SIZE", "512") or "512")
RAG_MIN_CHUNK_CHARS = int(_env("RAG_MIN_CHUNK_CHARS", "80") or "80")
RAG_CHUNKER = (_env("RAG_CHUNKER", "semantic") or "semantic").lower()
RAG_SEMANTIC_THRESHOLD = float(_env("RAG_SEMANTIC_THRESHOLD", "0.72") or "0.72")
RAG_OVERLAP_CONTEXT = float(_env("RAG_OVERLAP_CONTEXT", "0.2") or "0.2")
RAG_SEMANTIC_MODEL = _env("RAG_SEMANTIC_MODEL", "minishlab/potion-base-32M")


@dataclass(frozen=True)
class ChunkerInfo:
    mode: str
    label: str
    chunk_size: int
    overlap_context: float
    semantic_model: str | None = None
    semantic_threshold: float | None = None


_active_mode = RAG_CHUNKER if RAG_CHUNKER in ("semantic", "recursive") else "semantic"
_semantic_chunker = None
_recursive_chunker = None
_overlap_refinery = None


def _overlap_refinery() -> object | None:
    global _overlap_refinery
    if OverlapRefinery is None:
        return None
    if _overlap_refinery is None:
        _overlap_refinery = OverlapRefinery(
            tokenizer="character",
            context_size=RAG_OVERLAP_CONTEXT,
            mode="token",
            inplace=False,
        )
    return _overlap_refinery


def _recursive_chunker() -> object | None:
    global _recursive_chunker
    if RecursiveChunker is None:
        return None
    if _recursive_chunker is None:
        _recursive_chunker = RecursiveChunker(
            tokenizer="character",
            chunk_size=RAG_CHUNK_SIZE,
            min_characters_per_chunk=24,
        )
    return _recursive_chunker


def _semantic_chunker() -> object | None:
    global _semantic_chunker, _active_mode
    if SemanticChunker is None:
        _active_mode = "recursive"
        return None
    if _semantic_chunker is None:
        try:
            _semantic_chunker = SemanticChunker(
                embedding_model=RAG_SEMANTIC_MODEL,
                threshold=RAG_SEMANTIC_THRESHOLD,
                chunk_size=RAG_CHUNK_SIZE,
                min_sentences_per_chunk=1,
            )
        except Exception:
            _active_mode = "recursive"
            _semantic_chunker = None
    return _semantic_chunker


def chunker_info() -> ChunkerInfo:
    mode = _active_mode
    if mode == "semantic" and _semantic_chunker() is None:
        mode = "recursive"
    if mode == "semantic":
        label = f"chonkie:SemanticChunker+Overlap({RAG_OVERLAP_CONTEXT:.0%})"
        return ChunkerInfo(
            mode="semantic",
            label=label,
            chunk_size=RAG_CHUNK_SIZE,
            overlap_context=RAG_OVERLAP_CONTEXT,
            semantic_model=RAG_SEMANTIC_MODEL,
            semantic_threshold=RAG_SEMANTIC_THRESHOLD,
        )
    return ChunkerInfo(
        mode="recursive",
        label=f"chonkie:RecursiveChunker+Overlap({RAG_OVERLAP_CONTEXT:.0%})",
        chunk_size=RAG_CHUNK_SIZE,
        overlap_context=RAG_OVERLAP_CONTEXT,
    )


def _split_text(text: str) -> list[str]:
    global _active_mode

    if len(text) <= RAG_CHUNK_SIZE:
        return [text]

    chunker = _semantic_chunker() if _active_mode == "semantic" else None
    if chunker is None:
        chunker = _recursive_chunker()
    if chunker is None:
        return [text]

    try:
        parts = chunker.chunk(text)
    except Exception:
        fallback = _recursive_chunker()
        if fallback is None or fallback is chunker:
            return [text]
        _active_mode = "recursive"
        try:
            parts = fallback.chunk(text)
        except Exception:
            return [text]

    texts = [part.text.strip() for part in parts if part.text.strip()]
    if not texts:
        return [text]

    refinery = _overlap_refinery()
    if refinery is not None and len(texts) > 1:
        try:
            refined = refinery.refine(parts)
            texts = [part.text.strip() for part in refined if part.text.strip()]
        except Exception:
            pass

    return texts or [text]


def chunk_documents(
    documents: list[Document],
    *,
    chunk_size: int = RAG_CHUNK_SIZE,
    min_chars: int = RAG_MIN_CHUNK_CHARS,
) -> list[Document]:
    """Zerlegt LangChain-Dokumente in semantische Chunks mit Overlap (Chonkie V2)."""
    del chunk_size  # Konfiguration über Modul-Konstanten / .env

    if not documents:
        return []

    if RecursiveChunker is None and SemanticChunker is None:
        return documents

    chunked: list[Document] = []

    for doc in documents:
        text = (doc.page_content or "").strip()
        if len(text) < min_chars:
            continue

        pieces = _split_text(text)
        if len(pieces) == 1 and pieces[0] == text:
            chunked.append(doc)
            continue

        for idx, piece in enumerate(pieces):
            if len(piece) < min_chars:
                continue
            meta = dict(doc.metadata)
            meta["chunk_index"] = idx
            meta["chunk_total"] = len(pieces)
            meta["chunker"] = chunker_info().mode
            chunked.append(Document(page_content=piece, metadata=meta))

    return chunked if chunked else documents
