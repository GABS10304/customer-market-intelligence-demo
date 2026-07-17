# Customer & Market Intelligence Workspace

Portfolio-Projekt: internes **Product Intelligence**-Tool für RIWA — eine UI, BigQuery als Evidenz, source-aware Ingestion.

## Problem & Lösung

Product Teams haben Feedback aus Hotline, Umfragen und Feldbesuchen — fragmentiert, unterschiedliche Schemas, schwer vergleichbar.

**Dieses Workspace** vereint Quellen in BigQuery, erkennt CSV-Schemas automatisch, validiert vor Verarbeitung und liefert Chat, Vergleich und Kacheln auf derselben Evidenzbasis.

## Features (V2)

| Feature | Beschreibung |
|---------|--------------|
| **Ein UI** | Assistent + Catalog + Chat + Kacheln |
| **3 Quellen** | Tickets, Umfragen, Weihnachtsbesuche/Feldfeedback |
| **Backend-Ingest** | Dateien in `data/inbox/` ablegen — kein Fake-Upload |
| **Theme-Compare** | Export · Login · Import · Verbindung · Installation |
| **Snapshot-Cache** | `data/workspace_snapshot.json` — kein BQ-Reload pro Rerun |
| **Chonkie RAG V2** | Semantic Chunker + Overlap → Chroma (Ollama Embeddings) |
| **Hybrid-Chat** | BigQuery-Aggregate + semantische Textstellen pro Frage |
| **5 Kacheln** | Top Needs, Hotline, Compare, Strategy, Coverage |
| **Deterministische Strategie** | Regelbasiert, kein LLM für Kernlogik |
| **Chat-Synthese** | Optional über `.env`-Token (EU-API) |

### V2 vs. V1

| | V1 | V2 |
|---|----|----|
| Chunking | RecursiveChunker | SemanticChunker + OverlapRefinery (Fallback Recursive) |
| Quellen RAG | 2 (Tickets + Umfragen) | 3 (+ Weihnachtsbesuche) |
| Chat | BQ-Kontext only → hybrid | BQ + Chroma mit Treffer-Anzeige |
| Pipeline-Log | versteckt | Expander in Sidebar |

## Quick Start

**Öffentliche Demo (ohne Secrets):** siehe **[`DEMO.md`](DEMO.md)** — `DEMO_MODE=true` + `Start_Demo_Portal.bat`

```bash
Start_Portal.bat
# oder
streamlit run "PM Evidence AI Portal\Home.py"
```

### Daten ablegen (Backend)

| Quelle | Ordner |
|--------|--------|
| Hotline Tickets (HTML) | `data/html/` |
| Kundenumfragen (CSV `;`) | `data/inbox/umfragen/` |
| Weihnachtsbesuche (CSV `;`) | `data/inbox/weihnachtsbesuche/` |

Danach **Pipeline starten** in der Sidebar.

### Secrets (Projekt-Root, nicht committen)

| Datei | Zweck |
|-------|--------|
| `.env` | `IONOS_TOKEN=...` für Chat-Synthese |
| `gcp-key.json` | BigQuery Service Account |

Kopiere `.env.example` → `.env` und trage Werte ein. Details: **`DEPLOY.md`**.

`.env` Beispiel:

```env
IONOS_TOKEN=dein_token_hier
# Cloud-Synthese nur mit expliziter Freigabe:
CLOUD_SYNTHESIS_APPROVED=true
# BigQuery Staging (Standard: an):
BQ_USE_STAGING=true
BQ_MAX_ROW_DROP_PCT=0.5
# optional RAG/Chunking:
RAG_CHUNKER=semantic
RAG_CHUNK_SIZE=512
RAG_SEMANTIC_THRESHOLD=0.72
RAG_OVERLAP_CONTEXT=0.2
# optional BQ (Platzhalter — echtes Projekt in .env setzen):
BIGQUERY_TABLE=your-gcp-project.pm_daten.anonymes_pm_backlog
BIGQUERY_HTML_TABLE=your-gcp-project.pm_daten.html_tickets_rohdaten
BIGQUERY_FIELD_VISITS_TABLE=your-gcp-project.pm_daten.field_visits_feedback
BIGQUERY_SALES_TABLE=your-gcp-project.pm_daten.sales_product_penetration
```

Ohne Synthese-Token: Pipeline, Kacheln und Vergleich funktionieren — Chat-Synthese ist deaktiviert mit klarem Hinweis.

## GitHub / Deployment

Siehe **`DEPLOY.md`** — sicher pushen ohne CSV, Excel, Tokens oder `gcp-key.json`.

## Betriebsmodi (Degraded Mode)

| Modus | Verfügbar | Eingeschränkt |
|-------|-----------|---------------|
| **Vollbetrieb** | Evidenz, Compare, Kacheln, RAG, Chat | — |
| **Evidenz-Modus** | BQ/Snapshot, Compare, Kacheln | Ollama-Schritte, RAG, ggf. Chat |
| **Snapshot-Modus** | Letzter Snapshot von Disk | Live-BQ, Pipeline |

Start-Checks in `core/runtime.py`. Ollama fehlt → App startet trotzdem; Pipeline überspringt LLM-Schritte transparent.

## BigQuery-Upload (sicher)

Standard: **Staging → Validierung → Swap** (`core/bq_load.py`):

1. Load nach `{table}_staging`
2. Row-Count + Pflichtspalten prüfen
3. Max. Row-Drop vs. Prod (Default 50 %) — sonst **Prod unverändert**
4. `CREATE OR REPLACE` Swap nur nach OK

## Datenschutz / Cloud-Synthese

Chat-Synthese erfordert **beides**: `IONOS_TOKEN` **und** `CLOUD_SYNTHESIS_APPROVED=true`.  
Ohne Freigabe: Evidenz-UI bleibt, Chat blockiert mit klarem Hinweis.

## Installation (Windows)

```bash
Start_Portal.bat
```

Voraussetzungen (explizit):

| Komponente | Pflicht für | Installation |
|------------|-------------|--------------|
| Python 3.11+ | Alles | via venv in Bat |
| `gcp-key.json` | BQ-Evidenz live | PM / GCP-Admin |
| Ollama | CSV/HTML/RAG-Pipeline | https://ollama.com |
| Modelle `llama3.2`, `nomic-embed-text` | Pipeline + RAG | `ollama pull …` |
| IONOS Token + Freigabe | Chat-Synthese | `.env` |
| HF-Modell (Semantic Chunker) | RAG V2 Chunking | auto beim ersten RAG-Lauf |

## Architektur

```
┌─────────────────────────────────────────────────────────┐
│  Home.py (Interaction Layer)                            │
│  Catalog · Chat · Kacheln · Compare                     │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│  workspace/                                             │
│  snapshot · ingest · catalog · sources                  │
│  tiles · compare · strategy · chat                      │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│  pipeline/runner.py → BigQuery → Chonkie V2 → Chroma    │
└─────────────────────────────────────────────────────────┘
```

### Ebenen

1. **Ingestion** — Backend-Drop, Detection, Verify (`workspace/ingest.py`)
2. **Source Adapter** — Spalten-Mapping pro Quelle (`workspace/sources/adapters.py`)
3. **Normalization** — Pipeline → kanonische BQ-Tabellen
4. **Evidence** — `core/bq_evidence.py` + `workspace/snapshot.py` (Single Source of Truth)
5. **RAG** — `core/chunking.py` + `pipeline/rag_index.py` (Chonkie → Chroma)
6. **Interaction** — Hybrid-Chat, Charts, Strategy (deterministisch + optionale Synthese)

## Built-in Quellen

| Technisch | Anzeige | BQ-Tabelle |
|-----------|---------|------------|
| `support_tickets_html` | Hotline Tickets RIWA | `html_tickets_rohdaten` |
| `survey_freetext_250` | Kundenumfragen Freitext | `anonymes_pm_backlog` |
| `field_visits_weihnachtsbesuche` | Weihnachtsbesuche / Feldfeedback | `field_visits_feedback` |

Neue Quelle hinzufügen: Profile in `workspace/sources/profiles.py` ergänzen — kein UI-Rewrite nötig.

## Tests

```bash
venv\Scripts\python.exe test_credentials.py
```

## Legacy

Frühere Multipage-Seiten: `PM Evidence AI Portal/archive/`
