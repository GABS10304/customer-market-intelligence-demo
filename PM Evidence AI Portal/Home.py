"""
Customer & Market Intelligence Workspace — einheitliche UI (V2.1).
Fast-boot · Tabs · Strategie-Wizard · Initiative Challenger
"""

from __future__ import annotations

import io
import os
import sys
from contextlib import redirect_stdout

import pandas as pd
import streamlit as st

_PORTAL = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_PORTAL)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config import (  # noqa: E402
    DEMO_MODE,
    DEMO_EXCLUDED_SOURCE_KEYS,
    HTML_DIR,
    INBOX_FIELD_VISITS_DIR,
    INBOX_SURVEYS_DIR,
    WORKSPACE_VERSION,
    demo_fixtures_ready,
    setup_gcp_credentials,
)

_PORTAL_TITLE = "Customer & Market Intelligence" + (" DEMO" if DEMO_MODE else "")


def _default_source_keys() -> list[str]:
    keys = list(BUILTIN_PROFILES.keys())
    if DEMO_MODE:
        return [k for k in keys if k not in DEMO_EXCLUDED_SOURCE_KEYS]
    return keys
from core.bq_evidence import load_rag_meta  # noqa: E402
from core.llm import synthesis_available, synthesis_setup_hint  # noqa: E402
from core.runtime import get_runtime_status, rag_freshness  # noqa: E402
from core.product_lines import ALL_PRODUCT_LINES, PRODUCT_LINE_HINTS  # noqa: E402
from core.product_mapping import load_mapping_entries
from core.intent_patterns import ticket_routing_intent  # noqa: E402
from core.sales_evidence import SALES_TECHNICAL_NAME, top_by_kundentyp  # noqa: E402
from core.signal_inventory import signal_overview  # noqa: E402
from core.time_display import format_berlin  # noqa: E402
from initiative_challenger import analyze_initiative  # noqa: E402
from workspace.catalog import init_builtin_sources, list_catalog_sources  # noqa: E402
from workspace.snapshot import (  # noqa: E402
    SnapshotLoadResult,
    invalidate_workspace_snapshot,
    load_workspace_snapshot,
    rebuild_workspace_snapshot,
)
from workspace.sources.profiles import BUILTIN_PROFILES  # noqa: E402
from workspace.strategy_wizard import (  # noqa: E402
    build_strategy_brief,
    strategy_brief_to_markdown,
    synthesize_strategy_document,
)

st.set_page_config(
    page_title=_PORTAL_TITLE,
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

if DEMO_MODE:
    _demo_ok, _demo_missing = demo_fixtures_ready()
    if not _demo_ok:
        st.error(
            "**Demo-Modus:** Fehlende Fixtures in `data/demo/`: "
            + ", ".join(f"`{p}`" for p in _demo_missing)
            + ". Bitte Branch `demo/public` auschecken oder `git checkout demo/public -- data/demo/` ausführen.",
            icon="🛑",
        )
        st.stop()
    st.info(
        "**Demo-Modus** — alle Zahlen und Produktnamen sind synthetisch (GeoSuite, GeoClient, MapApp Demo). "
        "Keine Vertrags-, Umsatz- oder TERA-Lizenzdaten.",
        icon="ℹ️",
    )

# --- Session defaults ---
if "selected_sources" not in st.session_state:
    st.session_state.selected_sources = _default_source_keys()
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_selected_sources" not in st.session_state:
    st.session_state.last_selected_sources = list(st.session_state.selected_sources)
if "last_snapshot_fp" not in st.session_state:
    st.session_state.last_snapshot_fp = ""
if "strategy_md" not in st.session_state:
    st.session_state.strategy_md = ""
if "catalog_ready" not in st.session_state:
    init_builtin_sources()
    st.session_state.catalog_ready = True


@st.cache_data(ttl=45, show_spinner=False)
def _cached_runtime():
    return get_runtime_status(check_ollama=False)


@st.cache_resource(show_spinner=False)
def _cached_snapshot(force_token: str, _snapshot_api: str = "intent_module_rows_v1") -> SnapshotLoadResult:
    """force_token: 'refresh' triggert BQ-Rebuild. _snapshot_api bustet Cache bei Snapshot-API-Änderungen."""
    if force_token == "refresh":
        snap = rebuild_workspace_snapshot()
        return SnapshotLoadResult(snap, False, "", "bigquery")
    return load_workspace_snapshot(force_rebuild=False)


def _refresh_evidence() -> None:
    invalidate_workspace_snapshot()
    _cached_snapshot.clear()
    st.session_state.snapshot_force = "refresh"


if "snapshot_force" not in st.session_state:
    st.session_state.snapshot_force = "disk"

snap_result = _cached_snapshot(st.session_state.snapshot_force)
if st.session_state.snapshot_force == "refresh":
    st.session_state.snapshot_force = "disk"

ws = snap_result.snapshot
runtime = _cached_runtime()
can_synthesize = synthesis_available()
gcp_ok = setup_gcp_credentials() is not None


def _overview_source_totals(ws, selected: list[str], *, top_n: int = 30) -> pd.DataFrame:
    """Summiert Top-Cluster je aktiver Sidebar-Quelle (Snapshot, vergleichbar mit Produktlinien)."""
    rows: list[dict[str, int | str]] = []
    for name in selected:
        profile = BUILTIN_PROFILES.get(name)
        label = profile.display_name if profile else name
        if name == SALES_TECHNICAL_NAME:
            df = ws.sales_penetration(top_n)
            total = int(pd.to_numeric(df.get("anzahl"), errors="coerce").fillna(0).sum()) if not df.empty else 0
        else:
            cmp_df = ws.compare_sources([name], top_n=top_n)
            total = int(pd.to_numeric(cmp_df.get("anzahl"), errors="coerce").fillna(0).sum()) if not cmp_df.empty else 0
        if total > 0:
            rows.append({"quelle": label, "anzahl": total})
    if not rows:
        return pd.DataFrame(columns=["quelle", "anzahl"])
    return pd.DataFrame(rows).sort_values("anzahl", ascending=False)


def _banner_messages() -> list[str]:
    msgs = [
        m
        for m in runtime.messages
        if "Cloud-Synthese" not in m
        and "IONOS_TOKEN" not in m
        and "Chat-Synthese" not in m
        and not (runtime.mode != "full" and m.startswith("RAG veraltet:"))
    ]
    if snap_result.stale and snap_result.stale_reason:
        msgs.insert(0, snap_result.stale_reason)
    return msgs


# ===================== SIDEBAR =====================
with st.sidebar:
    st.header("📂 Quellen & Pipeline")
    st.caption(f"**{runtime.mode_label}** · Snapshot: {snap_result.source}")

    banner_msgs = _banner_messages()
    if banner_msgs:
        st.warning(" · ".join(banner_msgs[:2]), icon="⚠️")

    c1, c2 = st.columns(2)
    with c1:
        if gcp_ok:
            st.success("BigQuery", icon="✅")
        else:
            st.error("BigQuery", icon="❌")
    with c2:
        if can_synthesize:
            st.success("Synthese", icon="✅")
        else:
            st.warning("Synthese", icon="⚠️")

    st.caption(f"Evidenz: {format_berlin(ws.built_at)}")

    if st.button("⬇ Evidenz aus BQ laden", use_container_width=True):
        with st.spinner("BigQuery…"):
            _refresh_evidence()
        st.rerun()

    st.divider()

    selected: list[str] = []
    for src in list_catalog_sources():
        if src.get("status") == "pending_verify":
            continue
        if src.get("status") != "active":
            continue
        name = src["technical_name"]
        if st.checkbox(
            src.get("display_name", name),
            value=name in st.session_state.selected_sources,
            key=f"src_{name}",
        ):
            selected.append(name)

    st.session_state.selected_sources = selected or _default_source_keys()
    active = st.session_state.selected_sources

    with st.expander("📁 Daten ablegen", expanded=False):
        drop_paths = (
            f"""
- **Tickets (HTML):** `{HTML_DIR}`
- **Umfragen (CSV ;):** `{INBOX_SURVEYS_DIR}`
- **Feldbesuche (CSV ;):** `{INBOX_FIELD_VISITS_DIR}`
            """
        )
        if not DEMO_MODE:
            drop_paths += """
- **Sales (Excel):** `Rohe_Sales_Daten.xlsx` (Root, gitignored)
- **TERA Lizenzen (CSV ;):** `data/tera_installations.csv` oder `tera.csv` (Root)
            """
        st.markdown(drop_paths)

    if st.button("🔄 Pipeline starten", use_container_width=True):
        from pipeline.runner import run_pipeline

        with st.spinner("Pipeline…"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_pipeline(
                    steps=("cleanup", "csv", "html", "sales", "bq", "rag"),
                    log=lambda m: buf.write(m + "\n"),
                )
            st.session_state.last_pipeline_log = buf.getvalue()
        _refresh_evidence()
        st.success("Fertig.")
        st.rerun()

    if st.session_state.get("last_pipeline_log"):
        with st.expander("Pipeline-Log"):
            st.code(st.session_state.last_pipeline_log, language="text")


# ===================== HEADER =====================
st.title(f"🧠 {_PORTAL_TITLE}")
st.caption(
    f"V{WORKSPACE_VERSION} · {runtime.mode_label} · "
    f"{len(active)} Quelle(n) aktiv · Boot: {snap_result.source}"
)

_tab_labels = ["📊 Übersicht", "📈 Product Signals", "🎯 KI-Strategie", "🔍 Initiative prüfen"]
if not DEMO_MODE:
    _tab_labels.insert(2, "🏢 TERA")
if not DEMO_MODE:
    tab_overview, tab_signals, tab_tera, tab_strategy, tab_challenger = st.tabs(_tab_labels)
else:
    tab_overview, tab_signals, tab_strategy, tab_challenger = st.tabs(_tab_labels)

# ===================== TAB: ÜBERSICHT =====================
with tab_overview:
    from workspace.assistant_loader import load_assistant_ui

    _assistant = load_assistant_ui()

    st.subheader("Product Intelligence Assistent — alle Evidenzquellen")
    _assistant.render_assistant_panel(
        active,
        ws,
        can_synthesize=can_synthesize,
        snapshot_stale=snap_result.stale,
        snapshot_stale_reason=snap_result.stale_reason,
        compact=False,
        key_prefix="home",
    )
    st.divider()

    import plotly.express as px

    st.subheader("Quellen & Signale")
    overview = signal_overview()
    reach = overview.reach

    stimmen_df = pd.DataFrame(
        [{"Quelle": lane.label, "Anzahl": lane.count} for lane in overview.stimmen if lane.count > 0]
    )
    lens_df = pd.DataFrame(
        [
            {"Linse": "Stimmen (Say)", "Anzahl": overview.stimmen_total},
            {"Linse": "Feel (Skalen)", "Anzahl": overview.feel_skalen_total},
            {"Linse": "Reach (Do)", "Anzahl": reach.graylog_nutzer_sum + reach.ranking_kunden_sum},
        ]
    )
    lens_df = lens_df[lens_df["Anzahl"] > 0]
    active_src_df = _overview_source_totals(ws, active)

    pie_colors = ["#2563eb", "#16a34a", "#d97706", "#9333ea", "#64748b", "#dc2626"]
    pc1, pc2, pc3 = st.columns(3)

    with pc1:
        st.markdown("**Signale nach Quelle**")
        st.caption(
            "Freitext-Rohsignale (Say): Hotline-Tickets, Feldbesuche und Umfrage-Anregungen — "
            "Summen aus der Inbox/Pipeline, unabhängig von der Produkt-Matrix."
        )
        if stimmen_df.empty:
            st.info("Noch keine Stimmen-Signale in den Rohdaten.")
        else:
            fig_stimmen = px.pie(
                stimmen_df,
                names="Quelle",
                values="Anzahl",
                template="plotly_white",
                height=300,
                color_discrete_sequence=pie_colors,
            )
            fig_stimmen.update_traces(textposition="inside", textinfo="percent+label")
            fig_stimmen.update_layout(margin=dict(t=20, b=20, l=10, r=10), showlegend=False)
            st.plotly_chart(fig_stimmen, use_container_width=True)

    with pc2:
        st.markdown("**Stimmen · Feel · Reach**")
        st.caption(
            "Drei Linsen auf den Rohdaten: **Say** (Freitext), **Feel** (Umfrage-Skalen/NPS) und "
            "**Reach** (Graylog-Nutzer + Modul-Ranking-Kunden). Verschiedene Metriken — Anteile nur grob vergleichbar."
        )
        if lens_df.empty:
            st.info("Noch keine Linsen-Daten verfügbar.")
        else:
            fig_lens = px.pie(
                lens_df,
                names="Linse",
                values="Anzahl",
                template="plotly_white",
                height=300,
                color_discrete_map={
                    "Stimmen (Say)": "#2563eb",
                    "Feel (Skalen)": "#d97706",
                    "Reach (Do)": "#16a34a",
                },
            )
            fig_lens.update_traces(textposition="inside", textinfo="percent+label")
            fig_lens.update_layout(margin=dict(t=20, b=20, l=10, r=10), showlegend=False)
            st.plotly_chart(fig_lens, use_container_width=True)

    with pc3:
        st.markdown("**Aktive Quellen**")
        st.caption(
            f"Anteil der Top-30-Cluster je aktiver Sidebar-Quelle ({len(active)} ausgewählt). "
            + (
                "Feedback-Quellen = Ticket-/Eintrags-Häufigkeit."
                if DEMO_MODE
                else "Verträge = ERP-Kundenanzahl; Feedback-Quellen = Ticket-/Eintrags-Häufigkeit."
            )
        )
        if active_src_df.empty:
            st.info("Keine Cluster-Daten für die aktiven Quellen.")
        else:
            fig_active = px.pie(
                active_src_df,
                names="quelle",
                values="anzahl",
                template="plotly_white",
                height=300,
                color_discrete_sequence=pie_colors,
            )
            fig_active.update_traces(textposition="inside", textinfo="percent+label")
            fig_active.update_layout(margin=dict(t=20, b=20, l=10, r=10), showlegend=False)
            st.plotly_chart(fig_active, use_container_width=True)

    st.divider()

    pl_df = ws.product_line_breakdown(active)
    if not pl_df.empty:
        st.subheader("Produktlinien")
        st.caption(
            "Grobdarstellung nach Produkttyp (Modul · App · Dienstleistung · …). "
            "Klassifikation per Namens-Heuristik — **nicht** über `product_module_mapping.json`."
        )
        with st.expander("Was bedeuten die Spalten?", expanded=False):
            if DEMO_MODE:
                st.markdown(
                    "- **Signale Σ** — Hotline-Tickets + Umfrage-Einträge + Feldbesuche "
                    "(Top-30-Cluster je Quelle, vergleichbare Feedback-Signale).\n"
                    "- **Versch. Namen** — wie viele **unterschiedliche** Cluster-/Artikel-Bezeichnungen "
                    "in dieser Linie vorkommen.\n"
                    "- **Datenquellen** — aus wie vielen aktiven Quellen (Sidebar) diese Linie befüllt wird."
                )
            else:
                st.markdown(
                    "- **Signale Σ** — Hotline-Tickets + Umfrage-Einträge + Feldbesuche "
                    "(Top-30-Cluster je Quelle, vergleichbare Feedback-Signale).\n"
                    "- **Kunden (ERP)** — Summe `Anzahl_Kunden` aus Verträgen/Penetration "
                    "(Top-30-Artikel; Kunde kann in mehreren Produkten zählen).\n"
                    "- **Versch. Namen** — wie viele **unterschiedliche** Cluster-/Artikel-Bezeichnungen "
                    "in dieser Linie vorkommen.\n"
                    "- **Datenquellen** — aus wie vielen aktiven Quellen (Sidebar) diese Linie befüllt wird."
                )
        with st.expander("Was sind die Produktlinien?", expanded=False):
            for line in ALL_PRODUCT_LINES:
                hint = PRODUCT_LINE_HINTS.get(line, {})
                if not hint:
                    continue
                st.markdown(f"**{line}** — {hint.get('kurz', '')}")
                st.caption(f"Abgrenzung: {hint.get('abgrenzung', '')}")
                st.caption(f"Erkennung: {hint.get('keywords', '')}")
        pl_display = pl_df.rename(
            columns={
                "signale": "Signale Σ",
                "kunden_erp": "Kunden (ERP)",
                "Produkte": "Versch. Namen",
                "quellen": "Datenquellen",
            }
        )
        if DEMO_MODE:
            pl_display = pl_display.drop(columns=["Kunden (ERP)"], errors="ignore")
        pl_column_config = {
            "Produktlinie": st.column_config.TextColumn(
                "Produktlinie",
                help="Produkttyp per Namens-Heuristik — Details unter «Was sind die Produktlinien?»",
                width="medium",
            ),
            "Signale Σ": st.column_config.NumberColumn(
                "Signale Σ",
                help="Tickets, Umfrage-Einträge und Feldbesuche — Feedback-Signale.",
                format="%d",
            ),
            "Versch. Namen": st.column_config.NumberColumn(
                "Versch. Namen",
                help="Anzahl eindeutiger Cluster-/Artikelnamen in dieser Produktlinie.",
                format="%d",
            ),
            "Datenquellen": st.column_config.NumberColumn(
                "Datenquellen",
                help="Anzahl Quellen aus der Sidebar, die Top-Cluster in diese Linie liefern.",
                format="%d",
            ),
        }
        if not DEMO_MODE:
            pl_column_config["Kunden (ERP)"] = st.column_config.NumberColumn(
                "Kunden (ERP)",
                help="Kundenanzahl aus Verträgen/Penetration (Top-30-Artikel je Linie).",
                format="%d",
            )
        st.dataframe(
            pl_display,
            hide_index=True,
            use_container_width=True,
            column_config=pl_column_config,
        )
        chart_value_vars = ["signale"] if DEMO_MODE else ["signale", "kunden_erp"]
        chart_df = pl_df.melt(
            id_vars=["Produktlinie"],
            value_vars=chart_value_vars,
            var_name="Metrik",
            value_name="Anzahl",
        )
        metric_labels = {"signale": "Signale Σ"}
        if not DEMO_MODE:
            metric_labels["kunden_erp"] = "Kunden (ERP)"
        chart_df["Metrik"] = chart_df["Metrik"].map(metric_labels)
        fig_pl = px.bar(
            chart_df,
            x="Produktlinie",
            y="Anzahl",
            color="Metrik" if not DEMO_MODE else None,
            barmode="group",
            template="plotly_white",
            title=(
                "Signale nach Produktlinie (Top-30 je Quelle)"
                if DEMO_MODE
                else "Signale vs. ERP-Kunden nach Produktlinie (Top-30 je Quelle)"
            ),
            height=340,
            labels={"Anzahl": "Anzahl", "Produktlinie": "Produktlinie"},
            color_discrete_map={"Signale Σ": "#2563eb", "Kunden (ERP)": "#64748b"},
        )
        fig_pl.update_layout(xaxis_tickangle=-25)
        st.plotly_chart(fig_pl, use_container_width=True)
        line_pick = st.selectbox(
            "Produktlinie im Detail",
            pl_df["Produktlinie"].tolist(),
            key="product_line_pick",
        )
        line_row = pl_df.loc[pl_df["Produktlinie"] == line_pick].iloc[0]
        line_hint = PRODUCT_LINE_HINTS.get(line_pick, {})
        if line_hint:
            st.info(
                f"**{line_pick}** — {line_hint.get('kurz', '')}\n\n"
                f"**Abgrenzung:** {line_hint.get('abgrenzung', '')}\n\n"
                f"**Erkennung:** {line_hint.get('keywords', '')}"
            )
        if DEMO_MODE:
            mc1, mc3 = st.columns(2)
            mc1.metric(
                "Signale Σ",
                int(line_row["signale"]),
                help="Hotline-Tickets, Umfrage-Einträge, Feldbesuche (Top-30 je Quelle).",
            )
            mc3.metric(
                "Versch. Namen",
                int(line_row["Produkte"]),
                help="Eindeutige Cluster-/Artikelbezeichnungen in dieser Linie.",
            )
        else:
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric(
                "Signale Σ",
                int(line_row["signale"]),
                help="Hotline-Tickets, Umfrage-Einträge, Feldbesuche (Top-30 je Quelle).",
            )
            mc2.metric(
                "Kunden (ERP)",
                int(line_row["kunden_erp"]),
                help="Vertrags-Penetration: Anzahl_Kunden summiert über Top-Artikel dieser Linie.",
            )
            mc3.metric(
                "Versch. Namen",
                int(line_row["Produkte"]),
                help="Eindeutige Cluster-/Artikelbezeichnungen in dieser Linie.",
            )
        if (
            not DEMO_MODE
            and line_pick == "Paket / Daten"
            and int(line_row["signale"]) == 0
            and int(line_row["kunden_erp"]) > 0
        ):
            st.caption(
                "ℹ️ **Paket / Daten** kommt bei euch derzeit nur aus **Verträgen** — "
                "Datenhaltung, Filehosting, WMS-Anbindung (Kundenanzahl, keine Hotline-Tickets)."
            )
        detail_pl = ws.product_line_detail(active, line_pick, limit=12)
        if not detail_pl.empty:
            st.markdown(f"**Top-Einträge in {line_pick}**")
            detail_display = detail_pl.rename(
                columns={
                    "cluster": "Produkt / Cluster",
                    "anzahl": "Anzahl",
                    "einheit": "Einheit",
                    "quelle": "Datenquelle",
                    "zuordnung": "Warum diese Linie?",
                }
            )
            st.dataframe(
                detail_display,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Anzahl": st.column_config.NumberColumn(
                        "Anzahl",
                        help="Signale = Tickets/Einträge/Feldbesuche · Kunden (ERP) = Vertrags-Penetration.",
                        format="%d",
                    ),
                    "Warum diese Linie?": st.column_config.TextColumn(
                        "Warum diese Linie?",
                        help="Nachvollziehbare Zuordnung aus classify_product_line (Keyword/Prefix).",
                        width="large",
                    ),
                },
            )

    if len(active) >= 2:
        st.subheader("Themen-Vergleich")
        theme_df = ws.compare_themes(active)
        if not theme_df.empty:
            score_cols = [c for c in theme_df.columns if c.endswith("(Score)")]
            show_cols = ["Thema", "Overlap", "Gesamt_Score", *score_cols]
            st.dataframe(theme_df[show_cols], hide_index=True, use_container_width=True)
        for line in ws.find_overlap(active):
            st.markdown(line)

    top_df = ws.top_needs(active, limit=8)
    if not top_df.empty:
        fig = px.bar(
            top_df,
            x="cluster",
            y="anzahl",
            color="quelle",
            template="plotly_white",
            title="Top Pain Points",
        )
        fig.update_layout(xaxis_tickangle=-35, height=360)
        st.plotly_chart(fig, use_container_width=True)

    if not DEMO_MODE and SALES_TECHNICAL_NAME in active:
        rev_total = ws.sales_total_revenue
        if rev_total > 0:
            st.caption(f"ERP-Vertragsumsatz (aggregiert): **{rev_total:,.0f} €**".replace(",", "."))

        prio_df = ws.product_priority(12)
        if not prio_df.empty:
            st.subheader("Priorität: Umsatz × Ticket-Last")
            st.caption(
                "ERP-Umsatz (Summe_Umsatz) mit Hotline-Clustern gematcht — "
                "hoher Score = viel Umsatz und/oder viele Tickets. "
                f"Seed-Mapping: {len(load_mapping_entries())} Top-Produkte."
            )
            show_prio = prio_df.rename(
                columns={
                    "produkt": "Produkt",
                    "produktlinie": "Linie",
                    "summe_umsatz": "Umsatz €",
                    "anzahl_kunden": "Kunden",
                    "ticket_cluster": "Ticket-Cluster",
                    "ticket_anzahl": "Tickets",
                    "match_art": "Match",
                    "prioritaet_score": "Score",
                    "prioritaet_stufe": "Stufe",
                }
            )
            st.dataframe(
                show_prio[
                    [
                        "Produkt",
                        "Linie",
                        "Umsatz €",
                        "Kunden",
                        "Tickets",
                        "Match",
                        "Score",
                        "Stufe",
                    ]
                ],
                hide_index=True,
                use_container_width=True,
            )
            for line in ws.priority_summary(2):
                st.markdown(line)

        mod_intent = ws.module_intent_table(12)
        if not mod_intent.empty:
            st.subheader("Intent pro Modul (alle Quellen)")
            st.caption(
                "**Bedarf-Typ** ist die PM-Hauptkategorie (Feature Request, UX-Kritik, …). "
                "**Ticket-Routing** nur bei Defekt, Discovery, How-To oder Installation — "
                "nicht bei «Sonstiges» (z. B. S028: Feature Request · Defekt)."
            )
            mod_view = mod_intent.rename(
                columns={
                    "modul": "Modul",
                    "summe_umsatz": "Umsatz €",
                    "eintraege": "Einträge",
                    "dominant_intent": "Top-Intent",
                    "top_bedarf": "Bedarf-Typ",
                    "top_geltung": "Geltung",
                }
            ).copy()
            mod_view["Ticket-Routing"] = mod_view["Top-Intent"].map(ticket_routing_intent)
            st.dataframe(
                mod_view[
                    [
                        "Modul",
                        "Umsatz €",
                        "Einträge",
                        "Bedarf-Typ",
                        "Ticket-Routing",
                        "Geltung",
                        "Defekt",
                        "How-To",
                        "Discovery",
                        "quellen",
                    ]
                ],
                hide_index=True,
                use_container_width=True,
            )

        intent_grp = ws.intent_by_business_group(12)
        if not intent_grp.empty:
            st.subheader("Intent pro Business-Gruppe (ERP-Rahmen)")
            st.caption(
                "Hotline-HTML-Rohdaten, zugeordnet über product_module_mapping.json. "
                "Bedarf-Typ vor Ticket-Routing (siehe Modul-Tabelle)."
            )
            grp_view = intent_grp.rename(
                columns={
                    "business_gruppe": "Business-Gruppe",
                    "summe_umsatz": "Umsatz €",
                    "ticket_anzahl": "Tickets",
                    "dominant_intent": "Top-Intent",
                    "top_bedarf": "Bedarf-Typ",
                    "pct_How-To": "% How-To",
                    "pct_Discovery": "% Discovery",
                }
            ).copy()
            grp_view["Ticket-Routing"] = grp_view["Top-Intent"].map(ticket_routing_intent)
            st.dataframe(
                grp_view[
                    [
                        "Business-Gruppe",
                        "Umsatz €",
                        "Tickets",
                        "Bedarf-Typ",
                        "Ticket-Routing",
                        "How-To",
                        "Discovery",
                        "Defekt",
                        "% How-To",
                        "% Discovery",
                    ]
                ],
                hide_index=True,
                use_container_width=True,
            )

        c_rev, c_pen = st.columns(2)
        with c_rev:
            revenue_df = ws.sales_revenue(8)
            if not revenue_df.empty:
                st.markdown("**Top-Umsatz (ERP)**")
                st.dataframe(
                    revenue_df[["cluster", "umsatz"]].rename(columns={"cluster": "Produkt", "umsatz": "Umsatz €"}),
                    hide_index=True,
                    use_container_width=True,
                )
        with c_pen:
            sales_df = ws.sales_penetration(8)
            if not sales_df.empty:
                st.markdown("**Produkt-Penetration**")
                st.dataframe(sales_df, hide_index=True, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Hotline-Top**")
        hdf = ws.hotline_frequency(active)
        st.dataframe(
            hdf[["cluster", "anzahl"]].head(5) if not hdf.empty else pd.DataFrame(),
            hide_index=True,
            use_container_width=True,
        )
    with c2:
        st.markdown("**Strategie (Kurz)**")
        strat = ws.deterministic_strategy(active)
        st.info(strat["summary"])
    with c3:
        st.markdown("**Data Coverage**")
        cov = ws.data_coverage
        if cov:
            st.dataframe(pd.DataFrame(cov), hide_index=True, use_container_width=True)
        else:
            st.caption("—")

# ===================== TAB: PRODUCT SIGNALS =====================
with tab_signals:
    from workspace.product_signals_dashboard import render_product_signals_dashboard

    render_product_signals_dashboard()

# ===================== TAB: TERA =====================
if not DEMO_MODE:
    with tab_tera:
        from workspace.tera_dashboard import render_tera_dashboard

        render_tera_dashboard()

# ===================== TAB: KI-STRATEGIE =====================
with tab_strategy:
    st.subheader("KI-Strategie-Wizard")
    st.caption("Schritt 1–3: Evidenz aus Snapshot · Schritt 4: optional LLM-Synthese")

    brief = build_strategy_brief(ws, active)
    draft_md = strategy_brief_to_markdown(brief)

    st.markdown("#### Evidenz-Kern")
    st.markdown(draft_md)

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("📄 Entwurf speichern (Session)", use_container_width=True):
            st.session_state.strategy_md = draft_md
            st.success("Entwurf gespeichert.")
    with col_b:
        if st.button("✨ Mit LLM ausformulieren", use_container_width=True, disabled=not can_synthesize):
            with st.spinner("Synthese…"):
                try:
                    st.session_state.strategy_md = synthesize_strategy_document(brief, active)
                    st.success("Strategie-Dokument erstellt.")
                except Exception as exc:
                    st.error(str(exc))

    if st.session_state.strategy_md:
        st.divider()
        st.markdown("#### Export")
        st.download_button(
            "Markdown herunterladen",
            st.session_state.strategy_md,
            file_name="ki_strategie_entwurf.md",
            mime="text/markdown",
            use_container_width=True,
        )
        with st.expander("Vorschau gespeichertes Dokument"):
            st.markdown(st.session_state.strategy_md)

# ===================== TAB: INITIATIVE CHALLENGER =====================
with tab_challenger:
    st.subheader("Initiative Challenger")
    st.caption("Make / Buy / Partner — deterministisch, ohne LLM")

    init_text = st.text_area(
        "Initiative beschreiben",
        placeholder="z. B. ChatGPT-Integration für FAQ vs. internes RAG über Tickets…",
        height=120,
    )
    freq = st.slider(
        "Bekannte Häufigkeit / Evidenz-Stärke (0 = unbekannt)",
        0,
        50,
        value=0,
        help="Optional: Ticket-Häufigkeit oder Research-Score",
    )

    if st.button("Initiative prüfen", type="primary", use_container_width=True):
        if not init_text.strip():
            st.warning("Bitte Initiative beschreiben.")
        else:
            result = analyze_initiative(init_text.strip(), frequency=freq)
            dec = result["empfehlung"]
            st.markdown(f"### Empfehlung: **{dec['recommendation']}**")
            st.progress(min(1.0, dec.get("confidence", 0.5)))
            st.caption(f"Confidence {dec.get('confidence', 0):.0%} · {dec.get('reason', '')}")
            st.markdown("**Rückfragen**")
            for c in result["challenge"]:
                st.markdown(f"- {c}")
            st.info(result["insight"])
            caps = result.get("capabilities") or []
            if caps:
                st.markdown("**Capabilities**")
                for cap in caps:
                    icon = "✅" if cap.get("detected") else "—"
                    st.caption(f"{icon} {cap.get('capability')}: {', '.join(cap.get('signals') or []) or '—'}")

# Footer
rag_meta = load_rag_meta()
if rag_meta:
    rf, rr = rag_freshness()
    st.caption(
        f"RAG: {rag_meta.get('chunks', 0)} Chunks · "
        f"{'aktuell' if rf else rr} · Chonkie V2"
    )
