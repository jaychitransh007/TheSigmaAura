#!/usr/bin/env python3
"""Fix broken image URLs in Powerlook + Vastramay CSVs by fetching
real CDN URLs from each store's Shopify JSON endpoint, then re-ingest
all three stores (Campus Sutra, Powerlook, Vastramay) with proper
store-prefixed product_ids.

Usage:
    APP_ENV=staging python3 ops/scripts/fix_and_reingest_catalog_csvs.py
"""
import csv
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ["modules/platform_core/src", "modules/user/src", "modules/catalog/src", "modules/user_profiler/src"]:
    sys.path.insert(0, os.path.join(ROOT, p))

from platform_core.config import load_config
from platform_core.supabase_rest import SupabaseRestClient

config = load_config()
client = SupabaseRestClient(
    rest_url=config.supabase_rest_url,
    service_role_key=config.supabase_service_role_key,
)

CSV_FILES = [
    ("data/catalog/campussuta_processed.csv", "CAMPUSSUTRA"),
    ("data/catalog/powerlook_processed.csv", "POWERLOOK"),
    ("data/catalog/vastramay_processed.csv", "VASTRAMAY"),
]

OUTPUT_DIR = os.path.join(ROOT, "data", "catalog")


def fetch_image_from_shopify(product_url):
    """Fetch image URLs from the Shopify .json endpoint."""
    json_url = product_url.rstrip("/") + ".json"
    try:
        req = urllib.request.Request(json_url, headers={"User-Agent": "Aura/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        images = data.get("product", {}).get("images", [])
        img0 = images[0].get("src", "") if len(images) > 0 else ""
        img1 = images[1].get("src", "") if len(images) > 1 else ""
        return img0, img1
    except Exception as e:
        return "", ""


def fix_csv(input_path, store_prefix):
    """Fix image URLs and add store prefix to product_ids. Returns fixed rows."""
    with open(input_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    fixed = []
    total = len(rows)
    needs_fix = 0
    fetched = 0
    failed = 0

    for i, row in enumerate(rows):
        img = str(row.get("images_0_src") or "").strip()
        product_url = str(row.get("url") or "").strip()
        old_pid = str(row.get("product_id") or "").strip()

        # Add store prefix if missing
        if not old_pid.startswith(store_prefix):
            row["product_id"] = f"{store_prefix}_{old_pid}"

        # Add store field
        row["store"] = store_prefix.lower()

        # Fix broken image URL
        if img and not img.startswith("http") and product_url.startswith("http"):
            needs_fix += 1
            img0, img1 = fetch_image_from_shopify(product_url)
            if img0:
                row["images_0_src"] = img0
                row["images__0__src"] = img0
                row["images_1_src"] = img1
                row["images__1__src"] = img1
                fetched += 1
                if (fetched % 25) == 0:
                    print(f"    [{fetched}/{needs_fix}] {row['product_id'][:40]} → OK")
            else:
                failed += 1
                if failed <= 3:
                    print(f"    FAILED: {row['product_id'][:40]} — {product_url[:60]}")
            # Rate limit
            time.sleep(0.3)

        fixed.append(row)

    print(f"  Total: {total}, Needs fix: {needs_fix}, Fetched: {fetched}, Failed: {failed}")
    return fixed


def write_fixed_csv(rows, output_path):
    """Write the fixed rows to a new CSV."""
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def ingest_to_supabase(rows, store_name):
    """Upsert rows to catalog_enriched via the same build function the admin uses."""
    from catalog.retrieval.repository import build_catalog_enriched_rows
    from catalog.retrieval.vector_store import SupabaseVectorStore

    vector_store = SupabaseVectorStore(client)
    item_rows = build_catalog_enriched_rows(rows)
    print(f"  Built {len(item_rows)} enriched rows")
    saved = vector_store.upsert_catalog_enriched(item_rows)
    print(f"  Upserted {len(saved)} rows to catalog_enriched")
    return len(saved)


def main():
    print("=" * 60)
    print("Fix broken image URLs + re-ingest catalog CSVs")
    print("=" * 60)

    total_ingested = 0

    for csv_path, store_prefix in CSV_FILES:
        full_path = os.path.join(ROOT, csv_path)
        print(f"\n{'─'*60}")
        print(f"Processing: {store_prefix} ({csv_path})")
        print(f"{'─'*60}")

        # Step 1: Fix CSV
        print("  Fixing image URLs...")
        fixed_rows = fix_csv(full_path, store_prefix)

        # Step 2: Write fixed CSV
        output_path = os.path.join(OUTPUT_DIR, f"{store_prefix.lower()}_fixed.csv")
        write_fixed_csv(fixed_rows, output_path)
        print(f"  Fixed CSV saved: {output_path}")

        # Step 3: Ingest to Supabase
        print("  Ingesting to catalog_enriched...")
        # Convert back to the format build_catalog_enriched_rows expects
        ingest_rows = []
        for r in fixed_rows:
            img = str(r.get("images_0_src") or "").strip()
            if not img.startswith("http"):
                continue  # skip rows where image fix failed
            ingest_rows.append(r)

        if ingest_rows:
            saved = ingest_to_supabase(ingest_rows, store_prefix)
            total_ingested += saved
        else:
            print("  No valid rows to ingest!")

    print(f"\n{'='*60}")
    print(f"Done! Total ingested: {total_ingested}")
    print(f"{'='*60}")
    print(f"\nNext steps:")
    print(f"  1. Run re-enrich: APP_ENV=staging python3 ops/scripts/re_enrich_null_catalog.py")
    print(f"  2. Run embedding sync from catalog admin")


if __name__ == "__main__":
    main()
