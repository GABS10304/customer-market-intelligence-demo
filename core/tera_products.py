"""TERA ERP-Lizenzexport — laden und auf Basis-Produktcodes normalisieren."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from config import DATA_DIR, TERA_INSTALLATIONS_CSV, ROOT_DIR


TERA_INSTALLATIONS_FALLBACK = ROOT_DIR / "tera.csv"


def resolve_tera_installations_path() -> Path:
    if TERA_INSTALLATIONS_CSV.exists():
        return TERA_INSTALLATIONS_CSV
    if TERA_INSTALLATIONS_FALLBACK.exists():
        return TERA_INSTALLATIONS_FALLBACK
    return TERA_INSTALLATIONS_CSV


def normalize_tera_product_code(code: str | float | None) -> str:
    """
    Nur Basis-Familie behalten: TERA-RES-Technik → TERA-RES, TERA-FRI-Zusatzmodul → TERA-FRI.
    TERAmobil-* → TERAmobil. Alles nach dem zweiten Bindestrich wird ignoriert.
    """
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return ""
    raw = str(code).strip()
    if not raw:
        return ""

    upper = raw.upper()
    if upper.startswith("TERAMOBIL"):
        return "TERAmobil"

    parts = raw.split("-")
    if len(parts) >= 2 and parts[0].upper() == "TERA":
        return f"{parts[0]}-{parts[1]}".upper()

    return raw


def resolve_tera_csv_path() -> Path | None:
    path = resolve_tera_installations_path()
    return path if path.exists() else None


@lru_cache(maxsize=1)
def load_tera_installations_raw() -> pd.DataFrame:
    path = resolve_tera_installations_path()
    if not path.exists():
        return pd.DataFrame(
            columns=[
                "BEHOERDEN_NAME",
                "BEHOERDEN_NR",
                "produkt_raw",
                "produkt_base",
                "OBJEKT_NR",
                "LIZENZNR",
                "INSTALLATIONS_DAT",
            ]
        )

    df = pd.read_csv(path, sep=";", encoding="utf-8-sig", on_bad_lines="skip")
    if "BEZEICHNUNG.1" in df.columns:
        df = df.rename(columns={"BEZEICHNUNG.1": "produkt_raw"})
    elif "BEZEICHNUNG" in df.columns:
        df = df.rename(columns={"BEZEICHNUNG": "produkt_raw"})
    else:
        for col in df.columns:
            if str(col).lower().startswith("bezeichnung"):
                df = df.rename(columns={col: "produkt_raw"})
                break

    if "BEHOERDEN_NAME" not in df.columns:
        return pd.DataFrame()

    df["produkt_base"] = df["produkt_raw"].map(normalize_tera_product_code)
    df = df[df["produkt_base"].astype(str).str.len() > 0].copy()
    return df


@lru_cache(maxsize=1)
def tera_installation_by_product() -> pd.DataFrame:
    """Aggregiert Lizenzzeilen pro Basis-Produktcode."""
    df = load_tera_installations_raw()
    if df.empty:
        return pd.DataFrame(columns=["tera_base", "installationen", "kunden"])

    grouped = (
        df.groupby("produkt_base", dropna=False)
        .agg(
            installationen=("produkt_base", "size"),
            kunden=("BEHOERDEN_NAME", "nunique"),
        )
        .reset_index()
        .rename(columns={"produkt_base": "tera_base"})
        .sort_values("installationen", ascending=False)
    )
    return grouped


def clear_tera_installation_cache() -> None:
    load_tera_installations_raw.cache_clear()
    tera_installation_by_product.cache_clear()
