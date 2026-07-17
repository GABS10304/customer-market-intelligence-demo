import streamlit as st

from decision_ui_helpers import setup_gcp_credentials, setup_repo_imports

ROOT_DIR = setup_repo_imports()
setup_gcp_credentials()

from bq_decision_writer import write_capability_to_bq, write_decision_to_bq
from capability_detection import detected_capabilities_summary
from initiative_challenger import analyze_initiative

st.set_page_config(page_title="Initiative Challenger", layout="wide")

st.title("🎯 Initiative Challenger")
st.markdown(
    "Reiche eine Initiative als Freitext ein. Das System liefert **Challenge**, **Insight**, "
    "**Empfehlung** und **Capability Detection** – vollständig regelbasiert, ohne LLM-Berechnung."
)

st.divider()

col_input, col_meta = st.columns([3, 1])

with col_input:
    initiative_text = st.text_area(
        "Initiative / Idee (Freitext)",
        height=180,
        placeholder="z.B. Wir brauchen ChatGPT für Support-Mitarbeiter, damit sie schneller Antworten finden...",
    )

with col_meta:
    frequency = st.number_input(
        "Bekannte Häufigkeit (Tickets/Umfragen)",
        min_value=0,
        value=0,
        help="Optional: Anzahl aus BigQuery oder Schätzung",
    )
    save_to_bq = st.checkbox("In BigQuery speichern", value=True)
    save_to_memory = st.checkbox("In Decision Memory speichern", value=False)

if st.button("🔍 Analyse starten", type="primary", use_container_width=True):
    if not initiative_text.strip():
        st.warning("Bitte zuerst eine Initiative eingeben.")
    else:
        with st.spinner("Analysiere Initiative..."):
            result = analyze_initiative(initiative_text, frequency=frequency)
            decision = result["empfehlung"]

            if save_to_bq:
                bq_dec = write_decision_to_bq(
                    recommendation=decision["recommendation"],
                    reason=decision["reason"],
                    risk=decision["risk"],
                    confidence=decision["confidence"],
                    source="initiative_challenger",
                    input_text=initiative_text,
                    initiative_id=result["initiative_id"],
                )
                bq_cap = write_capability_to_bq(
                    capabilities=result["capabilities"],
                    source="initiative_challenger",
                    input_text=initiative_text,
                    initiative_id=result["initiative_id"],
                )
                if bq_dec["success"] and bq_cap["success"]:
                    st.success(f"Ergebnisse in BigQuery gespeichert (ID: `{result['initiative_id'][:8]}...`).")
                else:
                    st.warning(
                        f"BigQuery-Hinweis: Decision={bq_dec.get('error') or 'OK'}, "
                        f"Capability={bq_cap.get('error') or 'OK'}"
                    )

            if save_to_memory:
                from decision_memory import save_decision
                from initiative_challenger import slug_from_text

                slug = slug_from_text(initiative_text)
                save_decision({
                    "slug": slug,
                    "decision": decision["recommendation"],
                    "problem": initiative_text[:200],
                    "reasoning": decision["reason"],
                    "evidence": result["challenge"],
                    "risks": decision["risk"],
                    "reopen": f"Confidence unter 0.6 (aktuell: {decision['confidence']})",
                    "frequency": str(frequency) if frequency else "n/a",
                    "source": "initiative_challenger",
                })
                st.info(f"Decision Memory: `{slug}.md` gespeichert.")

        st.divider()
        st.subheader("📋 Ergebnis")

        c1, c2 = st.columns(2)

        with c1:
            st.markdown("#### ⚡ Challenge")
            for i, ch in enumerate(result["challenge"], 1):
                st.markdown(f"{i}. {ch}")

            st.markdown("#### 💡 Insight")
            st.info(result["insight"])

        with c2:
            st.markdown("#### ⚖️ Empfehlung (Decision Engine)")
            rec = decision["recommendation"]
            color = {"Make": "green", "Buy": "orange", "Partner": "blue"}.get(rec, "gray")
            st.markdown(f":{color}[**{rec}**] – Confidence: **{decision['confidence']:.0%}**")
            st.write(f"**Begründung:** {decision['reason']}")
            st.write(f"**Risiko:** {decision['risk']}")

            st.markdown("#### 🔧 Capability Detection")
            st.write(detected_capabilities_summary(result["capabilities"]))
            for cap in result["capabilities"]:
                icon = "✅" if cap["detected"] else "⬜"
                signals = ", ".join(cap["signals"]) if cap["signals"] else "–"
                st.caption(f"{icon} **{cap['capability']}** ({cap['confidence']:.0%}): {signals}")

        with st.expander("📦 Strukturiertes JSON"):
            st.json({
                "recommendation": decision["recommendation"],
                "reason": decision["reason"],
                "risk": decision["risk"],
                "confidence": decision["confidence"],
                "capabilities": result["capabilities"],
                "challenge": result["challenge"],
                "insight": result["insight"],
            })
