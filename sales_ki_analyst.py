import pandas as pd
import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from config import IONOS_BASE_URL, IONOS_MODEL, ROOT_DIR, get_ionos_token

BASE_DIR = str(ROOT_DIR)
INPUT_FILE = os.path.join(BASE_DIR, "Sales_ICP_Strategie_Daten.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "Sales_Strategie_Report.md")

IONOS_TOKEN = get_ionos_token()
if not IONOS_TOKEN:
    raise RuntimeError("IONOS_TOKEN fehlt in .env")

llm = ChatOpenAI(
    api_key=IONOS_TOKEN,
    base_url=IONOS_BASE_URL,
    model=IONOS_MODEL,
    temperature=0.0,
)

# ==========================================
# 2. DIE ANALYSE
# ==========================================
def analyze_sales():
    print("\n🚀 Starte den KI-Analysten für deine RevOps & ICP Daten...")
    
    if not os.path.exists(INPUT_FILE):
        print(f"⚠️ Die Datei {INPUT_FILE} wurde nicht gefunden!")
        print("Bitte führe zuerst das Datenskript 'sales_prep.py' aus.")
        return

    # Lade die bereinigten Daten
    df = pd.read_csv(INPUT_FILE, sep=";", encoding="utf-8-sig")
    if "Gesamt_Netto_Volumen" not in df.columns or "Ø_Rabatt_Prozent" not in df.columns:
        print(
            "Hinweis: sales_prep.py liefert jetzt Product-Penetration ohne Preise/Rabatt. "
            "Dieses Skript ist nur für Pricing/RevOps mit Umsatz-Spalten gedacht."
        )
        return

    # Nimm nur die Top 50 Ergebnisse (die wichtigsten Segmente), um die KI nicht zu überladen
    daten_text = df.head(50).to_markdown(index=False)

    prompt = ChatPromptTemplate.from_template("""
    Du bist der Head of Revenue Operations und Sales Strategist in einer B2B Software-Firma für Kommunen (GovTech).
    Hier ist eine fertig berechnete, 100% anonymisierte Tabelle unserer Verkäufe, sortiert nach unserem 'ICP_Score'.
    
    Analysiere diese Tabelle knallhart und erstelle ein 'Sales Cheat Sheet' für unser Vertriebsteam.
    Nutze ZWINGEND dieses Format zur Beantwortung:
    
    ### 🥇 1. Unser Traumkunde (Ideal Customer Profile)
    Welche Kombination aus Kundentyp und Modul sichert uns das wichtigste Geschäft? Begründe warum.
    
    ### 💸 2. Preis-Strategie (Rabatte)
    Wo lassen wir aktuell Geld auf dem Tisch liegen? In welchem Segment/Modul geben wir viel zu hohe Rabatte, obwohl wir das nicht müssten?
    
    ### 📈 3. Verstecktes Potenzial
    Gibt es Segmente mit hoher Käufer-Anzahl, aber erstaunlich niedrigem Gesamt-Volumen? Hier müssen wir Cross-Selling betreiben.
    
    ### 🎯 4. Deine 3 Sales-To-Dos
    Nenne 3 messerscharfe, sofort anwendbare Handlungsanweisungen für den Vertrieb in der nächsten Woche.
    
    ROHDATEN-TABELLE ZUR ANALYSE:
    {daten}
    """)

    print("🧠 Qwen studiert gerade deine ICP-Matrix. Bitte warten...")
    
    chain = prompt | llm
    ergebnis = chain.invoke({"daten": daten_text})

    # Exportieren als lesbares Markdown-Dokument
    with open(OUTPUT_FILE, "w", encoding="utf-8-sig") as f:
        f.write(ergebnis)

    print("\n============================================================")
    print("🎉 FERTIG! Dein fundiertes Sales Cheat Sheet ist bereit!")
    print("============================================================\n")
    print(ergebnis)
    print(f"\n📁 Speicherung erfolgreich: Die Datei liegt bereit unter {OUTPUT_FILE}")

if __name__ == "__main__":
    analyze_sales()