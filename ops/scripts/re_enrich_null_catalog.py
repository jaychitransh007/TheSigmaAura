#!/usr/bin/env python3
"""Re-enrich catalog rows that have null GarmentCategory using the
OpenAI Batch API — the same mechanism the catalog admin UI uses.

1. Fetches all null-enriched rows from catalog_enriched
2. Builds a JSONL batch file (same format as the admin enrichment)
3. Submits to OpenAI Batch API
4. Polls until complete
5. Parses results and updates catalog_enriched

Usage:
    APP_ENV=staging python3 ops/scripts/re_enrich_null_catalog.py

Expects SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, and OPENAI_API_KEY
in the environment (loaded from .env.staging via APP_ENV).
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ["modules/platform_core/src", "modules/user/src", "modules/catalog/src", "modules/user_profiler/src"]:
    sys.path.insert(0, os.path.join(ROOT, p))

from platform_core.config import load_config
from platform_core.supabase_rest import SupabaseRestClient
from catalog.enrichment.batch_builder import build_request_body
from catalog.enrichment.batch_runner import BatchRunner, extract_file_ids
from catalog.enrichment.config import PipelineConfig, get_api_key

# ── Setup ──
config = load_config()
client = SupabaseRestClient(
    rest_url=config.supabase_rest_url,
    service_role_key=config.supabase_service_role_key,
)
api_key = get_api_key()
pipeline_config = PipelineConfig()

OUTPUT_DIR = os.path.join(ROOT, "data", "catalog", "re_enrich")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_all_null_rows():
    """Fetch catalog rows where GarmentCategory is null (up to 5000)."""
    return client.select_many(
        "catalog_enriched",
        filters={"GarmentCategory": "is.null"},
        order="product_id.asc",
        limit=5000,
    )


def build_batch_jsonl(rows, output_path):
    """Build the JSONL batch input file from the null rows."""
    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for idx, row in enumerate(rows):
            image_url = str(row.get("images_0_src") or "").strip()
            if not image_url:
                continue
            # Build the same row format the batch_builder expects
            enrichment_row = {
                "product_id": str(row.get("product_id") or ""),
                "title": str(row.get("title") or ""),
                "description": str(row.get("description") or ""),
                "images__0__src": image_url,
                "images__1__src": str(row.get("images_1_src") or ""),
                "url": str(row.get("url") or ""),
            }
            req = {
                "custom_id": f"null_row_{idx}__{enrichment_row['product_id']}",
                "method": "POST",
                "url": pipeline_config.endpoint,
                "body": build_request_body(enrichment_row, pipeline_config),
            }
            f.write(json.dumps(req, ensure_ascii=True) + "\n")
            count += 1
    return count


def parse_and_update_results(results_path, rows):
    """Parse batch results and update catalog_enriched."""
    # Build a product_id lookup from the rows
    pid_map = {}
    for idx, row in enumerate(rows):
        pid_map[f"null_row_{idx}__{row.get('product_id', '')}"] = row.get("product_id", "")

    success = 0
    failed = 0
    with open(results_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            result = json.loads(line)
            custom_id = result.get("custom_id", "")
            product_id = pid_map.get(custom_id, "")
            if not product_id:
                continue

            response = result.get("response", {})
            status_code = response.get("status_code")
            if status_code != 200:
                print(f"  FAIL (HTTP {status_code}): {product_id}")
                failed += 1
                continue

            # Extract the model output
            body = response.get("body", {})
            output_text = ""
            for output_item in body.get("output", []):
                if output_item.get("type") == "message":
                    for content in output_item.get("content", []):
                        if content.get("type") == "output_text":
                            output_text = content.get("text", "")
                            break

            if not output_text:
                print(f"  FAIL (no output): {product_id}")
                failed += 1
                continue

            try:
                attributes = json.loads(output_text)
            except json.JSONDecodeError:
                print(f"  FAIL (bad JSON): {product_id}")
                failed += 1
                continue

            if not attributes.get("GarmentCategory"):
                print(f"  FAIL (null category): {product_id}")
                failed += 1
                continue

            # Build the update patch
            patch = {}
            for key, value in attributes.items():
                if key.endswith("_confidence"):
                    try:
                        patch[key] = float(value) if value is not None else None
                    except (TypeError, ValueError):
                        patch[key] = None
                else:
                    patch[key] = str(value).strip() if value is not None else None
            patch["row_status"] = "ok"

            try:
                client.update_one(
                    "catalog_enriched",
                    filters={"product_id": f"eq.{product_id}"},
                    patch=patch,
                )
                cat = attributes.get("GarmentCategory", "?")
                sub = attributes.get("GarmentSubtype", "?")
                print(f"  OK: {product_id[:50]:50s} → {cat}/{sub}")
                success += 1
            except Exception as exc:
                print(f"  FAIL (db update): {product_id} — {exc}")
                failed += 1

    return success, failed


def main():
    print("=" * 60)
    print("Re-enrich null catalog rows via OpenAI Batch API")
    print("=" * 60)

    # Step 1: Fetch null rows
    print("\n[1/5] Fetching null-enriched rows...")
    rows = fetch_all_null_rows()
    print(f"  Found {len(rows)} rows with null GarmentCategory")
    if not rows:
        print("  Nothing to do!")
        return

    # Step 2: Build batch JSONL
    jsonl_path = os.path.join(OUTPUT_DIR, "re_enrich_batch_input.jsonl")
    print(f"\n[2/5] Building batch JSONL → {jsonl_path}")
    count = build_batch_jsonl(rows, jsonl_path)
    print(f"  {count} requests written ({len(rows) - count} skipped — no image)")

    if count == 0:
        print("  No valid requests to submit!")
        return

    # Step 3: Submit batch
    print(f"\n[3/5] Submitting batch to OpenAI ({pipeline_config.model})...")
    runner = BatchRunner(api_key=api_key, config=pipeline_config)
    file_id = runner.upload_batch_file(jsonl_path)
    print(f"  Uploaded file: {file_id}")
    batch_id = runner.create_batch(file_id)
    print(f"  Batch created: {batch_id}")

    # Step 4: Wait for completion
    print(f"\n[4/5] Waiting for batch completion (polling every {pipeline_config.poll_interval_seconds}s, max {pipeline_config.max_wait_minutes}min)...")
    t0 = time.time()
    batch_data = runner.wait_for_completion(batch_id)
    elapsed_min = (time.time() - t0) / 60
    print(f"  Batch status: {batch_data.get('status')}")
    print(f"  Elapsed: {elapsed_min:.1f} minutes")

    file_ids = extract_file_ids(batch_data)
    output_file_id = file_ids.get("output_file_id")
    error_file_id = file_ids.get("error_file_id")

    if not output_file_id:
        print("  ERROR: No output file returned. Batch may have failed.")
        if error_file_id:
            err_path = os.path.join(OUTPUT_DIR, "re_enrich_errors.jsonl")
            runner.download_file_content(error_file_id, err_path)
            print(f"  Error file saved to: {err_path}")
        return

    # Download results
    results_path = os.path.join(OUTPUT_DIR, "re_enrich_batch_output.jsonl")
    runner.download_file_content(output_file_id, results_path)
    print(f"  Results downloaded: {results_path}")

    # Step 5: Parse and update
    print(f"\n[5/5] Parsing results and updating catalog_enriched...")
    success, failed = parse_and_update_results(results_path, rows)

    # Mark rows that were submitted but got no result back as
    # enrichment_failed so they don't loop forever on re-runs.
    # These are typically products with broken/expired image URLs.
    result_pids = set()
    with open(results_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            cid = r.get("custom_id", "")
            # Extract product_id from custom_id format: null_row_{idx}__{product_id}
            parts = cid.split("__", 1)
            if len(parts) == 2:
                result_pids.add(parts[1])

    missing_count = 0
    for idx, row in enumerate(rows):
        pid = str(row.get("product_id") or "")
        image_url = str(row.get("images_0_src") or "").strip()
        if not image_url:
            continue  # already counted as skipped
        if pid not in result_pids:
            # This row was submitted but got no result — mark it
            try:
                client.update_one(
                    "catalog_enriched",
                    filters={"product_id": f"eq.{pid}"},
                    patch={"row_status": "enrichment_failed", "error_reason": "batch_no_result_image_likely_broken"},
                )
                missing_count += 1
            except Exception:
                pass

    print(f"\n{'=' * 60}")
    print(f"Done!")
    print(f"  Total rows:  {len(rows)}")
    print(f"  Enriched:    {success}")
    print(f"  Failed:      {failed}")
    print(f"  No result:   {missing_count} (marked enrichment_failed — likely broken image URLs)")
    print(f"  Skipped:     {len(rows) - count} (no image)")
    print(f"{'=' * 60}")
    print(f"\nNext step: run embedding sync from the catalog admin to")
    print(f"regenerate embeddings with the new enrichment attributes.")


if __name__ == "__main__":
    main()
