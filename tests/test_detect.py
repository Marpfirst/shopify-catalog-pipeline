from catalog.detect import check


class FakeResp:
    def __init__(self, url, text="", headers=None, json_data=None, ok=True):
        self.url, self.text, self.headers, self._json, self.ok = url, text, headers or {}, json_data, ok

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json


class FakeSession:
    def __init__(self, home, products):
        self.headers, self.home, self.products = {}, home, products

    def get(self, url, **kw):
        return self.products if url.endswith("/products.json") else self.home


def test_open_shopify_store():
    s = FakeSession(FakeResp("https://shop.test/", text='<script src="//cdn.shopify.com/x.js">'),
                    FakeResp("", json_data={"products": [{}, {}]}))
    r = check("shop.test", s)
    assert r["shopify"] and r["signal"] == "html" and r["products_json"] and r["sample_products"] == 2


def test_shopify_with_closed_products_json():
    s = FakeSession(FakeResp("https://shop.test/", headers={"X-ShopId": "1"}),
                    FakeResp("", ok=False))
    r = check("shop.test", s)
    assert r["shopify"] and r["signal"] == "header" and not r["products_json"]


def test_not_shopify():
    s = FakeSession(FakeResp("https://other.test/", text="<html>woocommerce</html>"),
                    FakeResp("", text="<html>404</html>"))
    r = check("other.test", s)
    assert not r["shopify"] and not r["products_json"] and r["error"] == ""
