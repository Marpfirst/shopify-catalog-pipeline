"""Turn raw Shopify JSON into flat rows, and normalize option values for matching."""

from __future__ import annotations

import re

SIZE_ALIASES = {
    "extra small": "xs", "x-small": "xs", "xsmall": "xs",
    "small": "s", "medium": "m", "large": "l",
    "extra large": "xl", "x-large": "xl", "xlarge": "xl",
    "xx-large": "xxl", "2xl": "xxl", "xxlarge": "xxl",
}
COLOR_ALIASES = {"blk": "black", "wht": "white", "grey": "gray", "navy blue": "navy"}


def norm_value(value: str | None) -> str:
    v = re.sub(r"\s+", " ", (value or "").strip().lower())
    v = re.sub(r"^([a-z]{1,4}) - \d+$", r"\1", v)  # "M - 40" (size + chest measurement) -> "m"
    return SIZE_ALIASES.get(v) or COLOR_ALIASES.get(v) or v


def option_tuple(values: list[str | None]) -> tuple[str, ...]:
    return tuple(norm_value(v) for v in values if v and norm_value(v) != "default title")


def option_key(values: list[str | None]) -> frozenset[str]:
    """Order-independent key: 'Black / Large' == 'L / black'."""
    return frozenset(option_tuple(values))


def order_matters(values: tuple[str, ...]) -> bool:
    """'32 / 34' (waist / inseam) is not '34 / 32'; only purely numeric options are positional."""
    return len(values) > 1 and all(v.replace(".", "").isdigit() for v in values)


def split_variant_title(title: str) -> list[str]:
    return [p for p in (x.strip() for x in title.split("/")) if p]


def flatten(supplier: str, product: dict) -> tuple[dict, list[dict], list[dict]]:
    """Return (product_row, variant_rows, image_rows) for one raw product."""
    p = {
        "supplier": supplier,
        "product_id": product["id"],
        "handle": product["handle"],
        "title": product["title"],
        "vendor": product.get("vendor", ""),
        "product_type": product.get("product_type", ""),
        "tags": ", ".join(product.get("tags") or []) if isinstance(product.get("tags"), list)
                else product.get("tags", ""),
        "body_html": product.get("body_html") or "",
        "option_names": " | ".join(o["name"] for o in product.get("options", [])),
    }
    images = product.get("images", [])
    image_by_variant = {vid: img["src"] for img in images for vid in img.get("variant_ids", [])}
    variants = [{
        "supplier": supplier,
        "variant_id": v["id"],
        "product_id": product["id"],
        "title": v.get("title", ""),
        "option1": v.get("option1"), "option2": v.get("option2"), "option3": v.get("option3"),
        "sku": v.get("sku") or "",
        "price": float(v.get("price") or 0),
        "compare_at_price": float(v["compare_at_price"]) if v.get("compare_at_price") else None,
        "available": int(bool(v.get("available"))),
        "grams": v.get("grams") or 0,
        "image_src": image_by_variant.get(v["id"], ""),
    } for v in product.get("variants", [])]
    imgs = [{
        "supplier": supplier,
        "product_id": product["id"],
        "position": img.get("position", i + 1),
        "src": img["src"],
        "width": img.get("width"), "height": img.get("height"),
    } for i, img in enumerate(images)]
    return p, variants, imgs
