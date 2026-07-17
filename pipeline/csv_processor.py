"""
CSV-Verarbeitung aus data/inbox — Spalten-Erkennung, PII-Filter, lokales Llama.
"""

from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import OllamaLLM

from config import (
    BACKLOG_CSV,
    DELIMITER,
    INBOX_DIR,
    INBOX_FIELD_VISITS_DIR,
    INBOX_SURVEYS_DIR,
    OLLAMA_MODEL,
    OUTPUT_FIELDNAMES,
    PROCESSED_DIR,
    ROOT_DIR,
    ensure_data_dirs,
)
from core.governance import scrub_pii
from core.source_dedup import is_field_visits_csv, purge_survey_field_visit_duplicates
from core.ollama_runtime import is_ollama_running
from pipeline.field_visits_processor import process_field_visits_inbox
from pipeline.inbox import (
    is_unchanged,
    list_inbox_csvs,
    mark_processed,
    pending_inbox_files,
)

LogFn = Callable[[str], None]

LEGACY_PRESETS: dict[str, dict[str, Any]] = {
    # tickets_a.csv = historisch Weihnachtsbesuche — nicht mehr als Umfrage (siehe source_dedup)
    "tickets_b.csv": {
        "customer_col": 1,
        "freitext_col": 16,
        "delimiter": ";",
        "source_label": "NPS Umfrage (B)",
    },
}

FREITEXT_HINTS = (
    "freitext",
    "feedback",
    "kommentar",
    "comment",
    "text",
    "beschreibung",
    "antwort",
    "original",
    "problem",
    "anmerkung",
    "meinung",
)
CUSTOMER_HINTS = (
    "kunde",
    "customer",
    "firma",
    "account",
    "unternehmen",
    "name",
    "mandant",
    "organisation",
)

CATEGORIZE_PROMPT = """Du bist Product Manager für eine Software. Analysiere dieses Feedback.

Regel 1: Wenn es nur "Alles gut", "Keine", "passt" ist, antworte EXAKT mit dem Wort: IRRELEVANT
Regel 2: Wenn es Relevanz hat, ordne es ZWINGEND in eine dieser 4 Kategorien ein: [Bug/Performance, Usability, Feature-Wunsch, Service/Schulung].

Antworte EXAKT in diesem Format (mit dem Symbol | dazwischen):
KATEGORIE: [Deine Kategorie] | TEXT: [Fasse das Problem in 1 Satz zusammen]

FEEDBACK:
{freitext}
"""


def _default_log(message: str) -> None:
    print(message)


def _load_meta(path: Path) -> dict[str, Any]:
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if not meta_path.exists():
        meta_path = path.with_name(path.stem + ".meta.json")
    if not meta_path.exists():
        return {}
    try:
        with open(meta_path, encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}


def _resolve_col(spec: Any, headers: list[str]) -> int | None:
    if spec is None:
        return None
    if isinstance(spec, int):
        return spec
    spec_str = str(spec).strip().lower()
    for index, header in enumerate(headers):
        if header.strip().lower() == spec_str:
            return index
    return None


def _detect_columns(headers: list[str]) -> tuple[int | None, int | None]:
    customer_col = None
    freitext_col = None
    normalized = [h.strip().lower() for h in headers]

    for index, header in enumerate(normalized):
        if any(hint in header for hint in CUSTOMER_HINTS):
            customer_col = index
        if any(hint in header for hint in FREITEXT_HINTS):
            freitext_col = index

    if freitext_col is None and headers:
        freitext_col = max(range(len(headers)), key=lambda i: len(headers[i]))

    return customer_col, freitext_col


def resolve_csv_layout(path: Path) -> dict[str, Any]:
    preset = LEGACY_PRESETS.get(path.name.lower(), {})
    meta = _load_meta(path)
    merged = {**preset, **meta}

    delimiter = merged.get("delimiter", DELIMITER)
    source_label = merged.get("source_label") or path.stem.replace("_", " ")

    with open(path, encoding="utf-8-sig", errors="replace") as handle:
        sample = handle.read(4096)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        delimiter = merged.get("delimiter", dialect.delimiter)
    except csv.Error:
        pass

    with open(path, encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        headers = next(reader, [])

    customer_col = _resolve_col(merged.get("customer_col"), headers)
    freitext_col = _resolve_col(merged.get("freitext_col"), headers)

    if freitext_col is None:
        detected_customer, detected_freitext = _detect_columns(headers)
        customer_col = customer_col if customer_col is not None else detected_customer
        freitext_col = detected_freitext

    if freitext_col is None:
        raise ValueError(
            f"Keine Freitext-Spalte erkannt in {path.name}. "
            f"Lege {path.stem}.meta.json an (freitext_col)."
        )

    return {
        "delimiter": delimiter,
        "customer_col": customer_col if customer_col is not None else 0,
        "freitext_col": freitext_col,
        "source_label": source_label,
        "has_header": bool(headers),
    }


def migrate_root_csvs_to_inbox(log: LogFn = _default_log) -> int:
    """Kopiert legacy tickets_*.csv aus dem Repo-Root — nur wenn noch nicht verarbeitet."""
    from pipeline.inbox import file_hash, load_registry

    ensure_data_dirs()
    moved = 0
    known_hashes = {
        e.get("hash")
        for e in load_registry().get("files", {}).values()
        if e.get("status") == "done" and e.get("hash")
    }

    for path in ROOT_DIR.glob("tickets_*.csv"):
        if file_hash(path) in known_hashes:
            continue
        if (PROCESSED_DIR / path.name).exists():
            continue
        target = INBOX_DIR / path.name
        if target.exists():
            continue
        shutil.copy2(path, target)
        log(f"📥 Legacy-CSV in Inbox kopiert: {path.name}")
        moved += 1
    return moved


def _invoke_llm(chain, freitext: str) -> str:
    response = chain.invoke({"freitext": freitext})
    if hasattr(response, "content"):
        return str(response.content).strip()
    return str(response).strip()


def process_single_csv(
    path: Path,
    chain,
    *,
    log: LogFn = _default_log,
) -> list[dict[str, str]]:
    layout = resolve_csv_layout(path)
    results: list[dict[str, str]] = []
    processed_at = datetime.now(timezone.utc).isoformat()

    log(f"\n🚀 Verarbeite {path.name} (lokal / {OLLAMA_MODEL})...")

    with open(path, encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.reader(handle, delimiter=layout["delimiter"])
        if layout["has_header"]:
            next(reader, None)

        for row_num, row in enumerate(reader, start=2):
            if len(row) <= layout["freitext_col"]:
                continue

            customer_col = layout["customer_col"]
            kunde = (
                row[customer_col].strip()
                if len(row) > customer_col
                else f"Zeile {row_num}"
            )
            freitext = row[layout["freitext_col"]].strip()

            if not freitext or len(freitext) < 5:
                continue
            if freitext.lower() in {"nein", "keine", "-", "alles gut", "nichts", "passt"}:
                continue

            freitext = scrub_pii(freitext)
            log(f"   🦙 Analysiere: {kunde[:24]}...")

            try:
                answer = _invoke_llm(chain, freitext)
                if answer != "IRRELEVANT" and "|" in answer:
                    parts = answer.split("|", 1)
                    category = parts[0].replace("KATEGORIE:", "").strip()
                    summary = parts[1].replace("TEXT:", "").strip()
                    results.append(
                        {
                            "Kunde": kunde,
                            "Kategorie": category,
                            "Original-Wortlaut (Freitext)": summary,
                            "Quelle": layout["source_label"],
                            "source_file": path.name,
                            "processed_at": processed_at,
                        }
                    )
                    log(f"      ✅ [{category}]")
                else:
                    log("      🚮 Irrelevant.")
            except Exception as exc:
                log(f"      ⚠️ Fehler Zeile {row_num}: {exc}")

    return results


def load_backlog_rows() -> list[dict[str, str]]:
    if not BACKLOG_CSV.exists():
        return []
    with open(BACKLOG_CSV, encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter=DELIMITER)
        return list(reader)


def write_backlog(rows: list[dict[str, str]]) -> None:
    fieldnames = list(OUTPUT_FIELDNAMES)
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with open(BACKLOG_CSV, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)


def remove_rows_for_file(rows: list[dict[str, str]], filename: str) -> list[dict[str, str]]:
    return [row for row in rows if row.get("source_file") != filename]


def move_to_processed(path: Path) -> Path:
    ensure_data_dirs()
    target = PROCESSED_DIR / path.name
    if target.exists():
        target.unlink()
    shutil.move(str(path), str(target))
    return target


def process_inbox_csvs(log: LogFn = _default_log, *, ollama_ok: bool | None = None) -> dict[str, Any]:
    ensure_data_dirs()
    migrate_root_csvs_to_inbox(log=log)

    if ollama_ok is None:
        ollama_ok = is_ollama_running()

    field_result = process_field_visits_inbox(log=log)
    survey_result = _process_survey_inbox(log=log, ollama_ok=ollama_ok)

    dedup = purge_survey_field_visit_duplicates(log=log)

    total_processed = field_result.get("processed", 0) + survey_result.get("processed", 0)
    total_rows = field_result.get("rows_added", 0) + survey_result.get("rows_added", 0)
    all_files = field_result.get("files", []) + survey_result.get("files", [])

    if total_processed == 0:
        log(
            "\n📂 Keine neuen CSVs. Ablege Dateien in:\n"
            f"   · Umfragen: {INBOX_SURVEYS_DIR}\n"
            f"   · Weihnachtsbesuche: {INBOX_FIELD_VISITS_DIR}\n"
            f"   · Hotline-HTML: data/html/"
        )

    return {
        "processed": total_processed,
        "rows_added": total_rows,
        "files": all_files,
        "field_visits": field_result,
        "surveys": survey_result,
        "dedup": dedup,
    }


def _process_survey_inbox(log: LogFn = _default_log, *, ollama_ok: bool = True) -> dict[str, Any]:
    pending = pending_inbox_files(INBOX_SURVEYS_DIR)
    if not pending:
        return {"processed": 0, "rows_added": 0, "files": []}

    if not ollama_ok:
        log("⏭️ Umfragen-CSV übersprungen — Ollama offline (Feldbesuche ohne LLM weiter möglich).")
        return {"processed": 0, "rows_added": 0, "files": [], "skipped": True, "reason": "ollama_offline"}

    llm = OllamaLLM(model=OLLAMA_MODEL, temperature=0.0)
    chain = ChatPromptTemplate.from_template(CATEGORIZE_PROMPT) | llm

    backlog = load_backlog_rows()
    total_rows_added = 0
    processed_files: list[str] = []

    for path in pending:
        try:
            import pandas as pd

            preview = pd.read_csv(path, sep=";", encoding="utf-8-sig", nrows=8, on_bad_lines="skip")
            if is_field_visits_csv(path, preview):
                log(
                    f"⏭️ {path.name} ist Weihnachtsbesuche/Feldfeedback — "
                    f"bitte nach `{INBOX_FIELD_VISITS_DIR}` legen, nicht als Umfrage verarbeiten."
                )
                continue

            rows = process_single_csv(path, chain, log=log)
            backlog = remove_rows_for_file(backlog, path.name)
            backlog.extend(rows)
            total_rows_added += len(rows)
            mark_processed(path, rows=len(rows), status="done")
            move_to_processed(path)
            processed_files.append(path.name)
            log(f"✅ {path.name}: {len(rows)} Zeilen → Umfragen-Backlog")
        except Exception as exc:
            mark_processed(path, rows=0, status="error", error=str(exc))
            log(f"❌ Fehler bei {path.name}: {exc}")

    if processed_files:
        write_backlog(backlog)
        log(f"\n🎉 Umfragen-Backlog: {len(backlog)} Zeilen gesamt (+{total_rows_added} neu).")

    return {
        "processed": len(processed_files),
        "rows_added": total_rows_added,
        "files": processed_files,
    }
