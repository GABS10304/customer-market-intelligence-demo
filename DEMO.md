# Öffentliche Demo (GitHub)

Portfolio-tauglicher Demo-Modus **ohne BigQuery, Graylog, Ollama oder echte Kundendaten**.

## Schnellstart

```powershell
# Aus dem Projektroot
copy .env.example .env
# In .env: DEMO_MODE=true

pip install -r requirements.txt
streamlit run "PM Evidence AI Portal\Home.py"
```

Oder mit Batch-Datei:

```powershell
Start_Demo_Portal.bat
```

## Was funktioniert im Demo-Modus

| Feature | Status |
|---------|--------|
| Übersicht & Kacheln | ✅ aus `data/demo/workspace_snapshot.json` |
| Theme-Compare | ✅ |
| Produktlinien / Priorität | ✅ |
| GIS-Pain-Blöcke | ✅ aus Demo-HTML/CSVs |
| Strategie-Wizard (regelbasiert) | ✅ |
| TERA/ERP-Tab | ❌ ausgeblendet (fiktive Lizenzen nur in Fixtures) |
| Pipeline | ⚠️ schreibt in `data/demo/` (optional) |
| BigQuery-Upload | ❌ deaktiviert |
| RAG / Ollama-Chat | ❌ nicht nötig |

## Konfiguration

In `.env`:

```env
DEMO_MODE=true
```

## Demo-Daten

Alle Fixtures liegen unter **`data/demo/`** — siehe [`data/demo/README.md`](data/demo/README.md).

**Fiktive Produktnamen:** GeoSuite, GeoClient, ERP Suite Demo, MapApp Demo — keine RIWA/RGZ/TERA/KartenApp-Bezeichner in Fixtures.

Gemeinden: `Musterstadt`, `Demo-LK`, `Mustergemeinde`, `Demo-Zweckverband`.

## Tests

```powershell
$env:DEMO_MODE="true"
python -m pytest tests/test_demo_mode.py -q
```
