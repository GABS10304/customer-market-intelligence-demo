"""
HTML-Ticket-Schredder — DEPRECATED V0 (Ollama, IRRELEVANT-Filter).

Nutze pipeline/html_ticket_scraper.py (V1) — Original-Freitext, kein LLM.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Callable

from bs4 import BeautifulSoup
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import OllamaLLM

from config import HTML_DIR, HTML_OUTPUT_CSV, OLLAMA_MODEL, ensure_data_dirs
from core.governance import scrub_pii
from core.ollama_runtime import is_ollama_running

LogFn = Callable[[str], None]

TICKET_PROMPT = """Du bist Product Manager für die GIS-Software RIWA.
Lies dieses Support-Ticket, ignoriere Signaturen und E-Mail-Verläufe und finde den Kern des Software-Problems.

Regel 1: Wenn es reiner Support-Alltag (Passwort-Reset, Neustart, Hardware-Defekt, Danke) ist oder das Problem bereits gelöst ist, antworte EXAKT mit dem Wort: IRRELEVANT
Regel 2: Wenn ein echter Bug, ein Workaround, ein fehlendes Feature oder ein Usability-Problem beschrieben wird, antworte in 1-2 Sätzen mit der Kernbeschreibung des Problems.

TICKET-TEXT:
{ticket_text}
"""


def _default_log(message: str) -> None:
    print(message)


def run_html_shredder(log: LogFn = _default_log) -> dict[str, Any]:
    ensure_data_dirs()
    if not is_ollama_running():
        log("⏭️ HTML-Schredder übersprungen — Ollama offline.")
        return {"processed": 0, "skipped": True, "reason": "ollama_offline"}

    log("\n🚜 Starte HTML-Schredder (lokal)...")

    if not HTML_DIR.exists():
        log(f"⚠️ Ordner nicht gefunden: {HTML_DIR}")
        log("Lege HTML-Tickets unter data/html/ ab.")
        return {"rows": 0, "files_scanned": 0}

    if HTML_OUTPUT_CSV.exists():
        try:
            with open(HTML_OUTPUT_CSV, "a", encoding="utf-8-sig"):
                pass
        except PermissionError:
            log(f"🛑 {HTML_OUTPUT_CSV.name} ist in Excel geöffnet — bitte schließen.")
            return {"rows": 0, "files_scanned": 0, "error": "file_locked"}

    llm = OllamaLLM(model=OLLAMA_MODEL, temperature=0.0)
    chain = ChatPromptTemplate.from_template(TICKET_PROMPT) | llm
    results: list[dict[str, str]] = []
    files_scanned = 0

    for root, _, files in os.walk(HTML_DIR):
        for filename in files:
            if not filename.lower().endswith(".html"):
                continue

            filepath = Path(root) / filename
            files_scanned += 1
            module = filepath.parent.relative_to(HTML_DIR)
            module_label = "Hauptordner" if str(module) == "." else str(module)

            try:
                with open(filepath, encoding="utf-8", errors="ignore") as handle:
                    soup = BeautifulSoup(handle, "lxml")
                    text = soup.get_text(separator=" ", strip=True)

                if len(text) < 20:
                    continue

                snippet = scrub_pii(text[:3000])
                log(f"   ⏳ [{module_label}] {filename[:30]}...")

                answer = chain.invoke({"ticket_text": snippet})
                answer_text = answer.strip() if isinstance(answer, str) else str(answer).strip()

                if answer_text == "IRRELEVANT":
                    log("      🚮 Irrelevant.")
                    continue

                log("      ✅ Problem extrahiert.")
                results.append(
                    {
                        "Ordner / Modul": module_label,
                        "Quelle (Dateiname)": filename,
                        "Kategorie": "Ticket-Extrakt",
                        "Original-Wortlaut (Freitext)": answer_text,
                    }
                )
            except Exception as exc:
                log(f"      ⚠️ Fehler bei {filename}: {exc}")

    if results:
        fieldnames = list(results[0].keys())
        with open(HTML_OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(results)
        log(f"\n🎉 {len(results)} Ticket-Insights in {HTML_OUTPUT_CSV.name}")
    else:
        log("\n🤷 Keine relevanten Software-Probleme in HTML gefunden.")

    return {"rows": len(results), "files_scanned": files_scanned}
