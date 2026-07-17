"""
Gemeinsame Hilfsfunktionen für Streamlit Pages.
"""

import os
import sys

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from config import ROOT_DIR, setup_gcp_credentials

__all__ = ["setup_repo_imports", "setup_portal", "setup_gcp_credentials"]


def setup_repo_imports() -> str:
    """Gibt Repo-Root zurück (bereits im Python-Pfad)."""
    return str(ROOT_DIR)


def setup_portal() -> str:
    """Repo-Pfad + GCP-Credentials."""
    setup_gcp_credentials()
    return str(ROOT_DIR)
