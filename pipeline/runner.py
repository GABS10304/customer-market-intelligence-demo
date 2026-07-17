"""
Zentrale Pipeline — ein Entry Point für alle Verarbeitungsschritte.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from typing import Any, Callable

from config import INBOX_DIR, ensure_data_dirs
from core.data_cleanup import run_data_cleanup
from core.ollama_runtime import ensure_ollama_running, is_ollama_running
from core.runtime import get_runtime_status
from pipeline.aggregator import run_aggregator
from pipeline.bq_uploader import upload_to_bigquery
from pipeline.csv_processor import migrate_root_csvs_to_inbox, process_inbox_csvs
from pipeline.html_ticket_scraper import run_html_shredder
from pipeline.inbox import list_inbox_csvs, pending_inbox_files
from pipeline.rag_index import build_rag_index_from_bq
from pipeline.sales_processor import sync_sales_product_data

LogFn = Callable[[str], None]

ALL_STEPS = ("cleanup", "csv", "html", "aggregate", "sales", "bq", "rag")


def _default_log(message: str) -> None:
    print(message)


def inbox_status() -> dict[str, Any]:
    ensure_data_dirs()
    migrate_root_csvs_to_inbox()
    all_files = [path.name for path in list_inbox_csvs(INBOX_DIR)]
    pending = [path.name for path in pending_inbox_files(INBOX_DIR)]
    return {
        "inbox_dir": str(INBOX_DIR),
        "total": len(all_files),
        "pending": pending,
        "pending_count": len(pending),
    }


def run_pipeline(
    steps: tuple[str, ...] | None = None,
    log: LogFn | None = None,
) -> dict[str, Any]:
    logger = log or _default_log
    selected = steps or ALL_STEPS
    results: dict[str, Any] = {"steps": {}}

    ensure_data_dirs()
    logger("=" * 60)
    logger("RIWA PM Intelligence — Pipeline V2")
    logger("=" * 60)

    runtime = get_runtime_status()
    logger(f"Betriebsmodus: {runtime.mode_label} ({runtime.mode})")
    for msg in runtime.messages:
        logger(f"  · {msg}")

    ollama_ok = is_ollama_running()
    needs_ollama = any(step in selected for step in ("csv", "aggregate", "rag"))
    if needs_ollama and not ollama_ok:
        logger("\n--- Ollama (lokal) ---")
        ensure_ollama_running(log=logger)
        ollama_ok = is_ollama_running()
        if not ollama_ok:
            logger("⚠️ Degraded Mode: Ollama-Schritte werden übersprungen (Feldbesuche + BQ weiter möglich).")

    if "cleanup" in selected:
        logger("\n--- Schritt 0: Datenbereinigung ---")
        results["steps"]["cleanup"] = run_data_cleanup(log=logger)

    if "csv" in selected:
        logger("\n--- Schritt 1: CSV Inbox ---")
        results["steps"]["csv"] = process_inbox_csvs(log=logger, ollama_ok=ollama_ok)

    if "html" in selected:
        logger("\n--- Schritt 2: HTML-Scraper V1 (Original-Freitext) ---")
        results["steps"]["html"] = run_html_shredder(log=logger)

    if "aggregate" in selected:
        if ollama_ok:
            logger("\n--- Schritt 3: Aggregator (Top 5 Support + Umfragen) ---")
            results["steps"]["aggregate"] = run_aggregator(log=logger)
        else:
            logger("\n--- Schritt 3: Aggregator — übersprungen (Ollama offline) ---")
            results["steps"]["aggregate"] = {"skipped": True, "reason": "ollama_offline"}

    if "sales" in selected:
        logger("\n--- Schritt 3b: Sales Penetration (Verträge) ---")
        results["steps"]["sales"] = sync_sales_product_data(log=logger)

    if "bq" in selected:
        logger("\n--- Schritt 4: BigQuery Upload (Staging → Swap) ---")
        results["steps"]["bq"] = upload_to_bigquery(log=logger)

    if "rag" in selected:
        if ollama_ok:
            logger("\n--- Schritt 5: RAG-Index aus BigQuery ---")
            results["steps"]["rag"] = build_rag_index_from_bq(log=logger)
        else:
            logger("\n--- Schritt 5: RAG — übersprungen (Ollama offline) ---")
            results["steps"]["rag"] = {"skipped": True, "reason": "ollama_offline"}

    logger("\n" + "=" * 60)
    logger("Pipeline abgeschlossen.")
    logger("=" * 60)

    from workspace.catalog import mark_evidence_refreshed

    mark_evidence_refreshed()

    return results


def run_pipeline_capture(steps: tuple[str, ...] | None = None) -> tuple[dict[str, Any], str]:
    buffer = io.StringIO()

    def capture(message: str) -> None:
        buffer.write(message + "\n")

    with redirect_stdout(buffer):
        results = run_pipeline(steps=steps, log=capture)

    return results, buffer.getvalue()


if __name__ == "__main__":
    run_pipeline()
