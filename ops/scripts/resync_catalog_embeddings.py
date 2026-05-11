#!/usr/bin/env python3
"""Re-generate catalog embeddings from the current catalog_enriched DB state.

Reads all rows from catalog_enriched, builds embedding documents that
include the new ShapeArchitecture + v3 axes, generates fresh embeddings
via OpenAI, and upserts them into catalog_item_embeddings.

Uses admin_service.resync_catalog_embeddings, which has built-in disk-cache
resumability — if the run is interrupted after embeddings are generated
but before the Supabase upsert succeeds, re-running picks up from the
cache instead of paying for OpenAI again.

Usage:
    APP_ENV=staging python3 ops/scripts/resync_catalog_embeddings.py
"""
import logging
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ["modules/platform_core/src", "modules/user/src", "modules/catalog/src", "modules/user_profiler/src"]:
    sys.path.insert(0, os.path.join(ROOT, p))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)

from catalog.admin_service import CatalogAdminService


def main() -> int:
    t0 = time.time()
    service = CatalogAdminService()
    result = service.resync_catalog_embeddings()
    elapsed = time.time() - t0
    print()
    print("=" * 60)
    print(f"Done in {elapsed/60:.1f} min")
    print(f"  processed: {result['processed_rows']} documents")
    print(f"  saved:     {result['saved_rows']} embeddings")
    print(f"  job_id:    {result['job_id']}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
