"""
Umfrage-Rohdaten — tickets_b.csv laden und Landkreis→ERP matchen.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

from config import DELIMITER, INBOX_SURVEYS_DIR, SALES_RAW_XLSX
from core.product_mapping import find_seed_mapping
from sales_prep import load_sales_frame

SURVEY_SOURCE_LABEL = "Kundenumfrage"
SURVEY_SOURCE_FILE = "tickets_b.csv"


def _norm_compact(text: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", "", (text or "").lower())


def _pick_col(columns: list[str], *hints: str) -> str | None:
    for col in columns:
        lower = col.lower()
        if any(h in lower for h in hints):
            return col
    return None


@lru_cache(maxsize=1)
def _erp_customers() -> list[tuple[str, str]]:
    path = SALES_RAW_XLSX
    if not path.exists():
        return []
    df = load_sales_frame(str(path))
    cols = {c.lower(): c for c in df.columns}
    kcol = cols.get("kunde")
    if not kcol:
        return []
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for raw in df[kcol].dropna().astype(str):
        name = raw.strip()
        key = _norm_compact(name)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append((key, name))
    return out


def match_landkreis_to_kunde(landkreis: str) -> str:
    needle = _norm_compact(landkreis)
    if not needle or len(needle) < 3:
        return ""
    best = ""
    best_len = 0
    for key, name in _erp_customers():
        if needle == key:
            return name
        if len(needle) >= 4 and (needle in key or key in needle):
            if len(key) > best_len:
                best = name
                best_len = len(key)
    return best


@lru_cache(maxsize=1)
def customer_product_mapping_ids() -> dict[str, list[str]]:
    path = SALES_RAW_XLSX
    if not path.exists():
        return {}
    df = load_sales_frame(str(path))
    cols = {c.lower(): c for c in df.columns}
    kcol = cols.get("kunde")
    acol = cols.get("artikelbezeichnung")
    if not kcol or not acol:
        return {}
    out: dict[str, set[str]] = {}
    for _, row in df.iterrows():
        kunde = str(row.get(kcol) or "").strip()
        artikel = str(row.get(acol) or "").strip()
        if not kunde or not artikel:
            continue
        entry = find_seed_mapping(artikel)
        if not entry:
            continue
        out.setdefault(kunde, set()).add(entry.id)
    return {k: sorted(v) for k, v in out.items()}


def discover_survey_csv() -> Path | None:
    preferred = INBOX_SURVEYS_DIR / SURVEY_SOURCE_FILE if INBOX_SURVEYS_DIR.exists() else None
    if preferred and preferred.exists():
        return preferred
    if not INBOX_SURVEYS_DIR.exists():
        return None
    files = sorted(INBOX_SURVEYS_DIR.glob("*.csv"))
    return files[0] if files else None


def load_survey_frame(path: Path | None = None) -> pd.DataFrame:
    src = path or discover_survey_csv()
    if not src or not src.exists():
        return pd.DataFrame()
    return pd.read_csv(src, sep=DELIMITER, encoding="utf-8-sig", on_bad_lines="skip")


def survey_column_map(df: pd.DataFrame) -> dict[str, str]:
    cols = list(df.columns)
    return {
        "landkreis": _pick_col(cols, "landkreis") or cols[1] if len(cols) > 1 else "",
        "freitext": _pick_col(cols, "anregung", "wünsche", "wunsche", "verbesserung") or (cols[16] if len(cols) > 16 else ""),
        "nps": _pick_col(cols, "weiterempfehl") or (cols[-1] if cols else ""),
        "ux": _pick_col(cols, "benutzerfreundlichkeit") or "",
        "stabilitaet": _pick_col(cols, "stabilit") or "",
        "updates": _pick_col(cols, "software-updates", "updates") or "",
        "fachmodule": _pick_col(cols, "fachmodule") or "",
        "support": _pick_col(cols, "kundensupports") or "",
        "dienstleistung": _pick_col(cols, "dienstleistungen") or "",
    }
