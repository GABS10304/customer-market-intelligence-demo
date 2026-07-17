"""Hotline inventory alignment — Product Signals vs. Scraper scope."""

from core.hotline_inventory import HotlineInventory


def _inventory(
    *,
    scraper: int = 1032,
    tera: int = 271,
    product_signals_sum: int | None = 761,
    backlog: int | None = 1032,
    bq: int | None = None,
) -> HotlineInventory:
    return HotlineInventory(
        html_files=0,
        html_readable=0,
        html_skipped_short=0,
        scraper_scope_count=scraper,
        bigquery_rows=bq,
        backlog_csv_rows=backlog,
        product_signals_sum=product_signals_sum,
        tera_scope_count=tera,
    )


def test_aligned_when_product_signals_matches_riwa_ots_scope():
    inv = _inventory()
    assert inv.product_signals_scope_count == 761
    assert inv.aligned is True


def test_not_aligned_when_product_signals_differs_from_riwa_ots_scope():
    inv = _inventory(product_signals_sum=700)
    assert inv.aligned is False


def test_not_aligned_when_only_total_scraper_matches_but_ps_excludes_tera():
    """761 + 271 TERA = 1032 scraper — PS sum must not be compared to full scraper count."""
    inv = _inventory(product_signals_sum=761, scraper=1032, tera=271, backlog=1032)
    assert inv.product_signals_sum != inv.scraper_scope_count
    assert inv.aligned is True


def test_not_aligned_when_backlog_csv_differs_from_scraper():
    inv = _inventory(backlog=900)
    assert inv.aligned is False


def test_not_aligned_when_product_signals_sum_missing():
    inv = _inventory(product_signals_sum=None)
    assert inv.aligned is False
