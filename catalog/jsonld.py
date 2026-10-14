"""Fetcher for any store: product URLs from the sitemap, product data from schema.org JSON-LD.

Used when /products.json is closed (headless Shopify) or the site is not Shopify at all.
Yields the same dict shape as Shopify's products.json, so the DB, mapping and exports are unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from typing import Iterator
from urllib.parse import urljoin, urlparse

import requests

from .fetch import USER_AGENT

OPTION_PROPS = ("color", "size", "material", "pattern")
LD_RE = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
PRODUCT_PATH = re.compile(r"/products?/", re.I)


def _id(text: str) -> int:
    return int(hashlib.sha1(text.encode()).hexdigest()[:12], 16)


def _locs(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text.encode())
    except ET.ParseError:
        return []
    # only the <loc> directly under <url>/<sitemap>, not <image:loc> etc.
    return [loc.text.strip() for entry in root for loc in entry
            if loc.tag.split("}")[-1] == "loc" and loc.tag.split("}")[0] == entry.tag.split("}")[0]
            and loc.text]


LOCALE = re.compile(r"/[a-z]{2}-[a-z]{2}(/|$)", re.I)  # /en-CA/ storefronts often price in another currency


def product_urls(base: str, s: requests.Session, limit: int) -> list[str]:
    """Walk robots.txt / sitemap.xml (and nested sitemap indexes) for product page URLs."""
    host = urlparse(base if "://" in base else f"https://{base}").netloc.removeprefix("www.")
    robots = s.get(urljoin(base, "/robots.txt"), timeout=20)
    queue = list(dict.fromkeys(re.findall(r"(?im)^sitemap:\s*(\S+)", robots.text))) if robots.ok else []
    queue = queue or [urljoin(base, "/sitemap.xml")]
    seen, urls, localized = set(), [], []
    while queue and len(urls) < limit:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        resp = s.get(sm, timeout=30)
        if not resp.ok:
            print(f"  sitemap {sm}: HTTP {resp.status_code}")
            continue
        for loc in _locs(resp.text):
            path = urlparse(loc).path
            if urlparse(loc).netloc.removeprefix("www.") != host:
                continue
            if path.endswith(".xml"):
                # default-locale product sitemaps first; blogs/pages/collections last
                front = "product" in path and not LOCALE.search(path)
                queue.insert(0, loc) if front else queue.append(loc)
            elif PRODUCT_PATH.search(path) and loc not in urls:
                (localized if LOCALE.search(path) else urls).append(loc)
    return (urls or localized)[:limit]


def _ld_nodes(html: str) -> Iterator[dict]:
    for block in LD_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        stack = data if isinstance(data, list) else [data]
        for node in stack:
            if isinstance(node, dict):
                yield node
                yield from (n for n in node.get("@graph", []) if isinstance(n, dict))


def _offer(node: dict) -> dict:
    offers = node.get("offers") or {}
    offers = offers[0] if isinstance(offers, list) and offers else offers
    if offers.get("@type") == "AggregateOffer":
        offers = {**offers, "price": offers.get("lowPrice") or offers.get("price")}
    spec = offers.get("priceSpecification") or {}
    spec = spec if isinstance(spec, list) else [spec]
    strike = next((p.get("price") for p in spec if "Strikethrough" in str(p.get("priceType", ""))), None)
    return {"price": offers.get("price"), "compare_at_price": strike,
            "available": "InStock" in str(offers.get("availability", ""))}


def _image(node: dict) -> str:
    img = node.get("image")
    img = img[0] if isinstance(img, list) and img else img
    return (img.get("url") if isinstance(img, dict) else img) or ""


def parse_product(html: str, url: str) -> dict | None:
    """Turn a product page's JSON-LD (Product or ProductGroup) into a products.json-style dict."""
    node = next((n for n in _ld_nodes(html) if n.get("@type") in ("Product", "ProductGroup")), None)
    if not node:
        return None
    variants_ld = node.get("hasVariant") or [node]
    names = [p for p in OPTION_PROPS if any(v.get(p) for v in variants_ld)]
    variants, images = [], []
    for v in variants_ld:
        values = [str(v.get(p)) for p in names if v.get(p)]
        offer = _offer(v) if v.get("offers") else _offer(node)
        sku = v.get("sku") or node.get("sku") or ""
        img = _image(v) or _image(node)
        vid = _id(sku or f"{url}#{'/'.join(values)}")
        variants.append({"id": vid, "title": " / ".join(values) or "Default Title",
                         "option1": values[0] if values else "Default Title",
                         "option2": values[1] if len(values) > 1 else None,
                         "option3": values[2] if len(values) > 2 else None,
                         "sku": sku, "price": offer["price"], "compare_at_price": offer["compare_at_price"],
                         "available": offer["available"], "grams": 0})
        if img and img not in [i["src"] for i in images]:
            images.append({"id": _id(img), "position": len(images) + 1, "src": img, "variant_ids": [vid]})
        elif img:
            next(i for i in images if i["src"] == img)["variant_ids"].append(vid)
    brand = node.get("brand")
    name = re.sub(r"\s*\|\s*[^|]+$", "", node.get("name", "")) if "|" in node.get("name", "") else node.get("name", "")
    return {"id": _id(url.split("?")[0]), "handle": urlparse(url).path.rstrip("/").rsplit("/", 1)[-1],
            "title": name, "vendor": brand.get("name", "") if isinstance(brand, dict) else (brand or ""),
            "product_type": node.get("category", "") if isinstance(node.get("category"), str) else "",
            "tags": [], "body_html": node.get("description", ""),
            "options": [{"name": n.capitalize()} for n in names] or [{"name": "Title"}],
            "variants": variants, "images": images}


def iter_products(base_url: str, delay: float = 1.0, limit: int = 200, render: bool = False,
                  session: requests.Session | None = None) -> Iterator[dict]:
    s = session or requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    browser = None
    try:
        for url in product_urls(base_url, s, limit):
            resp = s.get(url, timeout=30)
            product = parse_product(resp.text, url) if resp.ok else None
            if product is None and render:
                browser = browser or _browser()
                product = parse_product(_rendered(browser, url), url)
            if product and product["variants"]:
                yield product
            time.sleep(delay)
    finally:
        if browser:
            browser.close()
            browser._pw.stop()


def _browser():
    """Headless Chromium for pages that only build their JSON-LD client-side."""
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch()
    browser._pw = pw
    return browser


def _rendered(browser, url: str) -> str:
    page = browser.new_page(user_agent=USER_AGENT)
    try:
        page.goto(url, wait_until="networkidle", timeout=45000)
        return page.content()
    finally:
        page.close()
