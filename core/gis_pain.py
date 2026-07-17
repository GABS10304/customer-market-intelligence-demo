"""GIS Pain Points — Themen nur aus riwaGisData-Hotline (ohne TERA/otsBau-Mix)."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from functools import lru_cache
from typing import Any

import pandas as pd

from config import DEMO_MODE, TICKETS_HTML_DIR
from core.demo_scope import BUILD_BEREICH, GIS_BEREICH, GIS_PLATFORM_LABEL, TERA_WIN_BEREICH
from core.intent_sources import iter_freetext_rows
from core.product_mapping import module_display_name
from core.tera_pain import is_tera_focused_question
from core.tera_scope import is_tera_hotline_cluster
from workspace.compare import THEME_KEYWORDS, themes_in_text

_DEMO_GIS_FOCUS = (
    r"\b(geosuite|geo[\s-]?suite|demo[\s-]?gis)\b",
    r"\bgeosuite\s?data\b",
    r"\b(landkreis[\s-]?gis|gis[\s-]?center)\b",
    r"\bgeoclient\b",
)

GIS_FOCUS_PATTERNS = _DEMO_GIS_FOCUS if DEMO_MODE else (
    r"\b(gis[\s-]?zentrum|riwa[\s-]?gis|riwagis)\b",
    r"\briwagisdata\b",
    r"\b(landkreis[\s-]?gis|gis[\s-]?center)\b",
    # PM-Kontext: „bei RIWA“ = riwaGisData-Portfolio (nicht TERA/teraWinData)
    r"\b(bei\s+)?riwa\b",
)

GIS_PAIN_PATTERNS = (
    r"\b(pain[\s-]?points?|painpoints?|schmerz|problem|hauptproblem|engpass|schwachstelle|bedürfnis)\b",
    r"\b(häufigste|top|haupt|wichtigste|\d+)\b.*\b(problem|themen|pain|bedürfnisse|pain[\s-]?points?)\b",
    r"\b(kontextsensitive[\s-]?hilfe|kontext[\s-]?hilfe|hot[\s-]?spot|hotspot)\b",
    r"\bhotline[\s-]?(aufkommen|volumen|last|anrufe)\b.*\b(reduzieren|senken|verringern|vermeiden)\b",
    r"\b(reduzieren|senken|verringern|vermeiden)\b.*\bhotline[\s-]?(aufkommen|volumen|last|anrufe)\b",
)

GIS_CONTEXT_HELP_PATTERNS = (
    r"\b(kontextsensitive[\s-]?hilfe|kontext[\s-]?hilfe)\b",
    r"\bhotline[\s-]?(aufkommen|volumen|last|anrufe)\b.*\b(reduzieren|senken|verringern|vermeiden)\b",
    r"\b(reduzieren|senken|verringern|vermeiden)\b.*\bhotline[\s-]?(aufkommen|volumen|last|anrufe)\b",
)

GIS_MODULE_VIEW_PATTERNS = (
    r"\b(modul|module|cluster)\b.*\b(priorit|top|wichtig|impact|ticket|umsetzung)\b",
    r"\b(priorit[äa]t|priorisier\w*|cluster|product[\s-]?signal|impact[\s-]?proxy)\b",
    r"\b(zweite[\s-]?sicht|sicht[\s-]?2|umsetzung)\b",
    r"\b(hotline.*modul|modul.*hotline)\b",
)

GIS_MODULE_ONLY_PATTERNS = (
    r"\b(nur|ausschließlich|only|lediglich)\b.*\b(modul|module|cluster|product[\s-]?signal)\b",
    r"\b(modul|cluster|product[\s-]?signal)\b.*\b(ohne\s+themen|ohne\s+pain|ohne\s+thema)\b",
    r"\b(nur|ausschließlich)\b.*\b(sicht[\s-]?2|modul[\s-]?priorit)\b",
)

# Deterministische Kontext-Hilfe-Vorschläge pro Thema (Template, kein LLM-Raten)
CONTEXT_HELP_SUGGESTIONS: dict[str, str] = {
    "Verbindung": (
        "Verbindungs-Assistent: Diagnose-Checkliste (Netz/Server/Offline), "
        "Self-Service vor Hotline-Anruf."
    ),
    "Login": (
        "Login-Hilfe im Kontext: Passwort-Reset, Single-User-Hinweise, "
        "Benutzerverwaltung-Schritte direkt am Anmeldedialog."
    ),
    "Export": (
        "Export-Wizard: Formatwahl, häufige Fehlercodes, Beispiel-Export "
        "mit Vorschau vor dem Anruf."
    ),
    "Import": (
        "Import-Assistent: Dateiformat-Check, Validierungsfehler erklären, "
        "Schritt-für-Schritt-Upload im Modul."
    ),
    "Installation": (
        "Setup-Hilfe: Installationsvoraussetzungen, Installer-Log-Auswertung, "
        "Neuinstallation vs. Update unterscheiden."
    ),
}


def is_gis_hotline_cluster(cluster: str) -> bool:
    """True nur für riwaGisData-Cluster — ohne teraWinData/otsBauData."""
    raw = (cluster or "").strip()
    if not raw or is_tera_hotline_cluster(raw):
        return False
    lower = raw.lower()
    prefix = f"{GIS_BEREICH}\\"
    return lower.startswith(prefix.lower()) or lower == GIS_BEREICH.lower()


def _has_explicit_gis_scope(lower: str) -> bool:
    """Expliziter riwaGisData-Scope (RIWA, riwaGis, GIS-Zentrum, …)."""
    return any(re.search(p, lower) for p in GIS_FOCUS_PATTERNS)


def is_gis_focused_question(question: str) -> bool:
    """True wenn die Frage sich auf RIWA GIS-Zentrum / riwaGisData bezieht (nicht TERA)."""
    lower = (question or "").lower()
    strong = _has_explicit_gis_scope(lower)
    weak_gis = bool(re.search(r"\bgis\b", lower))
    if not (strong or weak_gis):
        return False
    if is_tera_focused_question(question):
        return strong
    return True


def is_gis_context_help_question(question: str) -> bool:
    """True bei Fragen zu kontextsensitiver Hilfe / Hotline-Reduktion im RIWA-GIS-Scope."""
    if not is_gis_focused_question(question):
        return False
    lower = (question or "").lower()
    return any(re.search(p, lower) for p in GIS_CONTEXT_HELP_PATTERNS)


def is_gis_pain_question(question: str) -> bool:
    """True wenn nach Pain Points / Hotspots im GIS-Zentrum gefragt wird."""
    if not is_gis_focused_question(question):
        return False
    lower = (question or "").lower()
    if any(re.search(p, lower) for p in GIS_PAIN_PATTERNS):
        return True
    return is_gis_context_help_question(question)


def is_gis_module_view_requested(question: str) -> bool:
    """True bei expliziter Nachfrage nach Modul-/Cluster-Priorisierung oder Product Signals."""
    if not is_gis_focused_question(question):
        return False
    lower = (question or "").lower()
    return any(re.search(p, lower) for p in GIS_MODULE_VIEW_PATTERNS)


def wants_gis_module_only_view(question: str) -> bool:
    """True wenn nur Sicht 2 (Module+Impact) gewünscht — ohne thematische Top-5."""
    if not is_gis_focused_question(question):
        return False
    lower = (question or "").lower()
    if any(re.search(p, lower) for p in GIS_MODULE_ONLY_PATTERNS):
        return True
    if is_gis_module_view_requested(question) and not is_gis_pain_question(question):
        return True
    return False


def should_include_gis_thematic_view(question: str) -> bool:
    """Sicht 1 — Themen-Ranking (verbindliche Top-5)."""
    if not is_gis_focused_question(question):
        return False
    if wants_gis_module_only_view(question):
        return False
    return is_gis_pain_question(question) or is_gis_context_help_question(question)


def should_include_gis_module_view(question: str) -> bool:
    """Sicht 2 — Cluster + Product Signals Impact."""
    if not is_gis_focused_question(question):
        return False
    if is_gis_pain_question(question) or is_gis_context_help_question(question):
        return True
    return is_gis_module_view_requested(question)


def _cluster_leaf(cluster: str) -> str:
    raw = (cluster or "").strip()
    return raw.rsplit("\\", 1)[-1].strip()


def _gis_source_label() -> str:
    if DEMO_MODE:
        return "Demo-Fixture (synthetische Hotline-Daten)"
    return "Hotline HTML / riwaGisData (live)"


def _gis_iter_flags() -> tuple[bool, bool]:
    """include_html, include_csv — DEMO ohne HTML-Dateien nutzt tickets_backlog.csv."""
    if not DEMO_MODE:
        return True, False
    has_html = TICKETS_HTML_DIR.exists() and any(TICKETS_HTML_DIR.rglob("*.html"))
    if has_html:
        return True, True
    return False, True


def collect_gis_hotline_tickets() -> Counter[str]:
    """Roh-Cluster-Häufigkeit nur für GIS-Hotline-Scope."""
    counts: Counter[str] = Counter()
    include_html, include_csv = _gis_iter_flags()
    for row in iter_freetext_rows(include_html=include_html, include_csv=include_csv):
        cluster = row.cluster or ""
        if not is_gis_hotline_cluster(cluster):
            continue
        counts[cluster] += 1
    return counts


@lru_cache(maxsize=1)
def gis_hotline_detail() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for cluster, tickets in collect_gis_hotline_tickets().items():
        rows.append(
            {
                "cluster": cluster,
                "cluster_leaf": _cluster_leaf(cluster),
                "tickets": int(tickets),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["cluster", "cluster_leaf", "tickets"])
    return pd.DataFrame(rows).sort_values("tickets", ascending=False)


def _gis_freetext_samples(*, per_cluster: int = 2) -> dict[str, list[str]]:
    by_cluster: dict[str, list[str]] = defaultdict(list)
    include_html, include_csv = _gis_iter_flags()
    for row in iter_freetext_rows(include_html=include_html, include_csv=include_csv):
        cluster = row.cluster or ""
        if not is_gis_hotline_cluster(cluster):
            continue
        if len(by_cluster[cluster]) >= per_cluster:
            continue
        text = (row.freitext or "").strip()
        if text:
            by_cluster[cluster].append(text)
    return by_cluster


@lru_cache(maxsize=1)
def collect_gis_theme_scores() -> dict[str, dict[str, Any]]:
    """Themen-Scores nur aus riwaGisData-Hotline-Clustern."""
    detail = gis_hotline_detail()
    scores: dict[str, dict[str, Any]] = {
        theme: {"score": 0, "clusters": [], "modules": set()}
        for theme in THEME_KEYWORDS
    }
    if detail.empty:
        return scores

    samples = _gis_freetext_samples()

    for row in detail.itertuples():
        cluster = str(row.cluster)
        if not is_gis_hotline_cluster(cluster):
            continue
        count = int(row.tickets)
        matched = themes_in_text(cluster, from_cluster=True)
        if count >= 5 and not matched:
            for sample in samples.get(cluster, []):
                matched |= themes_in_text(sample, from_cluster=False)
        if not matched:
            continue

        module_leaf = str(getattr(row, "cluster_leaf", "") or _cluster_leaf(cluster))
        entry = f"{cluster} ({count}×)"
        for theme in matched:
            scores[theme]["score"] += count
            if entry not in scores[theme]["clusters"]:
                scores[theme]["clusters"].append(entry)
            if module_leaf:
                scores[theme]["modules"].add(module_leaf)

    return scores


def clear_gis_pain_cache() -> None:
    collect_gis_theme_scores.cache_clear()
    gis_hotline_detail.cache_clear()


def _top_gis_clusters(*, top_n: int = 5) -> list[tuple[str, int, str]]:
    """Top-GIS-Cluster nach Ticket-Häufigkeit (nur riwaGisData)."""
    detail = gis_hotline_detail()
    rows: list[tuple[str, int, str]] = []
    for row in detail.itertuples():
        cluster = str(row.cluster)
        if not is_gis_hotline_cluster(cluster):
            continue
        rows.append(
            (
                cluster,
                int(row.tickets),
                str(getattr(row, "cluster_leaf", "") or _cluster_leaf(cluster)),
            )
        )
    rows.sort(key=lambda item: item[1], reverse=True)
    return rows[:top_n]


def _gis_mapping_ids_from_hotline() -> set[str]:
    """mapping_ids mit mindestens einem riwaGisData-Hotline-Cluster."""
    from core.product_mapping import resolve_cluster_mapping

    ids: set[str] = set()
    for cluster in collect_gis_hotline_tickets():
        entry = resolve_cluster_mapping(cluster)
        if entry and entry.id:
            ids.add(entry.id)
    return ids


def _filter_gis_product_signals(signals_df: pd.DataFrame) -> pd.DataFrame:
    """Product Signals auf riwaGisData-Module filtern — ohne TERA."""
    from core.product_lines import classify_product_line
    from core.product_mapping import mapping_entry_by_id
    from core.tera_scope import is_tera_hotline_cluster

    if signals_df.empty:
        return signals_df

    gis_ids = _gis_mapping_ids_from_hotline()
    rows: list[dict[str, Any]] = []
    for row in signals_df.itertuples(index=False):
        modul = str(getattr(row, "modul", "") or "")
        mapping_id = str(getattr(row, "mapping_id", "") or "")
        if classify_product_line(modul) == "TERA":
            continue
        entry = mapping_entry_by_id(mapping_id) if mapping_id else None
        if entry and entry.ticket_clusters:
            if all(is_tera_hotline_cluster(c) for c in entry.ticket_clusters):
                continue
            has_gis = any(is_gis_hotline_cluster(c) for c in entry.ticket_clusters)
            if not has_gis and mapping_id not in gis_ids:
                continue
        elif mapping_id and mapping_id not in gis_ids:
            continue
        rows.append(row._asdict())

    if not rows:
        return pd.DataFrame(columns=signals_df.columns)
    return pd.DataFrame(rows)


def format_gis_module_prioritization_markdown(
    signals_df: pd.DataFrame | None = None,
    *,
    top_n: int = 8,
    cluster_top_n: int = 8,
) -> str:
    """Sicht 2 — Top-GIS-Cluster + Product-Signals-Impact (ohne TERA)."""
    lines = [
        f"### Sicht 2 — Module & Impact ({GIS_BEREICH} + Product Signals)",
        f"**Scope:** Hotline-Cluster `{GIS_BEREICH}\\…` und gemappte GIS-Module — **ohne ERP** (`{TERA_WIN_BEREICH}`).",
        "**Ranking Cluster:** Hotline-Ticket-Häufigkeit (deterministisch). "
        "**Ranking Impact:** `impact_proxy` aus Product Signals (Reach × Signale, ohne ERP).",
        "**Hinweis:** Product-Signals-`hotline_tickets` und Cluster-Ticketzahlen können abweichen "
        "(z. B. GeoClient-Modul in Signals vs. `GeoClient - Installation` im Cluster).",
    ]

    clusters = _top_gis_clusters(top_n=cluster_top_n)
    if clusters:
        lines.append(f"\n**Top-Cluster {GIS_BEREICH}** — Quelle: {_gis_source_label()}:")
        for index, (cluster, tickets, module_leaf) in enumerate(clusters, start=1):
            label = module_display_name(cluster) if module_leaf else module_leaf
            lines.append(f"{index}. **{label}** — {tickets} Tickets (`{cluster}`)")
    else:
        lines.append("\n- (keine GIS-Hotline-Cluster)")

    if signals_df is None:
        from config import DELIMITER
        from core.product_signals import DEFAULT_OUTPUT, aggregate_product_signals

        if DEFAULT_OUTPUT.exists():
            try:
                signals_df = pd.read_csv(DEFAULT_OUTPUT, sep=DELIMITER, encoding="utf-8-sig")
            except (OSError, pd.errors.ParserError):
                signals_df = aggregate_product_signals()
        else:
            signals_df = aggregate_product_signals()

    gis_signals = _filter_gis_product_signals(signals_df)
    if gis_signals.empty:
        lines.append(
            "\n**Product Signals CSV (ohne ERP)** — Impact-Ranking:"
        )
        lines.append("- (keine GIS-gemappten Product Signals)")
        return "\n".join(lines)

    sort_col = "impact_proxy" if "impact_proxy" in gis_signals.columns else "signale_gesamt"
    view = gis_signals.sort_values(sort_col, ascending=False).head(top_n)
    lines.append(
        "\n**Product Signals CSV (ohne ERP)** — Impact-Ranking:"
    )
    lines.append("| Modul | Impact | Hotline | Reach | NPS |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for row in view.itertuples():
        hotline = int(getattr(row, "hotline_tickets", 0) or 0)
        reach = int(getattr(row, "reach_nutzer", 0) or 0)
        impact = getattr(row, "impact_proxy", "—")
        nps = getattr(row, "umfrage_avg_nps", None)
        nps_s = f"{float(nps):.1f}" if pd.notna(nps) else "—"
        lines.append(f"| **{row.modul}** | {impact} | {hotline} | {reach} | {nps_s} |")

    return "\n".join(lines)


def format_gis_combined_evidence_markdown(
    *,
    question: str = "",
    signals_df: pd.DataFrame | None = None,
    top_n: int = 5,
    module_top_n: int = 8,
) -> str:
    """Kombiniert Sicht 1 (Themen) und/oder Sicht 2 (Module+Impact) je nach Frage."""
    parts: list[str] = []
    include_thematic = should_include_gis_thematic_view(question)
    include_module = should_include_gis_module_view(question)

    if include_thematic and include_module:
        parts.append(
            f"### GIS Evidenz — Zwei Sichten (nur {GIS_BEREICH})\n"
            f"**Hinweis:** Sicht 1 = Hotline-Themen aus `core/gis_pain.py` ({GIS_BEREICH}-Cluster, "
            "deterministisch) — **nicht** Snapshot oder Quellen-Overlap. "
            f"Sicht 2 = Top-Cluster {GIS_BEREICH} + Product Signals CSV (ohne ERP). "
            "Themen-Scores sind nicht disjunkt — keine %-Anteil-Aussagen / Reduktionen schätzen."
        )

    if include_thematic:
        thematic = (
            format_gis_context_help_markdown(
                top_n=top_n,
                question=question,
                include_secondary_clusters=not include_module,
            )
            if is_gis_context_help_question(question)
            else format_gis_pain_markdown(
                top_n=top_n,
                question=question,
                include_secondary_clusters=not include_module,
            )
        )
        if include_thematic and include_module:
            thematic = thematic.replace(
                "### GIS Pain Points",
                "### Sicht 1 — Themen (Hotline → Kontext-Hilfe)"
                if "Kontextsensitive" in thematic
                else "### Sicht 1 — Themen (Hotline-Pain-Points)",
                1,
            )
        parts.append(thematic)

    if include_module:
        parts.append(
            format_gis_module_prioritization_markdown(
                signals_df,
                top_n=module_top_n,
            )
        )

    return "\n\n".join(parts) if parts else format_gis_pain_markdown(top_n=top_n, question=question)


def format_gis_pain_markdown(
    *, top_n: int = 5, question: str = "", include_secondary_clusters: bool = True
) -> str:
    """Deterministischer Evidenzblock — Top-Pain-Points nur aus RIWA GIS-Hotline."""
    scores = collect_gis_theme_scores()
    ranked = sorted(
        [(theme, data) for theme, data in scores.items() if int(data.get("score") or 0) > 0],
        key=lambda item: int(item[1]["score"]),
        reverse=True,
    )

    lines = [
        f"### GIS Pain Points (nur {GIS_BEREICH})",
        f"**Scope:** Nur Hotline-Cluster `{GIS_BEREICH}\\…` — **ohne** `{TERA_WIN_BEREICH}`/`{BUILD_BEREICH}` "
        "und **ohne** Umfrage-Quellen-Overlap.",
        "**Ranking:** Hotline-Ticket-Häufigkeit pro Thema (deterministisch, verbindlich).",
        f"**Quelle:** {_gis_source_label()} — kein Snapshot-Overlap.",
        "**Hinweis:** Themen-Scores sind nicht disjunkt — keine %-Anteil-Aussagen / Reduktionen schätzen.",
    ]

    if not ranked:
        clusters = _top_gis_clusters(top_n=top_n)
        if not clusters:
            lines.append("- (keine GIS-Hotline-Daten für Themen-Analyse)")
            return "\n".join(lines)
        lines.append("\n**Top-Cluster nach Hotline-Tickets (kein Themen-Match im Cluster-Namen):**")
        for index, (cluster, tickets, module_leaf) in enumerate(clusters, start=1):
            lines.append(f"{index}. **{cluster}** — {tickets} Tickets (Modul: {module_leaf})")
        return "\n".join(lines)

    show = ranked[:top_n]
    for index, (theme, data) in enumerate(show, start=1):
        cluster_hint = ", ".join(data["clusters"][:2]) or "—"
        modules = ", ".join(sorted(data["modules"])[:4]) if data["modules"] else "—"
        lines.append(
            f"{index}. **{theme}** — {int(data['score'])} Hotline-Tickets "
            f"(GIS-Module: {modules}; z. B. {cluster_hint})"
        )

    if len(ranked) > top_n:
        lines.append(f"- … {len(ranked) - top_n} weitere GIS-Themen mit Signal")

    if include_secondary_clusters:
        top_clusters = _top_gis_clusters(top_n=3)
        if top_clusters:
            lines.append("\n**Top-GIS-Cluster (GeoSuite Demo):**")
            for cluster, tickets, module_leaf in top_clusters:
                lines.append(f"- **{module_leaf}** — {tickets} Tickets (`{cluster}`)")

    return "\n".join(lines)


def format_gis_context_help_markdown(
    *, top_n: int = 5, question: str = "", include_secondary_clusters: bool = True
) -> str:
    """GIS-Pain-Block inkl. kontextsensitiver Hilfe-Vorschläge (deterministisch)."""
    scores = collect_gis_theme_scores()
    ranked = sorted(
        [(theme, data) for theme, data in scores.items() if int(data.get("score") or 0) > 0],
        key=lambda item: int(item[1]["score"]),
        reverse=True,
    )

    lines = [
        f"### GIS Pain Points — Kontextsensitive Hilfe (nur {GIS_BEREICH})",
        f"**Scope:** Nur Hotline-Cluster `{GIS_BEREICH}\\…` — **ohne** `{TERA_WIN_BEREICH}`/`{BUILD_BEREICH}`, "
        "**ohne** Portfolio-Snapshot-Overlap, **ohne** Umfrage/Feldbesuch als Hotline-Ersatz.",
        "**Zweck:** Top-Themen für In-App-Hilfe priorisieren, um Hotline-Aufkommen zu reduzieren.",
        "**Ranking:** Hotline-Ticket-Häufigkeit pro Thema (verbindlich für Top-5).",
        f"**Quelle:** {_gis_source_label()} — kein Snapshot-Overlap.",
        "**Hinweis:** Themen-Scores sind nicht disjunkt — keine %-Anteil-Aussagen / Reduktionen schätzen.",
    ]

    if not ranked:
        clusters = _top_gis_clusters(top_n=top_n)
        if not clusters:
            lines.append("- (keine GIS-Hotline-Daten für Themen-Analyse)")
            return "\n".join(lines)
        lines.append("\n**Top-Cluster nach Hotline-Tickets:**")
        for index, (cluster, tickets, module_leaf) in enumerate(clusters, start=1):
            lines.append(f"{index}. **{module_leaf}** — {tickets} Tickets (`{cluster}`)")
        return "\n".join(lines)

    show = ranked[:top_n]
    lines.append("\n**Top-Themen (Hotline → Kontext-Hilfe):**")
    for index, (theme, data) in enumerate(show, start=1):
        suggestion = CONTEXT_HELP_SUGGESTIONS.get(
            theme,
            f"Modul-spezifische Hilfe zu «{theme}» direkt im betroffenen Dialog anbieten.",
        )
        cluster_hint = ", ".join(data["clusters"][:2]) or "—"
        modules = ", ".join(sorted(data["modules"])[:4]) if data["modules"] else "—"
        lines.append(
            f"{index}. **{theme}** — {int(data['score'])} Hotline-Tickets "
            f"(Module: {modules}; z. B. {cluster_hint})"
        )
        lines.append(f"   → Kontext-Hilfe: {suggestion}")

    if include_secondary_clusters:
        top_clusters = _top_gis_clusters(top_n=5)
        if top_clusters:
            lines.append("\n**Sekundär — Top-GIS-Cluster nach Ticket-Häufigkeit:**")
            for cluster, tickets, module_leaf in top_clusters:
                lines.append(f"- **{module_leaf}** — {tickets} Tickets (`{cluster}`)")

    return "\n".join(lines)
