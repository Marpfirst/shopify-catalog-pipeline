"""Map each store variant (e.g. 'Malibu Pants / Black / Large') to its exact supplier variant."""

from __future__ import annotations

import re
import sqlite3
from difflib import SequenceMatcher

from .normalize import option_key, option_tuple, order_matters, split_variant_title

TITLE_THRESHOLD = 0.6


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower())) - {"the", "in", "and", "with", "for"}


def title_score(store_title: str, supplier_title: str) -> float:
    """Best of character similarity and 'every store word appears in the supplier title'."""
    seq = SequenceMatcher(None, store_title.lower(), supplier_title.lower()).ratio()
    want, have = _tokens(store_title), _tokens(supplier_title)
    contained = len(want & have) / len(want) * 0.95 if want else 0
    return max(seq, contained)


def _variant_matches(want: tuple[str, ...], v: sqlite3.Row) -> bool:
    have = option_tuple([v["option1"], v["option2"], v["option3"]])
    if order_matters(want):
        return want == have
    return frozenset(want) == option_key(list(have))


def map_row(con: sqlite3.Connection, row: dict) -> dict:
    """row keys: store_product, store_variant, supplier, supplier_handle (optional hint)."""
    supplier = row["supplier"]
    if row.get("supplier_handle"):
        candidates = con.execute("SELECT * FROM products WHERE supplier=? AND handle=?",
                                 (supplier, row["supplier_handle"])).fetchall()
        scored = [(1.0, p) for p in candidates]
    else:
        products = con.execute("SELECT * FROM products WHERE supplier=?", (supplier,)).fetchall()
        scored = sorted(((title_score(row["store_product"], p["title"]), p) for p in products),
                        key=lambda t: t[0], reverse=True)[:3]
        scored = [(s, p) for s, p in scored if s >= TITLE_THRESHOLD]

    want = option_tuple(split_variant_title(row["store_variant"]))
    for score, product in scored:
        for v in con.execute("SELECT * FROM variants WHERE supplier=? AND product_id=?",
                             (supplier, product["product_id"])):
            if _variant_matches(want, v):
                return {**row, "status": "matched", "confidence": round(score, 2),
                        "supplier_product": product["title"], "supplier_handle": product["handle"],
                        "supplier_variant": v["title"], "supplier_variant_id": v["variant_id"],
                        "supplier_sku": v["sku"], "supplier_price": v["price"],
                        "supplier_available": bool(v["available"])}
    status = "variant_not_found" if scored else "product_not_found"
    best = scored[0][1]["title"] if scored else ""
    return {**row, "status": status, "confidence": round(scored[0][0], 2) if scored else 0,
            "supplier_product": best}
