# Intent-Feld-Audit — Konsolidierungsempfehlung (Demo)

_Synthetische Demo-Zahlen für das öffentliche Portfolio — keine Produktionsdaten._

_Erzeugt: 2026-07-17 via `extract_intent_field_audit.py` (Demo-Export)_

## Kurzfassung

- Hotline-Zeilen: **87** (87.0% des analysierten Bestands)
- Top Hotline intents: Sonstiges (61), Defekt (16), Installation (8)
- Top Hotline bedarf (befüllt): Feature Request (16), Bugmeldung (12), Service-Kritik (5)
- Umfragen (`survey_freetext_demo`): **0 Zeilen** im Demo-Bestand (nur Hotline + Feldbesuche vorhanden)

## 1. Datenvolumen nach Quelle

**Gesamt Freitext-Zeilen:** 100
**Klassifiziert:** 100 (vollständig)

### Nach `quelle_technisch`

| quelle_technisch | Zeilen | Anteil |
|---|---:|---:|
| support_tickets_demo | 87 | 87.0% |
| field_visits_demo | 13 | 13.0% |

### Nach `quelle` (Display)

| quelle | Zeilen | Anteil |
|---|---:|---:|
| Support-Tickets (Demo) | 87 | 87.0% |
| Feldbesuche (Demo) | 13 | 13.0% |

### Nach `input_typ`

| input_typ | Zeilen | Anteil |
|---|---:|---:|
| html_roh | 87 | 87.0% |
| csv | 13 | 13.0% |

## 2. Fill-Rates pro Feld

| Feld | Gesamt | Hotline | Feldbesuche | Umfragen |
|---|---:|---:|---:|---:|
| bedarf | 42.0% | 40.0% | 100.0% | — |
| geltung | 2.0% | 1.0% | 23.0% | — |
| themen (≥1 Tag) | 60.0% | 58.0% | 98.0% | — |
| request_thema | 29.0% | 27.0% | 88.0% | — |
| request_detail | 12.0% | 9.0% | 85.0% | — |
| kontakt_angebot | 4.0% | 4.0% | 2.0% | — |
| ansprechpartner | 4.0% | 4.0% | 2.0% | — |
| kontakt_zeitraum | 0.0% | 0.0% | 2.0% | — |
| aktion_todo | 1.0% | 0.0% | 5.0% | — |

### themen_auto — leer / single / multi

| Quelle | leer | 1 Tag | >1 Tag |
|---|---:|---:|---:|
| Feldbesuche | 2.0% | 58.0% | 40.0% |
| Hotline | 42.0% | 45.0% | 13.0% |
| **Gesamt** | 41.0% | 46.0% | 13.0% |

## 3. intent_auto & bedarf_auto nach Quelle

### Hotline (`support_tickets_demo`) — n=87

**intent_auto**

| intent | n | % |
|---|---:|---:|
| Sonstiges | 61 | 70.1% |
| Defekt | 16 | 18.4% |
| Installation | 8 | 9.2% |
| Discovery | 2 | 2.3% |

**bedarf_auto** (nur befüllt)

| bedarf | n | % |
|---|---:|---:|
| Feature Request | 16 | 48.5% |
| Bugmeldung | 12 | 36.4% |
| Service-Kritik | 5 | 15.2% |

### Feldbesuche (`field_visits_demo`) — n=13

**intent_auto**

| intent | n | % |
|---|---:|---:|
| Sonstiges | 11 | 84.6% |
| Defekt | 2 | 15.4% |

**bedarf_auto** (nur befüllt)

| bedarf | n | % |
|---|---:|---:|
| Feature Request | 8 | 61.5% |
| UX-Kritik | 2 | 15.4% |
| Service-Kritik | 2 | 15.4% |
| Produkt-Lücke | 1 | 7.7% |

## 4. Hotline vs. Feldbesuche

| Metrik | Hotline | Feldbesuche |
|---|---:|---:|
| Zeilen | 87 | 13 |
| Top intent | Sonstiges (70.1%) | Sonstiges (84.6%) |
| Sonstiges (intent) | 70.1% | 84.6% |
| intent ≠ Sonstiges | 29.9% | 15.4% |
| bedarf fill | 40.0% | 100.0% |
| Top bedarf | Feature Request (48.5%) | Feature Request (61.5%) |
| request_thema fill | 27.0% | 88.0% |
| themen fill | 58.0% | 98.0% |
| aktion_todo fill | 0.0% | 5.0% |

**Interpretation:**

- Hotline: `intent_auto` liefert bei **29.9%** einen Routing-Wert; **70.1%** landen in Sonstiges — PM-Review sollte `bedarf`/`request_*` priorisieren.
- Feldbesuche: `intent_auto` wenig differenzierend (**84.6%** Sonstiges); `bedarf_auto` fill **100.0%** vs Hotline **40.0%**.
- `bedarf` auf Hotline: leer bei Mehrheit (60.0% leer); PM-Kategorie stärker und vollständiger bei Feldbesuchen.

## 5. Feld-Überlappungen

| Überlappung | Gesamt | Hotline | Feldbesuche |
|---|---:|---:|---:|
| cluster ∩ themen (Substring) | 41.0% | 39.0% | 94.0% |
| request_* ohne bedarf | 5.0% | 5.0% | 0.0% |

- **intent vs bedarf:** `intent` = Support-Routing (Discovery/Defekt/How-To); `bedarf` = PM-Kategorie (Feature Request, UX-Kritik). Beide können parallel befüllt sein — nicht zusammenlegen.
- **cluster vs themen:** `cluster` ist Quell-Metadatum (Ordner/Modul); `themen_auto` extrahiert Produkt-Keywords aus Freitext — ergänzen sich.
- **request_thema/detail vs bedarf:** request_* fasst den konkreten Wunsch zusammen; bedarf ist die übergeordnete PM-Etikettierung.

## 6. Konsolidierungsvorschlag

### Top-Empfehlungen

1. **Einheitliches PM-Modell:** `bedarf` + `request_thema` + `request_detail` + `themen` als Kern für alle Quellen; `intent` nur als **Hotline-Routing-Spalte** (`ticket_routing`) behalten, nicht ins PM-Review-Set.
2. **Kontakt-Felder zusammenführen:** `kontakt_angebot`, `ansprechpartner`, `kontakt_zeitraum` in eine Spalte `kontakt_auto` (oder ganz weglassen im PM-Export) — Fill-Rate <5%.
3. **`geltung` als optionales Querschnitts-Flag** (nicht Pflichtspalte) — selten befüllt, nur bei modulübergreifenden Fällen relevant.

### Vorgeschlagenes einheitliches PM-Modell (minimal)

| Spalte | Rolle | Quellen |
|---|---|---|
| `cluster` | Quell-Metadatum (Modul/Ordner) | alle |
| `freitext` | Original | alle |
| `bedarf` | PM-Kategorie | alle |
| `request_thema` | Wunsch-Kopf | alle |
| `request_detail` | Wunsch-Detail | alle |
| `themen` | Produkt-Keywords aus Text | alle |
| `ticket_routing` (≈ intent) | Support-Routing | nur Hotline |
| `geltung` | Querschnitt/Alle Module | optional, Voll-Export |
| `aktion_todo` | PM-Nächster Schritt | Feld/Umfrage primär |
| `kontakt_auto` | Ansprechpartner/Zeitraum | optional, niedrige Fill-Rate |

### Drop / Merge / Quellenspezifisch

- **Drop im PM-Review:** `intent_confidence`, `matched_keywords`, `intent_manual` (Debug)
- **Merge:** `kontakt_angebot` + `ansprechpartner` + `kontakt_zeitraum` → `kontakt_auto`
- **Umbenennen (Hotline):** `intent_auto` → `ticket_routing` zur Klarstellung
- **Nicht mergen:** `bedarf` ≠ `intent` (unterschiedliche Semantik); `cluster` ≠ `themen` (Metadatum vs Extraktion)
