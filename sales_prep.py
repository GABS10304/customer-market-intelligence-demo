"""
Sales-Daten für Product Intelligence: Kundentyp × Modul × Penetration + Umsatz (ERP).

ERP-Export (Excel) — Spaltenlogik Vertragspositionen
------------------------------------------------------
| Spalte | Feld         | Bedeutung |
|--------|--------------|-----------|
| L      | Einzelpreis  | Basispreis der Position (z. B. Pauschalpreis Modul) |
| M      | Prozent      | Anteil bezogen auf Einzelpreis (z. B. 24 % Wartung → Wartungspauschale) |
| N      | Rabatt       | Rabatt bezogen auf Einzelpreis (nicht mit Prozent verwechseln) |
| Q      | gesamt       | Ergebnispreis der Zeile (typisch Einzelpreis × Prozent × Menge) |

Dieses Skript exportiert Penetration (Kunden) und Summe_Umsatz pro Produkt/Segment.
"""

from __future__ import annotations

import os

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "Rohe_Sales_Daten.xlsx")
OUTPUT_FILE = os.path.join(BASE_DIR, "Sales_Product_Penetration.csv")
LEGACY_OUTPUT_FILE = os.path.join(BASE_DIR, "Sales_ICP_Strategie_Daten.csv")

# ERP-Export: Spaltenbuchstaben → typische Header-Namen (nach lower/strip in load_sales_frame)
ERP_PRICE_FIELDS = {
    "einzelpreis": "L",   # Basispreis Position
    "prozent": "M",       # Anteil auf Einzelpreis (z. B. Wartungs-%)
    "rabatt": "N",        # Rabatt auf Einzelpreis
    "gesamtpreis": "Q",   # abgeleiteter Gesamtpreis
}


def finde_spalte(spalten_liste: list[str], suchbegriffe: list[str]) -> str | None:
    for spalte in spalten_liste:
        for begriff in suchbegriffe:
            if begriff in spalte:
                return spalte
    return None


def finde_artikel_bezeichnung(spalten: list[str]) -> str | None:
    for begriff in ("artikelbezeichnung", "artikelgruppe", "bezeichnung"):
        hit = finde_spalte(spalten, [begriff])
        if hit:
            return hit
    return None


def finde_artikel_nr(spalten: list[str]) -> str | None:
    for spalte in spalten:
        name = spalte.strip().lower()
        if name in {"artikel", "art.nr.", "art.nr", "artikelnr", "artikelnr."}:
            return spalte
    for spalte in spalten:
        name = spalte.strip().lower()
        if "bezeichnung" in name or "gruppe" in name:
            continue
        if name.startswith("art") or "art.nr" in name:
            return spalte
    return None


def extrahiere_kundentyp(name: str) -> str:
    name_lower = name.lower()
    org_formen = {
        "bistum": "Bistum / Kirche",
        "diözese": "Bistum / Kirche",
        "pfarrei": "Bistum / Kirche",
        "zweckverband": "Zweckverband",
        "wasserverband": "Zweckverband",
        "zwa": "Zweckverband",
        "gmbh": "Privatwirtschaft (Firma)",
        " ag ": "Privatwirtschaft (Firma)",
        "& co": "Privatwirtschaft (Firma)",
        "verwaltungsgemeinschaft": "Verwaltungsgemeinschaft (VG)",
        "vg ": "Verwaltungsgemeinschaft (VG)",
        "landratsamt": "Landkreis (LRA)",
        "landkreis": "Landkreis (LRA)",
        "stadt": "Stadt",
        "markt ": "Marktgemeinde",
        "marktgemeinde": "Marktgemeinde",
        "gemeinde": "Gemeinde",
    }
    for schluesselwort, kategorie in org_formen.items():
        if schluesselwort in name_lower:
            return kategorie
    return "Behörde/Orga (ohne Kürzel)"


def load_sales_frame(path: str) -> pd.DataFrame:
    if path.lower().endswith(".csv"):
        return pd.read_csv(path, sep=";", encoding="utf-8-sig", on_bad_lines="skip")
    return pd.read_excel(path, sheet_name=0)


def _parse_erp_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    ).fillna(0)


def _find_price_column(columns: list[str], hints: tuple[str, ...]) -> str | None:
    for col in columns:
        lower = col.lower().strip()
        if lower in hints:
            return col
    for col in columns:
        lower = col.lower()
        if any(h in lower for h in hints):
            return col
    return None


def _line_umsatz(row: pd.Series, *, gesamt_col: str | None) -> float:
    if gesamt_col:
        val = float(row.get(gesamt_col) or 0)
        if val > 0:
            return val

    einzel = float(row.get("_einzelpreis") or 0)
    menge = float(row.get("_menge") or 1)
    prozent = float(row.get("_prozent") or 0)
    rabatt = float(row.get("_rabatt") or 0)

    base = einzel * menge
    if rabatt > 0:
        if rabatt <= 1:
            return base * (1 - rabatt)
        return max(0.0, base - rabatt)
    if prozent > 0:
        return base * prozent
    preis = float(row.get("_preis") or 0)
    if preis > 0:
        return preis * menge
    return base


def process_sales_data(
    input_file: str = INPUT_FILE,
    output_file: str = OUTPUT_FILE,
) -> pd.DataFrame | None:
    print("Starte Product-Penetration aus Vertragsdaten...")

    if not os.path.exists(input_file):
        print(f"Fehler: Datei {input_file} nicht gefunden!")
        print("Bitte Rohe_Sales_Daten.xlsx (oder .csv) ins Projektroot legen.")
        return None

    try:
        df = load_sales_frame(input_file)
        if not input_file.lower().endswith(".csv"):
            print("Excel-Vertragsdaten gelesen.")
    except Exception as exc:
        print(f"Dateifehler beim Laden: {exc}")
        return None

    df.columns = df.columns.str.lower().str.strip()

    kd_col = "kunde" if "kunde" in df.columns else finde_spalte(list(df.columns), ["kunde", "name"])
    artikel_col = finde_artikel_bezeichnung(list(df.columns))
    artikel_nr_col = finde_artikel_nr(list(df.columns))
    menge_col = finde_spalte(list(df.columns), ["menge"])
    gesamt_col = _find_price_column(list(df.columns), ("gesamt", "gesamtpreis"))
    einzel_col = _find_price_column(list(df.columns), ("einzelpreis",))
    prozent_col = _find_price_column(list(df.columns), ("prozent",))
    rabatt_col = _find_price_column(list(df.columns), ("rabatt",))
    preis_col = _find_price_column(list(df.columns), ("preis",))

    if not kd_col or not artikel_col:
        print("Abbruch: Spalten 'Kunde' und 'Artikelbezeichnung' werden benötigt.")
        print(f"Gefundene Spalten: {list(df.columns)}")
        return None

    print(f"{len(df)} Vertragszeilen geladen.")
    print(
        f"Mapping: Kunde={kd_col!r}, Modul={artikel_col!r}, "
        f"Artikel-Nr={artikel_nr_col!r}, Menge={menge_col!r}, Umsatz={gesamt_col!r}"
    )

    df[kd_col] = df[kd_col].fillna("Unbekannt").astype(str)
    df["Kundentyp"] = df[kd_col].apply(extrahiere_kundentyp)
    if menge_col:
        df["_menge"] = _parse_erp_number(df[menge_col]).replace(0, 1)
    else:
        df["_menge"] = 1

    df["_einzelpreis"] = _parse_erp_number(df[einzel_col]) if einzel_col else 0
    df["_prozent"] = _parse_erp_number(df[prozent_col]) if prozent_col else 0
    df["_rabatt"] = _parse_erp_number(df[rabatt_col]) if rabatt_col else 0
    df["_preis"] = _parse_erp_number(df[preis_col]) if preis_col else 0
    df["_umsatz"] = df.apply(lambda row: _line_umsatz(row, gesamt_col=gesamt_col), axis=1)

    group_cols = ["Kundentyp", artikel_col]
    if artikel_nr_col:
        group_cols.append(artikel_nr_col)

    grouped = (
        df.groupby(group_cols, dropna=False)
        .agg(
            Anzahl_Kunden=(kd_col, "nunique"),
            Anzahl_Vertragspositionen=(kd_col, "size"),
            Summe_Menge=("_menge", "sum"),
            Summe_Umsatz=("_umsatz", "sum"),
        )
        .reset_index()
        .sort_values(["Summe_Umsatz", "Anzahl_Kunden"], ascending=False)
    )
    grouped["Summe_Menge"] = grouped["Summe_Menge"].round(2)
    grouped["Summe_Umsatz"] = grouped["Summe_Umsatz"].round(2)

    rename_map = {artikel_col: "artikelbezeichnung"}
    if artikel_nr_col:
        rename_map[artikel_nr_col] = "artikel"
    grouped = grouped.rename(columns=rename_map)

    grouped.to_csv(output_file, sep=";", index=False, encoding="utf-8-sig")
    total_umsatz = grouped["Summe_Umsatz"].sum()
    print(
        f"Export: {os.path.basename(output_file)} ({len(grouped)} Zeilen, "
        f"Summe Umsatz {total_umsatz:,.0f} EUR)."
    )

    from config import SALES_PRODUCT_PENETRATION_CSV, ensure_data_dirs
    ensure_data_dirs()
    grouped.to_csv(SALES_PRODUCT_PENETRATION_CSV, sep=";", index=False, encoding="utf-8-sig")
    print(f"Workspace: {SALES_PRODUCT_PENETRATION_CSV.name}")

    if output_file != LEGACY_OUTPUT_FILE:
        grouped.to_csv(LEGACY_OUTPUT_FILE, sep=";", index=False, encoding="utf-8-sig")
        print(f"Hinweis: Legacy-Kopie für alte Skripte: {os.path.basename(LEGACY_OUTPUT_FILE)}")

    return grouped


if __name__ == "__main__":
    process_sales_data()
