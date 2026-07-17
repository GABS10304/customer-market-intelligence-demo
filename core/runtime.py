"""Betriebsmodus — Start-Checks, Degraded Mode, sichtbarer Systemstatus."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from config import (
    CLOUD_SYNTHESIS_APPROVED,
    DEMO_MODE,
    DEPLOYMENT_MODE,
    SNAPSHOT_PATH,
    WORKSPACE_VERSION,
    get_ionos_token,
    setup_gcp_credentials,
)
from core.bq_evidence import RAG_INDEX_DIR, load_rag_meta
from core.ollama_runtime import is_ollama_running
from workspace.catalog import load_catalog


@dataclass(frozen=True)
class RuntimeStatus:
    """Aktueller Betriebsmodus des Workspaces."""

    mode: str  # full | evidence | snapshot-only
    workspace_version: str = WORKSPACE_VERSION
    deployment_mode: str = DEPLOYMENT_MODE
    gcp_ok: bool = False
    ollama_ok: bool = False
    synthesis_token: bool = False
    synthesis_approved: bool = False
    synthesis_ok: bool = False
    snapshot_ok: bool = False
    rag_index_ok: bool = False
    rag_fresh: bool = False
    rag_stale_reason: str = ""
    messages: tuple[str, ...] = field(default_factory=tuple)
    demo_mode: bool = False

    @property
    def mode_label(self) -> str:
        if self.demo_mode:
            return "Demo-Modus (synthetische Daten)"
        return {
            "full": "Vollbetrieb",
            "evidence": "Evidenz-Modus (ohne LLM/RAG)",
            "snapshot-only": "Snapshot-Modus (offline)",
        }.get(self.mode, self.mode)

    @property
    def chat_available(self) -> bool:
        return self.synthesis_ok and self.gcp_ok

    @property
    def rag_available(self) -> bool:
        return self.rag_index_ok and self.rag_fresh and self.ollama_ok


def _parse_iso(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None


RAG_CATALOG_SOURCES: dict[str, str] = {
    "field_visits": "field_visits_weihnachtsbesuche",
    "support": "support_tickets_html",
    "surveys": "survey_freetext_250",
}


def _rag_evidence_timestamp(meta: dict) -> datetime | None:
    """Zeitstempel der zuletzt indexierten Quellen — nicht catalog.updated_at."""
    catalog = load_catalog()
    indexed = meta.get("sources_indexed") or list(RAG_CATALOG_SOURCES.keys())
    times: list[datetime] = []
    for key in indexed:
        tech = RAG_CATALOG_SOURCES.get(str(key), str(key))
        entry = catalog.get("sources", {}).get(tech, {})
        t = _parse_iso(entry.get("last_updated"))
        if t:
            times.append(t)
    if times:
        return max(times)
    return _parse_iso(meta.get("evidence_at"))


def rag_freshness() -> tuple[bool, str]:
    """Prüft ob RAG-Index existiert und zur Evidenz der indexierten Quellen passt."""
    meta = load_rag_meta()
    if not meta:
        return False, "Kein RAG-Index — Pipeline starten (Schritt RAG)."

    if not RAG_INDEX_DIR.exists() or not any(RAG_INDEX_DIR.iterdir()):
        return False, "Chroma-Index fehlt auf Disk."

    rag_at = _parse_iso(meta.get("built_at"))
    evidence_at = _rag_evidence_timestamp(meta)
    if rag_at and evidence_at and evidence_at > rag_at:
        return False, "RAG-Index älter als BigQuery-Evidenz — Pipeline Schritt 5 (RAG) ausführen."

    return True, "Index aktuell"


def get_runtime_status(*, check_ollama: bool = True) -> RuntimeStatus:
    """Ermittelt den Betriebsmodus für UI und Pipeline."""
    messages: list[str] = []

    if DEMO_MODE:
        messages.append(
            "Demo-Modus: synthetische Fixtures aus data/demo/ — kein BigQuery, Graylog oder Ollama nötig."
        )
        snapshot_ok = SNAPSHOT_PATH.exists()
        if not snapshot_ok:
            messages.append("Demo-Snapshot fehlt — data/demo/workspace_snapshot.json prüfen.")
        return RuntimeStatus(
            mode="evidence",
            gcp_ok=False,
            ollama_ok=False,
            synthesis_token=False,
            synthesis_approved=False,
            synthesis_ok=False,
            snapshot_ok=snapshot_ok,
            rag_index_ok=False,
            rag_fresh=False,
            rag_stale_reason="RAG im Demo-Modus deaktiviert.",
            messages=tuple(messages),
            demo_mode=True,
        )

    gcp_ok = setup_gcp_credentials() is not None
    if not gcp_ok:
        messages.append("BigQuery: gcp-key.json fehlt — nur Snapshot von Disk möglich.")

    ollama_ok = is_ollama_running() if check_ollama else False
    if check_ollama and not ollama_ok:
        messages.append("Ollama offline — CSV/HTML/RAG übersprungen; Evidenz aus BQ/Snapshot bleibt.")

    synthesis_token = bool(get_ionos_token())
    synthesis_approved = CLOUD_SYNTHESIS_APPROVED
    synthesis_ok = synthesis_token and synthesis_approved

    if synthesis_token and not synthesis_approved:
        messages.append(
            "Cloud-Synthese blockiert: CLOUD_SYNTHESIS_APPROVED=true in .env setzen "
            "(explizite Datenschutz-Freigabe erforderlich)."
        )
    elif not synthesis_token:
        messages.append("Chat-Synthese deaktiviert — IONOS_TOKEN fehlt.")

    snapshot_ok = SNAPSHOT_PATH.exists()
    if not snapshot_ok:
        messages.append("Kein Evidenz-Snapshot — Pipeline oder BigQuery-Zugriff nötig.")

    rag_meta = load_rag_meta()
    rag_index_ok = bool(rag_meta) and RAG_INDEX_DIR.exists() and any(RAG_INDEX_DIR.iterdir())
    rag_fresh, rag_reason = rag_freshness()
    if rag_index_ok and not rag_fresh:
        messages.append(f"RAG veraltet: {rag_reason}")

    if gcp_ok and ollama_ok and synthesis_ok and rag_fresh:
        mode = "full"
    elif gcp_ok or snapshot_ok:
        mode = "evidence"
    else:
        mode = "snapshot-only"

    return RuntimeStatus(
        mode=mode,
        gcp_ok=gcp_ok,
        ollama_ok=ollama_ok,
        synthesis_token=synthesis_token,
        synthesis_approved=synthesis_approved,
        synthesis_ok=synthesis_ok,
        snapshot_ok=snapshot_ok,
        rag_index_ok=rag_index_ok,
        rag_fresh=rag_fresh,
        rag_stale_reason=rag_reason if not rag_fresh else "",
        messages=tuple(messages),
    )
