"""Fetch a supplier's public Shopify catalog via the storefront /products.json endpoint."""

from __future__ import annotations

import time
from typing import Iterator

import requests

PAGE_SIZE = 250  # Shopify's max for /products.json
USER_AGENT = "catalog-pipeline/1.0 (+product data sync)"


def iter_products(base_url: str, delay: float = 1.0, max_pages: int = 100,
                  session: requests.Session | None = None) -> Iterator[dict]:
    """Yield raw product dicts, page by page, until the store returns an empty page."""
    s = session or requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    base = base_url.rstrip("/")
    for page in range(1, max_pages + 1):
        resp = _get(s, f"{base}/products.json", {"limit": PAGE_SIZE, "page": page})
        products = resp.json().get("products", [])
        if not products:
            return
        yield from products
        time.sleep(delay)


def _get(s: requests.Session, url: str, params: dict, retries: int = 3) -> requests.Response:
    for attempt in range(retries):
        resp = s.get(url, params=params, timeout=30)
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = float(resp.headers.get("Retry-After", 2 ** attempt * 5))
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp
