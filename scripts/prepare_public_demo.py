#!/usr/bin/env python3
"""
Erstellt eine bereinigte Demo-Kopie des Repos (ohne Secrets und Rohdaten).

Nur Code + data/demo/ — für manuellen Upload oder separates Public-Repo.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_NAMES = {
    ".git",
    "venv",
    "ragenv",
    "__pycache__",
    ".cursor",
    "vectordb",
    "pm_brain",
    ".coverage",
    "data/inbox",
    "data/Tickets_neu",
    "data/rag_index",
    "data/uploads",
    "data/processed",
    "data/html",
}

SKIP_FILES = {
    ".env",
    "gcp-key.json",
    "Analyse Top 3 User Pain Points (RIW.txt",
}

SKIP_SUFFIXES = {".xlsx", ".xls", ".pem", ".key"}


def _should_skip(rel: Path) -> bool:
    parts = set(rel.parts)
    if parts & SKIP_NAMES:
        return True
    if rel.name in SKIP_FILES:
        return True
    if rel.suffix.lower() in SKIP_SUFFIXES:
        return True
    if rel.name.endswith(".csv") and not rel.as_posix().startswith("data/demo/"):
        return True
    if rel.name == "workspace_snapshot.json" and "demo" not in rel.parts:
        return True
    if rel.name == "graylog_top_functions_cache.json" and "demo" not in rel.parts:
        return True
    return False


def export_demo(output: Path) -> None:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    env_demo = ROOT / ".env.example"
    if env_demo.exists():
        dest_env = output / ".env.example"
        shutil.copy2(env_demo, dest_env)
        text = dest_env.read_text(encoding="utf-8")
        if "DEMO_MODE=" not in text:
            dest_env.write_text(text + "\nDEMO_MODE=true\n", encoding="utf-8")

    for src in ROOT.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(ROOT)
        if _should_skip(rel):
            continue
        dest = output / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    readme = output / "README_PUBLIC.md"
    readme.write_text(
        "# Public Demo Export\n\n"
        "Generiert von `scripts/prepare_public_demo.py`.\n\n"
        "1. `copy .env.example .env` (DEMO_MODE=true ist gesetzt)\n"
        "2. `pip install -r requirements.txt`\n"
        "3. `streamlit run \"PM Evidence AI Portal\\Home.py\"`\n\n"
        "Siehe `DEMO.md`.\n",
        encoding="utf-8",
    )
    print(f"Demo-Export erstellt: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bereinigte Demo-Kopie exportieren")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT.parent / "rag_project_public_demo",
        help="Zielverzeichnis",
    )
    args = parser.parse_args()
    export_demo(args.output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
