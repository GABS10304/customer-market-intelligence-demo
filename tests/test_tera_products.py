from core.tera_products import normalize_tera_product_code


def test_normalize_tera_product_strips_suffix():
    assert normalize_tera_product_code("TERA-RES-Technik") == "TERA-RES"
    assert normalize_tera_product_code("TERA-FRI-Zusatzmodul") == "TERA-FRI"
    assert normalize_tera_product_code("TERA-MAP") == "TERA-MAP"
    assert normalize_tera_product_code("TERAmobil Aufträge") == "TERAmobil"


def test_normalize_tera_product_empty():
    assert normalize_tera_product_code("") == ""
    assert normalize_tera_product_code(None) == ""
