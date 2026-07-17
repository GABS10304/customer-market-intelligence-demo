"""Kurzer Credential-Check — gibt keine Secrets aus."""
import os
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from config import BIGQUERY_HTML_TABLE, BIGQUERY_TABLE, BQ_DATASET, BQ_PROJECT, GCP_KEY_PATH

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

DECISION_TABLE = f"{BQ_PROJECT}.{BQ_DATASET}.decision_results"
CAPABILITY_TABLE = f"{BQ_PROJECT}.{BQ_DATASET}.capability_results"
    print("=== BigQuery Test ===")
    try:
        from google.cloud import bigquery

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(GCP_KEY_PATH)
        client = bigquery.Client()
        tables = [
            BIGQUERY_TABLE,
            BIGQUERY_HTML_TABLE,
            DECISION_TABLE,
            CAPABILITY_TABLE,
        ]
        for table in tables:
            try:
                query = f"SELECT COUNT(*) AS n FROM `{table}`"
                count = list(client.query(query).result())[0].n
                print(f"OK  {table}: {count} Zeilen")
            except Exception as exc:
                print(f"ERR {table}: {type(exc).__name__}: {str(exc)[:140]}")
    except Exception as exc:
        print(f"BigQuery Client FEHLER: {type(exc).__name__}: {str(exc)[:200]}")


def test_ionos() -> None:
    print("=== IONOS Test ===")
    token = os.getenv("IONOS_TOKEN")
    base = os.getenv("IONOS_BASE_URL", "https://openai.inference.de-txl.ionos.com/v1")
    if not token:
        print("IONOS_TOKEN: fehlt")
        return
    try:
        req = urllib.request.Request(
            base.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"IONOS /models: HTTP {resp.status} OK")
    except Exception as exc:
        print(f"IONOS FEHLER: {type(exc).__name__}: {str(exc)[:200]}")


def test_ollama() -> None:
    print("=== Ollama Test ===")
    try:
        urllib.request.urlopen("http://localhost:11434/", timeout=3)
        print("Ollama: ONLINE")
    except Exception:
        print("Ollama: OFFLINE oder nicht erreichbar")


if __name__ == "__main__":
    test_bigquery()
    test_ionos()
    test_ollama()
