"""Sales Product Penetration — lokale CSV-Evidenz (kein Freitext, kein RAG)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import SALES_PRODUCT_PENETRATION_CSV, SALES_PRODUCT_PENETRATION_ROOT

SALES_TECHNICAL_NAME = "sales_product_penetration"
SALES_LABEL = "Verträge / Penetration"


def resolve_sales_csv_path() -> Path | None:
    for path in (SALES_PRODUCT_PENETRATION_CSV, SALES_PRODUCT_PENETRATION_ROOT):
        if path.exists():
            return path
    return None


def load_sales_penetration() -> pd.DataFrame:
    path = resolve_sales_csv_path()
    if path is None:
        return pd.DataFrame(
            columns=[
                "Kundentyp",
                "artikelbezeichnung",
                "artikel",
                "Anzahl_Kunden",
                "Anzahl_Vertragspositionen",
                "Summe_Menge",
                "Summe_Umsatz",
            ]
        )

    df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
    for col in ("Anzahl_Kunden", "Anzahl_Vertragspositionen", "Summe_Menge", "Summe_Umsatz"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    if "artikelbezeichnung" in df.columns:
        df["artikelbezeichnung"] = df["artikelbezeichnung"].astype(str).str.strip()
    if "Kundentyp" in df.columns:
        df["Kundentyp"] = df["Kundentyp"].astype(str).str.strip()
    return df


def sales_row_count() -> int:
    return len(load_sales_penetration())


def sales_fingerprint_token() -> str:
    path = resolve_sales_csv_path()
    if path is None:
        return "sales:missing"
    stat = path.stat()
    return f"sales:{path.name}:{stat.st_mtime_ns}:{stat.st_size}"


def load_sales_revenue_by_product() -> pd.DataFrame:
    """Aggregiert ERP-Umsatz (Summe_Umsatz) über alle Kundentypen pro Artikel."""
    df = load_sales_penetration()
    if df.empty or "Summe_Umsatz" not in df.columns:
        return pd.DataFrame(columns=["artikelbezeichnung", "summe_umsatz", "anzahl_kunden"])

    grouped = (
        df.groupby("artikelbezeichnung", dropna=False)
        .agg(
            summe_umsatz=("Summe_Umsatz", "sum"),
            anzahl_kunden=("Anzahl_Kunden", "sum"),
        )
        .reset_index()
        .sort_values("summe_umsatz", ascending=False)
    )
    grouped["summe_umsatz"] = grouped["summe_umsatz"].round(2)
    return grouped


def top_products_by_revenue(limit: int = 10, kundentyp: str | None = None) -> pd.DataFrame:
    df = load_sales_penetration()
    if df.empty or "Summe_Umsatz" not in df.columns:
        return pd.DataFrame(columns=["quelle", "cluster", "umsatz", "Kundentyp"])

    if kundentyp:
        df = df[df["Kundentyp"] == kundentyp]

    grouped = (
        df.groupby("artikelbezeichnung", dropna=False)["Summe_Umsatz"]
        .sum()
        .reset_index()
        .rename(columns={"artikelbezeichnung": "cluster", "Summe_Umsatz": "umsatz"})
        .sort_values("umsatz", ascending=False)
        .head(limit)
    )
    grouped["quelle"] = SALES_LABEL
    grouped["Kundentyp"] = kundentyp or "Alle"
    grouped["umsatz"] = grouped["umsatz"].round(2)
    return grouped[["quelle", "cluster", "umsatz", "Kundentyp"]]


def total_revenue() -> float:
    df = load_sales_penetration()
    if df.empty or "Summe_Umsatz" not in df.columns:
        return 0.0
    return float(df["Summe_Umsatz"].sum())


def top_products(limit: int = 10, kundentyp: str | None = None) -> pd.DataFrame:
    df = load_sales_penetration()
    if df.empty:
        return pd.DataFrame(columns=["quelle", "cluster", "anzahl", "Kundentyp"])

    if kundentyp:
        df = df[df["Kundentyp"] == kundentyp]

    grouped = (
        df.groupby("artikelbezeichnung", dropna=False)["Anzahl_Kunden"]
        .sum()
        .reset_index()
        .rename(columns={"artikelbezeichnung": "cluster", "Anzahl_Kunden": "anzahl"})
        .sort_values("anzahl", ascending=False)
        .head(limit)
    )
    grouped["quelle"] = SALES_LABEL
    grouped["Kundentyp"] = kundentyp or "Alle"
    return grouped[["quelle", "cluster", "anzahl", "Kundentyp"]]


def top_by_kundentyp(limit: int = 8) -> pd.DataFrame:
    df = load_sales_penetration()
    if df.empty:
        return pd.DataFrame(columns=["Kundentyp", "Anzahl_Kunden", "Produkte"])

    return (
        df.groupby("Kundentyp", dropna=False)
        .agg(
            Anzahl_Kunden=("Anzahl_Kunden", "sum"),
            Produkte=("artikelbezeichnung", "nunique"),
        )
        .reset_index()
        .sort_values("Anzahl_Kunden", ascending=False)
        .head(limit)
    )


def penetration_detail(limit: int = 15) -> pd.DataFrame:
    df = load_sales_penetration()
    if df.empty:
        return df
    cols = [
        c
        for c in (
            "Kundentyp",
            "artikelbezeichnung",
            "artikel",
            "Anzahl_Kunden",
            "Anzahl_Vertragspositionen",
        )
        if c in df.columns
    ]
    return df[cols].sort_values("Anzahl_Kunden", ascending=False).head(limit)


def collect_sales_theme_scores(limit: int = 30) -> dict[str, dict]:
    from workspace.compare import THEME_KEYWORDS, themes_in_text

    df = load_sales_penetration()
    scores: dict[str, dict] = {
        t: {"score": 0, "clusters": [], "samples": [], "quelle": SALES_LABEL}
        for t in THEME_KEYWORDS
    }
    if df.empty:
        return scores

    grouped = (
        df.groupby("artikelbezeichnung", dropna=False)["Anzahl_Kunden"]
        .sum()
        .reset_index()
        .sort_values("Anzahl_Kunden", ascending=False)
        .head(limit)
    )

    for row in grouped.itertuples():
        product = str(row.artikelbezeichnung)
        count = int(row.Anzahl_Kunden)
        themes = themes_in_text(product, from_cluster=True)
        for theme in themes:
            scores[theme]["score"] += count
            entry = f"{product} ({count} Kunden)"
            if entry not in scores[theme]["clusters"]:
                scores[theme]["clusters"].append(entry)

    return scores


def build_sales_context(top_n: int = 10) -> str:
    df = load_sales_penetration()
    if df.empty:
        return (
            f"--- {SALES_LABEL} ---\n"
            "Keine Sales-Daten — sales_prep.py oder Pipeline-Schritt sales ausführen."
        )

    total_customers = int(df["Anzahl_Kunden"].sum()) if "Anzahl_Kunden" in df.columns else len(df)
    revenue_total = total_revenue()
    products = top_products(top_n)
    revenue = top_products_by_revenue(top_n)
    segments = top_by_kundentyp(5)

    lines = [
        f"--- {SALES_LABEL} (aggregiert, anonym) ---",
        f"Segmente×Produkte: {len(df)} Zeilen · Summe Kunden (über Segmente): {total_customers}",
    ]
    if revenue_total > 0:
        lines.append(f"Summe Vertragsumsatz (ERP gesamt): {revenue_total:,.0f} EUR".replace(",", "."))

    lines.append("Top-Produkte nach Umsatz (ERP):")
    if revenue.empty:
        lines.append("  · (keine Umsatzspalte — sales_prep neu ausführen)")
    else:
        for row in revenue.itertuples():
            lines.append(f"  · {row.cluster}: {row.umsatz:,.0f} EUR".replace(",", "."))

    lines.append("Top-Produkte (Summe Anzahl_Kunden):")
    for row in products.itertuples():
        lines.append(f"  · {row.cluster}: {int(row.anzahl)} Kunden")

    lines.append("Top-Kundentypen:")
    for row in segments.itertuples():
        lines.append(
            f"  · {row.Kundentyp}: {int(row.Anzahl_Kunden)} Kunden · {int(row.Produkte)} Produkte"
        )
    return "\n".join(lines)
