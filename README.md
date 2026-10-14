# Supplier → Shopify Catalog Pipeline

Pulls product data from supplier stores, keeps it in a local product database, maps every
**store variant to the exact supplier variant**, and exports a ready-to-import Shopify CSV plus an
Excel report. Re-running it detects price and stock changes.

Built for the common e-commerce request: *"For each supplier product we need title, price,
colors/sizes, SKU, high-res images and availability — and when an order comes in, our team must
know exactly which supplier variant to buy."*

```
Supplier stores ──► fetch (paginated, rate-limited, retries)
                      │
                      ▼
               SQLite product DB ──► change log (price / availability)
                      │
        ┌─────────────┼──────────────────┐
        ▼             ▼                  ▼
 Variant mapping   Shopify import CSV   Excel report
 (store → supplier) (products, variants,  (variants, changes,
                     images)              mapping)
```

## Results on real data

Run against two public Shopify catalogs (Taylor Stitch, Allbirds), 500 products / 4,353 variants:

| Output | What's in it |
|---|---|
| `output/shopify_import_<supplier>.csv` | Shopify product-import format: one row per variant, extra image rows, options, SKU, price, compare-at price, variant images. Imported as **draft** so nothing goes live by accident. |
| `output/variant_mapping.csv` | Each store variant → supplier product, variant, SKU, price, stock, with a match status and confidence. |
| `output/catalog_report.xlsx` | Sheets: *Variants*, *Changes*, *Variant mapping*; filters and frozen headers. |
| `output/images/` (optional) | Original-resolution images, `supplier/handle/position.jpg`. |

Variant mapping sample (`sample/store_catalog.csv` uses deliberately messy, reworded names):

| Store product / variant | → Supplier variant | SKU | Status |
|---|---|---|---|
| Apres Pant - Cypress Sashiko / **Large / Long** | The Apres Pant in Cypress Sashiko / L / Long | 2207APCSLT | matched |
| Democratic Jean - Light Wash Hemp / **32 / 34** | The Democratic Jean in Light Wash Hemp Denim / 32 / 34 | 2605DJLWHD3234 | matched |
| The Jack - Timber Houndstooth / **Medium** | The Jack in Timber Houndstooth / M - 40 | 2310JTH40 | matched |
| Organic Waffle Crew - Burgundy / **Extra Large** | The Organic Cotton Short Sleeve Crew in Burgundy Waffle / XL - 44 | 2408OCWSSCB44 | matched |
| Apres Pant - Cypress Sashiko / XXXL / Long | — | — | variant_not_found |
| Malibu Pants / Black / Large | — | — | product_not_found |

Unmatched rows are reported, never guessed, so a human reviews them before an order is placed.

### How matching works
- **Product:** best of character similarity and "every word of the store title appears in the
  supplier title", or an explicit supplier handle when you have one.
- **Variant:** option values are normalized (`Large`→`l`, `X-Large`→`xl`, `Grey`→`gray`,
  `M - 40`→`m`). Text options match in any order (`Black / L` = `L / Black`); purely numeric
  options keep their order, so waist 32 / inseam 34 never matches 34 / 32.

## Usage

```bash
pip install -r requirements.txt
python -m catalog all              # sync suppliers, map variants, export everything
python -m catalog sync             # only refresh the product DB (logs price/stock changes)
python -m catalog export --images 3   # also download 3 images per product
python -m pytest                   # 16 tests
```

- Check which sites are Shopify and scrapable: put domains in `sample/domains.txt`, run
  `python -m catalog detect` → `output/shopify_detect.csv` (signal: response header, page HTML
  or `products.json`; and whether `products.json` is open).
- Suppliers: `config/suppliers.json` (`name`, `url`).
- Store catalog to map: `sample/store_catalog.csv` with
  `store_product, store_variant, supplier, supplier_handle (optional)`.
- Schedule `python -m catalog sync` daily (cron, Windows Task Scheduler or GitHub Actions) to keep
  prices and stock current; the *Changes* sheet shows what moved.

## Extending it
- **Non-Shopify suppliers:** add a fetcher that yields the same product dict; the DB, mapping and
  exports stay unchanged.
- **Push to Shopify directly:** replace the CSV step with the Shopify Admin API.
- **AI clean-up:** normalize inconsistent supplier attributes (colors, materials, size charts) with
  an LLM before mapping.

## Responsible use
Reads only the public storefront `products.json` endpoint, one page at a time with a delay and
`Retry-After` handling. Downloaded images are meant for products you are authorized to resell;
check each supplier's terms.
