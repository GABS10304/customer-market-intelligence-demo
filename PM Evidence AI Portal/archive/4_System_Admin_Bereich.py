import io
import os
import sys
import urllib.request
from contextlib import redirect_stdout

import streamlit as st

# Repo-Root zuerst — vor allen core/pipeline Imports
_PORTAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT_DIR = os.path.dirname(_PORTAL_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from config import INBOX_DIR, get_ionos_token, setup_gcp_credentials
from decision_ui_helpers import setup_portal
from pipeline.inbox import load_registry
from pipeline.runner import inbox_status, run_pipeline

setup_portal()

st.set_page_config(page_title="Admin & Pipeline", page_icon="⚙️", layout="wide")
st.title("⚙️ Daten-Pipeline & System")
st.markdown("Zentraler Steuerungsbereich für **V1** — Inbox, Verarbeitung, BigQuery.")

st.divider()

# --- Health ---
st.subheader("🏥 System-Status")
c1, c2, c3 = st.columns(3)

with c1:
    try:
        urllib.request.urlopen("http://localhost:11434/", timeout=2)
        st.success("Ollama (lokal): ONLINE")
    except OSError:
        st.error("Ollama (lokal): OFFLINE")

with c2:
    if get_ionos_token():
        st.success("IONOS Token (.env): gesetzt")
    else:
        st.warning("IONOS Token (.env): fehlt")

with c3:
    if setup_gcp_credentials():
        st.success("GCP Key: vorhanden")
    else:
        st.warning("gcp-key.json: fehlt")

st.divider()

# --- Inbox ---
st.subheader("📂 CSV Inbox")
status = inbox_status()

st.markdown(f"**Ordner:** `{status['inbox_dir']}`")

if status["pending_count"]:
    st.warning(f"**{status['pending_count']} Datei(en)** warten auf Verarbeitung:")
    for name in status["pending"]:
        st.write(f"- `{name}`")
else:
    if status["total"]:
        st.success(f"Alle {status['total']} Inbox-Datei(en) sind aktuell verarbeitet.")
    else:
        st.info("Inbox ist leer — lege CSVs in `data/inbox/` ab.")

with st.expander("Verarbeitete Dateien (Registry)"):
    registry = load_registry().get("files", {})
    if registry:
        for filename, meta in sorted(registry.items()):
            st.write(
                f"**{filename}** — {meta.get('rows', 0)} Zeilen, "
                f"{meta.get('status', '?')}, {meta.get('processed_at', '')[:19]}"
            )
    else:
        st.caption("Noch keine Dateien verarbeitet.")

st.divider()

# --- Pipeline ---
st.subheader("🚀 Pipeline")

st.markdown(
    """
**Ein Klick** führt alle Schritte aus:
1. CSV Inbox verarbeiten (lokal / Ollama)
2. HTML-Tickets schreddern
3. Top-5-Reports (optional, nur Menschen-Leseversion)
4. BigQuery-Upload
5. **RAG-Index aus BigQuery** (für Deep Dive)
"""
)

col_a, col_b = st.columns(2)

with col_a:
    run_all = st.button("▶️ Daten aktualisieren (komplett)", type="primary", use_container_width=True)

with col_b:
    run_csv_only = st.button("Nur CSV-Inbox", use_container_width=True)

log_box = st.empty()

if run_all or run_csv_only:
    steps = ("csv",) if run_csv_only else ("csv", "html", "aggregate", "bq", "rag")
    buffer = io.StringIO()

    def stream_log(message: str) -> None:
        buffer.write(message + "\n")
        log_box.code(buffer.getvalue(), language="bash")

    with st.spinner("Pipeline läuft..."):
        with redirect_stdout(buffer):
            run_pipeline(steps=steps, log=stream_log)

    st.success("Pipeline abgeschlossen.")
    st.rerun()

st.divider()

st.subheader("Einzel-Schritte (optional)")

c1, c2, c3, c4, c5 = st.columns(5)
step_buttons = {
    c1: ("csv", "CSV Inbox"),
    c2: ("html", "HTML"),
    c3: ("aggregate", "Top-5 Reports"),
    c4: ("bq", "BigQuery"),
    c5: ("rag", "RAG-Index"),
}

for col, (step, label) in step_buttons.items():
    with col:
        if st.button(label, use_container_width=True, key=f"step_{step}"):
            buffer = io.StringIO()

            def stream_log(message: str) -> None:
                buffer.write(message + "\n")
                log_box.code(buffer.getvalue(), language="bash")

            with st.spinner(f"{label}..."):
                run_pipeline(steps=(step,), log=stream_log)
            st.rerun()

st.divider()
st.caption(f"Inbox-Pfad: {INBOX_DIR}")
