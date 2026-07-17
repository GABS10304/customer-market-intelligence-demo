"""Vertrauens-Strip — kompakte Verlässlichkeits-Anzeige im Portal."""

from __future__ import annotations

import streamlit as st

from core.trust_status import TrustStatus, build_trust_status


def render_trust_strip(
    status: TrustStatus | None = None,
    *,
    df=None,
    snapshot_at: str = "",
    snapshot_source: str = "",
    expanded: bool = False,
) -> TrustStatus:
    trust = status or build_trust_status(df, snapshot_at=snapshot_at, snapshot_source=snapshot_source)

    icon = {"hoch": "✅", "mittel": "⚠️", "niedrig": "🛑"}.get(trust.level, "ℹ️")
    st.markdown(f"##### {icon} Vertrauen · **{trust.level.upper()}**")
    st.caption(trust.summary)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(
        "Mapping",
        f"{trust.matrix_mapped_pct:.0f}%",
        delta=f"{trust.matrix_mapped}/{trust.matrix_rows} Produkte",
        help=f"{trust.mapping_seed_entries} Seed-Einträge in product_module_mapping.json",
    )
    c2.metric(
        "Hotline gemappt",
        f"{100 - trust.hotline_unmapped_pct:.0f}%",
        delta="abgestimmt" if trust.hotline_aligned else "Abweichung",
        delta_color="normal" if trust.hotline_aligned else "inverse",
        help=f"{trust.hotline_unmapped_pct:.0f}% Tickets an unmapped:* Clustern",
    )
    c3.metric(
        "Umfrage-Match",
        f"{trust.survey_match_pct:.0f}%",
        help="Anteil tickets_b-Zeilen mit Landkreis→ERP-Treffer",
    )
    c4.metric(
        "RAG",
        "ok" if trust.rag_fresh else "alt",
        delta=f"{trust.rag_documents} Docs",
        delta_color="normal" if trust.rag_fresh else "inverse",
        help=trust.rag_label,
    )
    c5.metric(
        "Snapshot",
        trust.snapshot_at[:10] if trust.snapshot_at not in ("—", "") else "—",
        delta=trust.snapshot_source,
        help=f"Product Signals: {trust.product_signals_label}",
    )

    with st.expander("Details & nächste Schritte", expanded=expanded or trust.level == "niedrig"):
        if trust.warnings:
            for w in trust.warnings:
                st.warning(w, icon="⚠️")
        else:
            st.success("Keine kritischen Abweichungen.", icon="✅")
        if 0 < trust.survey_match_pct < 75:
            st.info(
                f"Umfrage Feel: {trust.survey_match_pct:.0f}% Landkreis→ERP gematcht — "
                "betrifft nur NPS/UX-Produktvergleiche, nicht Hotline/TERA/Graylog/RAG.",
                icon="ℹ️",
            )
        if trust.actions:
            st.markdown("**Empfohlen:**")
            for a in trust.actions:
                st.markdown(f"- {a}")
        if trust.top_unmapped:
            st.markdown("**Top unmapped (Hotline-Tickets):**")
            for name, count in trust.top_unmapped:
                st.caption(f"· {name} — {count} Tickets")
            st.caption("Vorschläge: `python suggest_product_mappings.py --apply`")

    return trust


def render_trust_strip_compact(
    *,
    snapshot_at: str = "",
    snapshot_source: str = "",
) -> None:
    """Sidebar-Kurzform."""
    from core.trust_status import trust_fingerprint, trust_status_cached

    trust = trust_status_cached(trust_fingerprint(), snapshot_at, snapshot_source)
    icon = {"hoch": "✅", "mittel": "⚠️", "niedrig": "🛑"}.get(trust.level, "ℹ️")
    st.caption(
        f"{icon} **Vertrauen {trust.level}** · Mapping {trust.matrix_mapped_pct:.0f}% · "
        f"Hotline gemappt {100 - trust.hotline_unmapped_pct:.0f}% · "
        f"RAG {'ok' if trust.rag_fresh else 'alt'}"
    )
    if trust.warnings:
        with st.expander("Vertrauen — Hinweise", expanded=trust.level == "niedrig"):
            for w in trust.warnings[:3]:
                st.caption(f"⚠ {w}")
