# Product Signal Matrix

Planungsgrundlage für PM Evidence — vier Linsen (Say · Feel · Do · Pay), Quellen, Lücken, Kompensation.

_Entwurf: 2026-07-14 · noch keine Pipeline-Implementierung_

---

## 1. Vier Linsen (Product Science)

| Linse | Frage | Status |
|-------|--------|--------|
| **Say** | Was sagen Kunden (explizit)? | Stark |
| **Feel** | Wie zufrieden / loyal? | Mittel (Umfrage Scores) |
| **Do** | Was tun sie / wo hängen sie? | Schwach (kein Usage-Tracking) |
| **Pay** | Welcher Kunden-/Produktwert? | Stark (ERP) |

Ziel-Join: alle Signale an **`mapping_id`** aus `product_module_mapping.json` (Produkt-Achse).

---

## 2. Matrix: Quelle × Linse × PM-Felder

| Quelle | Volumen (lokal) | Say | Feel | Do | Pay | Native Felder (verlässlich) | PM-Felder (Ziel) |
|--------|----------------:|-----|------|-----|-----|----------------------------|------------------|
| **Hotline** | ~1.281 | ●●● | ○ | ●● | ●● | `Ordner/Modul` (Cluster), Freitext, Hotline-Routing | `modul` ← Cluster, `ticket_routing` ← intent, Häufigkeit |
| **Umfrage** | 543 (208 Freitext) | ●● | ●●● | ○ | ●● | 14 Skalen, NPS, Landkreis, Freitext optional | `nps`, `score_*`, `landkreis` → ERP; Freitext → `bedarf` |
| **Feldbesuche** | ~48 | ●●● | ○ | ○ | ● | Modul/App/Verfahren, Freitext Kritik | `modul`, `bedarf`, `request_*` |
| **ERP** | ~1.597 Kunden | — | — | — | ●●● | Kunde, Artikel, Umsatz | `mapping_id`, Summe Umsatz, Portfolio |
| **Modul-Ranking** | 121 Module | — | ●● | — | ●● | `Modulname`, **Kunden**, Umsatz, ABC | `kunden` = Reach (Orgs/Lizenzen, **kein MAU**) |

Legende: ●●● stark · ●● nutzbar · ● Proxy · ○ fehlt

---

## 3. Einheitliches Ziel-Schema (minimal, quellenbewusst)

| Feld | Hotline | Umfrage | Feldbesuch | ERP |
|------|---------|---------|------------|-----|
| `quelle` | ✓ | ✓ | ✓ | (join) |
| `modul` / `mapping_id` | Cluster → Mapping | Landkreis → Kunde → Artikel → Mapping | Cluster → Mapping | Artikel → Mapping |
| `ticket_routing` | ✓ (intent) | — | — | — |
| `bedarf` | optional / später | Freitext only | ✓ primär | — |
| `nps` / `score_*` | — | ✓ primär | — | — |
| `freitext` | ✓ | optional | ✓ | — |
| `prioritaet_hinweis` | Ticket-Count × Umsatz | Low NPS/Score × Umsatz | manuell / Gold | Umsatz |

**Nicht vereinheitlichen:** `themen_auto` überall — Modul kommt aus Cluster (Hotline/Feldbesuch) oder ERP (Umfrage).

---

## 4. Bekannte Lücken & Kompensation (ohne neues Analytics)

| Lücke | Risiko | Kompensation (jetzt) | Später (Software) |
|-------|--------|----------------------|-------------------|
| Kein Usage / MAU (Do) | Laute Wünsche ≠ Impact | **`Kunden` pro Modul** aus `module_ranking.csv` (Reach-Proxy, Stichtag 2026-01-14); How-To/Discovery-Rate | Echte User-Telemetry (nicht verfügbar) |
| Selection bias | Nur Beschwerer | Umfrage-Scores für alle 543; Detractor auch ohne Freitext | Panel / stratified sampling |
| Kein Trend | Release-Regression unsichtbar | Quartals-Ticket-Aggregation; Umfrage-Wellen vergleichen | Zeitreihen-Dashboard |
| Keine Rolle (Persona) | LRA ≠ Bauhof | Hotline-Cluster als Proxy; Freitext-Rolle extrahieren | Persona-Feld in Quellen |
| Feldbesuch n klein | Nicht repräsentativ | Als „validiert / deep dive“ labeln | Mehr Besuche, gleiche Matrix |
| Landkreis→Kunde | ~58 % auto-match | Lookup-Tabelle pflegen | `survey_customer_lookup.json` |

---

## 5. Priorisierungs-Logik (V1 — deterministisch)

Pro `mapping_id`:

```
signal_strength =
  normalize(ticket_count)     × w_hotline
+ normalize(low_nps_count)    × w_survey_feel
+ normalize(detractor_scores) × w_survey_feel
+ normalize(bedarf_count)     × w_field_say
```

Gewichtung × **Summe_Umsatz** (ERP) → `prioritaet_score` (analog `core/product_priority.py`).

Freitext/Bedarf liefert **Epic-Titel & Beispiele**, nicht allein die Rangfolge.

---

## 6. Nächste Build-Schritte (Software)

| Step | Was | Output |
|------|-----|--------|
| **A** | Diese Matrix (✓) | `data/product_signal_matrix.md` |
| **B** | Hotline-only View: Cluster + intent + Count + ERP | `data/signal_by_module_hotline.csv` |
| **C** | Umfrage: Scores + NPS + Landkreis→ERP (Lookup) | `data/survey_enriched.csv` |
| **D** | Feldbesuche: bedarf + Cluster (bestehend) | in gleiches Schema mappen |
| **E** | Join auf `mapping_id` → eine Tabelle | `data/product_signals_unified.csv` |
| **F** | Portal-Tab „Product Signals“ (Read-only) | `Home.py` |

**Reihenfolge empfohlen:** B → C → D → E → F. Kein LLM für Step B–E.

---

## 7. Abgrenzung Step 1 (Freitext-Classifier)

Der regelbasierte Classifier (`core/intent_patterns.py`) bleibt **primär für Feldbesuche** (bedarf-Gold-Set).

Hotline: **Cluster + intent** — Classifier-Bedarf optional.  
Umfrage: **Scores + ERP** primär; Freitext → einfache Kategorie-Map (4 Umfrage-Kategorien → bedarf).

---

## 8. Erfolgskriterien

- [ ] Hotline-Stichprobe 50: Cluster + intent von PM als „verlässlich“ bestätigt
- [ ] Umfrage: ≥80 % Landkreise im Lookup (manuell ergänzt)
- [ ] Pro Top-10 `mapping_id`: mindestens 2 Linsen mit Signal (Say oder Feel + Pay)
- [ ] Feldbesuche: 45 Gold-Zeilen bedarf stabil
- [ ] Ein Report: „Modul X — Tickets, NPS, Umsatz, Zitate“ ohne manuelles Excel

---

_Bei Änderungen: Matrix zuerst, dann Pipeline — nicht umgekehrt._
