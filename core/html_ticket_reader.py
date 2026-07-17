"""
Rohe Hotline-HTML-Tickets lesen — ohne LLM, nur Textextraktion.

Ordnerstruktur unter data/Tickets_neu/html spiegelt Ordner___Modul in BigQuery:
  riwaGisData/Modul - Friedhof (fh)/4041234.html  ->  riwaGisData\\Modul - Friedhof (fh)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from bs4 import BeautifulSoup

from config import TICKETS_HTML_DIR
from core.governance import scrub_pii

MIN_TEXT_LEN = 15

# Ordner mit «Allgemein» / «Allg» — «genereller Bereich» in der Hotline-Struktur
_ALLGEMEIN_HINTS = ("allgemein", "allg")


def module_label(html_root: Path, filepath: Path) -> str:
    rel = filepath.relative_to(html_root)
    parts = rel.parts[:-1]
    if not parts:
        return "Hauptordner"
    if len(parts) >= 2:
        return f"{parts[0]}\\{parts[1]}"
    return parts[0]


def bereich_label(html_root: Path, filepath: Path) -> str:
    rel = filepath.relative_to(html_root)
    return rel.parts[0] if len(rel.parts) > 1 else "Hauptordner"


def is_genereller_bereich_cluster(cluster: str) -> bool:
    lower = cluster.lower()
    return any(h in lower for h in _ALLGEMEIN_HINTS)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def extract_ticket_text(raw_html: str) -> str:
    """
    Extrahiert Freitext aus HTML — bevorzugt Kunden-Mail, sonst Froala-Block, sonst gesamt.
    """
    soup = BeautifulSoup(raw_html, "lxml")
    candidates: list[str] = []

    for node in soup.select(".mail_body"):
        t = _normalize_text(node.get_text(separator=" ", strip=True))
        if len(t) >= MIN_TEXT_LEN:
            candidates.append(t)

    for node in soup.select(".richContent_froala"):
        t = _normalize_text(node.get_text(separator=" ", strip=True))
        if len(t) >= MIN_TEXT_LEN:
            candidates.append(t)

    if not candidates:
        t = _normalize_text(soup.get_text(separator=" ", strip=True))
        if t:
            candidates.append(t)

    if not candidates:
        return ""

    # Längster Block = meist Kundenanfrage (Signaturen oft kürzer als Mail-Body)
    text = max(candidates, key=len)
    if len(text) > 8000:
        text = text[:8000]
    return scrub_pii(text)


def read_html_ticket(html_root: Path, filepath: Path) -> dict[str, str] | None:
    try:
        raw = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    text = extract_ticket_text(raw)
    if len(text) < MIN_TEXT_LEN:
        return None

    cluster = module_label(html_root, filepath)
    return {
        "ticket_id": filepath.stem,
        "ticket_datei": filepath.name,
        "html_pfad": str(filepath.resolve()),
        "bereich": bereich_label(html_root, filepath),
        "cluster": cluster,
        "freitext": text,
    }


def iter_html_tickets(
    html_root: Path | None = None,
    *,
    only_genereller_bereich: bool = False,
) -> Iterator[dict[str, str]]:
    root = html_root or TICKETS_HTML_DIR
    if not root.exists():
        return

    for path in sorted(root.rglob("*.html")):
        row = read_html_ticket(root, path)
        if not row:
            continue
        if only_genereller_bereich and not is_genereller_bereich_cluster(row["cluster"]):
            continue
        yield row
