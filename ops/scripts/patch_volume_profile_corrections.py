"""One-shot patch: correct mistagged products surfaced in the May-9 office-
meeting pairing turn (turn efe101b1).

Two products were inappropriately recommended for an office-meeting pairing
because their formality / occasion attributes overstated their workplace fit.
Product 1 also had a localized architectural sleeve shape that the schema
couldn't represent until ``sculpted`` was added to the VolumeProfile enum
(this PR).

Patches ``catalog_enriched`` and triggers an in-process embedding resync for
each affected product (catalog_item_embeddings is rebuilt from the new
enriched row).

Idempotent: a re-run will simply re-set the same target values and re-embed.

Usage:
  set -a && source .env.staging && set +a
  python ops/scripts/patch_volume_profile_corrections.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).resolve().parents[2]
for _p in (
    _ROOT,
    _ROOT / "modules" / "platform_core" / "src",
    _ROOT / "modules" / "catalog" / "src",
    _ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(_p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from platform_core.supabase_rest import SupabaseRestClient  # type: ignore[import-not-found]


PRODUCTS: list[dict[str, Any]] = [
    {
        "product_id": "SHOWOFFFF_10081148305684_51822366720276",
        "label": "Women's Ribbed Black Ombre Sculpted Sleeve Top",
        "patch": {
            "FormalityLevel": "casual",
            "OccasionFit": "casual",
            "VolumeProfile": "sculpted",
        },
    },
    {
        "product_id": "SHOWOFFFF_9883075346708_50927282618644",
        "label": "Women's Grey Pleated Trousers w/ Drawstring Waistband",
        "patch": {
            "FormalityLevel": "smart_casual",
            "OccasionFit": "casual",
        },
    },
]


def _client() -> SupabaseRestClient:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise SystemExit(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY. "
            "Source .env.staging first, e.g. `set -a && source .env.staging && set +a`."
        )
    return SupabaseRestClient(rest_url=f"{url}/rest/v1", service_role_key=key)


def _read(client: SupabaseRestClient, product_id: str, columns: list[str]) -> Dict[str, Any]:
    cols = ",".join(['"' + c + '"' for c in columns] + ["product_id", "title"])
    rows = client.select_many(
        "catalog_enriched",
        filters={"product_id": f"eq.{product_id}"},
        columns=cols,
        limit=1,
    )
    if not rows:
        raise SystemExit(f"product_id {product_id!r} not found in catalog_enriched")
    return rows[0]


def _resync(product_id: str) -> Dict[str, Any]:
    """Re-embed a single product in-process (no HTTP server required)."""
    from catalog.admin_service import CatalogAdminService  # type: ignore[import-not-found]
    from catalog.retrieval.vector_store import SupabaseVectorStore  # type: ignore[import-not-found]

    service = CatalogAdminService(vector_store=SupabaseVectorStore())
    return service.resync_catalog_embeddings(product_id_prefix=product_id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-resync",
        action="store_true",
        help="Apply DB patch only; skip the embedding resync step.",
    )
    args = parser.parse_args()

    client = _client()
    try:
        for entry in PRODUCTS:
            pid = entry["product_id"]
            patch = entry["patch"]
            cols = list(patch.keys())
            before = _read(client, pid, cols)
            print(f"[{entry['label']}] product_id={pid}")
            for col in cols:
                print(f"  before  {col:18s} = {before.get(col)!r}")
            updated = client.update_one(
                "catalog_enriched",
                filters={"product_id": f"eq.{pid}"},
                patch=patch,
            )
            if updated is None:
                print("  WARN: update returned no row")
                continue
            after = _read(client, pid, cols)
            for col in cols:
                print(f"  after   {col:18s} = {after.get(col)!r}")
            print()
    finally:
        client.close()

    if args.skip_resync:
        print("--skip-resync set; not re-embedding. Run later via admin API or rerun this script.")
        return 0

    print("Re-embedding products in-process...")
    for entry in PRODUCTS:
        pid = entry["product_id"]
        result = _resync(pid)
        print(f"  {pid}: processed={result.get('processed_rows')} saved={result.get('saved_rows')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
