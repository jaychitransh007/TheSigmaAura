#!/usr/bin/env python3
"""Re-enrich catalog rows that have null GarmentCategory.

One-time fix for ~2,762 catalog items that were imported and embedded
but never vision-enriched. Runs synchronously row by row so it can be
stopped (Ctrl-C) and resumed safely — it only updates rows that are
still null, so re-running skips already-fixed rows.

Usage:
    APP_ENV=staging python3 ops/scripts/re_enrich_null_catalog.py

Expects SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, and OPENAI_API_KEY
in the environment (loaded from .env.staging via APP_ENV).

Estimated time: ~2 seconds per row × 2,762 rows ≈ 90 minutes.
"""
import json
import os
import sys
import time

# Add module paths
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ["modules/platform_core/src", "modules/user/src", "modules/catalog/src", "modules/user_profiler/src"]:
    sys.path.insert(0, os.path.join(ROOT, p))

from platform_core.config import load_config
from platform_core.supabase_rest import SupabaseRestClient
from catalog.enrichment.schema_builder import response_format
from catalog.enrichment.config import PipelineConfig

# Load config
config = load_config()
_sb_url = os.environ.get("SUPABASE_URL") or config.get("SUPABASE_URL", "")
_sb_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or config.get("SUPABASE_SERVICE_ROLE_KEY", "")
client = SupabaseRestClient(rest_url=_sb_url, service_role_key=_sb_key)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or config.get("OPENAI_API_KEY", "")
MODEL = "gpt-5-mini"
BATCH_SIZE = 50  # fetch this many null rows at a time


def fetch_null_rows(limit: int = BATCH_SIZE) -> list:
    """Fetch catalog rows where GarmentCategory is null."""
    return client.select_many(
        "catalog_enriched",
        filters={"GarmentCategory": "is.null"},
        order="product_id.asc",
        limit=limit,
    )


def enrich_one(row: dict) -> dict | None:
    """Call the vision model to enrich one catalog row. Returns the extracted attributes or None."""
    from openai import OpenAI

    image_url = str(row.get("images_0_src") or "").strip()
    if not image_url:
        return None

    title = str(row.get("title") or "").strip()

    # Load the same system prompt used by the batch enrichment pipeline
    prompt_path = os.path.join(ROOT, "modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt")
    with open(prompt_path) as f:
        system_prompt = f.read().strip()

    user_text = (
        f"Analyze this product image and return the required JSON.\n"
        f"Title: {title}\n"
    )

    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    response = openai_client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_text},
                    {"type": "input_image", "image_url": image_url},
                ],
            },
        ],
        text={"format": response_format()},
    )

    raw_text = getattr(response, "output_text", "") or "{}"
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return None


def update_row(product_id: str, attributes: dict) -> None:
    """Update the catalog_enriched row with the extracted attributes."""
    patch = {}
    for key, value in attributes.items():
        if key.endswith("_confidence"):
            try:
                patch[key] = float(value) if value is not None else None
            except (TypeError, ValueError):
                patch[key] = None
        else:
            patch[key] = str(value).strip() if value is not None else None

    # Also set row_status to 'ok' now that enrichment succeeded
    patch["row_status"] = "ok"

    client.update_one(
        "catalog_enriched",
        filters={"product_id": f"eq.{product_id}"},
        patch=patch,
    )


def main():
    print("Re-enriching catalog rows with null GarmentCategory...")
    print(f"Model: {MODEL}")
    print()

    total_processed = 0
    total_success = 0
    total_failed = 0
    total_skipped = 0

    while True:
        rows = fetch_null_rows()
        if not rows:
            print("\nNo more null rows. Done!")
            break

        print(f"\nBatch: {len(rows)} rows to process (total so far: {total_processed})")

        for row in rows:
            product_id = str(row.get("product_id") or "")
            title = str(row.get("title") or "")[:50]
            image_url = str(row.get("images_0_src") or "").strip()

            if not image_url:
                print(f"  SKIP (no image): {product_id} — {title}")
                total_skipped += 1
                # Mark as missing so we don't re-fetch it
                client.update_one(
                    "catalog_enriched",
                    filters={"product_id": f"eq.{product_id}"},
                    patch={"row_status": "missing", "error_reason": "no_image_url"},
                )
                total_processed += 1
                continue

            try:
                t0 = time.time()
                attributes = enrich_one(row)
                elapsed = time.time() - t0

                if attributes and attributes.get("GarmentCategory"):
                    update_row(product_id, attributes)
                    cat = attributes.get("GarmentCategory", "?")
                    sub = attributes.get("GarmentSubtype", "?")
                    print(f"  OK ({elapsed:.1f}s): {product_id} — {title} → {cat}/{sub}")
                    total_success += 1
                else:
                    print(f"  FAIL (null result): {product_id} — {title}")
                    client.update_one(
                        "catalog_enriched",
                        filters={"product_id": f"eq.{product_id}"},
                        patch={"row_status": "enrichment_failed", "error_reason": "null_attributes_from_model"},
                    )
                    total_failed += 1
            except KeyboardInterrupt:
                print("\n\nInterrupted! Progress is saved — re-run to continue.")
                break
            except Exception as exc:
                print(f"  ERROR: {product_id} — {title} — {exc}")
                total_failed += 1

            total_processed += 1

            # Rate limit: ~1 request per second
            time.sleep(0.5)
        else:
            continue
        break  # KeyboardInterrupt

    print(f"\n{'='*50}")
    print(f"Total processed: {total_processed}")
    print(f"  Success: {total_success}")
    print(f"  Failed:  {total_failed}")
    print(f"  Skipped: {total_skipped}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
