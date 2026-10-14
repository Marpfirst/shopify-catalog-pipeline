# Upwork portfolio item (copy-paste)

**Project title**
Supplier-to-Shopify Product Data Pipeline (Scraping, Variant Mapping, Import CSV)

**Project description**
Python pipeline that pulls product data from supplier websites, stores it in a database, and prepares it for a Shopify store.

What it does:
- Scrapes titles, prices, sale prices, SKUs, sizes/colors, stock and image URLs from supplier sites
- Works with Shopify suppliers and with stores that block products.json (sitemap + structured data), and checks which sites are scrapable
- Maps each of your store variants to the exact supplier variant (handles reworded product names, "Large" vs "L", waist/inseam order), and flags anything it cannot match instead of guessing
- Exports a Shopify product-import CSV (drafts) and an Excel report with variants, mapping and price/stock changes
- Re-runs daily to detect price and stock changes
- 20 automated tests

Tested on 4 real stores, 500+ products and 4,000+ variants.

**Link**
https://github.com/Marpfirst/shopify-catalog-pipeline

**Skills tags**
Web Scraping, Python, Data Extraction, Shopify, Data Mining, Microsoft Excel, API Integration

**Images to upload** (screenshots, 3 is enough)
1. catalog_report.xlsx, sheet "Variant mapping" (matched / variant_not_found rows)
2. catalog_report.xlsx, sheet "Variants" (SKU, price, compare-at price, stock)
3. Terminal: `python -m catalog detect` output (Shopify / closed / not Shopify)
