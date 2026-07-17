"""
Product Signals Dashboard — Say · Feel · Do · Pay pro mapping_id.

Daten: data/product_signals_unified.csv (Fallback: live aggregate_product_signals).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import DATA_DIR
from core.hotline_inventory import (
    clear_hotline_inventory_cache,
    hotline_inventory,
)
from core.intent_patterns import ticket_routing_intent
from core.product_lines import classify_product_line
from core.product_signals import DEFAULT_OUTPUT, aggregate_product_signals
from core.signal_inventory import signal_overview
from core.survey_signals import SURVEY_SOURCE_LABEL, survey_inventory
from workspace.trust_strip import render_trust_strip

SIGNALS_CSV = DEFAULT_OUTPUT


def _numeric_column(df: pd.DataFrame, column: str) -> pd.Series:
    """Spalte als numerische Series — fehlende Spalte → Nullen."""
    if column in df.columns:
        return pd.to_numeric(df[column], errors="coerce").fillna(0)
    return pd.Series(0, index=df.index, dtype=float)


def load_signals_dataframe(*, refresh: bool = False) -> pd.DataFrame:
    """Lädt Product Signals von Disk oder berechnet live."""
    if refresh or not SIGNALS_CSV.exists():
        return aggregate_product_signals()
    df = pd.read_csv(SIGNALS_CSV, sep=";", encoding="utf-8-sig")
    if df.empty:
        return aggregate_product_signals()
    return df


def prepare_signals_view(df: pd.DataFrame) -> pd.DataFrame:
    """Reichert Signale für Dashboard-Filter und Charts an."""
    if df.empty:
        return df
    view = df.copy()
    view["produktlinie"] = view["modul"].map(classify_product_line)
    view["is_mapped"] = ~view["mapping_id"].astype(str).str.startswith("unmapped:")
    view["has_usage"] = _numeric_column(view, "usage_nutzer") > 0
    view["has_survey"] = _numeric_column(view, "umfrage_antworten") > 0
    view["has_reach"] = _numeric_column(view, "reach_nutzer") > 0
    for col in (
        "hotline_tickets",
        "feldbesuche",
        "signale_gesamt",
        "reach_nutzer",
        "ranking_kunden",
        "usage_nutzer",
        "impact_proxy",
        "erp_umsatz_eur",
        "umfrage_avg_nps",
        "umfrage_antworten",
    ):
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").fillna(0)
    for col in ("umfrage_detractors", "umfrage_avg_ux", "umfrage_avg_support"):
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").fillna(0)
    if "top_ticket_routing" not in view.columns and "dominant_intent" in view.columns:
        view["top_ticket_routing"] = view["dominant_intent"].map(ticket_routing_intent)
    return view


def _kpi_row(df: pd.DataFrame) -> None:
    """Zwei Ebenen: Rohsignale (Summen) vs. Produkte in der Matrix (Abdeckung)."""
    total_products = len(df)
    with_say = int((df["signale_gesamt"] > 0).sum())
    with_feel = int(df["has_survey"].sum())
    with_reach = int(df["has_reach"].sum())
    with_usage = int(df["has_usage"].sum())
    with_ranking_only = int(
        ((df["has_reach"]) & (~df["has_usage"]) & (pd.to_numeric(df["ranking_kunden"], errors="coerce").fillna(0) > 0)).sum()
    )
    hotline_sum = int(df["hotline_tickets"].sum())
    overview = signal_overview()
    reach = overview.reach

    st.markdown("**Signale vs. Reach** — Rohdaten nach Linse (Summen, nicht Produkte)")
    c_stimmen, c_feel, c_reach = st.columns(3)

    with c_stimmen:
        st.metric(
            "Stimmen Σ",
            overview.stimmen_total,
            delta=overview.stimmen_breakdown(),
            help="Say · Freitext: Hotline + Feldbesuche + Umfrage-Anregungen (≥15 Zeichen). "
            "Hotline nur HTML, nicht zusätzlich tickets_backlog.csv.",
        )
        for lane in overview.stimmen:
            st.caption(f"· **{lane.label}** {lane.count} — {lane.hint}")

    with c_feel:
        st.metric(
            "Feel · Skalen",
            overview.feel_skalen_total,
            delta=f"{overview.feel[1].count} nur Skalen · {overview.feel[2].count} mit Anregung",
            help=(
                f"Strukturierte {SURVEY_SOURCE_LABEL} (NPS/UX) in tickets_b — "
                "getrennt von Stimmen Σ. Anregungs-Freitexte zählen zusätzlich unter Stimmen."
            ),
        )
        inv_survey = survey_inventory()
        st.caption(
            f"· **ERP-gematcht** {inv_survey.matched_rows} von {inv_survey.raw_rows} Zeilen → "
            f"{inv_survey.product_attributions} Produkt-Zuordnungen"
        )

    with c_reach:
        st.metric(
            "Reach Σ",
            reach.graylog_nutzer_sum + reach.ranking_kunden_sum,
            delta=reach.breakdown,
            help=(
                "Do · Nutzung/Verbreitung: Graylog-Nutzer plus Kunden aus Modul-Ranking — "
                "verschiedene Metriken, nicht 1:1 vergleichbar. "
                "In der Matrix pro Produkt: max(Graylog, Ranking)."
            ),
        )
        st.caption(
            f"· **Graylog** {reach.graylog_nutzer_sum} Nutzer in {reach.graylog_module_rows} Modul-Zeilen"
        )
        st.caption(
            f"· **Modul-Ranking** {reach.ranking_kunden_sum} Kunden in {reach.ranking_module_rows} Modulen"
        )

    st.markdown(
        f"**Produkte in der Matrix** — Abdeckung auf **{total_products}** `mapping_id`-Zeilen"
    )
    r2c1, r2c2, r2c3, r2c4 = st.columns(4)
    r2c1.metric(
        "Say",
        with_say,
        delta=f"von {total_products}",
        help=f"Produkte mit Hotline/Feld — Rohsignale: {hotline_sum} Hotline-Tickets in der Matrix.",
    )
    r2c2.metric(
        "Feel",
        with_feel,
        delta=f"von {total_products}",
        help=f"Produkte mit Umfrage-Zuordnung aus tickets_b ({with_feel} Stück).",
    )
    r2c3.metric(
        "Do · Reach",
        with_reach,
        delta=f"{with_usage} Graylog · {with_ranking_only} Ranking",
        help="Produkte mit reach_nutzer > 0 in der Matrix.",
    )
    r2c4.metric(
        "Pay · ERP",
        int((pd.to_numeric(df.get("erp_umsatz_eur"), errors="coerce").fillna(0) > 0).sum()),
        delta=f"von {total_products}",
        help=(
            "Produkte mit ERP-Umsatz > 0: Summe_Umsatz aus sales_product_penetration.csv, "
            "Artikel → mapping_id (alle Kundentypen)."
        ),
    )


def _filter_bar(df: pd.DataFrame) -> pd.DataFrame:
    with st.expander("Filter", expanded=True):
        st.caption(
            "**Say** = Hotline + Feldbesuche pro Produkt · **Feel** = Kundenumfrage (tickets_b) · "
            "**Gemappt** = Eintrag in `product_module_mapping.json` (sonst `unmapped:…`)."
        )
        c1, c2, c3, c4, c5 = st.columns(5)
        lines = sorted(df["produktlinie"].dropna().unique())
        line_pick = c1.multiselect("Produktlinie", lines, default=lines, key="ps_line")
        max_sig = int(max(df["signale_gesamt"].max(), 1))
        min_sig = c2.slider(
            "Min. Hotline + Feld",
            0,
            max_sig,
            0,
            key="ps_min_sig",
            help=(
                "Mindestanzahl **Hotline-Tickets + Feldbesuche** für dieses Produkt in der Matrix "
                "(Spalte signale_gesamt). Beispiel: 5 = nur Produkte mit ≥5 Tickets/Besuchen zusammen. "
                "Umfrage zählt hier **nicht** — dafür der Feel-Filter."
            ),
        )
        only_mapped = c3.checkbox(
            "Nur gemappt",
            value=False,
            key="ps_mapped",
            help=(
                "Nur Produkte mit bekannter mapping_id aus der Seed-Map "
                "(product_module_mapping.json). "
                "Unmapped = Hotline-Cluster, die noch keinem ERP-Produkt zugeordnet sind."
            ),
        )
        only_voice = c4.checkbox(
            "Nur mit Say",
            value=False,
            key="ps_voice",
            help="Produkte mit mindestens 1 Hotline-Ticket oder Feldbesuch (ohne reine Feel-Zeilen).",
        )
        only_survey = c5.checkbox(
            "Nur mit Feel",
            value=False,
            key="ps_survey",
            help="Produkte mit Kundenumfrage-Zuordnung (tickets_b → ERP-Produkte). Kann mit Say überlappen.",
        )

    out = df[df["produktlinie"].isin(line_pick)] if line_pick else df.iloc[0:0]
    out = out[out["signale_gesamt"] >= min_sig]
    if only_mapped:
        out = out[out["is_mapped"]]
    if only_voice:
        out = out[out["signale_gesamt"] > 0]
    if only_survey:
        out = out[out["has_survey"]]
    return out.sort_values("impact_proxy", ascending=False)


def _chart_impact_top(df: pd.DataFrame, limit: int = 15) -> None:
    top = df.head(limit).iloc[::-1]
    if top.empty:
        st.info("Keine Daten für Impact-Chart.")
        return
    fig = px.bar(
        top,
        x="impact_proxy",
        y="modul",
        color="produktlinie",
        orientation="h",
        title=f"Top {limit} — Impact-Proxy (Signale × Reach × Umsatz)",
        labels={"impact_proxy": "Impact", "modul": "Produkt"},
        template="plotly_white",
        height=max(320, 28 * len(top)),
    )
    fig.update_layout(margin=dict(l=8, r=8, t=40, b=8), legend_title_text="Linie")
    st.plotly_chart(fig, use_container_width=True)


def _chart_scatter_voice_reach(df: pd.DataFrame) -> None:
    voice = df[df["signale_gesamt"] > 0]
    if voice.empty:
        return
    fig = px.scatter(
        voice,
        x="signale_gesamt",
        y="reach_nutzer",
        size="impact_proxy",
        color="produktlinie",
        hover_name="modul",
        log_x=True,
        log_y=True,
        size_max=40,
        title="Stimmen vs. Reach (log)",
        labels={"signale_gesamt": "Signale (Hotline + Feld)", "reach_nutzer": "Reach (Nutzer/Kunden)"},
        template="plotly_white",
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)


def _chart_feel_survey(df: pd.DataFrame, limit: int = 15) -> None:
    """Umfrage-Feel: NPS, UX, Detractors — auch ohne Hotline/Feld."""
    subset = df[df["has_survey"]].sort_values("umfrage_antworten", ascending=False).head(limit)
    if subset.empty:
        st.caption("Keine Umfrage-Daten zugeordnet.")
        return
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Produkt-Zuordnungen",
            x=subset["modul"],
            y=subset["umfrage_antworten"],
            marker_color="#AB63FA",
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Ø NPS",
            x=subset["modul"],
            y=subset["umfrage_avg_nps"],
            yaxis="y2",
            mode="markers+lines",
            marker=dict(size=10, color="#EF553B"),
        )
    )
    detr_vals = subset["umfrage_detractors"] if "umfrage_detractors" in subset.columns else 0
    fig.add_trace(
        go.Scatter(
            name="Detractors",
            x=subset["modul"],
            y=detr_vals,
            yaxis="y3",
            mode="markers",
            marker=dict(size=8, color="#FFA15A", symbol="diamond"),
        )
    )
    fig.update_layout(
        title="Feel — Kundenumfrage (NPS · Zuordnungen · Detractors)",
        template="plotly_white",
        height=420,
        yaxis=dict(title="Produkt-Zuordnungen"),
        yaxis2=dict(title="Ø NPS", overlaying="y", side="right", range=[0, 5.5]),
        yaxis3=dict(title="Detr.", anchor="free", overlaying="y", side="right", position=0.95),
        xaxis_tickangle=-30,
        margin=dict(b=120),
    )
    st.plotly_chart(fig, use_container_width=True)


def _chart_say_feel(df: pd.DataFrame, limit: int = 12) -> None:
    """Hotline + Feldbesuch vs. NPS für Produkte mit Umfrage."""
    subset = df[(df["signale_gesamt"] > 0) & (df["has_survey"])].head(limit)
    if subset.empty:
        st.caption("Keine Produkte mit gleichzeitig Stimmen und Umfrage-Daten.")
        return
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Hotline",
            x=subset["modul"],
            y=subset["hotline_tickets"],
            marker_color="#636EFA",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Feldbesuche",
            x=subset["modul"],
            y=subset["feldbesuche"],
            marker_color="#00CC96",
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Ø NPS",
            x=subset["modul"],
            y=subset["umfrage_avg_nps"],
            yaxis="y2",
            mode="markers+lines",
            marker=dict(size=10, color="#EF553B"),
        )
    )
    fig.update_layout(
        title="Say (Stimmen) + Feel (NPS)",
        template="plotly_white",
        barmode="stack",
        height=420,
        yaxis=dict(title="Tickets / Besuche"),
        yaxis2=dict(title="Ø NPS", overlaying="y", side="right", range=[0, 5.5]),
        xaxis_tickangle=-30,
        margin=dict(b=120),
    )
    st.plotly_chart(fig, use_container_width=True)


def _lens_cards(row: pd.Series) -> None:
    """Vier Linsen für ein Produkt."""
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown("**Say** — Was sagen sie?")
        st.metric("Hotline", int(row.get("hotline_tickets") or 0))
        st.metric("Feldbesuche", int(row.get("feldbesuche") or 0))
        if row.get("top_bedarf"):
            st.caption(f"Bedarf: {row['top_bedarf']}")
    with c2:
        st.markdown("**Feel** — Umfrage")
        nps = row.get("umfrage_avg_nps")
        st.metric("Ø NPS", f"{nps:.2f}" if pd.notna(nps) and float(nps) > 0 else "—")
        antw = int(row.get("umfrage_antworten") or 0)
        if antw:
            st.caption(f"{antw} Produkt-Zuordnungen")
        detr = int(row.get("umfrage_detractors") or 0)
        if detr:
            st.caption(f"{detr} Detractors")
        ux = row.get("umfrage_avg_ux")
        if pd.notna(ux) and float(ux) > 0:
            st.caption(f"Ø UX: {float(ux):.2f}")
    with c3:
        st.markdown("**Do** — Nutzung")
        st.metric("Reach", int(row.get("reach_nutzer") or 0))
        usage = row.get("usage_nutzer")
        if pd.notna(usage) and float(usage) > 0:
            st.caption(f"Graylog: {int(usage)} Nutzer")
        elif int(row.get("ranking_kunden") or 0) > 0:
            st.caption(f"Ranking: {int(row['ranking_kunden'])} Kunden")
    with c4:
        st.markdown("**Pay** — Wert")
        erp = float(row.get("erp_umsatz_eur") or 0)
        st.metric("ERP Umsatz", f"{erp:,.0f} €".replace(",", ".") if erp else "—")
        st.caption(
            "Summe Summe_Umsatz aus sales_product_penetration.csv, "
            "pro Artikel → mapping_id (alle Kundentypen)."
        )
        rank_u = float(row.get("ranking_umsatz_eur") or 0)
        if rank_u:
            st.caption(f"Ranking: {rank_u:,.0f} €".replace(",", "."))


def _detail_table(df: pd.DataFrame) -> None:
    cols = [
        "modul",
        "produktlinie",
        "impact_proxy",
        "signale_gesamt",
        "hotline_tickets",
        "feldbesuche",
        "reach_nutzer",
        "usage_nutzer",
        "umfrage_avg_nps",
        "umfrage_antworten",
        "umfrage_detractors",
        "umfrage_avg_ux",
        "top_bedarf",
        "top_ticket_routing",
        "erp_umsatz_eur",
    ]
    show = [c for c in cols if c in df.columns]
    st.dataframe(
        df[show].rename(
            columns={
                "modul": "Produkt",
                "produktlinie": "Linie",
                "impact_proxy": "Impact",
                "signale_gesamt": "Signale",
                "hotline_tickets": "Hotline",
                "feldbesuche": "Feldbesuche",
                "reach_nutzer": "Reach",
                "usage_nutzer": "Usage",
                "umfrage_avg_nps": "Ø NPS",
                "umfrage_antworten": "Umfrage-Zuordn.",
                "umfrage_detractors": "Detractors",
                "umfrage_avg_ux": "Ø UX",
                "top_bedarf": "Bedarf",
                "top_ticket_routing": "Routing",
                "erp_umsatz_eur": "ERP €",
            }
        ),
        hide_index=True,
        use_container_width=True,
        height=min(520, 38 + 35 * min(len(df), 14)),
    )


def render_product_signals_dashboard(*, csv_path: Path | None = None) -> None:
    """Streamlit-Seite: Product Signals Dashboard."""
    path = csv_path or SIGNALS_CSV
    st.subheader("Product Signals")
    st.caption(
        "Vier Linsen pro Produkt — **Say** (Hotline/Feld) · **Feel** (Kundenumfrage/tickets_b) · "
        "**Do** (Reach/Graylog) · **Pay** (ERP). Join-Achse: `mapping_id`. "
        "**TERA** (`teraWinData`, ERP `TERA-*`) → eigener Tab **TERA**, nicht in dieser Matrix."
    )

    c_ref, c_meta = st.columns([1, 3])
    with c_ref:
        refresh = st.button("↻ Neu berechnen", use_container_width=True, key="ps_refresh")
    with c_meta:
        if path.exists():
            mtime = path.stat().st_mtime
            from datetime import datetime

            st.caption(f"Quelle: `{path.name}` · Stand: {datetime.fromtimestamp(mtime):%Y-%m-%d %H:%M}")
        else:
            st.caption("Keine CSV — live aus Quellen (kann dauern).")

    with st.spinner("Product Signals laden…"):
        df = load_signals_dataframe(refresh=refresh)
    view = prepare_signals_view(df)

    if view.empty:
        st.warning("Noch keine Product Signals — Pipeline oder `python extract_product_signals.py` ausführen.")
        return

    render_trust_strip(df=view, expanded=False)
    st.divider()
    _kpi_row(view)
    clear_hotline_inventory_cache()
    inv = hotline_inventory(
        product_signals_sum=int(view["hotline_tickets"].sum()) if not view.empty else None
    )
    if not inv.aligned:
        st.caption("Hotline-Abweichung — siehe Vertrauens-Strip oben.")
    filtered = _filter_bar(view)

    tab_rank, tab_matrix, tab_detail = st.tabs(["🏆 Priorität", "📐 Matrix", "🔎 Detail"])

    with tab_rank:
        left, right = st.columns([1.1, 1])
        with left:
            _chart_impact_top(filtered, limit=15)
        with right:
            _chart_scatter_voice_reach(filtered)

    with tab_matrix:
        _chart_feel_survey(filtered, limit=15)
        _chart_say_feel(filtered, limit=12)
        bedarf_cols = [c for c in filtered.columns if c.startswith("bedarf_")]
        if bedarf_cols:
            bedarf_sum = filtered[bedarf_cols].sum().sort_values(ascending=False).head(8)
            bedarf_sum = bedarf_sum[bedarf_sum > 0]
            if not bedarf_sum.empty:
                fig_b = px.bar(
                    x=bedarf_sum.values,
                    y=[c.replace("bedarf_", "").replace("_", " ") for c in bedarf_sum.index],
                    orientation="h",
                    title="Bedarf-Typen (Feldbesuche, aggregiert)",
                    labels={"x": "Anzahl", "y": "Bedarf"},
                    template="plotly_white",
                    height=320,
                )
                st.plotly_chart(fig_b, use_container_width=True)

    with tab_detail:
        products = filtered["modul"].tolist()
        if not products:
            st.info("Keine Produkte für aktuelle Filter.")
            return
        pick = st.selectbox("Produkt", products, key="ps_product_pick")
        row = filtered[filtered["modul"] == pick].iloc[0]
        _lens_cards(row)
        if row.get("beispiel_hotline"):
            with st.expander("Beispiel Hotline"):
                st.write(str(row["beispiel_hotline"]))
        if row.get("beispiel_feldbesuch"):
            with st.expander("Beispiel Feldbesuch"):
                st.write(str(row["beispiel_feldbesuch"]))
        st.divider()
        _detail_table(filtered)
