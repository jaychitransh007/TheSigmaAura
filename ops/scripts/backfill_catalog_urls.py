#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
for p in (
    ROOT,
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "catalog_retrieval" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from catalog.admin_service import CatalogAdminService
from catalog_retrieval.vector_store import SupabaseVectorStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill canonical product URLs in catalog_enriched.")
    parser.add_argument("--max-rows", type=int, default=0, help="Limit rows processed; 0 means all matching rows.")
    args = parser.parse_args()

    service = CatalogAdminService(vector_store=SupabaseVectorStore())
    result = service.backfill_catalog_urls(max_rows=args.max_rows)
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
