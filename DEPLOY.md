# Deployment & GitHub — sicher ohne Kundendaten

Code gehört in Git. **Rohdaten, Tokens und Keys nie.**

## Was ins Repo darf

| Ja | Nein |
|----|------|
| Python, Portal, `requirements.txt` | `.env`, `gcp-key.json` |
| `.env.example`, `DEPLOY.md`, `README.md` | `*.csv`, `*.xlsx` (Rohdaten) |
| Tests, Konfiguration ohne Secrets | `data/inbox/`, `data/rag_index/`, Snapshots |

## Secrets lokal anlegen

```powershell
cd <projektroot>
copy .env.example .env
# .env bearbeiten: IONOS_TOKEN, ggf. CLOUD_SYNTHESIS_APPROVED=true
# gcp-key.json vom GCP-Admin ins Projektroot legen
```

## Vor dem ersten Push (Checkliste)

```powershell
cd <projektroot>

git status
git check-ignore -v .env gcp-key.json Rohe_Sales_Daten.xlsx Sales_Product_Penetration.csv

# Falls jemals Secrets committed wurden → Keys rotieren + History bereinigen
git log --all --oneline -- .env gcp-key.json
```

Erwartung: sensible Dateien erscheinen **nicht** unter „Changes to be committed“ und `check-ignore` zeigt eine Regel.

## GitHub anlegen (privat empfohlen)

```powershell
git remote add origin https://github.com/ORG/rag-intelligence.git
git push -u origin main
```

**Privates Repo** für internes PM-Tool mit BQ-Anbindung.

## Daten aktuell halten (nicht über Git)

| Was | Wie |
|-----|-----|
| **Code** | `git pull` |
| **Feedback/Tickets/Umfragen** | Dateien in `data/inbox/` → Sidebar **Pipeline starten** |
| **Sales** | `Rohe_Sales_Daten.xlsx` im Root → Pipeline Schritt `sales` oder `python sales_prep.py` |
| **RAG** | Pipeline mit Schritt `rag` (Ollama + `nomic-embed-text`) |
| **Evidenz live** | BigQuery (SSOT) — Pipeline Schritt `bq` |

Typischer Refresh nach neuen Dateien:

```powershell
venv\Scripts\python.exe -c "from pipeline.runner import run_pipeline; run_pipeline(steps=('cleanup','csv','html','sales','bq','rag'))"
```

## Ordner für lokale Daten (gitignored)

```
data/inbox/umfragen/          # Umfrage-CSVs
data/inbox/weihnachtsbesuche/ # Feldbesuche
data/Tickets_neu/             # Hotline Text/html
Rohe_Sales_Daten.xlsx         # Sales-Rohdaten (Root)
.env                          # Tokens
gcp-key.json                  # GCP Service Account
```

## Team-Onboarding

1. Repo klonen
2. `venv` + `pip install -r requirements.txt`
3. `.env` aus `.env.example`, `gcp-key.json` vom Admin
4. Rohdaten **nicht** aus Git — lokal oder geteilter sicherer Speicher (SharePoint/GCS)
5. `Start_Portal.bat` oder `streamlit run "PM Evidence AI Portal\Home.py"`

## Optional: geplante Updates

Windows Task Scheduler oder manuell wöchentlich:

- Pipeline laufen lassen, wenn neue CSVs/HTML in Inbox liegen
- **Kein** automatisches `git commit` von Daten
