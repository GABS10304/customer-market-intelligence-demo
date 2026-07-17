"""Ollama-Laufzeit — prüfen und bei Bedarf automatisch starten (Windows/lokal)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Callable

from config import OLLAMA_URL

LogFn = Callable[[str], None]

_POLL_INTERVAL_S = 1.0
_DEFAULT_TIMEOUT_S = 90


def _base_url() -> str:
    return (OLLAMA_URL or "http://localhost:11434").rstrip("/")


def is_ollama_running(timeout: float = 2.0) -> bool:
    try:
        urllib.request.urlopen(f"{_base_url()}/", timeout=timeout)
        return True
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def _find_ollama_exe() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found

    local_app = os.environ.get("LOCALAPPDATA", "")
    if local_app:
        for name in ("ollama.exe", "Ollama.exe"):
            candidate = os.path.join(local_app, "Programs", "Ollama", name)
            if os.path.isfile(candidate):
                return candidate
    return None


def _start_ollama_process(log: LogFn | None = None) -> bool:
    exe = _find_ollama_exe()
    if not exe:
        if log:
            log("🛑 Ollama nicht gefunden — bitte von https://ollama.com installieren.")
        return False

    if log:
        log(f"🦙 Starte Ollama ({exe})…")

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

    try:
        name = os.path.basename(exe).lower()
        if name == "ollama.exe":
            subprocess.Popen(
                [exe, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        else:
            # Ollama Desktop — startet den Server im Hintergrund mit
            subprocess.Popen(
                [exe],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        return True
    except OSError as exc:
        if log:
            log(f"🛑 Ollama-Start fehlgeschlagen: {exc}")
        return False


def ensure_ollama_running(
    *,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
    log: LogFn | None = None,
) -> bool:
    """Ollama erreichbar machen — startet lokalen Dienst falls nötig."""
    if is_ollama_running():
        return True

    if not _start_ollama_process(log):
        return False

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if is_ollama_running(timeout=2.0):
            if log:
                log("✅ Ollama online.")
            return True
        time.sleep(_POLL_INTERVAL_S)

    if log:
        log(f"🛑 Ollama nach {timeout_s}s nicht erreichbar unter {_base_url()}")
    return False
