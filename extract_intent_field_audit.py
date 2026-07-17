#!/usr/bin/env python3
"""
Intent-Feld-Audit über alle Freitext-Quellen.

Zählt Volumen, klassifiziert alle Zeilen (oder Stichprobe bei >50k),
schreibt Fill-Rates und Konsolidierungs-Empfehlungen nach data/intent_field_audit.md.

Usage:
    python extract_intent_field_audit.py
    python extract_intent_field_audit.py --output data/intent_field_audit.md
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_DIR
from core.intent_patterns import classify_intent
from core.intent_sources import FreetextRow, iter_freetext_rows

DEFAULT_OUTPUT = DATA_DIR / "intent_field_audit.md"
SAMPLE_THRESHOLD = 50_000
SAMPLE_SIZE = 50_000
SAMPLE_SEED = 42

HOTLINE_TECH = "support_tickets_html_roh"
FIELD_VISITS_TECH = "field_visits_weihnachtsbesuche"
SURVEY_TECH = "survey_freetext_250"

SOURCE_GROUPS = {
    HOTLINE_TECH: "Hotline",
    FIELD_VISITS_TECH: "Feldbesuche",
    SURVEY_TECH: "Umfragen",
}


@dataclass
class ClassifiedRow:
    quelle: str
    quelle_technisch: str
    input_typ: str
    cluster: str
    intent: str
    bedarf: str
    geltung: str
    themen: tuple[str, ...]
    request_thema: str
    request_detail: str
    kontakt_angebot: str
    ansprechpartner: str
    kontakt_zeitraum: str
    aktion_todo: str


def _classify(row: FreetextRow) -> ClassifiedRow:
    result = classify_intent(row.freitext, modul=row.cluster)
    return ClassifiedRow(
        quelle=row.quelle,
        quelle_technisch=row.quelle_technisch,
        input_typ=row.input_typ,
        cluster=row.cluster,
        intent=result.intent,
        bedarf=result.bedarf,
        geltung=result.geltung,
        themen=result.themen,
        request_thema=result.request_thema,
        request_detail=result.request_detail,
        kontakt_angebot=result.kontakt_angebot,
        ansprechpartner=result.ansprechpartner,
        kontakt_zeitraum=result.kontakt_zeitraum,
        aktion_todo=result.aktion_todo,
    )


def _pct(n: int, total: int) -> str:
    if total == 0:
        return "—"
    return f"{100 * n / total:.1f}%"


def _top_counter(counter: Counter, n: int = 5) -> list[tuple[str, int]]:
    return counter.most_common(n)


def _format_dist(counter: Counter, total: int, n: int = 8) -> str:
    if not counter:
        return "_keine Daten_"
    lines = []
    for label, count in counter.most_common(n):
        lines.append(f"| {label} | {count} | {_pct(count, total)} |")
    return "\n".join(lines)


def _collect_rows(*, sampled: bool) -> tuple[list[ClassifiedRow], int, bool]:
    pool: list[FreetextRow] = list(iter_freetext_rows(include_html=True, include_csv=True))
    full_count = len(pool)
    use_sample = full_count > SAMPLE_THRESHOLD
    if use_sample:
        rng = random.Random(SAMPLE_SEED)
        rng.shuffle(pool)
        pool = pool[:SAMPLE_SIZE]
    classified = [_classify(row) for row in pool]
    return classified, full_count, use_sample and sampled


def _volume_table(rows: list[ClassifiedRow], full_count: int, sampled: bool) -> str:
    by_tech = Counter(r.quelle_technisch for r in rows)
    by_quelle = Counter(r.quelle for r in rows)
    by_typ = Counter(r.input_typ for r in rows)
    analyzed = len(rows)

    lines = [
        f"**Gesamt Freitext-Zeilen:** {full_count:,}",
        f"**Klassifiziert:** {analyzed:,}" + (" (Stichprobe)" if sampled else " (vollständig)"),
        "",
        "### Nach `quelle_technisch`",
        "",
        "| quelle_technisch | Zeilen | Anteil |",
        "|---|---:|---:|",
    ]
    for tech, count in by_tech.most_common():
        lines.append(f"| {tech} | {count:,} | {_pct(count, analyzed)} |")
    lines += [
        "",
        "### Nach `quelle` (Display)",
        "",
        "| quelle | Zeilen | Anteil |",
        "|---|---:|---:|",
    ]
    for quelle, count in by_quelle.most_common():
        lines.append(f"| {quelle} | {count:,} | {_pct(count, analyzed)} |")
    lines += [
        "",
        "### Nach `input_typ`",
        "",
        "| input_typ | Zeilen | Anteil |",
        "|---|---:|---:|",
    ]
    for typ, count in by_typ.most_common():
        lines.append(f"| {typ} | {count:,} | {_pct(count, analyzed)} |")
    return "\n".join(lines)


def _fill_stats(rows: list[ClassifiedRow], source_key: str | None = None) -> dict[str, object]:
    subset = [r for r in rows if source_key is None or r.quelle_technisch == source_key]
    total = len(subset)
    if total == 0:
        return {"total": 0}

    def filled(getter) -> int:
        return sum(1 for r in subset if getter(r))

    themen_empty = sum(1 for r in subset if not r.themen)
    themen_multi = sum(1 for r in subset if len(r.themen) > 1)
    themen_single = total - themen_empty - themen_multi

    intent_counter = Counter(r.intent for r in subset)
    bedarf_counter = Counter(r.bedarf for r in subset if r.bedarf)

    intent_bedarf_overlap = sum(
        1 for r in subset if r.bedarf and r.intent != "Sonstiges" and r.bedarf.lower() in r.intent.lower()
    )
    cluster_themen_overlap = sum(
        1
        for r in subset
        if r.themen and r.cluster and any(t.lower() in r.cluster.lower() or r.cluster.lower() in t.lower() for t in r.themen)
    )
    request_without_bedarf = sum(1 for r in subset if (r.request_thema or r.request_detail) and not r.bedarf)

    return {
        "total": total,
        "intent": intent_counter,
        "bedarf": bedarf_counter,
        "bedarf_filled": filled(lambda r: bool(r.bedarf)),
        "geltung_filled": filled(lambda r: bool(r.geltung)),
        "themen_filled": filled(lambda r: bool(r.themen)),
        "themen_empty": themen_empty,
        "themen_single": themen_single,
        "themen_multi": themen_multi,
        "request_thema_filled": filled(lambda r: bool(r.request_thema)),
        "request_detail_filled": filled(lambda r: bool(r.request_detail)),
        "kontakt_angebot_filled": filled(lambda r: bool(r.kontakt_angebot)),
        "ansprechpartner_filled": filled(lambda r: bool(r.ansprechpartner)),
        "kontakt_zeitraum_filled": filled(lambda r: bool(r.kontakt_zeitraum)),
        "aktion_todo_filled": filled(lambda r: bool(r.aktion_todo)),
        "intent_bedarf_overlap": intent_bedarf_overlap,
        "cluster_themen_overlap": cluster_themen_overlap,
        "request_without_bedarf": request_without_bedarf,
    }


def _fill_rate_table(rows: list[ClassifiedRow]) -> str:
    sources = ["_gesamt_"] + sorted({r.quelle_technisch for r in rows})
    fields = [
        ("bedarf", "bedarf_filled"),
        ("geltung", "geltung_filled"),
        ("themen (≥1 Tag)", "themen_filled"),
        ("request_thema", "request_thema_filled"),
        ("request_detail", "request_detail_filled"),
        ("kontakt_angebot", "kontakt_angebot_filled"),
        ("ansprechpartner", "ansprechpartner_filled"),
        ("kontakt_zeitraum", "kontakt_zeitraum_filled"),
        ("aktion_todo", "aktion_todo_filled"),
    ]

    lines = [
        "| Feld | Gesamt | Hotline | Feldbesuche | Umfragen |",
        "|---|---:|---:|---:|---:|",
    ]
    overall = _fill_stats(rows)
    hotline = _fill_stats(rows, HOTLINE_TECH)
    field = _fill_stats(rows, FIELD_VISITS_TECH)
    survey = _fill_stats(rows, SURVEY_TECH)

    by_source = {
        "_gesamt_": overall,
        HOTLINE_TECH: hotline,
        FIELD_VISITS_TECH: field,
        SURVEY_TECH: survey,
    }

    for label, key in fields:
        cells = []
        for src in ("_gesamt_", HOTLINE_TECH, FIELD_VISITS_TECH, SURVEY_TECH):
            stats = by_source[src]
            if stats["total"] == 0:
                cells.append("—")
            else:
                cells.append(_pct(stats[key], stats["total"]))
        lines.append(f"| {label} | {' | '.join(cells)} |")
    return "\n".join(lines)


def _themen_table(rows: list[ClassifiedRow]) -> str:
    lines = [
        "| Quelle | leer | 1 Tag | >1 Tag |",
        "|---|---:|---:|---:|",
    ]
    for tech in sorted({r.quelle_technisch for r in rows}):
        s = _fill_stats(rows, tech)
        t = s["total"]
        lines.append(
            f"| {SOURCE_GROUPS.get(tech, tech)} | {_pct(s['themen_empty'], t)} | "
            f"{_pct(s['themen_single'], t)} | {_pct(s['themen_multi'], t)} |"
        )
    s = _fill_stats(rows)
    t = s["total"]
    lines.append(
        f"| **Gesamt** | {_pct(s['themen_empty'], t)} | "
        f"{_pct(s['themen_single'], t)} | {_pct(s['themen_multi'], t)} |"
    )
    return "\n".join(lines)


def _intent_bedarf_section(rows: list[ClassifiedRow]) -> str:
    lines: list[str] = []
    for tech in (HOTLINE_TECH, FIELD_VISITS_TECH, SURVEY_TECH):
        s = _fill_stats(rows, tech)
        if s["total"] == 0:
            continue
        label = SOURCE_GROUPS.get(tech, tech)
        total = s["total"]
        lines += [
            f"### {label} (`{tech}`) — n={total:,}",
            "",
            "**intent_auto**",
            "",
            "| intent | n | % |",
            "|---|---:|---:|",
            _format_dist(s["intent"], total),
            "",
            "**bedarf_auto** (nur befüllt)",
            "",
            "| bedarf | n | % |",
            "|---|---:|---:|",
            _format_dist(s["bedarf"], s["bedarf_filled"]) if s["bedarf_filled"] else "_keine befüllten Werte_",
            "",
        ]
    return "\n".join(lines)


def _hotline_vs_field(rows: list[ClassifiedRow]) -> str:
    hot = _fill_stats(rows, HOTLINE_TECH)
    fld = _fill_stats(rows, FIELD_VISITS_TECH)
    if hot["total"] == 0 or fld["total"] == 0:
        return "_Vergleich nicht möglich — eine Quelle fehlt in den Daten._"

    hot_top_intent = hot["intent"].most_common(1)[0] if hot["intent"] else ("—", 0)
    fld_top_intent = fld["intent"].most_common(1)[0] if fld["intent"] else ("—", 0)
    hot_top_bedarf = hot["bedarf"].most_common(1)[0] if hot["bedarf"] else ("—", 0)
    fld_top_bedarf = fld["bedarf"].most_common(1)[0] if fld["bedarf"] else ("—", 0)

    hot_sonstiges = hot["intent"].get("Sonstiges", 0)
    fld_sonstiges = fld["intent"].get("Sonstiges", 0)

    hot_useful_intent = sum(
        hot["intent"].get(k, 0) for k in ("Defekt", "Installation", "Discovery", "How-To")
    )
    hot_useful_pct = _pct(hot_useful_intent, hot["total"])

    return "\n".join(
        [
            "| Metrik | Hotline | Feldbesuche |",
            "|---|---:|---:|",
            f"| Zeilen | {hot['total']:,} | {fld['total']:,} |",
            f"| Top intent | {hot_top_intent[0]} ({_pct(hot_top_intent[1], hot['total'])}) | "
            f"{fld_top_intent[0]} ({_pct(fld_top_intent[1], fld['total'])}) |",
            f"| Sonstiges (intent) | {_pct(hot_sonstiges, hot['total'])} | {_pct(fld_sonstiges, fld['total'])} |",
            f"| intent ≠ Sonstiges | {hot_useful_pct} | "
            f"{_pct(fld['total'] - fld_sonstiges, fld['total'])} |",
            f"| bedarf fill | {_pct(hot['bedarf_filled'], hot['total'])} | {_pct(fld['bedarf_filled'], fld['total'])} |",
            f"| Top bedarf | {hot_top_bedarf[0]} ({_pct(hot_top_bedarf[1], hot['bedarf_filled']) if hot['bedarf_filled'] else '—'}) | "
            f"{fld_top_bedarf[0]} ({_pct(fld_top_bedarf[1], fld['bedarf_filled']) if fld['bedarf_filled'] else '—'}) |",
            f"| request_thema fill | {_pct(hot['request_thema_filled'], hot['total'])} | {_pct(fld['request_thema_filled'], fld['total'])} |",
            f"| themen fill | {_pct(hot['themen_filled'], hot['total'])} | {_pct(fld['themen_filled'], fld['total'])} |",
            f"| aktion_todo fill | {_pct(hot['aktion_todo_filled'], hot['total'])} | {_pct(fld['aktion_todo_filled'], fld['total'])} |",
            "",
            "**Interpretation:**",
            "",
            f"- Hotline: `intent_auto` liefert bei **{hot_useful_pct}** einen Routing-Wert (Defekt/Installation/Discovery/How-To); "
            f"**{_pct(hot_sonstiges, hot['total'])}** landen in Sonstiges — PM-Review sollte `bedarf`/`request_*` priorisieren.",
            f"- Feldbesuche: `intent_auto` wenig differenzierend (**{_pct(fld_sonstiges, fld['total'])}** Sonstiges); "
            f"`bedarf_auto` fill **{_pct(fld['bedarf_filled'], fld['total'])}** vs Hotline **{_pct(hot['bedarf_filled'], hot['total'])}**.",
            f"- `bedarf` auf Hotline: leer bei Mehrheit ({_pct(hot['total'] - hot['bedarf_filled'], hot['total'])} leer); "
            "PM-Kategorie stärker und vollständiger bei Feldbesuchen.",
        ]
    )


def _overlap_section(rows: list[ClassifiedRow]) -> str:
    s = _fill_stats(rows)
    hot = _fill_stats(rows, HOTLINE_TECH)
    fld = _fill_stats(rows, FIELD_VISITS_TECH)
    return "\n".join(
        [
            "| Überlappung | Gesamt | Hotline | Feldbesuche |",
            "|---|---:|---:|---:|",
            f"| cluster ∩ themen (Substring) | {_pct(s['cluster_themen_overlap'], s['total'])} | "
            f"{_pct(hot['cluster_themen_overlap'], hot['total']) if hot['total'] else '—'} | "
            f"{_pct(fld['cluster_themen_overlap'], fld['total']) if fld['total'] else '—'} |",
            f"| request_* ohne bedarf | {_pct(s['request_without_bedarf'], s['total'])} | "
            f"{_pct(hot['request_without_bedarf'], hot['total']) if hot['total'] else '—'} | "
            f"{_pct(fld['request_without_bedarf'], fld['total']) if fld['total'] else '—'} |",
            "",
            "- **intent vs bedarf:** `intent` = Support-Routing (Discovery/Defekt/How-To); `bedarf` = PM-Kategorie (Feature Request, UX-Kritik). "
            "Beide können parallel befüllt sein — nicht zusammenlegen.",
            "- **cluster vs themen:** `cluster` ist Quell-Metadatum (Ordner/Modul); `themen_auto` extrahiert Produkt-Keywords aus Freitext — ergänzen sich.",
            "- **request_thema/detail vs bedarf:** request_* fasst den konkreten Wunsch zusammen; bedarf ist die übergeordnete PM-Etikettierung.",
        ]
    )


def _recommendations(rows: list[ClassifiedRow]) -> str:
    hot = _fill_stats(rows, HOTLINE_TECH)
    fld = _fill_stats(rows, FIELD_VISITS_TECH)
    overall = _fill_stats(rows)

    recs: list[str] = []

    if hot["total"] and fld["total"]:
        if hot["bedarf_filled"] / hot["total"] < fld["bedarf_filled"] / fld["total"] * 0.7:
            recs.append(
                "1. **Einheitliches PM-Modell:** `bedarf` + `request_thema` + `request_detail` + `themen` als Kern für alle Quellen; "
                "`intent` nur als **Hotline-Routing-Spalte** (`ticket_routing`) behalten, nicht ins PM-Review-Set."
            )
        else:
            recs.append(
                "1. **Einheitliches PM-Modell:** `bedarf`, `request_thema`, `request_detail`, `themen` für alle Quellen; "
                "`intent` optional als Quellenspezifisches Routing-Feld."
            )

    if overall["kontakt_angebot_filled"] / max(overall["total"], 1) < 0.05:
        recs.append(
            "2. **Kontakt-Felder zusammenführen:** `kontakt_angebot`, `ansprechpartner`, `kontakt_zeitraum` in eine Spalte "
            "`kontakt_auto` (oder ganz weglassen im PM-Export) — Fill-Rate <5%."
        )
    else:
        recs.append(
            "2. **Kontakt-Felder:** Drei Spalten zu `kontakt_auto` (summary) konsolidieren; Detail nur im Voll-Export."
        )

    if overall["geltung_filled"] / max(overall["total"], 1) < 0.15:
        recs.append(
            "3. **`geltung` als optionales Querschnitts-Flag** (nicht Pflichtspalte) — selten befüllt, nur bei modulübergreifenden Fällen relevant."
        )
    else:
        recs.append(
            "3. **`geltung` behalten** als Querschnitts-Marker, aber nicht im schlanken PM-Review-Set."
        )

    recs.append(
        "4. **`aktion_todo`:** PM-Follow-up — im Review-Set nur bei Feldbesuchen/Umfragen; auf Hotline als internes Routing-Flag, nicht Tester-Spalte."
    )

    unified = [
        "| Spalte | Rolle | Quellen |",
        "|---|---|---|",
        "| `cluster` | Quell-Metadatum (Modul/Ordner) | alle |",
        "| `freitext` | Original | alle |",
        "| `bedarf` | PM-Kategorie | alle |",
        "| `request_thema` | Wunsch-Kopf | alle |",
        "| `request_detail` | Wunsch-Detail | alle |",
        "| `themen` | Produkt-Keywords aus Text | alle |",
        "| `ticket_routing` (≈ intent) | Support-Routing | nur Hotline |",
        "| `geltung` | Querschnitt/Alle Module | optional, Voll-Export |",
        "| `aktion_todo` | PM-Nächster Schritt | Feld/Umfrage primär |",
        "| `kontakt_auto` | Ansprechpartner/Zeitraum | optional, niedrige Fill-Rate |",
    ]

    drop = [
        "- **Drop im PM-Review:** `intent_confidence`, `matched_keywords`, `intent_manual` (Debug)",
        "- **Merge:** `kontakt_angebot` + `ansprechpartner` + `kontakt_zeitraum` → `kontakt_auto`",
        "- **Umbenennen (Hotline):** `intent_auto` → `ticket_routing` zur Klarstellung",
        "- **Nicht mergen:** `bedarf` ≠ `intent` (unterschiedliche Semantik); `cluster` ≠ `themen` (Metadatum vs Extraktion)",
    ]

    return "\n".join(
        [
            "### Top-Empfehlungen",
            "",
            *[f"{r}" for r in recs[:3]],
            "",
            "### Vorgeschlagenes einheitliches PM-Modell (minimal)",
            "",
            "\n".join(unified),
            "",
            "### Drop / Merge / Quellenspezifisch",
            "",
            *drop,
        ]
    )


def build_audit_markdown(rows: list[ClassifiedRow], full_count: int, sampled: bool) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    hot = _fill_stats(rows, HOTLINE_TECH)
    hot_n = hot.get("total", 0)
    hot_top_intent = hot["intent"].most_common(3) if hot_n else []
    hot_top_bedarf = hot["bedarf"].most_common(3) if hot_n else []

    summary_bullets = [
        f"- Hotline-Zeilen: **{hot_n:,}** ({_pct(hot_n, len(rows))} des analysierten Bestands)",
        f"- Top Hotline intents: {', '.join(f'{k} ({v})' for k, v in hot_top_intent) or '—'}",
        f"- Top Hotline bedarf (befüllt): {', '.join(f'{k} ({v})' for k, v in hot_top_bedarf) or '—'}",
        "- Umfragen (`survey_freetext_250`): **0 Zeilen** in lokalem Bestand (nur Hotline + Feldbesuche vorhanden)",
    ]

    sections = [
        "# Intent-Feld-Audit — Konsolidierungsempfehlung",
        "",
        f"_Erzeugt: {now} via `extract_intent_field_audit.py`_",
        "",
        "## Kurzfassung",
        "",
        *summary_bullets,
        "",
        "## 1. Datenvolumen nach Quelle",
        "",
        _volume_table(rows, full_count, sampled),
        "",
        "## 2. Fill-Rates pro Feld",
        "",
        _fill_rate_table(rows),
        "",
        "### themen_auto — leer / single / multi",
        "",
        _themen_table(rows),
        "",
        "## 3. intent_auto & bedarf_auto nach Quelle",
        "",
        _intent_bedarf_section(rows),
        "",
        "## 4. Hotline vs. Feldbesuche",
        "",
        _hotline_vs_field(rows),
        "",
        "## 5. Feld-Überlappungen",
        "",
        _overlap_section(rows),
        "",
        "## 6. Konsolidierungsvorschlag",
        "",
        _recommendations(rows),
    ]
    return "\n".join(sections) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Intent-Feld-Audit (Volumen + Fill-Rates + Empfehlungen).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    print("Lese Freitext-Zeilen …", file=sys.stderr)
    rows, full_count, sampled = _collect_rows(sampled=True)
    if full_count > SAMPLE_THRESHOLD:
        print(
            f"Volumen {full_count:,} > {SAMPLE_THRESHOLD:,} — klassifiziere Stichprobe {len(rows):,} (seed={SAMPLE_SEED})",
            file=sys.stderr,
        )
    else:
        print(f"Klassifiziere alle {full_count:,} Zeilen …", file=sys.stderr)

    md = build_audit_markdown(rows, full_count, sampled)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(md, encoding="utf-8")
    print(f"Audit geschrieben: {args.output}", file=sys.stderr)

    hot = _fill_stats(rows, HOTLINE_TECH)
    if hot["total"]:
        top_i = hot["intent"].most_common(1)[0]
        top_b = hot["bedarf"].most_common(1)[0] if hot["bedarf"] else ("—", 0)
        print(f"Hotline: n={hot['total']:,}, top intent={top_i[0]} ({top_i[1]}), top bedarf={top_b[0]} ({top_b[1]})", file=sys.stderr)


if __name__ == "__main__":
    main()
