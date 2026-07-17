"""TERA Vergleich — ERP-Lizenzen vs. Hotline-Tickets auf Basis-Produktcode."""

from __future__ import annotations

import re
from functools import lru_cache

import numpy as np
import pandas as pd

from core.tera_hotline import tera_hotline_by_product, tera_hotline_detail
from core.tera_products import tera_installation_by_product

TERA_REQUEST_QUESTION_PATTERNS = (
    r"\b(meiste|meisten|höchste|max|top)\b.*\b(anfragen|tickets?|support)\b",
    r"\b(anfragen|tickets?)\b.*\b(tera|terawin)\b",
    r"\b(tera|terawin)\b.*\b(anfragen|tickets?|hotline)\b",
    r"\bproduziert\b.*\b(anfragen|tickets?)\b",
)


def is_tera_request_question(question: str) -> bool:
    """True wenn die Frage nach Hotline-Anfragen/Tickets fragt (nicht ERP-Lizenzen)."""
    lower = (question or "").lower()
    return any(re.search(p, lower) for p in TERA_REQUEST_QUESTION_PATTERNS)


@lru_cache(maxsize=1)
def tera_compare_matrix() -> pd.DataFrame:
    """Outer join ERP-Installationen vs. Hotline-Tickets pro TERA-Basiscode."""
    erp = tera_installation_by_product().rename(
        columns={"installationen": "erp_installationen", "kunden": "erp_kunden"}
    )
    hotline = tera_hotline_by_product().rename(
        columns={"tickets": "hotline_tickets", "cluster": "hotline_cluster_n", "beispiel_cluster": "hotline_beispiel"}
    )

    if erp.empty and hotline.empty:
        return pd.DataFrame(
            columns=[
                "tera_base",
                "erp_installationen",
                "erp_kunden",
                "hotline_tickets",
                "hotline_cluster_n",
                "hotline_beispiel",
                "delta_kunden_vs_tickets",
                "hotline_pro_100_kunden",
            ]
        )

    merged = erp.merge(hotline, on="tera_base", how="outer")
    for col in ("erp_installationen", "erp_kunden", "hotline_tickets", "hotline_cluster_n"):
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0).astype(int)

    merged["delta_kunden_vs_tickets"] = merged["erp_kunden"] - merged["hotline_tickets"]
    with_kunden = merged["erp_kunden"] > 0
    merged["hotline_pro_100_kunden"] = np.where(
        with_kunden,
        (100.0 * merged["hotline_tickets"] / merged["erp_kunden"]).round(1),
        np.nan,
    ).astype(float)
    merged = merged.sort_values(
        ["hotline_pro_100_kunden", "hotline_tickets"],
        ascending=[False, False],
        na_position="last",
    )
    return merged


def clear_tera_compare_cache() -> None:
    tera_compare_matrix.cache_clear()


def format_tera_evidence_markdown(*, question: str = "", top_n: int = 8, full: bool = False) -> str:
    """Markdown-Evidenzblock für Assistent — klare Semantik: Anfragen = Hotline-Tickets."""
    compare = tera_compare_matrix()
    if compare.empty:
        return "### TERA (ERP vs. Hotline)\n- (keine TERA-Daten — `tera.csv` / Hotline teraWinData)"

    lines = [
        "### TERA — ERP-Lizenzen vs. Hotline-Tickets",
        "**Semantik:** *Anfragen* = nur **Hotline-Tickets**. "
        "ERP-Kunden = Lizenzbasis (Behörden mit Produkt), **keine Anfragen** — niemals addieren.",
        "**Support-Druck %** = Hotline-Tickets je 100 ERP-Kunden.",
    ]

    request_focus = is_tera_request_question(question)
    if request_focus:
        view = compare.sort_values(["hotline_tickets", "tera_base"], ascending=[False, True])
        top = view.iloc[0]
        lines.append(
            f"- **Antwort (verbindlich):** Meiste Hotline-Anfragen → **{top['tera_base']}** "
            f"({int(top['hotline_tickets'])} Tickets). "
            f"ERP-Kunden ({int(top['erp_kunden'])}) sind Lizenzen, nicht Anfragen."
        )
        show = view.head(top_n if full else min(5, top_n))
        lines.append("\n**Ranking nach Hotline-Tickets (Anfragen):**")
    else:
        show = compare.head(top_n if full else min(5, top_n))
        lines.append("\n**Ranking nach Support-Druck (Hotline je 100 ERP-Kunden):**")

    for row in show.itertuples():
        druck = getattr(row, "hotline_pro_100_kunden", None)
        druck_s = f"{druck:.1f} %" if pd.notna(druck) else "—"
        lines.append(
            f"- **{row.tera_base}** — Hotline {int(row.hotline_tickets)} Anfragen, "
            f"ERP-Kunden {int(row.erp_kunden)} (Lizenzen), Druck {druck_s}"
        )

    if not full and len(compare) > len(show):
        lines.append(f"- … {len(compare) - len(show)} weitere TERA-Basisprodukte im TERA-Tab")

    return "\n".join(lines)


def clear_tera_all_caches() -> None:
    """ERP-, Hotline- und Vergleichs-Caches leeren (z. B. nach Daten-Update)."""
    from core.tera_hotline import clear_tera_hotline_cache
    from core.tera_products import clear_tera_installation_cache

    clear_tera_installation_cache()
    clear_tera_hotline_cache()
    clear_tera_compare_cache()
