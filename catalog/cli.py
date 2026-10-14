"""Command line: sync suppliers, map store variants, export Shopify CSV + Excel report."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from . import export, store
from .detect import detect_file
from .fetch import iter_products
from .mapping import map_row
from .normalize import flatten

ROOT = Path(__file__).resolve().parent.parent


def cmd_sync(args, con) -> None:
    suppliers = json.loads(Path(args.config).read_text(encoding="utf-8"))
    for sup in suppliers:
        n = changes = 0
        for raw in iter_products(sup["url"], delay=args.delay, max_pages=args.max_pages):
            changes += store.save(con, *flatten(sup["name"], raw))
            n += 1
        con.commit()
        print(f"{sup['name']}: {n} products synced, {changes} price/stock changes")


def cmd_map(args, con) -> list[dict]:
    with open(args.store_catalog, newline="", encoding="utf-8") as f:
        rows = [map_row(con, r) for r in csv.DictReader(f)]
    out = Path(args.out) / "variant_mapping.csv"
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(rows)
    ok = sum(r["status"] == "matched" for r in rows)
    print(f"mapping: {ok}/{len(rows)} store variants matched -> {out}")
    return rows


def cmd_export(args, con, mapping: list[dict] | None = None) -> None:
    out = Path(args.out)
    for (sup,) in con.execute("SELECT DISTINCT supplier FROM products"):
        n = export.write_shopify_csv(con, sup, out / f"shopify_import_{sup}.csv")
        print(f"{sup}: {n} rows -> shopify_import_{sup}.csv")
        if args.images:
            print(f"{sup}: {export.download_images(con, sup, out / 'images', args.images)} images saved")
    export.write_report(con, out / "catalog_report.xlsx", mapping)
    print(f"report -> {out / 'catalog_report.xlsx'}")


def cmd_detect(args) -> None:
    out = Path(args.out) / "shopify_detect.csv"
    rows = detect_file(Path(args.domains), out)
    for r in rows:
        status = ("SHOPIFY, products.json open" if r["products_json"] else
                  "SHOPIFY, products.json closed" if r["shopify"] else
                  f"error: {r['error']}" if r["error"] else "not Shopify")
        print(f"{r['domain']:35} {status}")
    print(f"{sum(r['products_json'] for r in rows)}/{len(rows)} scrapable -> {out}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="catalog", description=__doc__)
    ap.add_argument("command", choices=["sync", "map", "export", "all", "detect"])
    ap.add_argument("--domains", default=ROOT / "sample" / "domains.txt",
                    help="detect: text file, one domain per line")
    ap.add_argument("--config", default=ROOT / "config" / "suppliers.json")
    ap.add_argument("--store-catalog", default=ROOT / "sample" / "store_catalog.csv")
    ap.add_argument("--db", default=ROOT / "output" / "catalog.db")
    ap.add_argument("--out", default=ROOT / "output")
    ap.add_argument("--max-pages", type=int, default=4, help="250 products per page")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between page requests")
    ap.add_argument("--images", type=int, default=0, help="download N images per product")
    args = ap.parse_args(argv)

    Path(args.out).mkdir(parents=True, exist_ok=True)
    if args.command == "detect":
        return cmd_detect(args)
    con = store.connect(args.db)
    mapping = None
    if args.command in ("sync", "all"):
        cmd_sync(args, con)
    if args.command in ("map", "all"):
        mapping = cmd_map(args, con)
    if args.command in ("export", "all"):
        cmd_export(args, con, mapping)


if __name__ == "__main__":
    main()
