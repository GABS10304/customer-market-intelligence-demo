import streamlit as st
import os

from decision_ui_helpers import setup_gcp_credentials, setup_repo_imports

ROOT_DIR = setup_repo_imports()
KEY_PATH = setup_gcp_credentials() or ""

from bq_decision_writer import load_recent_decisions, write_capability_to_bq, write_decision_to_bq
from capability_detection import detected_capabilities_summary
from initiative_challenger import analyze_initiative

st.set_page_config(page_title="Decision Hub", layout="wide")

st.title("🧠 Decision & Strategy Hub")

BASE_PATH = "pm_brain"
DECISION_PATH = os.path.join(BASE_PATH, "decisions")
HYPOTHESIS_PATH = os.path.join(BASE_PATH, "hypotheses")


def load_markdown_files(folder):
    data = []
    if not os.path.exists(folder):
        return data
    for file in os.listdir(folder):
        if file.endswith(".md"):
            with open(os.path.join(folder, file), "r", encoding="utf-8") as f:
                data.append({"filename": file, "content": f.read()})
    return data


def run_decision_analysis(problem: str, frequency: int, source: str):
    """Decision Engine + Capability Detection + BigQuery Speicherung."""
    result = analyze_initiative(problem, frequency=frequency, source=source)
    decision = result["empfehlung"]

    bq_dec = write_decision_to_bq(
        recommendation=decision["recommendation"],
        reason=decision["reason"],
        risk=decision["risk"],
        confidence=decision["confidence"],
        source=source,
        input_text=problem,
        initiative_id=result["initiative_id"],
    )
    bq_cap = write_capability_to_bq(
        capabilities=result["capabilities"],
        source=source,
        input_text=problem,
        initiative_id=result["initiative_id"],
    )
    return result, decision, bq_dec, bq_cap


decisions = load_markdown_files(DECISION_PATH)
hypotheses = load_markdown_files(HYPOTHESIS_PATH)

tab_analyse, tab_decisions, tab_hypotheses, tab_bq = st.tabs([
    "🚀 Analyse starten",
    "⚖️ Decisions (Memory)",
    "🧪 Hypotheses",
    "☁️ BigQuery History",
])

# =========================
# ANALYSE TAB
# =========================
with tab_analyse:
    st.subheader("Entscheidung aus Evidenz ableiten")
    st.caption("Regelbasierte Decision Engine – kein LLM für Berechnungen.")

    problem_input = st.text_area(
        "Problem / Initiative",
        height=120,
        placeholder="z.B. Import-Schnittstelle zu Google fehlt, 23 Support-Tickets...",
    )
    freq_input = st.number_input("Häufigkeit (optional)", min_value=0, value=0)

    if st.button("🔍 Analyse starten", type="primary"):
        if not problem_input.strip():
            st.warning("Bitte ein Problem oder eine Initiative beschreiben.")
        else:
            with st.spinner("Decision Engine läuft..."):
                result, decision, bq_dec, bq_cap = run_decision_analysis(
                    problem_input, freq_input, source="decision_hub"
                )

            if bq_dec["success"]:
                st.success("Entscheidung in `decision_results` gespeichert.")
            else:
                st.warning(f"BigQuery (decision_results): {bq_dec.get('error', 'Fehler')}")

            if bq_cap["success"]:
                st.success(f"Capabilities in `capability_results` gespeichert ({bq_cap['count']} Zeilen).")
            else:
                st.warning(f"BigQuery (capability_results): {bq_cap.get('error', 'Fehler')}")

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("#### ⚖️ Empfehlung")
                st.metric("Make / Buy / Partner", decision["recommendation"])
                st.write(f"**Confidence:** {decision['confidence']:.0%}")
                st.write(f"**Begründung:** {decision['reason']}")
                st.write(f"**Risiko:** {decision['risk']}")

            with col_b:
                st.markdown("#### 🔧 Capabilities")
                st.write(detected_capabilities_summary(result["capabilities"]))
                st.markdown("#### ⚡ Challenges")
                for i, ch in enumerate(result["challenge"], 1):
                    st.caption(f"{i}. {ch}")

            with st.expander("JSON Output"):
                st.json(decision)

# =========================
# DECISIONS TAB
# =========================
with tab_decisions:
    st.subheader("📊 Gespeicherte Entscheidungen (PM Brain)")
    if len(decisions) == 0:
        st.info("Keine Decisions vorhanden.")
    else:
        for d in decisions:
            with st.expander(f"📂 {d['filename']}"):
                st.markdown(d["content"])

# =========================
# HYPOTHESES TAB
# =========================
with tab_hypotheses:
    st.subheader("🧪 Offene Hypothesen")
    if len(hypotheses) == 0:
        st.info("Keine Hypothesen vorhanden.")
    else:
        for h in hypotheses:
            with st.expander(f"📂 {h['filename']}"):
                st.markdown(h["content"])

# =========================
# BIGQUERY HISTORY TAB
# =========================
with tab_bq:
    st.subheader("☁️ Letzte Entscheidungen aus BigQuery")
    if not os.path.exists(KEY_PATH):
        st.error("GCP-Schlüssel nicht gefunden – BigQuery-History nicht verfügbar.")
    else:
        df = load_recent_decisions(limit=25)
        if df.empty:
            st.info("Noch keine Einträge in `decision_results` – starte eine Analyse.")
        else:
            st.dataframe(df, hide_index=True, use_container_width=True)
