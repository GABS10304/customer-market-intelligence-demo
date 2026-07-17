import streamlit as st
import pandas as pd
import os
import plotly.express as px

# ==========================================
# 1. SETUP
# ==========================================
st.set_page_config(page_title="Sales Strategy Brain", layout="wide")
st.title("💼 Sales Strategy Brain (ICP & RevOps)")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEXT_REPORT = os.path.join(BASE_DIR, "Sales_Strategie_Report.md")
TABELLEN_DATEN = os.path.join(BASE_DIR, "Sales_ICP_Strategie_Daten.csv")

if os.path.exists(TABELLEN_DATEN):
    try:
        df_sales = pd.read_csv(TABELLEN_DATEN, sep=";", encoding="utf-8-sig")
        
        # ==========================================
        # 2. DER VISUELLE BEWEIS (RABATT-RADAR)
        # ==========================================
        st.subheader("🕵️‍♂️ Die Beweiskammer: Rabatt-Radar")
        st.markdown("Dieses Diagramm zeigt deterministische (rechenfehlerfreie) Python-Kalkulationen direkt aus der ERP/CRM-Export-Datei.")
        
        # Wir suchen dynamisch die richtige Spalte für die Modul-Namen, damit es nicht abstürzt!
        modul_spalte = "artikelbezeichnung" if "artikelbezeichnung" in df_sales.columns else df_sales.columns[1]
        
        # Wir prüfen, wie die Zähl-Spalte für die Größe der Blasen heißt
        groessen_spalte = "Anzahl_Vertragspositionen" if "Anzahl_Vertragspositionen" in df_sales.columns else None
        
        fig = px.scatter(
            df_sales,
            x="Gesamt_Netto_Volumen",
            y="Ø_Rabatt_Prozent",
            size=groessen_spalte,
            color="Kundentyp",
            hover_name=modul_spalte,
            title="Rabatt-Verteilung vs. Umsatz (Jeder Punkt ist ein Software-Modul)",
            template="plotly_white",
            labels={
                "Gesamt_Netto_Volumen": "Generierter Umsatz (€)",
                "Ø_Rabatt_Prozent": "Durchschnittlicher Rabatt (%)"
            }
        )
        
        # Rote Warn-Linie für "Zu viel Rabatt" (über 15%)
        fig.add_hline(y=15, line_dash="dash", line_color="red", annotation_text="Kritische Rabatt-Grenze")
        st.plotly_chart(fig, use_container_width=True)
        st.divider()

        # ==========================================
        # 3. DAS BERECHNETE DASHBOARD ANZEIGEN
        # ==========================================
        col1, col2 = st.columns([1, 1])

        with col1:
            st.subheader("🧠 KI-Generiertes Sales Cheat Sheet")
            st.info("Dieser Report wurde offline und sicher durch lokale KIs generiert.")
            if os.path.exists(TEXT_REPORT):
                with open(TEXT_REPORT, "r", encoding="utf-8-sig") as f:
                    st.markdown(f.read())
            else:
                st.warning("⚠️ Kein Report gefunden. Bitte 'sales_ki_analyst.py' ausführen.")

        with col2:
            st.subheader("📊 ICP Daten-Matrix (Rohdaten)")
            st.info("Diese Zahlen wurden deterministisch (fehlerfrei) per Python berechnet.")
            st.dataframe(df_sales, hide_index=True, use_container_width=True)
            
            st.divider()
            st.metric("Erfasste Kundensegmente", len(df_sales))
            if "Gesamt_Netto_Volumen" in df_sales.columns:
                st.metric("Erkanntes Gesamtvolumen", f"{df_sales['Gesamt_Netto_Volumen'].sum():,.2f} €")

    except Exception as e:
        st.error(f"Fehler bei der Darstellung: {e}")
else:
    st.error("⚠️ Keine Daten gefunden! Bitte erst das Skript 'sales_prep.py' ausführen.")