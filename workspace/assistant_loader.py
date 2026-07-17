"""
Assistenten-Module bei jedem Streamlit-Rerun neu laden.

Streamlit cached sys.modules — ohne Reload bleibt alte chat.system_message aktiv.
Fehlgeschlagene Imports können ein partielles core.evidence_orchestrator in
sys.modules hinterlassen (ohne assemble_assistant_context) — das muss verworfen werden.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType

ASSISTANT_ENGINE_REV = "2026-07-17-v8"

_RELOAD_ORDER = (
    "core.evidence_orchestrator",
    "workspace.chat",
    "workspace.assistant_ui",
)

_ORCHESTRATOR_REQUIRED = (
    "assemble_assistant_context",
    "build_snapshot_system_context",
)


def _drop_incomplete_module(name: str, required: tuple[str, ...]) -> None:
    """Entfernt Module, die nach fehlgeschlagenem Import unvollständig in sys.modules liegen."""
    mod = sys.modules.get(name)
    if mod is None:
        return
    if all(hasattr(mod, attr) for attr in required):
        return
    del sys.modules[name]


def _ensure_orchestrator_complete() -> None:
    """Verwirft kaputte Orchestrator-Reste (z. B. nach fehlgeschlagenem importlib.reload)."""
    _drop_incomplete_module("core.evidence_orchestrator", _ORCHESTRATOR_REQUIRED)


def _reload_module(name: str) -> ModuleType:
    if name == "core.evidence_orchestrator":
        _ensure_orchestrator_complete()
    try:
        if name in sys.modules:
            mod = importlib.reload(sys.modules[name])
        else:
            mod = importlib.import_module(name)
    except Exception:
        sys.modules.pop(name, None)
        if name != "core.evidence_orchestrator":
            raise
        mod = importlib.import_module(name)
    if name == "core.evidence_orchestrator":
        missing = [a for a in _ORCHESTRATOR_REQUIRED if not hasattr(mod, a)]
        if missing:
            sys.modules.pop(name, None)
            raise ImportError(
                f"core.evidence_orchestrator unvollständig nach Reload "
                f"(fehlt: {', '.join(missing)}) — Streamlit-Prozess neu starten."
            )
    return mod


def chat_system_message_supports_stale_kwargs() -> bool:
    """Prüft, ob die geladene chat.system_message snapshot_stale akzeptiert."""
    import inspect

    try:
        chat_mod = sys.modules.get("workspace.chat") or importlib.import_module("workspace.chat")
        sig = inspect.signature(chat_mod.system_message)
    except (TypeError, ValueError, ImportError, AttributeError):
        return False

    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return True
    return "snapshot_stale" in sig.parameters


def load_assistant_ui() -> ModuleType:
    """Frische assistant_ui-Referenz (inkl. chat + orchestrator)."""
    # Eigenes Modul zuerst — damit ASSISTANT_ENGINE_REV-Änderungen sofort greifen.
    _reload_module(__name__)
    _ensure_orchestrator_complete()
    for name in _RELOAD_ORDER:
        if name != "core.evidence_orchestrator":
            _ensure_orchestrator_complete()
        _reload_module(name)
    mod = sys.modules["workspace.assistant_ui"]
    if not hasattr(mod, "_make_session_system_message"):
        raise RuntimeError(
            "workspace.assistant_ui fehlt _make_session_system_message — "
            "bitte Streamlit-Prozess vollständig neu starten."
        )
    return mod
