"""
Hotline-Bestand — Abgleich HTML-Ordner, Scraper-Scope, BigQuery, Product Signals.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from config import BIGQUERY_HTML_TABLE, TICKETS_BACKLOG_CSV, TICKETS_HTML_DIR, setup_gcp_credentials
from core.hotline_scope import DEFAULT_BEREICHE, ticket_in_hotline_scope
from core.html_ticket_reader import iter_html_tickets
from core.tera_scope import is_tera_hotline_cluster


@dataclass(frozen=True)
class HotlineInventory:
    html_files: int
    html_readable: int
    html_skipped_short: int
    scraper_scope_count: int
    bigquery_rows: int | None
    backlog_csv_rows: int | None
    product_signals_sum: int | None
    tera_scope_count: int

    @property
    def product_signals_scope_count(self) -> int:
        """Scraper-Scope ohne TERA — Product Signals zählt nur riwaGis + otsBau."""
        return self.scraper_scope_count - self.tera_scope_count

    @property
    def aligned(self) -> bool:
        """Scraper-Scope, CSV/BQ und Product Signals stimmen überein."""
        if self.product_signals_sum is None:
            return False
        # Product Signals schließt teraWinData bewusst aus (TERA = eigener Tab/Produktlinie).
        if self.product_signals_sum != self.product_signals_scope_count:
            return False
        if self.backlog_csv_rows is not None and self.backlog_csv_rows != self.scraper_scope_count:
            return False
        if self.bigquery_rows is not None and self.bigquery_rows != self.scraper_scope_count:
            return False
        return True


def _count_local_html() -> tuple[int, int, int, int, int]:
    from core.html_ticket_reader import read_html_ticket

    root = TICKETS_HTML_DIR
    if not root.exists():
        return 0, 0, 0, 0, 0
    files = list(root.rglob("*.html"))
    readable = 0
    skipped = 0
    in_scope = 0
    tera_in_scope = 0
    for path in files:
        row = read_html_ticket(root, path)
        if not row:
            skipped += 1
            continue
        readable += 1
        if ticket_in_hotline_scope(row):
            in_scope += 1
            if is_tera_hotline_cluster(row.get("cluster") or ""):
                tera_in_scope += 1
    return len(files), readable, skipped, in_scope, tera_in_scope


def _count_backlog_csv() -> int | None:
    if not TICKETS_BACKLOG_CSV.exists():
        return None
    try:
        import pandas as pd

        df = pd.read_csv(TICKETS_BACKLOG_CSV, sep=";", encoding="utf-8-sig")
        return len(df)
    except Exception:
        return None


def _count_bigquery_html() -> int | None:
    try:
        setup_gcp_credentials()
        from google.cloud import bigquery

        client = bigquery.Client()
        table = BIGQUERY_HTML_TABLE
        query = f"SELECT COUNT(*) AS n FROM `{table}`"
        return int(list(client.query(query).result())[0].n)
    except Exception:
        return None


def clear_hotline_inventory_cache() -> None:
    hotline_inventory.cache_clear()


@lru_cache(maxsize=1)
def hotline_inventory(*, product_signals_sum: int | None = None) -> HotlineInventory:
    html_files, readable, skipped, in_scope, tera_in_scope = _count_local_html()
    return HotlineInventory(
        html_files=html_files,
        html_readable=readable,
        html_skipped_short=skipped,
        scraper_scope_count=in_scope,
        bigquery_rows=_count_bigquery_html(),
        backlog_csv_rows=_count_backlog_csv(),
        product_signals_sum=product_signals_sum,
        tera_scope_count=tera_in_scope,
    )


def hotline_inventory_explain(inv: HotlineInventory) -> str:
    def fmt(n: int) -> str:
        return f"{n:,}".replace(",", ".")

    scope = ", ".join(DEFAULT_BEREICHE)
    lines = [
        f"**Rohdaten-Ordner:** {fmt(inv.html_readable)} auswertbare HTML "
        f"({fmt(inv.html_files)} Dateien, {inv.html_skipped_short} leer/zu kurz)",
        f"**Scraper-Scope** ({scope}, ohne Allgemein): **{fmt(inv.scraper_scope_count)}** Tickets",
    ]
    if inv.backlog_csv_rows is not None:
        lines.append(f"**tickets_backlog.csv:** {fmt(inv.backlog_csv_rows)} Zeilen")
    if inv.bigquery_rows is not None:
        lines.append(f"**BigQuery (Portal):** {fmt(inv.bigquery_rows)} Zeilen")
    if inv.product_signals_sum is not None:
        lines.append(f"**Product Signals Hotline Σ:** {fmt(inv.product_signals_sum)} (riwaGis + otsBau)")
    if inv.tera_scope_count:
        lines.append(
            f"**TERA (teraWinData, separater Tab):** {fmt(inv.tera_scope_count)} — "
            "nicht in Product Signals Σ"
        )

    if inv.aligned:
        lines.append(
            "Scraper, Product Signals (ohne TERA)"
            + (", BigQuery" if inv.bigquery_rows is not None else "")
            + f" sind **abgestimmt** ({fmt(inv.product_signals_scope_count)} RIWA/OTS + "
            f"{fmt(inv.tera_scope_count)} TERA = {fmt(inv.scraper_scope_count)} Hotline-Tickets)."
        )
    else:
        parts: list[str] = []
        if inv.product_signals_sum != inv.product_signals_scope_count:
            parts.append(
                f"Product Signals ({fmt(inv.product_signals_sum or 0)}) ≠ RIWA/OTS-Scope "
                f"({fmt(inv.product_signals_scope_count)}) — `python extract_product_signals.py`"
            )
        if inv.backlog_csv_rows is not None and inv.backlog_csv_rows != inv.scraper_scope_count:
            parts.append(
                f"tickets_backlog.csv ({fmt(inv.backlog_csv_rows)}) ≠ Scraper-Scope — "
                "`python scrape_html_tickets.py`"
            )
        if inv.bigquery_rows is not None and inv.bigquery_rows != inv.scraper_scope_count:
            parts.append(
                f"BigQuery ({fmt(inv.bigquery_rows)}) ≠ Scraper-Scope — Pipeline-Upload prüfen"
            )
        lines.append("Abweichung: " + " · ".join(parts) if parts else "Zählung unvollständig.")
    return "\n\n".join(lines)
