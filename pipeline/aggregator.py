"""
Map-Reduce Aggregator — pro Datenquelle eine aggregierte Top-5 Strategie-Analyse.

Map (lokal/Ollama): Roh-Feedbacks → Batch-Stichpunkte
Reduce (IONOS):     Batch-Notizen → finale Top 5 Epics
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Literal

import pandas as pd
from langchain_core.prompts import ChatPromptTemplate

from config import BACKLOG_CSV, HTML_OUTPUT_CSV, ROOT_DIR
from core.llm import get_ionos_llm, get_local_llm, llm_text

REPORT_SUPPORT_MD = ROOT_DIR / "Finaler_PM_Report_Support.md"
REPORT_SURVEYS_MD = ROOT_DIR / "Finaler_PM_Report_Umfragen.md"

LogFn = Callable[[str], None]
SourceKey = Literal["support", "surveys"]
BATCH_SIZE = 50

SOURCE_CONFIG: dict[SourceKey, dict[str, Any]] = {
    "support": {
        "label": "Support-Tickets",
        "input_csv": HTML_OUTPUT_CSV,
        "report_path": REPORT_SUPPORT_MD,
        "map_prompt": """
Analysiere die folgenden Support-Ticket-Zusammenfassungen.
Finde die 3 bis 5 am häufigsten genannten Software-Probleme (keine Einzelfälle).
Antworte STRIKT in diesem Format pro Problem:
- [Stichwort/Thema] - Kurzer Grund.

TICKETS:
{chunk_text}
""",
    },
    "surveys": {
        "label": "Kundenumfragen",
        "input_csv": BACKLOG_CSV,
        "report_path": REPORT_SURVEYS_MD,
        "map_prompt": """
Analysiere die folgenden Kundenumfrage-Feedbacks (NPS / CSV).
Finde die 3 bis 5 am häufigsten genannten Produkt-Probleme oder Feature-Wünsche.
Antworte STRIKT in diesem Format pro Problem:
- [Stichwort/Thema] - Kurzer Grund.

FEEDBACKS:
{chunk_text}
""",
    },
}

REDUCE_PROMPT = """
Du bist Senior Product Manager. Hier sind Zwischenergebnisse aus der Analyse von exakt {total_items} {source_label}.
Deine Aufgabe:
Fasse diese Zwischenergebnisse zu einer finalen **TOP 5 EPICS** Liste zusammen. Fasse inhaltlich gleiche Themen zusammen.
Priorisiere nach Relevanz für Endanwender (Häufigkeit und Impact).

Beginne deinen Report ZWINGEND mit genau diesem Satz:
"Basierend auf der Analyse von {total_items} {source_label}, sind hier die priorisierten Top 5 Problemfelder:"

Formatiere jedes Epic so:
🚨 **Epic N: [Titel]**
- **Kernproblem:** ...
- **Häufigkeit im Kontext:** ... (schätze aus den Daten)
- **PM-Empfehlung:** ...

ZWISCHENERGEBNISSE:
{alle_zusammenfassungen}
"""


def _default_log(message: str) -> None:
    print(message)


def _load_feedbacks(csv_path: Path) -> list[str]:
    df = pd.read_csv(csv_path, sep=";", encoding="utf-8-sig", on_bad_lines="skip")
    if "Original-Wortlaut (Freitext)" not in df.columns:
        raise ValueError(f"Spalte 'Original-Wortlaut (Freitext)' fehlt in {csv_path.name}")
    return df["Original-Wortlaut (Freitext)"].dropna().astype(str).tolist()


def aggregate_source(source: SourceKey, log: LogFn = _default_log) -> dict[str, Any]:
    cfg = SOURCE_CONFIG[source]
    input_csv: Path = cfg["input_csv"]
    report_path: Path = cfg["report_path"]
    source_label: str = cfg["label"]

    log(f"\n📊 Aggregator: {source_label}")

    if not input_csv.exists():
        log(f"⚠️ {input_csv.name} nicht gefunden — Schritt übersprungen.")
        return {"source": source, "rows": 0, "blocks": 0, "skipped": True}

    feedbacks = _load_feedbacks(input_csv)
    if not feedbacks:
        log(f"🛑 Keine Freitexte in {input_csv.name}.")
        return {"source": source, "rows": 0, "blocks": 0, "skipped": True}

    map_llm = get_local_llm()
    map_chain = ChatPromptTemplate.from_template(cfg["map_prompt"]) | map_llm
    zwischen_ergebnisse = ""

    log(f"   Map (lokal): {len(feedbacks)} Einträge in {BATCH_SIZE}er-Blöcken...")

    blocks = 0
    for index in range(0, len(feedbacks), BATCH_SIZE):
        chunk = feedbacks[index : index + BATCH_SIZE]
        chunk_text = "\n".join(f"- {text}" for text in chunk)
        block_num = index // BATCH_SIZE + 1
        log(f"   Block {block_num}...")

        try:
            result_text = llm_text(map_chain.invoke({"chunk_text": chunk_text}))
            zwischen_ergebnisse += f"\n--- Batch {block_num} ---\n{result_text}\n"
            blocks += 1
        except Exception as exc:
            log(f"      ⚠️ Fehler Block {block_num}: {exc}")

    if not zwischen_ergebnisse.strip():
        log("🛑 Keine Zwischenergebnisse — Reduce abgebrochen.")
        return {"source": source, "rows": len(feedbacks), "blocks": blocks, "error": "no_map_results"}

    log(f"   Reduce (IONOS): Top 5 aus {len(feedbacks)} {source_label}...")
    reduce_llm = get_ionos_llm()
    reduce_chain = ChatPromptTemplate.from_template(REDUCE_PROMPT) | reduce_llm

    try:
        final_report = llm_text(
            reduce_chain.invoke(
                {
                    "alle_zusammenfassungen": zwischen_ergebnisse,
                    "total_items": len(feedbacks),
                    "source_label": source_label,
                }
            )
        )
    except Exception as exc:
        log(f"❌ IONOS Reduce fehlgeschlagen: {exc}")
        return {"source": source, "rows": len(feedbacks), "blocks": blocks, "error": str(exc)}

    with open(report_path, "w", encoding="utf-8-sig") as handle:
        handle.write(final_report)

    log(f"✅ Report: {report_path.name}")
    return {"source": source, "rows": len(feedbacks), "blocks": blocks, "report": str(report_path)}


def run_aggregator(
    sources: tuple[SourceKey, ...] | None = None,
    log: LogFn = _default_log,
) -> dict[str, Any]:
    selected = sources or ("support", "surveys")
    log("🚀 Starte Map-Reduce Aggregator (Map=lokal, Reduce=IONOS)...")
    results = {}
    for source in selected:
        results[source] = aggregate_source(source, log=log)
    return results


def report_path_for_source(source: SourceKey) -> Path:
    return SOURCE_CONFIG[source]["report_path"]
