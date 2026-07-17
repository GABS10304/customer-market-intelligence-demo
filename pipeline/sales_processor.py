"""Sales Product Penetration — sales_prep → data/sales_product_penetration.csv."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from typing import Any, Callable

from config import (
    SALES_PRODUCT_PENETRATION_CSV,
    SALES_PRODUCT_PENETRATION_ROOT,
    SALES_RAW_XLSX,
    ensure_data_dirs,
)
from core.sales_evidence import sales_row_count
from workspace.catalog import load_catalog, save_catalog

LogFn = Callable[[str], None]


def _default_log(message: str) -> None:
    print(message)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _update_catalog(rows: int, log: LogFn) -> None:
    catalog = load_catalog()
    entry = catalog.get("sources", {}).get("sales_product_penetration", {})
    catalog.setdefault("sources", {})["sales_product_penetration"] = {
        **entry,
        "technical_name": "sales_product_penetration",
        "display_name": entry.get("display_name", "Verträge / Modul-Penetration"),
        "status": entry.get("status", "active"),
        "last_updated": _now(),
        "row_count": rows,
        "mapping_status": "confirmed",
        "source_type": "builtin",
    }
    save_catalog(catalog)
    log(f"Catalog: sales_product_penetration → {rows} Zeilen")


def sync_sales_product_data(*, log: LogFn = _default_log) -> dict[str, Any]:
    """Rohe Excel aufbereiten (falls vorhanden) und CSV unter data/ bereitstellen."""
    ensure_data_dirs()
    result: dict[str, Any] = {"ok": False, "rows": 0, "source": None}

    if SALES_RAW_XLSX.exists():
        log(f"Sales: {SALES_RAW_XLSX.name} gefunden — sales_prep ausführen…")
        import sales_prep

        frame = sales_prep.process_sales_data(
            input_file=str(SALES_RAW_XLSX),
            output_file=str(SALES_PRODUCT_PENETRATION_ROOT),
        )
        if frame is None:
            log("Sales: sales_prep fehlgeschlagen.")
            return result
        result["source"] = "sales_prep"
    elif SALES_PRODUCT_PENETRATION_ROOT.exists():
        log("Sales: nutze vorhandene Sales_Product_Penetration.csv im Root.")
        result["source"] = "root_csv"
    else:
        log("Sales: keine Rohe_Sales_Daten.xlsx und keine Sales_Product_Penetration.csv.")
        return result

    if not SALES_PRODUCT_PENETRATION_ROOT.exists():
        return result

    shutil.copy2(SALES_PRODUCT_PENETRATION_ROOT, SALES_PRODUCT_PENETRATION_CSV)
    rows = sales_row_count()
    _update_catalog(rows, log)
    log(f"Sales: {SALES_PRODUCT_PENETRATION_CSV.name} ({rows} Zeilen)")
    result["ok"] = True
    result["rows"] = rows
    return result
