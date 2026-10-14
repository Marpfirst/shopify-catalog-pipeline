import csv

import pytest

from catalog import export, store
from catalog.mapping import map_row
from catalog.normalize import flatten, norm_value, option_key

RAW = {
    "id": 1, "handle": "malibu-pants", "title": "Malibu Pants", "vendor": "Acme",
    "product_type": "Pants", "tags": ["linen"], "body_html": "<p>Linen</p>",
    "options": [{"name": "Color"}, {"name": "Size"}],
    "variants": [
        {"id": 11, "title": "Black / L", "option1": "Black", "option2": "L", "option3": None,
         "sku": "MP-BLK-L", "price": "49.00", "compare_at_price": "59.00", "available": True, "grams": 400},
        {"id": 12, "title": "Grey / S", "option1": "Grey", "option2": "S", "option3": None,
         "sku": "MP-GRY-S", "price": "49.00", "compare_at_price": None, "available": False, "grams": 380},
    ],
    "images": [{"id": 5, "position": 1, "src": "https://cdn.example/a.jpg", "variant_ids": [11]},
               {"id": 6, "position": 2, "src": "https://cdn.example/b.jpg", "variant_ids": []},
               {"id": 7, "position": 3, "src": "https://cdn.example/c.jpg", "variant_ids": []}],
}


@pytest.fixture
def con(tmp_path):
    c = store.connect(tmp_path / "t.db")
    store.save(c, *flatten("acme", RAW))
    return c


@pytest.mark.parametrize("raw,expected", [
    ("Large", "l"), (" X-Large ", "xl"), ("Grey", "gray"), ("M - 40", "m"), ("32", "32"),
])
def test_norm_value(raw, expected):
    assert norm_value(raw) == expected


def test_option_key_ignores_order_and_aliases():
    assert option_key(["Black", "Large"]) == option_key(["L", "black"])
    assert option_key(["Default Title"]) == frozenset()


def test_flatten_links_variant_images(con):
    v = con.execute("SELECT * FROM variants WHERE variant_id=11").fetchone()
    assert v["image_src"] == "https://cdn.example/a.jpg"
    assert v["price"] == 49.0 and v["available"] == 1


def test_price_and_stock_changes_are_recorded(con):
    raw = {**RAW, "variants": [{**RAW["variants"][0], "price": "39.00", "available": False}]}
    assert store.save(con, *flatten("acme", raw)) == 2
    fields = {r["field"] for r in con.execute("SELECT field FROM changes")}
    assert fields == {"price", "available"}


def test_map_by_title_and_options(con):
    r = map_row(con, {"store_product": "Malibu Pant", "store_variant": "Large / Black",
                      "supplier": "acme", "supplier_handle": ""})
    assert r["status"] == "matched" and r["supplier_sku"] == "MP-BLK-L"


def test_numeric_options_keep_their_order(tmp_path):
    jean = {**RAW, "id": 2, "handle": "jean", "title": "Democratic Jean",
            "options": [{"name": "Waist"}, {"name": "Inseam"}], "images": [],
            "variants": [{**RAW["variants"][0], "id": 21, "option1": "34", "option2": "32", "sku": "J-34-32"},
                         {**RAW["variants"][0], "id": 22, "option1": "32", "option2": "34", "sku": "J-32-34"}]}
    c = store.connect(tmp_path / "j.db")
    store.save(c, *flatten("acme", jean))
    r = map_row(c, {"store_product": "Democratic Jean", "store_variant": "32 / 34",
                    "supplier": "acme", "supplier_handle": ""})
    assert r["supplier_sku"] == "J-32-34"


def test_title_match_tolerates_reworded_names(con):
    r = map_row(con, {"store_product": "Pants Malibu", "store_variant": "Black / L",
                      "supplier": "acme", "supplier_handle": ""})
    assert r["status"] == "matched"


def test_map_reports_missing_variant_and_product(con):
    r = map_row(con, {"store_product": "Malibu Pants", "store_variant": "Black / XL",
                      "supplier": "acme", "supplier_handle": ""})
    assert r["status"] == "variant_not_found"
    r = map_row(con, {"store_product": "Totally Different Jacket", "store_variant": "M",
                      "supplier": "acme", "supplier_handle": ""})
    assert r["status"] == "product_not_found"


def test_shopify_csv_layout(con, tmp_path):
    path = tmp_path / "out.csv"
    assert export.write_shopify_csv(con, "acme", path) == 3  # 2 variants, 3 images
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert rows[0]["Title"] == "Malibu Pants" and rows[0]["Option1 Name"] == "Color"
    assert rows[1]["Title"] == "" and rows[1]["Option2 Value"] == "S"
    assert rows[2]["Variant SKU"] == "" and rows[2]["Image Src"].endswith("c.jpg")
    assert {r["Handle"] for r in rows} == {"malibu-pants"}
