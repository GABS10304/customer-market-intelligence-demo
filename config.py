"""
Zentrale Konfiguration — Pfade, Secrets und LLM-Policy.
Liegt im Projekt-Root; .env wird aus dem Root geladen.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    """Liest .env-Wert; leere Strings gelten als nicht gesetzt."""
    value = os.getenv(key)
    if value is None or not str(value).strip():
        return default
    return str(value).strip()


# Früh definieren — wird von Home.py, runtime.py, chat.py importiert
WORKSPACE_VERSION = "2.1"

DEMO_MODE = _env("DEMO_MODE", "").lower() in ("1", "true", "yes") or _env(
    "USE_DEMO_DATA", ""
).lower() in ("1", "true", "yes")

# Quellen mit ERP/TERA-Vertragsdaten — im Demo-Modus ausblenden
DEMO_EXCLUDED_SOURCE_KEYS = frozenset({"sales_product_penetration"})

DATA_DIR = ROOT_DIR / "data"
DEMO_DATA_DIR = DATA_DIR / "demo"
INBOX_DIR = DATA_DIR / "inbox"
INBOX_SURVEYS_DIR = INBOX_DIR / "umfragen"
INBOX_FIELD_VISITS_DIR = INBOX_DIR / "weihnachtsbesuche"
TICKETS_DIR = DATA_DIR / "Tickets_neu"
TICKETS_TEXT_DIR = TICKETS_DIR / "Text"
TICKETS_HTML_DIR = TICKETS_DIR / "html"
PROCESSED_DIR = DATA_DIR / "processed"
# Legacy-Alias — Hotline liegt unter Tickets_neu
HTML_DIR = TICKETS_HTML_DIR
UPLOAD_DIR = DATA_DIR / "uploads"
REGISTRY_PATH = DATA_DIR / ".registry.json"
CATALOG_PATH = DATA_DIR / "catalog.json"
SNAPSHOT_PATH = DATA_DIR / "workspace_snapshot.json"

# Pipeline-Outputs (aus Originalquellen, nicht Repo-Root)
SURVEYS_NPS_CSV = DATA_DIR / "surveys_nps.csv"
TICKETS_BACKLOG_CSV = DATA_DIR / "tickets_backlog.csv"
FIELD_VISITS_CSV = DATA_DIR / "field_visits_backlog.csv"
SALES_RAW_XLSX = ROOT_DIR / "Rohe_Sales_Daten.xlsx"
SALES_PRODUCT_PENETRATION_CSV = DATA_DIR / "sales_product_penetration.csv"
SALES_PRODUCT_PENETRATION_ROOT = ROOT_DIR / "Sales_Product_Penetration.csv"
TERA_INSTALLATIONS_CSV = DATA_DIR / "tera_installations.csv"
RAG_INDEX_DIR = DATA_DIR / "rag_index"
RAG_META_PATH = DATA_DIR / "rag_index_meta.json"
GRAYLOG_CACHE_PATH = DATA_DIR / "graylog_top_functions_cache.json"
PRODUCT_MODULE_MAPPING_PATH = DATA_DIR / "product_module_mapping.json"
TERA_HOTLINE_MAPPING_PATH = DATA_DIR / "tera_hotline_mapping.json"
GRAYLOG_EVENT_MAPPING_PATH = DATA_DIR / "graylog_event_mapping.json"
PRODUCT_SIGNALS_CSV = DATA_DIR / "product_signals_unified.csv"

DELIMITER = ";"
OUTPUT_FIELDNAMES = [
    "Kunde",
    "Kategorie",
    "Original-Wortlaut (Freitext)",
    "Quelle",
    "source_file",
    "processed_at",
]

DEPLOYMENT_MODE = _env("DEPLOYMENT_MODE", "single-user")

# Cloud-Synthese nur mit expliziter Freigabe (Datenschutz)
CLOUD_SYNTHESIS_APPROVED = _env("CLOUD_SYNTHESIS_APPROVED", "").lower() in ("1", "true", "yes")

# BigQuery: Staging → Validierung → Swap (kein direktes WRITE_TRUNCATE auf Prod)
BQ_USE_STAGING = _env("BQ_USE_STAGING", "true").lower() not in ("0", "false", "no")
BQ_MIN_ROWS = int(_env("BQ_MIN_ROWS", "1") or "1")
BQ_MAX_ROW_DROP_PCT = float(_env("BQ_MAX_ROW_DROP_PCT", "0.5") or "0.5")

OLLAMA_MODEL = _env("OLLAMA_MODEL", "llama3.2")
OLLAMA_URL = _env("OLLAMA_URL", "http://localhost:11434")
IONOS_BASE_URL = _env("IONOS_BASE_URL", "https://openai.inference.de-txl.ionos.com/v1")
IONOS_MODEL = _env("IONOS_MODEL", "openai/gpt-oss-120b")

BIGQUERY_TABLE = _env(
    "BIGQUERY_TABLE",
    "pm-analytics-496606.pm_daten.anonymes_pm_backlog",
)
BIGQUERY_HTML_TABLE = _env(
    "BIGQUERY_HTML_TABLE",
    "pm-analytics-496606.pm_daten.html_tickets_rohdaten",
)
BIGQUERY_FIELD_VISITS_TABLE = _env(
    "BIGQUERY_FIELD_VISITS_TABLE",
    "pm-analytics-496606.pm_daten.field_visits_feedback",
)
BIGQUERY_SALES_TABLE = _env(
    "BIGQUERY_SALES_TABLE",
    "pm-analytics-496606.pm_daten.sales_product_penetration",
)

# Graylog — Modul-Nutzung (Usage-Import)
GRAYLOG_URL = _env("GRAYLOG_URL", "")
GRAYLOG_TOKEN = _env("GRAYLOG_TOKEN", "")
GRAYLOG_STREAMS = _env("GRAYLOG_STREAMS", "")
GRAYLOG_DAYS = _env("GRAYLOG_DAYS", "30")
GRAYLOG_MODULE_FIELD = _env("GRAYLOG_MODULE_FIELD", "")
GRAYLOG_USER_FIELD = _env("GRAYLOG_USER_FIELD", "")
GRAYLOG_VERIFY_SSL = _env("GRAYLOG_VERIFY_SSL", "true").lower() not in ("0", "false", "no")

REPORT_SUPPORT_MD = ROOT_DIR / "Finaler_PM_Report_Support.md"
REPORT_SURVEYS_MD = ROOT_DIR / "Finaler_PM_Report_Umfragen.md"
REPORT_MD = REPORT_SUPPORT_MD
GCP_KEY_PATH = ROOT_DIR / "gcp-key.json"

FIELD_VISITS_FIELDNAMES = [
    "Kunde",
    "AP",
    "Modul_App_Verfahren",
    "Original_Wortlaut_Freitext",
    "Quelle",
    "source_file",
    "processed_at",
]


def get_ionos_token() -> str | None:
    token = os.getenv("IONOS_TOKEN")
    if not token or not str(token).strip():
        return None
    return str(token).strip().strip('"').strip("'")


def setup_gcp_credentials() -> Path | None:
    if DEMO_MODE:
        return None
    if GCP_KEY_PATH.exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(GCP_KEY_PATH)
        return GCP_KEY_PATH
    return None


def apply_demo_paths() -> None:
    """Leitet Pfade auf data/demo/ um — nur bei DEMO_MODE=true."""
    if not DEMO_MODE:
        return
    global INBOX_DIR, INBOX_SURVEYS_DIR, INBOX_FIELD_VISITS_DIR
    global TICKETS_DIR, TICKETS_TEXT_DIR, TICKETS_HTML_DIR, HTML_DIR
    global PROCESSED_DIR, UPLOAD_DIR, REGISTRY_PATH, CATALOG_PATH, SNAPSHOT_PATH
    global SURVEYS_NPS_CSV, TICKETS_BACKLOG_CSV, FIELD_VISITS_CSV
    global RAG_INDEX_DIR, RAG_META_PATH, GRAYLOG_CACHE_PATH
    global PRODUCT_SIGNALS_CSV, PRODUCT_MODULE_MAPPING_PATH
    global GRAYLOG_EVENT_MAPPING_PATH

    INBOX_DIR = DEMO_DATA_DIR / "inbox"
    INBOX_SURVEYS_DIR = INBOX_DIR / "umfragen"
    INBOX_FIELD_VISITS_DIR = INBOX_DIR / "weihnachtsbesuche"
    TICKETS_DIR = DEMO_DATA_DIR / "Tickets_neu"
    TICKETS_TEXT_DIR = TICKETS_DIR / "Text"
    TICKETS_HTML_DIR = TICKETS_DIR / "html"
    HTML_DIR = TICKETS_HTML_DIR
    PROCESSED_DIR = DEMO_DATA_DIR / "processed"
    UPLOAD_DIR = DEMO_DATA_DIR / "uploads"
    REGISTRY_PATH = DEMO_DATA_DIR / ".registry.json"
    CATALOG_PATH = DEMO_DATA_DIR / "catalog.json"
    SNAPSHOT_PATH = DEMO_DATA_DIR / "workspace_snapshot.json"
    SURVEYS_NPS_CSV = DEMO_DATA_DIR / "surveys_nps.csv"
    TICKETS_BACKLOG_CSV = DEMO_DATA_DIR / "tickets_backlog.csv"
    FIELD_VISITS_CSV = DEMO_DATA_DIR / "field_visits_backlog.csv"
    RAG_INDEX_DIR = DEMO_DATA_DIR / "rag_index"
    RAG_META_PATH = DEMO_DATA_DIR / "rag_index_meta.json"
    GRAYLOG_CACHE_PATH = DEMO_DATA_DIR / "graylog_top_functions_cache.json"
    PRODUCT_SIGNALS_CSV = DEMO_DATA_DIR / "product_signals_unified.csv"
    PRODUCT_MODULE_MAPPING_PATH = DEMO_DATA_DIR / "product_module_mapping.json"
    GRAYLOG_EVENT_MAPPING_PATH = DEMO_DATA_DIR / "graylog_event_mapping.json"


apply_demo_paths()


def demo_fixtures_ready() -> tuple[bool, list[str]]:
    """Prüft minimale Demo-Fixtures — fail-closed mit klarer Meldung."""
    if not DEMO_MODE:
        return True, []
    required = (
        SNAPSHOT_PATH,
        CATALOG_PATH,
        TICKETS_BACKLOG_CSV,
        PRODUCT_MODULE_MAPPING_PATH,
        TICKETS_HTML_DIR,
    )
    missing = [str(p.relative_to(ROOT_DIR)) for p in required if not p.exists()]
    return not missing, missing

# Aliase für bestehende Module (nach Demo-Pfad-Umleitung)
BACKLOG_CSV = SURVEYS_NPS_CSV
HTML_OUTPUT_CSV = TICKETS_BACKLOG_CSV


def ensure_data_dirs() -> None:
    for directory in (
        INBOX_DIR,
        INBOX_SURVEYS_DIR,
        INBOX_FIELD_VISITS_DIR,
        TICKETS_DIR,
        TICKETS_TEXT_DIR,
        TICKETS_HTML_DIR,
        PROCESSED_DIR,
        UPLOAD_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
