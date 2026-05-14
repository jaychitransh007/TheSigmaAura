#!/usr/bin/env python3
"""Build the Shopify product import CSV for TheSigmaVibe from
catalog_enriched_full.csv.

Output: data/thesigmavibe_shopify_import.csv

For each enriched row that has price + title, emits Shopify CSV rows:
  - 5 variant rows (XS, S, M, L, XL), the first carries all product fields
    and image position 1
  - 1 image-only row (image position 2) if images_1_src is present

Usage:
    python3 scripts/seed_thesigmavibe_catalog/build_shopify_csv.py
    python3 scripts/seed_thesigmavibe_catalog/build_shopify_csv.py --limit 5  # sample
"""
import argparse
import csv
import sys
from pathlib import Path

# Make sibling modules importable.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from brands import brand_from_url
from generate import (
    build_description_html,
    build_handle,
    build_lede,
    build_seo_description,
    build_seo_title,
    build_tags,
    build_type,
)

WORKTREE = HERE.parent.parent
INPUT_CSV = WORKTREE / "data" / "catalog_enriched_full.csv"
OUTPUT_CSV = WORKTREE / "data" / "thesigmavibe_shopify_import.csv"
TENANT_ID = "t_Oq0BSHnewiEAAAAAagWWlmnV-0sJmcGk"

SIZES = ["XS", "S", "M", "L", "XL"]

# Markup applied on top of the source retailer price. We collect the
# customer's payment at this price; manual-fulfillment cost to us is the
# original retailer price, so the 0.2 spread is gross margin before
# shipping/returns. Round to whole rupees (Indian retail convention).
PRICE_MARKUP = 1.2


def marked_up_price(raw: str) -> str:
    """Apply markup + round to whole rupees. Returns "" if raw is unparseable."""
    try:
        return str(round(float((raw or "").strip()) * PRICE_MARKUP))
    except (ValueError, TypeError):
        return ""

SHOPIFY_COLUMNS = [
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Product Category",
    "Type",
    "Tags",
    "Published",
    "Option1 Name", "Option1 Value",
    "Variant SKU",
    "Variant Grams",
    "Variant Inventory Tracker",
    "Variant Inventory Qty",
    "Variant Inventory Policy",
    "Variant Fulfillment Service",
    "Variant Price",
    "Variant Compare At Price",
    "Variant Requires Shipping",
    "Variant Taxable",
    "Variant Barcode",
    "Image Src",
    "Image Position",
    "Image Alt Text",
    "Gift Card",
    "SEO Title",
    "SEO Description",
    "Status",
    # Metafields (Shopify CSV supports `Metafield: namespace.key [type]` columns).
    "Metafield: vibe.tenant_id [single_line_text_field]",
    "Metafield: vibe.enriched_id [single_line_text_field]",
    "Metafield: vibe.source_product_id [single_line_text_field]",
    "Metafield: vibe.source_retailer [single_line_text_field]",
    "Metafield: vibe.source_url [url]",
]


def empty_row() -> dict[str, str]:
    return {col: "" for col in SHOPIFY_COLUMNS}


def make_product_rows(src: dict) -> list[dict]:
    """Build the 5–6 Shopify CSV rows for one enriched product row."""
    product_id = (src.get("product_id") or "").strip()
    title = (src.get("title") or "").strip()
    price = marked_up_price(src.get("price") or "")
    if not product_id or not title or not price:
        return []

    url = (src.get("url") or "").strip()
    brand = brand_from_url(url) or "Vibe"

    handle = build_handle(brand, title, product_id)
    description_html = build_description_html(src)
    lede_text = build_lede(src)
    tags = build_tags(src, brand)
    product_type = build_type(src)
    seo_title = build_seo_title(title, brand)
    seo_description = build_seo_description(lede_text)

    image_0 = (src.get("images_0_src") or "").strip()
    image_1 = (src.get("images_1_src") or "").strip()
    enriched_id = (src.get("id") or "").strip()

    out_rows: list[dict] = []
    for i, size in enumerate(SIZES):
        row = empty_row()
        row["Handle"] = handle
        row["Option1 Name"] = "Size"
        row["Option1 Value"] = size
        row["Variant SKU"] = f"{handle}-{size}"
        row["Variant Inventory Tracker"] = ""  # no tracking → always sellable
        row["Variant Inventory Policy"] = "continue"
        row["Variant Fulfillment Service"] = "manual"
        row["Variant Price"] = price
        row["Variant Requires Shipping"] = "TRUE"
        row["Variant Taxable"] = "TRUE"

        if i == 0:
            # First row carries all product-level fields.
            row["Title"] = title
            row["Body (HTML)"] = description_html
            row["Vendor"] = brand
            row["Type"] = product_type
            row["Tags"] = tags
            row["Published"] = "TRUE"
            row["Status"] = "draft"  # safer first import; user bulk-publishes after review
            row["SEO Title"] = seo_title
            row["SEO Description"] = seo_description
            row["Gift Card"] = "FALSE"
            if image_0:
                row["Image Src"] = image_0
                row["Image Position"] = "1"
                row["Image Alt Text"] = title
            row["Metafield: vibe.tenant_id [single_line_text_field]"] = TENANT_ID
            row["Metafield: vibe.enriched_id [single_line_text_field]"] = enriched_id
            row["Metafield: vibe.source_product_id [single_line_text_field]"] = product_id
            row["Metafield: vibe.source_retailer [single_line_text_field]"] = brand
            row["Metafield: vibe.source_url [url]"] = url

        out_rows.append(row)

    # Second image row (handle + image only).
    if image_1:
        img_row = empty_row()
        img_row["Handle"] = handle
        img_row["Image Src"] = image_1
        img_row["Image Position"] = "2"
        img_row["Image Alt Text"] = title
        out_rows.append(img_row)

    return out_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Stop after N products (0 = all).")
    parser.add_argument(
        "--output",
        default=str(OUTPUT_CSV),
        help="Output CSV path (default: data/thesigmavibe_shopify_import.csv).",
    )
    args = parser.parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    csv.field_size_limit(sys.maxsize)

    total_scanned = 0
    written_products = 0
    written_rows = 0
    skipped_no_price = 0
    skipped_no_title = 0

    with open(INPUT_CSV, "r", encoding="utf-8", newline="") as inp, \
         open(output_path, "w", encoding="utf-8", newline="") as out:
        reader = csv.DictReader(inp)
        writer = csv.DictWriter(out, fieldnames=SHOPIFY_COLUMNS)
        writer.writeheader()

        for src in reader:
            total_scanned += 1
            price = (src.get("price") or "").strip()
            title = (src.get("title") or "").strip()
            if not price:
                skipped_no_price += 1
                continue
            if not title:
                skipped_no_title += 1
                continue

            rows = make_product_rows(src)
            if not rows:
                continue
            for r in rows:
                writer.writerow(r)
                written_rows += 1
            written_products += 1

            if args.limit and written_products >= args.limit:
                break

            if written_products % 1000 == 0:
                print(f"  ... {written_products} products written", flush=True)

    print(f"\nScanned:           {total_scanned}")
    print(f"Skipped (no price): {skipped_no_price}")
    print(f"Skipped (no title): {skipped_no_title}")
    print(f"Products written:  {written_products}")
    print(f"CSV rows written:  {written_rows}")
    print(f"Output:            {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
