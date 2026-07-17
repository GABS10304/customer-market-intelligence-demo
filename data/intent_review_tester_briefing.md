# Intent-Review — Tester-Briefing (3 × 3 Fälle)

**Datei:** `data/intent_review_sample.csv` (Excel, Trennzeichen `;`)  
**Zuordnung:** `data/intent_review_tester_assignments.csv`  
**Seed:** 42, Limit 50 → 45 Zeilen S001–S045 (reproduzierbare Stichprobe)

---

## Was ihr prüft (30 Min.)

Automatische **Strukturierung von Feldbesuchs-Notizen** — noch **kein LLM**, nur Regeln.

Fokus: **Freitext-Interpretation** — passt die automatische Extraktion zum Originaltext?

### Spalten in der Haupt-CSV (PM-Review)

| Spalte | Frage |
|--------|--------|
| **`cluster`** + **`freitext`** | Originalkontext lesen |
| **`bedarf_auto`** | Stimmt die PM-Kategorie? (Feature Request, UX-Kritik, Service-Kritik, Update-Kritik, Bugmeldung, …) |
| **`request_thema_auto` / `request_detail_auto`** | Ist der Wunsch/Kritikpunkt richtig extrahiert? |
| **`themen_auto`** | Passendes Modul/Produkt? |

### Ausfüllen in der Haupt-CSV

In **`intent_review_sample.csv`** für **eure 3 Zeilen** (`sample_id`):

- **`challenge_ok`:** `ja` / `nein` / `teilweise`
- **`challenge_notiz`:** kurz — was fehlt oder falsch ist

### Nur bei Debug / Vollexport (`--full`)

Folgende Spalten sind in der schlanken CSV **nicht** enthalten; bei Bedarf kann Gabriel eine Vollversion erzeugen:

- `intent_auto`, `geltung_auto`, `aktion_todo_auto`
- `kontakt_angebot_auto`, `ansprechpartner_auto`, `kontakt_zeitraum_auto`
- `intent_confidence`, `matched_keywords`, `intent_manual`
- Metadaten: `bereich`, `quelle_technisch`, `input_typ`, `ticket_id`, `ticket_datei`, `csv_datei`, `csv_pfad`, `html_pfad`, `zeilen_index`

---

## Zuordnung

### Tester 1

| ID | Cluster | Kurztext |
|----|---------|----------|
| **S035** | eAkte zu KIC | Stapelverarbeitung / Serienbrief in ER, BauAV, FH … |
| **S001** | Basisentwicklung | Alle Module — individuelle Berichte aus RIWA |
| **S010** | Geonotizen | Nachträglich Dokumente/Bilder ergänzen |

### Tester 2

| ID | Cluster | Kurztext |
|----|---------|----------|
| **S045** | Basisentwicklung | Ebenen-Darstellung selbst editierbar (Alle Module) |
| **S040** | Versorgungsleitungen | Private Sparten darstellen vs. Modul zu komplex |
| **S034** | Verkehr | Modulumstellung / Programmierung unübersichtlich |

### Tester 3

| ID | Cluster | Kurztext |
|----|---------|----------|
| **S003** | BVL Schnittstelle Prosoz | Fehlende Daten Entwurfsverfassen / Bauherr |
| **S039** | BVL Schnittstelle BOLL | BOLL-Schnittstelle macht wiederholt Probleme |
| **S020** | VM/Wasser | VM-Daten → Edit-Modul / Schieber-Sachdatenmaske |

---

## So geht ihr vor

1. CSV öffnen → Zeile anhand **`sample_id`** suchen (z. B. S035).
2. **`cluster`** + **`freitext`** lesen (Original).
3. Auto-Spalten (`bedarf_auto`, `request_thema_auto`, `request_detail_auto`, `themen_auto`) mit eurem Verständnis vergleichen.
4. **`challenge_ok`** + **`challenge_notiz`** eintragen.
5. Datei speichern und an Gabriel zurückgeben (oder nur die 3 Zeilen als Screenshot/Kommentar).

**Gutes Feedback:** «bedarf sollte Service-Kritik sein», «request_detail fehlt: …», «Thema eher BauAV als …»  
**Weniger hilfreich:** Rechtschreibung im Freitext korrigieren.

---

## Rückgabe

Bitte bis **[Datum eintragen]** — eine gemeinsame CSV reicht (jeder trägt seine 3 Zeilen ein).

Bei Fragen: Gabriel
