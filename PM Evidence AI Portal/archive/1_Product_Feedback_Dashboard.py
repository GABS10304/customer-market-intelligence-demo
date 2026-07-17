import os

import sys



import pandas as pd

import plotly.express as px

import streamlit as st

from google.cloud import bigquery

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from langchain_openai import ChatOpenAI



PORTAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROOT_DIR = os.path.dirname(PORTAL_DIR)

if ROOT_DIR not in sys.path:

    sys.path.insert(0, ROOT_DIR)



from core.bq_evidence import build_evidence_context, fetch_cluster_counts

from config import IONOS_BASE_URL, IONOS_MODEL, get_ionos_token

from decision_ui_helpers import setup_gcp_credentials, setup_repo_imports

from pipeline.aggregator import report_path_for_source



setup_repo_imports()

setup_gcp_credentials()



st.set_page_config(page_title="PM Feedback Dashboard", page_icon="📊", layout="wide")

st.title("📊 Product Feedback (Live aus BigQuery)")



IONOS_TOKEN = get_ionos_token()



BASE_DIR = str(ROOT_DIR)

key_path = os.path.join(BASE_DIR, "gcp-key.json")



if not os.path.exists(key_path):

    st.error(f"Schlüssel nicht gefunden unter: {key_path}")

    st.stop()



os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path



if "dash_messages" not in st.session_state:

    st.session_state.dash_messages = []

if "last_datenquelle" not in st.session_state:

    st.session_state.last_datenquelle = None

if "bq_context_key" not in st.session_state:

    st.session_state.bq_context_key = None



# ==========================================

# 2. DER DATENQUELLEN-SCHALTER

# ==========================================

st.markdown("### 🎛️ Datenquelle wählen")

datenquelle = st.radio(

    "Welche Metrik möchtest du auswerten?",

    options=["🔧 Support-Tickets (HTML-Inbox)", "📋 Kundenumfragen (NPS / CSV)"],

    horizontal=True,

)



if "Support-Tickets" in datenquelle:

    aktuelle_tabelle = "your-gcp-project.pm_daten.html_tickets_rohdaten"

    gruppierungs_spalte = "Ordner___Modul"

    ui_name = "Modul"

    bq_source = "support"

    quelle_label = "Support-Tickets"

else:

    aktuelle_tabelle = "your-gcp-project.pm_daten.anonymes_pm_backlog"

    gruppierungs_spalte = "Kategorie"

    ui_name = "Problem_Kategorie"

    bq_source = "surveys"

    quelle_label = "Kundenumfragen"



report_path = str(report_path_for_source(bq_source))



if st.session_state.last_datenquelle != datenquelle:

    st.session_state.dash_messages = []

    st.session_state.bq_context_key = None

    st.session_state.last_datenquelle = datenquelle





@st.cache_data(ttl=600)

def load_bigquery_data(table_name, group_col, label):

    client = bigquery.Client()

    safe_label = label.replace(" / ", "_")

    query = f"""

        SELECT {group_col} as {safe_label}, COUNT(*) as Anzahl

        FROM `{table_name}`

        GROUP BY {group_col}

        ORDER BY Anzahl DESC

    """

    return client.query(query).to_dataframe()





@st.cache_data(ttl=600)

def load_bq_evidence_context(source: str) -> str:

    return build_evidence_context(source, top_n=5, samples_per_cluster=3)





def init_qa_context(source: str) -> None:

    context = load_bq_evidence_context(source)

    st.session_state.bq_context_key = context

    st.session_state.dash_messages = [

        SystemMessage(

            content=(

                f"Du bist Product Manager. Beantworte Fragen AUSSCHLIESSLICH basierend "

                f"auf diesen Live-Daten aus BigQuery ({quelle_label}). "

                f"Erfinde nichts.\n\n{context}"

            )

        )

    ]





# ==========================================

# 4. DAS FRONTEND-LAYOUT

# ==========================================

try:

    with st.spinner(f"Lade Live-Daten aus {aktuelle_tabelle}..."):

        df = load_bigquery_data(aktuelle_tabelle, gruppierungs_spalte, ui_name)

        safe_col_name = ui_name.replace(" / ", "_")



    st.subheader(f"Verteilung der Schmerzpunkte ({datenquelle[:15]}...)")

    fig = px.bar(

        df, x=safe_col_name, y="Anzahl", text="Anzahl",

        color=safe_col_name, template="plotly_white",

    )

    fig.update_traces(textposition="outside")

    st.plotly_chart(fig, use_container_width=True)



    st.divider()



    # --- LIVE TOP 5 AUS BIGQUERY ---

    st.subheader(f"💡 Top-Probleme — live aus BigQuery ({quelle_label})")

    top_df = fetch_cluster_counts(bq_source, limit=5)



    if top_df.empty:

        st.warning("Keine Cluster in BigQuery gefunden. Bitte Pipeline im Admin ausführen.")

    else:

        display = top_df.rename(columns={"cluster": ui_name, "anzahl": "Anzahl"})

        st.dataframe(display[[ui_name, "Anzahl"]], hide_index=True, use_container_width=True)



    with st.expander("Optional: Aggregator-Report (Markdown, nicht für Q&A)"):

        if os.path.exists(report_path):

            with open(report_path, encoding="utf-8-sig") as handle:

                st.markdown(handle.read())

            st.caption("Nur Menschen-Leseversion — Q&A nutzt BigQuery live.")

        else:

            st.caption("Noch nicht generiert. Pipeline-Schritt „Top-5 Reports“ im Admin.")



    st.divider()



    # --- DEEP-DIVE ---

    st.subheader("🔍 Deep-Dive: Rohdaten-Verifizierung")

    alle_kategorien = df[safe_col_name].tolist()

    gewaehltes_item = st.selectbox(f"{ui_name} auswählen:", options=alle_kategorien)



    if gewaehltes_item:

        client = bigquery.Client()

        safe_item = gewaehltes_item.replace("\\", "\\\\")



        detail_query = f"""

            SELECT *

            FROM `{aktuelle_tabelle}`

            WHERE {gruppierungs_spalte} = '{safe_item}'

        """

        detail_df = client.query(detail_query).to_dataframe()



        cols_to_show = [c for c in detail_df.columns if c not in ["Kategorie", "Ordner___Modul"]]

        st.dataframe(detail_df[cols_to_show], hide_index=True, use_container_width=True)



        st.markdown("#### ⚖️ Decision Engine")

        st.caption("Regelbasierte Make/Buy-Analyse – speichert in BigQuery.")

        freq_count = int(df.loc[df[safe_col_name] == gewaehltes_item, "Anzahl"].iloc[0])

        problem_text = f"{ui_name}: {gewaehltes_item} ({freq_count} Vorkommen in {datenquelle})"



        if st.button("🔍 Analyse starten", key="dash_decision_analyse"):

            from bq_decision_writer import write_capability_to_bq, write_decision_to_bq

            from capability_detection import detected_capabilities_summary

            from initiative_challenger import analyze_initiative



            with st.spinner("Decision Engine + Capability Detection..."):

                result = analyze_initiative(problem_text, frequency=freq_count, source="pm_dashboard")

                decision = result["empfehlung"]

                bq_dec = write_decision_to_bq(

                    recommendation=decision["recommendation"],

                    reason=decision["reason"],

                    risk=decision["risk"],

                    confidence=decision["confidence"],

                    source="pm_dashboard",

                    input_text=problem_text,

                    initiative_id=result["initiative_id"],

                    frequency=freq_count,

                )

                write_capability_to_bq(

                    capabilities=result["capabilities"],

                    source="pm_dashboard",

                    input_text=problem_text,

                    initiative_id=result["initiative_id"],

                )



            c1, c2 = st.columns(2)

            with c1:

                st.success(f"**{decision['recommendation']}** (Confidence {decision['confidence']:.0%})")

                st.write(decision["reason"])

                st.write(f"**Risiko:** {decision['risk']}")

            with c2:

                st.write(detected_capabilities_summary(result["capabilities"]))

                if bq_dec["success"]:

                    st.caption("Gespeichert in decision_results + capability_results")

                else:

                    st.warning(f"BigQuery: {bq_dec.get('error', 'Speichern fehlgeschlagen')}")



    st.divider()



    # --- Q&A AUS BIGQUERY ---

    st.subheader(f"💬 Q&A zu den Live-Daten ({quelle_label})")

    st.caption("Kontext kommt direkt aus BigQuery — kein Markdown-Report nötig.")



    if not st.session_state.dash_messages:

        init_qa_context(bq_source)



    with st.expander("Aktueller BigQuery-Kontext (für Q&A)"):

        st.text(st.session_state.bq_context_key or load_bq_evidence_context(bq_source))



    if st.button("🔄 Kontext aus BigQuery neu laden", key="refresh_bq_context"):

        load_bq_evidence_context.clear()

        load_bigquery_data.clear()

        init_qa_context(bq_source)

        st.rerun()



    for msg in st.session_state.dash_messages:

        if isinstance(msg, HumanMessage):

            with st.chat_message("user"):

                st.write(msg.content)

        elif isinstance(msg, AIMessage):

            with st.chat_message("assistant"):

                st.write(msg.content)



    if user_input := st.chat_input("Beispiel: Was sind die Top-3 Probleme und warum?"):

        with st.chat_message("user"):

            st.write(user_input)

        st.session_state.dash_messages.append(HumanMessage(content=user_input))



        with st.chat_message("assistant"):

            response_placeholder = st.empty()

            full_response = ""



            llm = ChatOpenAI(

                api_key=IONOS_TOKEN,

                base_url=IONOS_BASE_URL,

                model=IONOS_MODEL,

                temperature=0.0,

            )



            for chunk in llm.stream(st.session_state.dash_messages):

                full_response += chunk.content

                response_placeholder.markdown(full_response + "▌")



            response_placeholder.markdown(full_response)

            st.session_state.dash_messages.append(AIMessage(content=full_response))



except Exception as e:

    st.error(f"Es gab ein Problem bei der Auswertung (SQL/API): {e}")


