"""
Graylog-Nachrichten → module_usage.csv (aktive Nutzer pro Modul).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from config import DELIMITER
from core.graylog_event_mapping import is_graylog_skipped, resolve_graylog_modul
from core.module_ranking import resolve_ranking_modul

MODULE_FIELD_CANDIDATES = (
    "module",
    "modul",
    "application",
    "app",
    "Modul",
    "Modulname",
    "service",
    "event",
    "moduleKey",
    "dialogName",
    "description",
    "source",
)

USER_FIELD_CANDIDATES = (
    "user_id",
    "userId",
    "username",
    "user",
    "User",
    "login",
    "account",
    "adminId",
    "adminName",
)

METRIC_LABEL = "aktive_nutzer"
SOURCE_LABEL = "graylog"


def flatten_graylog_message(raw: dict[str, Any]) -> dict[str, Any]:
    """Flacht Graylog-Nachricht; parst JSON-String im Feld message."""
    if not isinstance(raw, dict):
        return {}
    flat = dict(raw)
    inner = flat.get("message")
    if isinstance(inner, str):
        text = inner.strip()
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    flat.setdefault(key, value)
    return flat


def normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalisiert Roh-Nachrichten für Feld-Erkennung und Aggregation."""
    return [flatten_graylog_message(msg) for msg in messages if isinstance(msg, dict)]


def _message_field_keys(messages: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for msg in messages:
        if isinstance(msg, dict):
            keys.update(msg.keys())
    return keys


def _pick_field(candidates: tuple[str, ...], available: set[str]) -> str | None:
    for name in candidates:
        if name in available:
            return name
    return None


def detect_fields(
    sample_messages: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    """Erkennt Modul- und Nutzer-Feld aus Beispielnachrichten."""
    available = _message_field_keys(sample_messages)
    module_field = _pick_field(MODULE_FIELD_CANDIDATES, available)
    user_field = _pick_field(USER_FIELD_CANDIDATES, available)
    return module_field, user_field


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ("none", "null", "nan"):
        return ""
    return text




def _module_label_from_message(msg: dict[str, Any], module_field: str) -> str:
    """RGZ-Statistik: dialogName statt generischem event für Dialog-Aktionen."""
    modul = _clean_value(msg.get(module_field))
    if module_field == "event" and modul.startswith("module.dialog."):
        dialog = _clean_value(msg.get("dialogName"))
        if dialog:
            return dialog
    return modul

def aggregate_usage(
    messages: list[dict[str, Any]],
    module_field: str,
    user_field: str,
) -> pd.DataFrame:
    """Zählt eindeutige Nutzer pro Modul."""
    if not module_field or not user_field:
        return pd.DataFrame(columns=["modulname", "aktive_nutzer"])

    pairs: list[tuple[str, str]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        modul = _module_label_from_message(msg, module_field)
        user = _clean_value(msg.get(user_field))
        if modul and user:
            pairs.append((modul, user))

    if not pairs:
        return pd.DataFrame(columns=["modulname", "aktive_nutzer"])

    raw = pd.DataFrame(pairs, columns=["modulname", "user"])
    agg = (
        raw.groupby("modulname", as_index=False)["user"]
        .nunique()
        .rename(columns={"user": "aktive_nutzer"})
        .sort_values("aktive_nutzer", ascending=False)
    )
    agg["aktive_nutzer"] = agg["aktive_nutzer"].astype(int)
    return agg.reset_index(drop=True)


def resolve_usage_mapping_id(modulname: str) -> str:
    """Graylog-Mapping zuerst, dann Modul-Ranking als Fallback."""
    label = (modulname or "").strip()
    if not label or is_graylog_skipped(label):
        return ""
    graylog_id = resolve_graylog_modul(label)
    if graylog_id:
        return graylog_id
    return resolve_ranking_modul(label).mapping_id


def aggregate_usage_by_mapping(
    messages: list[dict[str, Any]],
    module_field: str,
    user_field: str,
) -> pd.DataFrame:
    """
    Zählt eindeutige Nutzer pro mapping_id.

    Graylog-Event-Mapping vor Ranking-Fallback; skip-Events werden ignoriert.
    Nutzer werden über alle Dialoge desselben Produkts dedupliziert.
    """
    if not module_field or not user_field:
        return pd.DataFrame(columns=["mapping_id", "modulname", "aktive_nutzer"])

    users_by_mapping: dict[str, set[str]] = {}
    modulnames_by_mapping: dict[str, set[str]] = {}

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        modul = _module_label_from_message(msg, module_field)
        user = _clean_value(msg.get(user_field))
        if not modul or not user or is_graylog_skipped(modul):
            continue

        mapping_id = resolve_usage_mapping_id(modul)
        if not mapping_id:
            continue

        users_by_mapping.setdefault(mapping_id, set()).add(user)
        modulnames_by_mapping.setdefault(mapping_id, set()).add(modul)

    if not users_by_mapping:
        return pd.DataFrame(columns=["mapping_id", "modulname", "aktive_nutzer"])

    rows: list[dict[str, object]] = []
    for mapping_id, users in users_by_mapping.items():
        modulnames = sorted(modulnames_by_mapping.get(mapping_id, set()))
        if len(modulnames) == 1:
            modulname = modulnames[0]
        elif len(modulnames) <= 3:
            modulname = " | ".join(modulnames)
        else:
            modulname = " | ".join(modulnames[:3]) + f" (+{len(modulnames) - 3})"
        rows.append(
            {
                "mapping_id": mapping_id,
                "modulname": modulname,
                "aktive_nutzer": len(users),
            }
        )

    agg = pd.DataFrame(rows).sort_values("aktive_nutzer", ascending=False)
    agg["aktive_nutzer"] = agg["aktive_nutzer"].astype(int)
    return agg.reset_index(drop=True)


def usage_rows_with_mapping(
    usage_df: pd.DataFrame,
    *,
    stichtag: str | None = None,
    quelle: str = SOURCE_LABEL,
) -> pd.DataFrame:
    """Reichert Usage-DF mit mapping_id und CSV-Spalten an."""
    if usage_df.empty:
        return pd.DataFrame(
            columns=["mapping_id", "modulname", "aktive_nutzer", "metrik", "stichtag", "quelle"]
        )

    tag = stichtag or date.today().isoformat()
    has_mapping = "mapping_id" in usage_df.columns
    rows: list[dict[str, object]] = []
    for _, row in usage_df.iterrows():
        modulname = str(row["modulname"]).strip()
        if has_mapping:
            mapping_id = str(row.get("mapping_id") or "").strip()
        else:
            mapping_id = ""
        if not mapping_id:
            mapping_id = resolve_usage_mapping_id(modulname)
        rows.append(
            {
                "mapping_id": mapping_id,
                "modulname": modulname,
                "aktive_nutzer": int(row["aktive_nutzer"]),
                "metrik": METRIC_LABEL,
                "stichtag": tag,
                "quelle": quelle,
            }
        )
    return pd.DataFrame(rows)


def write_module_usage_csv(df: pd.DataFrame, path: Path) -> int:
    """Schreibt module_usage.csv (Semicolon)."""
    columns = ["mapping_id", "modulname", "aktive_nutzer", "metrik", "stichtag", "quelle"]
    out = df.reindex(columns=columns)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, sep=DELIMITER, index=False, encoding="utf-8-sig")
    return len(out)


def baum_related_label_counts(
    messages: list[dict[str, Any]],
) -> list[tuple[str, int]]:
    """Unique dialogName/event values containing 'baum' (case-insensitive) with counts."""
    counts: dict[str, int] = {}
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        for field in ("dialogName", "event"):
            val = _clean_value(msg.get(field))
            if val and "baum" in val.lower():
                key = f"{field}: {val}"
                counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def top_module_values(
    messages: list[dict[str, Any]],
    module_field: str | None,
    *,
    limit: int = 10,
) -> list[tuple[str, int]]:
    """Häufigste Modulwerte für Probe-Ausgabe."""
    if not module_field:
        return []
    counts: dict[str, int] = {}
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        val = _clean_value(msg.get(module_field))
        if val:
            counts[val] = counts.get(val, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ranked[:limit]
