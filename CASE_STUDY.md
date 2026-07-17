# Case Study: Customer & Market Intelligence Workspace

**Role:** Product / Technical PM (portfolio project)  
**Context:** B2G SaaS vendor — municipal GIS and related modules  
**Stack:** Python · Streamlit · BigQuery · LangChain · Chroma · Ollama · Chonkie · Plotly  

---

## Executive summary

Product teams at a B2G software company received customer signal from four disconnected channels: support tickets, NPS survey free text, field-visit feedback, and anonymized sales product penetration. Each source used different schemas, lived in different tools, and was difficult to compare.

I designed and built a **Customer & Market Intelligence Workspace**: a single Streamlit application backed by **BigQuery as the evidence layer**, with pipeline-driven ingestion, cross-source theme comparison, insight tiles, and an optional **hybrid RAG chat** (structured aggregates + semantic retrieval). Core metrics and strategy logic stay **deterministic**; LLMs are used only where they add value (ticket summarization, chat synthesis, embeddings).

The system runs in **degraded modes** when Ollama, BigQuery, or cloud synthesis is unavailable — evidence and tiles still work from cache.

---

## The problem

| Pain | Impact |
|------|--------|
| Fragmented feedback | PMs manually stitched support, surveys, and visit notes |
| Inconsistent schemas | Same concept (e.g. “export”) appeared under different column names |
| No shared evidence base | Dashboards, chat, and reports disagreed on numbers |
| Privacy constraints | Freitext could not be sent to cloud APIs without explicit approval |
| Slow UI | Re-querying BigQuery on every Streamlit rerun |

**Goal:** One UI, one evidence layer, source-aware ingestion, and governance by default.

---

## Solution overview

```
┌─────────────────────────────────────────────────────────┐
│  Streamlit UI — Catalog · Chat · Tiles · Theme Compare  │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│  workspace/ — snapshot cache · ingest · source profiles   │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│  pipeline/ — cleanup → CSV/HTML → sales → BQ → RAG    │
└─────────────────────────────────────────────────────────┘
```

### Four evidence sources

| Source | Input | Evidence store |
|--------|--------|----------------|
| Support tickets | HTML ticket exports | BigQuery |
| Customer surveys | Semicolon CSV (NPS free text) | BigQuery |
| Field visits | Semicolon CSV (improvement suggestions) | BigQuery |
| Sales penetration | Local Excel → aggregated CSV (product × customer type) | CSV (no PII pricing focus) |

Sources are defined as **profiles** (`workspace/sources/profiles.py`): column hints, detection keywords, and BQ table mapping. Adding a source does not require rewriting the UI.

---

## Key design decisions

### 1. Backend ingestion, not upload theatre

Users drop files into known folders (`data/inbox/`, ticket HTML paths). The sidebar triggers a **pipeline** that detects schema, validates mappings, and writes canonical tables. This matches how PM and ops actually work and avoids fake in-app uploads.

### 2. BigQuery with safe writes

Uploads use **staging → validation → swap** (`core/bq_load.py`):

1. Load into `{table}_staging`
2. Check row counts and required columns
3. Abort if row drop exceeds threshold (default 50%) — production stays untouched
4. Swap only after validation passes

### 3. Snapshot cache for UX

`workspace/snapshot.py` precomputes cluster counts, theme scores, compare matrices, and coverage metadata into `data/workspace_snapshot.json`. Streamlit reads the snapshot on rerun instead of hitting BigQuery every time. Invalidation is tied to pipeline runs and catalog/RAG fingerprints.

### 4. Hybrid RAG chat (V2)

| Layer | Purpose |
|-------|---------|
| **BigQuery context** | Top clusters and theme scores per selected source — numbers stay grounded |
| **Chroma retrieval** | Semantic chunks from Chonkie V2 (semantic chunker + overlap, Ollama embeddings) |
| **Cloud synthesis (optional)** | Natural-language answer — only when token **and** explicit approval flag are set |

Chat prompts instruct the model to answer **only from provided evidence** and to state gaps explicitly.

### 5. Privacy and degraded operation

- **PII scrubbing** before local LLM steps (`core/governance.py`: email, phone, IBAN patterns)
- **Cloud synthesis gated** by `IONOS_TOKEN` **and** `CLOUD_SYNTHESIS_APPROVED=true`
- **Runtime modes** (`core/runtime.py`): full · evidence-only (no Ollama/RAG) · snapshot-only (offline)
- **Git policy:** no raw CSV/Excel, no keys, no `.env` — code only in version control

---

## What the UI delivers

### Data catalog (sidebar)

Checkbox selection of active sources, pipeline trigger, runtime status (BigQuery, synthesis, Ollama, RAG freshness).

### Insight tiles (deterministic)

Examples:

- **Top needs** — highest-volume problem clusters across selected sources  
- **Hotline frequency** — support ticket module breakdown  
- **Theme compare** — Export, Login, Import, Connection, Installation across sources  
- **Strategy** — rule-based recommendations from theme overlap (no LLM for core logic)  
- **Data coverage** — row counts, backend type (BQ / CSV / Chroma), last update  

### Assistant chat

Example questions:

- *Which five customer needs dominate across sources?*  
- *Which themes appear in both tickets and surveys?*  
- *What do field visits say about export and import?*

When synthesis is disabled, evidence tiles and compare remain usable; chat shows a clear setup hint instead of failing silently.

---

## Pipeline (automated ETL)

Steps in `pipeline/runner.py`:

| Step | Function |
|------|----------|
| `cleanup` | Route misplaced files to correct inbox folders |
| `csv` | Surveys + field visits → normalized backlog CSVs |
| `html` | Ticket HTML → summarized rows via local Ollama |
| `sales` | Product penetration aggregation (customer type × product × counts) |
| `bq` | Staged upload to BigQuery |
| `rag` | Fetch documents from BQ → Chonkie chunk → Chroma index |

Ollama offline → HTML/RAG steps skip transparently; BQ/snapshot path continues.

---

## Results (representative scale)

Figures from a production-style deployment (anonymized aggregates):

| Metric | Order of magnitude |
|--------|-------------------|
| Support ticket clusters indexed | ~380 rows |
| Survey free-text entries | ~200 rows |
| Field visit suggestions | ~50 rows |
| Sales penetration aggregates | ~8,800 product × segment rows |
| RAG chunks (semantic + overlap) | ~600 chunks |
| Built-in compare themes | 5 cross-source themes |

**Outcomes for the PM workflow:**

- Single place to compare “what support says” vs “what surveys say” vs “what sales penetration shows”
- Faster standups — snapshot-backed tiles load in seconds
- Auditable path from raw drop → BQ → UI (no mystery CSVs in git)
- Clear policy for when cloud LLM is allowed

---

## Technical highlights (for engineering readers)

- **Source detection** — column/header keyword matching + adapter mapping (`workspace/sources/detector.py`, `adapters.py`)
- **Dedup logic** — field-visit rows excluded from survey backlog (`core/source_dedup.py`)
- **Chunking** — Chonkie SemanticChunker with overlap refinery; fallback to RecursiveChunker
- **Embeddings** — Ollama `nomic-embed-text`; base URL fix for large batches in index build
- **Compare engine** — keyword + category theme matrix across sources (`workspace/compare.py`)
- **Sales evidence** — CSV-only layer, no BQ/RAG for contract aggregates (`core/sales_evidence.py`)

---

## Lessons learned

1. **Evidence first, chat second** — aggregates and compare tiles deliver value without any cloud API.  
2. **Governance as code** — an env flag for cloud synthesis prevents “accidental” freitext export.  
3. **Profiles beat hardcoding** — new sources extend config, not Streamlit pages.  
4. **Degraded mode is a feature** — PMs still get dashboards when LLM infra is down.  
5. **Do not commit customer data** — pipeline + gitignore + private repo; portfolio sharing via case study and blurred screenshots.

---

## Portfolio note

This case study describes architecture and outcomes from a **real internal project** at a B2G SaaS vendor. Customer names, product modules, GCP project IDs, and raw feedback are **omitted**. The implementation is maintained in a **private repository**; a sanitized public code release was evaluated and deprioritized in favor of documented architecture and controlled demos.

---

## One-line CV bullet

Built a product intelligence workspace unifying support, NPS, field feedback, and sales penetration in BigQuery, with hybrid RAG chat, pipeline-driven ingestion, staging-safe uploads, and privacy-gated cloud synthesis.

---

## Skills demonstrated

Product discovery · Evidence-based prioritization · Data pipeline design · BigQuery · RAG / retrieval design · Streamlit UX · Privacy & governance · Degraded-mode operations · B2G domain (municipal software)
