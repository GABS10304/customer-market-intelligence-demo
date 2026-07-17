#!/usr/bin/env python3
"""
Prüft das Repo auf typische Sensitive-Data-Leaks vor einem öffentlichen Push.

Exit 0 = OK, Exit 1 = Funde (Review nötig).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_TRACKED_GLOBS = (
    "*.xlsx",
    "*.xls",
    ".env",
    "gcp-key.json",
    "*.pem",
    "*.key",
)

CONTENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("GCP-Projekt-ID (pm-analytics)", re.compile(r"pm-analytics-\d+")),
    ("Windows-User-Pfad GABS", re.compile(r"C:\\Users\\GABS", re.IGNORECASE)),
    ("E-Mail-Adresse", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    ("Echter Graylog-Host", re.compile(r"dockrzm\.in\.riwa-gis\.de")),
]

SKIP_DIRS = {".git", "venv", "ragenv", "__pycache__", ".cursor", "vectordb", "data/demo"}

REAL_MUNICIPALITY_HINTS = re.compile(
    r"\b(Irschenberg|Bad Staffelstein|Wildflecken|Miltenberg|Schweinfurt|Würzburg)\b",
    re.IGNORECASE,
)

DEMO_FORBIDDEN = re.compile(
    r"\b(riwagisdata|terawindata|riwa[\s-]?gis|\brgz\b|kartenapp)\b",
    re.IGNORECASE,
)


def _tracked_files() -> list[Path]:
    import subprocess

    out = subprocess.check_output(
        ["git", "ls-files"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return [ROOT / line.strip() for line in out.splitlines() if line.strip()]


def _scan_content(path: Path) -> list[str]:
    findings: list[str] = []
    if path.suffix.lower() in {".bin", ".pickle", ".sqlite3", ".pyc"}:
        return findings
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    rel = path.relative_to(ROOT).as_posix()
    for label, pattern in CONTENT_PATTERNS:
        if pattern.search(text):
            findings.append(f"{rel}: {label}")
    if REAL_MUNICIPALITY_HINTS.search(text) and not rel.startswith("data/demo/"):
        findings.append(f"{rel}: möglicher echter Gemeindename")
    if rel.startswith("data/demo/") and DEMO_FORBIDDEN.search(text):
        findings.append(f"{rel}: RIWA/RGZ/TERA-Leak in Demo-Fixture")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanitize-Check vor öffentlichem Push")
    parser.add_argument("--strict", action="store_true", help="Warnungen als Fehler werten")
    args = parser.parse_args()

    issues: list[str] = []

    for path in _tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        for glob in FORBIDDEN_TRACKED_GLOBS:
            if path.match(glob):
                issues.append(f"Getrackt (sollte gitignored sein): {rel}")
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        issues.extend(_scan_content(path))

    demo_snapshot = ROOT / "data" / "demo" / "workspace_snapshot.json"
    if not demo_snapshot.exists():
        issues.append("Fehlt: data/demo/workspace_snapshot.json")

    if issues:
        print("SANITIZE CHECK — Funde:\n")
        for item in issues:
            print(f"  - {item}")
        return 1 if args.strict or any("Getrackt" in i for i in issues) else 0

    print("SANITIZE CHECK — OK (keine kritischen Funde)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
