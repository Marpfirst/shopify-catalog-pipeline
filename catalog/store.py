"""SQLite product database with price/availability change tracking."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
  supplier TEXT, product_id INTEGER, handle TEXT, title TEXT, vendor TEXT,
  product_type TEXT, tags TEXT, body_html TEXT, option_names TEXT, last_seen TEXT,
  PRIMARY KEY (supplier, product_id));
CREATE TABLE IF NOT EXISTS variants (
  supplier TEXT, variant_id INTEGER, product_id INTEGER, title TEXT,
  option1 TEXT, option2 TEXT, option3 TEXT, sku TEXT, price REAL, compare_at_price REAL,
  available INTEGER, grams INTEGER, image_src TEXT, last_seen TEXT,
  PRIMARY KEY (supplier, variant_id));
CREATE TABLE IF NOT EXISTS images (
  supplier TEXT, product_id INTEGER, position INTEGER, src TEXT, width INTEGER, height INTEGER,
  PRIMARY KEY (supplier, product_id, position));
CREATE TABLE IF NOT EXISTS changes (
  at TEXT, supplier TEXT, variant_id INTEGER, field TEXT, old TEXT, new TEXT);
"""
TRACKED = ("price", "available")


def connect(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def upsert(con: sqlite3.Connection, table: str, row: dict) -> None:
    cols = ", ".join(row)
    marks = ", ".join("?" * len(row))
    con.execute(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})", list(row.values()))


def save(con: sqlite3.Connection, product: dict, variants: list[dict], images: list[dict]) -> int:
    """Store one product; return the number of tracked-field changes recorded."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    upsert(con, "products", {**product, "last_seen": now})
    con.execute("DELETE FROM images WHERE supplier=? AND product_id=?",
                (product["supplier"], product["product_id"]))
    for img in images:
        upsert(con, "images", img)
    changed = 0
    for v in variants:
        old = con.execute("SELECT price, available FROM variants WHERE supplier=? AND variant_id=?",
                          (v["supplier"], v["variant_id"])).fetchone()
        if old:
            for field in TRACKED:
                if old[field] != v[field]:
                    con.execute("INSERT INTO changes VALUES (?,?,?,?,?,?)",
                                (now, v["supplier"], v["variant_id"], field, old[field], v[field]))
                    changed += 1
        upsert(con, "variants", {**v, "last_seen": now})
    return changed
