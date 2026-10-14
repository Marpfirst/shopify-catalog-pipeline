import json

from catalog.jsonld import _locs, parse_product
from catalog.normalize import flatten

GROUP = {
    "@context": "https://schema.org", "@type": "ProductGroup", "name": "Daisy Rug | Shop",
    "brand": {"@type": "Brand", "name": "Acme"}, "description": "Washable rug",
    "hasVariant": [
        {"@type": "Product", "sku": "R-23", "size": "2'x3'", "image": "https://cdn.test/a.jpg",
         "offers": [{"@type": "Offer", "price": "71.20", "availability": "http://schema.org/InStock",
                     "priceSpecification": {"priceType": "https://schema.org/StrikethroughPrice", "price": "89.00"}}]},
        {"@type": "Product", "sku": "R-58", "size": "5'x8'", "image": "https://cdn.test/a.jpg",
         "offers": {"@type": "Offer", "price": "249.00", "availability": "https://schema.org/OutOfStock"}},
    ],
}


def page(*nodes):
    blocks = "".join(f'<script type="application/ld+json">{json.dumps(n)}</script>' for n in nodes)
    return f"<html><head>{blocks}</head></html>"


def test_product_group_becomes_variants():
    p = parse_product(page({"@type": "BreadcrumbList"}, [GROUP]), "https://shop.test/products/daisy-rug?x=1")
    assert p["handle"] == "daisy-rug" and p["title"] == "Daisy Rug" and p["vendor"] == "Acme"
    assert [o["name"] for o in p["options"]] == ["Size"]
    a, b = p["variants"]
    assert (a["option1"], a["price"], a["compare_at_price"], a["available"]) == ("2'x3'", "71.20", "89.00", True)
    assert (b["sku"], b["available"]) == ("R-58", False)
    assert len(p["images"]) == 1 and p["images"][0]["variant_ids"] == [a["id"], b["id"]]
    flatten("acme", p)  # same shape the DB layer expects


def test_single_product_in_graph_with_aggregate_offer():
    node = {"@type": "Product", "name": "Socks", "sku": "S1",
            "offers": {"@type": "AggregateOffer", "lowPrice": "12.00", "availability": "InStock"}}
    p = parse_product(page({"@graph": [{"@type": "WebPage"}, node]}), "https://shop.test/product/socks")
    assert p["variants"][0]["price"] == "12.00" and p["variants"][0]["option1"] == "Default Title"


def test_page_without_product_data():
    assert parse_product("<html>no data</html>", "https://shop.test/products/x") is None


def test_sitemap_ignores_image_locs():
    xml = ('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
           'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">'
           '<url><loc>https://shop.test/products/a</loc>'
           '<image:image><image:loc>https://cdn.test/a.jpg</image:loc></image:image></url></urlset>')
    assert _locs(xml) == ["https://shop.test/products/a"]
