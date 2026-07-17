"""
Produkt-Priorität — Pain (Tickets/Feedback) × Umsatz (ERP-Verträge).

Einfaches Modul-Matching zwischen Ticket-Cluster und Artikelbezeichnung (V1, deterministisch).
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from core.product_lines import classify_product_line
from core.product_mapping import MAPPING_PATH, find_seed_mapping, load_mapping_entries, resolve_product_tickets
from core.sales_evidence import load_sales_penetration, load_sales_revenue_by_product

_MATCH_THRESHOLD = 0.45


def _norm_label(text: str) -> str:
    s = (text or "").lower()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^a-zäöüß0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _leaf_cluster(cluster: str) -> str:
    part = (cluster or "").rsplit("\\", 1)[-1].strip()
    if " - " in part:
        return part.split(" - ", 1)[1].strip()
    return part


def match_score(cluster: str, artikel: str) -> float:
    """0..1 — Token-Overlap zwischen Ticket-Cluster und ERP-Artikel."""
    a = _norm_label(_leaf_cluster(cluster))
    b = _norm_label(artikel)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    ta = {t for t in a.split() if len(t) > 2}
    tb = {t for t in b.split() if len(t) > 2}
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / min(len(ta), len(tb))


def _ticket_index(ticket_rows: list[dict[str, Any]]) -> dict[str, int]:
    idx: dict[str, int] = {}
    for row in ticket_rows:
        cluster = str(row.get("cluster", "")).strip()
        if not cluster:
            continue
        idx[cluster] = idx.get(cluster, 0) + int(row.get("anzahl") or 0)
    return idx


def _best_ticket_match(artikel: str, ticket_idx: dict[str, int]) -> tuple[str, int, float]:
    best_cluster = ""
    best_count = 0
    best_score = 0.0
    for cluster, count in ticket_idx.items():
        score = match_score(cluster, artikel)
        if score > best_score:
            best_score = score
            best_cluster = cluster
            best_count = count
    if best_score < _MATCH_THRESHOLD:
        return "", 0, 0.0
    return best_cluster, best_count, best_score


def _norm_series(values: pd.Series) -> pd.Series:
    if values.empty:
        return values
    mx = float(values.max() or 0)
    if mx <= 0:
        return values * 0.0
    return (values / mx).clip(0, 1)


def build_priority_matrix(
    ticket_rows: list[dict[str, Any]],
    *,
    limit: int = 20,
) -> pd.DataFrame:
    """
    Prioritäts-Matrix: ERP-Umsatz + Ticket-Last → PM-Prioritätsscore (0–100).

    ticket_rows: z. B. support-Cluster aus Snapshot [{cluster, anzahl}, …]
    """
    revenue_df = load_sales_revenue_by_product()
    if revenue_df.empty:
        return pd.DataFrame(
            columns=[
                "produkt",
                "produktlinie",
                "summe_umsatz",
                "anzahl_kunden",
                "ticket_cluster",
                "ticket_anzahl",
                "match_score",
                "match_art",
                "mapping_id",
                "prioritaet_score",
                "prioritaet_stufe",
            ]
        )

    ticket_idx = _ticket_index(ticket_rows)
    rows: list[dict[str, Any]] = []

    for rec in revenue_df.head(max(limit * 3, 60)).itertuples():
        artikel = str(rec.artikelbezeichnung)
        cluster, tickets, mscore, match_art, mapping_id = resolve_product_tickets(
            artikel,
            ticket_idx,
            heuristic_match_fn=_best_ticket_match,
        )
        rows.append(
            {
                "produkt": artikel,
                "produktlinie": classify_product_line(artikel),
                "summe_umsatz": float(rec.summe_umsatz),
                "anzahl_kunden": int(rec.anzahl_kunden),
                "ticket_cluster": cluster,
                "ticket_anzahl": tickets,
                "match_score": round(mscore, 2),
                "match_art": match_art,
                "mapping_id": mapping_id,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["umsatz_norm"] = _norm_series(df["summe_umsatz"])
    df["ticket_norm"] = _norm_series(df["ticket_anzahl"].astype(float))
    # Umsatz stärker gewichtet — «wo viel Geld liegt, zählt Priorität mehr»
    df["prioritaet_score"] = (
        (0.55 * df["umsatz_norm"] + 0.45 * df["ticket_norm"]) * 100
    ).round(1)

    def _stufe(score: float, tickets: int, umsatz: float) -> str:
        if score >= 65:
            return "Hoch"
        if score >= 35 or (tickets >= 10 and umsatz > 0):
            return "Mittel"
        return "Niedrig"

    df["prioritaet_stufe"] = [
        _stufe(s, t, u) for s, t, u in zip(df["prioritaet_score"], df["ticket_anzahl"], df["summe_umsatz"])
    ]

    return (
        df.sort_values(["prioritaet_score", "summe_umsatz"], ascending=False)
        .head(limit)
        .drop(columns=["umsatz_norm", "ticket_norm"])
        .reset_index(drop=True)
    )


def priority_insights(matrix: pd.DataFrame, *, top_n: int = 3) -> list[str]:
    if matrix.empty:
        return ["Keine ERP-Umsatzdaten — Rohe_Sales_Daten.xlsx und Pipeline-Schritt «sales» ausführen."]
    lines: list[str] = []
    for row in matrix.head(top_n).itertuples():
        umsatz = f"{row.summe_umsatz:,.0f} €".replace(",", ".")
        ticket_part = f", {row.ticket_anzahl} Tickets" if row.ticket_anzahl else ", wenig Ticket-Signal"
        lines.append(
            f"**{row.produkt}** — Priorität {row.prioritaet_stufe} "
            f"(Score {row.prioritaet_score:.0f}): Umsatz {umsatz}{ticket_part}."
        )
    high_pain = matrix[matrix["ticket_anzahl"] >= 15].sort_values("ticket_anzahl", ascending=False)
    if not high_pain.empty:
        row = high_pain.iloc[0]
        if row["summe_umsatz"] < matrix["summe_umsatz"].quantile(0.5):
            lines.append(
                f"Gap: **{row.produkt}** — viele Tickets ({int(row.ticket_anzahl)}×), "
                "aber unterdurchschnittlicher Umsatz → UX/Support vor Ausbau."
            )
    return lines


def seed_mapping_status() -> dict[str, Any]:
    entries = load_mapping_entries()
    return {
        "path": str(MAPPING_PATH),
        "count": len(entries),
        "ids": [e.id for e in entries],
    }
