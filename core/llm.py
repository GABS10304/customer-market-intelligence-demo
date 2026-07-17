"""LLM-Fabrik — lokal für Rohdaten, IONOS für Synthese (nur mit Freigabe)."""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from langchain_ollama import OllamaLLM

from config import (
    CLOUD_SYNTHESIS_APPROVED,
    IONOS_BASE_URL,
    IONOS_MODEL,
    OLLAMA_MODEL,
    get_ionos_token,
)


def synthesis_available() -> bool:
    """Cloud-Synthese nur wenn Token UND explizite Datenschutz-Freigabe gesetzt."""
    return bool(get_ionos_token()) and CLOUD_SYNTHESIS_APPROVED


def synthesis_setup_hint() -> str:
    if not get_ionos_token():
        return (
            "Synthese-API nicht konfiguriert. "
            "Hinterlege IONOS_TOKEN in `.env`. "
            "Evidenz, Kacheln und Quellenvergleich funktionieren weiter ohne Chat."
        )
    if not CLOUD_SYNTHESIS_APPROVED:
        return (
            "Cloud-Synthese blockiert — Freitext darf nicht extern verarbeitet werden, "
            "bis CLOUD_SYNTHESIS_APPROVED=true in `.env` gesetzt ist (explizite Freigabe). "
            "Evidenz, Kacheln und Vergleich bleiben verfügbar."
        )
    return "Synthese bereit."


def get_local_llm(*, num_ctx: int = 8192) -> OllamaLLM:
    return OllamaLLM(model=OLLAMA_MODEL, temperature=0.0, num_ctx=num_ctx)


def get_ionos_llm() -> ChatOpenAI:
    if not synthesis_available():
        raise RuntimeError(synthesis_setup_hint())
    token = get_ionos_token()
    return ChatOpenAI(
        api_key=token,
        base_url=IONOS_BASE_URL,
        model=IONOS_MODEL,
        temperature=0.0,
    )


def llm_text(response) -> str:
    if hasattr(response, "content"):
        return str(response.content).strip()
    return str(response).strip()
