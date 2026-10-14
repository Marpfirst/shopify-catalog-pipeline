"""Check a list of domains: is it a Shopify store, and is its products.json open?"""

from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from .fetch import USER_AGENT

HTML_MARKERS = ("cdn.shopify.com", "Shopify.theme", "myshopify.com")


def _url(domain: str) -> str:
    d = domain.strip().rstrip("/")
    return d if d.startswith("http") else f"https://{d}"


def check(domain: str, session: requests.Session | None = None) -> dict:
    s = session or requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    base = _url(domain)
    result = {"domain": domain.strip(), "final_url": "", "shopify": False, "signal": "",
              "products_json": False, "sample_products": 0, "error": ""}
    try:
        home = s.get(base, timeout=20)
        result["final_url"] = home.url
        headers = {k.lower(): v for k, v in home.headers.items()}
        if "x-shopid" in headers or "shopify" in headers.get("powered-by", "").lower():
            result.update(shopify=True, signal="header")
        elif any(m in home.text for m in HTML_MARKERS):
            result.update(shopify=True, signal="html")

        root = home.url.split("?")[0].rstrip("/")
        pj = s.get(f"{root}/products.json", params={"limit": 5}, timeout=20)
        try:
            products = pj.json().get("products") if pj.ok else None
        except ValueError:  # HTML page / bot challenge instead of JSON
            products = None
        if isinstance(products, list):
            result.update(products_json=True, sample_products=len(products))
            if not result["shopify"]:
                result.update(shopify=True, signal="products.json")
    except (requests.RequestException, ValueError) as e:
        result["error"] = type(e).__name__
    return result


def detect_file(domains_file: Path, out: Path, workers: int = 8) -> list[dict]:
    domains = [d for d in domains_file.read_text(encoding="utf-8").splitlines()
               if d.strip() and not d.startswith("#")]
    with ThreadPoolExecutor(workers) as pool:
        rows = list(pool.map(check, domains))
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(rows[0]) if rows else ["domain"])
        w.writeheader()
        w.writerows(rows)
    return rows
