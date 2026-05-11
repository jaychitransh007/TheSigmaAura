#!/usr/bin/env python3
"""Upsert the final enrichment CSV into catalog_enriched.

Uses on_conflict=product_id semantics — existing rows get their
enrichment columns REPLACED with the new values. id (uuid) and
created_at are preserved by Postgres; updated_at trigger fires.

Usage:
    APP_ENV=staging python3 ops/scripts/upsert_enriched_to_db.py \\
        --input out/full_enrichment_final.csv
"""
import argparse
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ["modules/platform_core/src", "modules/user/src", "modules/catalog/src", "modules/user_profiler/src"]:
    sys.path.insert(0, os.path.join(ROOT, p))

from catalog.retrieval.repository import read_catalog_rows, build_catalog_enriched_rows
from catalog.retrieval.vector_store import SupabaseVectorStore


# Columns that exist on the catalog_enriched payload-builder output but
# are NOT real columns on the catalog_enriched table — they live in
# raw_row_json instead. Without this filter, Supabase rejects the
# upsert with "Could not find the 'store' column" 400.
_NON_TABLE_COLUMNS = {"store", "handle"}


def _drop_non_table_columns(rows):
    for row in rows:
        for col in _NON_TABLE_COLUMNS:
            row.pop(col, None)
    return rows


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="Enriched CSV path.")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    print(f"[1/3] Reading {args.input}", flush=True)
    t0 = time.time()
    rows = read_catalog_rows(args.input)
    print(f"      {len(rows)} rows in {time.time()-t0:.1f}s", flush=True)

    print(f"[2/3] Building catalog_enriched payload rows", flush=True)
    t0 = time.time()
    item_rows = build_catalog_enriched_rows(rows)
    item_rows = _drop_non_table_columns(item_rows)
    print(f"      {len(item_rows)} payload rows in {time.time()-t0:.1f}s", flush=True)

    print(f"[3/3] Upserting into catalog_enriched (on_conflict=product_id)", flush=True)
    t0 = time.time()
    store = SupabaseVectorStore()
    saved = store.upsert_catalog_enriched(item_rows)
    print(f"      upserted {len(saved)} rows in {time.time()-t0:.1f}s", flush=True)

    print(f"\nDone. {len(saved)}/{len(item_rows)} rows persisted to catalog_enriched.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
