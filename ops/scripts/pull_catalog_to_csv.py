#!/usr/bin/env python3
"""Pull every row from catalog_enriched into a CSV that the
catalog vision-enrichment pipeline (main.py) can consume directly.

Pages through the table 1000 rows at a time — Supabase REST has an
implicit cap, and catalog_enriched is ~14K rows. Reports image
coverage stats so we know how many rows the batch will actually hit.

Usage:
    APP_ENV=staging python3 ops/scripts/pull_catalog_to_csv.py \\
        --output out/full_enrichment_input.csv
"""
import argparse
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ["modules/platform_core/src", "modules/user/src", "modules/catalog/src", "modules/user_profiler/src"]:
    sys.path.insert(0, os.path.join(ROOT, p))

from platform_core.config import load_config
from platform_core.supabase_rest import SupabaseRestClient


PAGE_SIZE = 1000
COLUMNS = "product_id,title,description,images_0_src,images_1_src,url"
INPUT_FIELDS = ["product_id", "description", "store", "url", "images__0__src", "images__1__src"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pull catalog_enriched rows into CSV for re-enrichment.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    parser.add_argument(
        "--require-image",
        action="store_true",
        default=True,
        help="Skip rows missing images_0_src (default: True). Vision pipeline needs at least one image.",
    )
    return parser.parse_args()


def page_all_rows(client: SupabaseRestClient):
    offset = 0
    while True:
        page = client.select_many(
            "catalog_enriched",
            columns=COLUMNS,
            order="product_id.asc",
            limit=PAGE_SIZE,
            offset=offset,
        )
        if not page:
            break
        for row in page:
            yield row
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE


def main() -> int:
    args = parse_args()
    config = load_config()
    client = SupabaseRestClient(
        rest_url=config.supabase_rest_url,
        service_role_key=config.supabase_service_role_key,
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)

    total = 0
    with_image_0 = 0
    with_image_1 = 0
    with_description = 0
    written = 0
    skipped_no_image = 0

    print(f"Pulling rows from catalog_enriched (paged, {PAGE_SIZE} per page)...", flush=True)
    with open(args.output, "w", encoding="utf-8", newline="") as out_file:
        writer = csv.DictWriter(out_file, fieldnames=INPUT_FIELDS)
        writer.writeheader()
        for row in page_all_rows(client):
            total += 1
            pid = (row.get("product_id") or "").strip()
            description = (row.get("description") or "").strip()
            img0 = (row.get("images_0_src") or "").strip()
            img1 = (row.get("images_1_src") or "").strip()
            url = (row.get("url") or "").strip()
            store = pid.split("_")[0] if "_" in pid else ""

            if img0:
                with_image_0 += 1
            if img1:
                with_image_1 += 1
            if description:
                with_description += 1

            if args.require_image and not img0:
                skipped_no_image += 1
                continue

            writer.writerow({
                "product_id": pid,
                "description": description,
                "store": store,
                "url": url,
                "images__0__src": img0,
                "images__1__src": img1,
            })
            written += 1

            if total % 2000 == 0:
                print(f"  ... {total} rows scanned, {written} written", flush=True)

    print()
    print(f"Total catalog_enriched rows : {total}")
    print(f"  With image_0_src           : {with_image_0}")
    print(f"  With image_1_src           : {with_image_1}")
    print(f"  With description           : {with_description}")
    print(f"  Skipped (no image_0_src)   : {skipped_no_image}")
    print(f"Written to {args.output} : {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
