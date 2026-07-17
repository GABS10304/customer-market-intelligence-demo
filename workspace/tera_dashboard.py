"""TERA Dashboard — ERP-Lizenzen vs. Hotline-Tickets (teraWinData)."""

from __future__ import annotations

import math

import plotly.express as px
import streamlit as st


def _format_support_druck(value: float | None) -> str:
    """Deutsches Prozent-Label für die Vergleichstabelle (z. B. «31,0 %»)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    text = f"{float(value):.1f}"
    return text.replace(".", ",") + " %"


def render_tera_dashboard() -> None:
    from config import DEMO_MODE

    if DEMO_MODE:
        st.info("TERA / ERP-Daten sind im Demo-Modus nicht verfügbar.")
        return

    from core.tera_compare import clear_tera_compare_cache, tera_compare_matrix
    from core.tera_hotline import tera_hotline_detail
    from core.tera_products import load_tera_installations_raw, resolve_tera_installations_path

    clear_tera_compare_cache()

    st.subheader("TERA — Lizenzen vs. Hotline")
    st.caption(
        "Vergleich **ERP-Lizenzexport** (`tera.csv`) mit **Hotline-Tickets** (`teraWinData\\…`). "
        "Regel: nur Basis-Codes — `TERA-RES-Technik` → **TERA-RES**, Suffix wird ignoriert. "
        "Pain-Point-Auswertungen im Assistenten nutzen **nur** `teraWinData` — nicht `riwaGisData`."
    )

    path = resolve_tera_installations_path()
    if not path.exists():
        st.warning(
            "Keine TERA-Datei gefunden. Lege `data/tera_installations.csv` oder `tera.csv` im Projekt-Root ab."
        )
        return

    st.caption(f"ERP-Quelle: `{path}` · {len(load_tera_installations_raw())} Lizenzzeilen")

    compare = tera_compare_matrix()
    if compare.empty:
        st.info("Keine TERA-Daten zum Vergleichen.")
        return

    mapped_hotline = int((compare["hotline_tickets"] > 0).sum())
    unmapped = tera_hotline_detail()
    unmapped_n = int((unmapped["tera_base"] == "—").sum()) if not unmapped.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("TERA-Basisprodukte (ERP)", int(compare["tera_base"].nunique()))
    c2.metric("ERP-Kunden Σ", int(compare["erp_kunden"].sum()))
    c3.metric("Hotline-Tickets Σ", int(compare["hotline_tickets"].sum()))
    c4.metric("Hotline-Cluster gemappt", mapped_hotline, delta=f"{unmapped_n} offen" if unmapped_n else "vollständig")

    st.markdown("**Vergleich pro TERA-Basiscode**")
    st.caption(
        "**Support-Druck %** = Hotline-Tickets je 100 ERP-Kunden (Behörden mit Lizenz). "
        "Hoher Wert = viel Hotline **relativ** zur Verbreitung — Pain aus Kundensicht. "
        "**Anfragen** sind nur Hotline-Tickets — ERP-Kunden sind Lizenzen, keine Anfragen. "
        "Sortierung: höchster Druck zuerst."
    )
    show = compare.rename(
        columns={
            "tera_base": "TERA-Basis",
            "erp_installationen": "ERP Installationen",
            "erp_kunden": "ERP Kunden",
            "hotline_tickets": "Hotline-Tickets",
            "hotline_beispiel": "Hotline-Cluster (Beispiel)",
            "delta_kunden_vs_tickets": "Δ Kunden − Tickets",
        }
    )
    show["support_druck_pct"] = compare["hotline_pro_100_kunden"].map(_format_support_druck)
    st.dataframe(
        show[
            [
                "TERA-Basis",
                "ERP Kunden",
                "Hotline-Tickets",
                "support_druck_pct",
                "Δ Kunden − Tickets",
                "Hotline-Cluster (Beispiel)",
            ]
        ],
        hide_index=True,
        use_container_width=True,
        column_config={
            "support_druck_pct": st.column_config.TextColumn(
                "Support-Druck %",
                help="Hotline-Tickets je 100 Lizenz-Kunden. Beispiel: 31,0 % = 31 Tickets pro 100 Kunden.",
            ),
            "Δ Kunden − Tickets": st.column_config.NumberColumn(
                "Δ Kunden − Tickets",
                help="Absolute Differenz ERP-Kunden minus Hotline-Tickets (nicht Prozent).",
                format="%d",
            ),
        },
    )

    chart_df = compare[(compare["erp_kunden"] > 0) | (compare["hotline_tickets"] > 0)].head(15)
    if not chart_df.empty:
        melted = chart_df.melt(
            id_vars=["tera_base"],
            value_vars=["erp_kunden", "hotline_tickets"],
            var_name="Quelle",
            value_name="Anzahl",
        )
        melted["Quelle"] = melted["Quelle"].map(
            {"erp_kunden": "ERP Kunden", "hotline_tickets": "Hotline-Tickets"}
        )
        fig = px.bar(
            melted,
            x="tera_base",
            y="Anzahl",
            color="Quelle",
            barmode="group",
            template="plotly_white",
            title="Top TERA-Produkte: ERP-Kunden vs. Hotline-Tickets",
            height=380,
        )
        fig.update_layout(xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("Hotline-Cluster → TERA-Basis (Detail)", expanded=False):
        st.caption("Mapping über `data/tera_hotline_mapping.json` — editierbar.")
        st.dataframe(
            unmapped.rename(
                columns={
                    "cluster": "Hotline-Cluster",
                    "cluster_leaf": "Leaf",
                    "tickets": "Tickets",
                    "tera_base": "TERA-Basis",
                    "match_reason": "Zuordnung",
                }
            ),
            hide_index=True,
            use_container_width=True,
        )

    with st.expander("ERP-Rohzeilen (normalisiert)", expanded=False):
        raw = load_tera_installations_raw()
        if raw.empty:
            st.caption("—")
        else:
            st.dataframe(
                raw[["BEHOERDEN_NAME", "produkt_raw", "produkt_base", "INSTALLATIONS_DAT"]].head(200),
                hide_index=True,
                use_container_width=True,
            )
