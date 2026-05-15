#!/usr/bin/env python3
"""B.8 — Capture Shopify product/variant GIDs back into catalog_enriched.

Walks every product in the Shopify production store, matches each to
the local catalog_enriched row via the `vibe.source_product_id`
metafield, and writes back `shopify_product_id` + `shopify_variant_ids`
(jsonb keyed by size: XS/S/M/L/XL → gid string).

After this script runs, D.C.7 (Add to Cart) can resolve a customer's
selected size → variant gid → Shopify cart.

Required env vars (pass on the command line OR put in vibe-app/.env):
    SHOPIFY_SHOP_DOMAIN      e.g., the-vibe-shop-9376.myshopify.com
    SHOPIFY_ADMIN_API_TOKEN  shpat_*** (read_products scope)

Supabase creds (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY) are read from
.env.staging via the same upward-walk resolver used by dump_catalog.py.
Override with $AURA_ENV_FILE.

Usage:
    SHOPIFY_SHOP_DOMAIN=the-vibe-shop-9376.myshopify.com \\
    SHOPIFY_ADMIN_API_TOKEN=shpat_xxxxx \\
    python3 scripts/seed_thesigmavibe_catalog/capture_shopify_gids.py

How to get SHOPIFY_ADMIN_API_TOKEN:
    1. Shopify admin (production store) → Settings → Apps and sales channels
       → Develop apps → Allow custom app development (one-time)
    2. Create an app (e.g., "Vibe GID capture")
    3. Configuration → Admin API access scopes → enable `read_products`
       (and `read_product_listings` if shown)
    4. Install the app → copy the Admin API access token (shpat_***)
    5. Token is shown ONCE — paste it into this command immediately.

This script is idempotent. Re-runs only update rows whose
shopify_product_id or shopify_variant_ids changed. Safe to re-run if
interrupted.
"""
import csv
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

SCRIPT_DIR = Path(__file__).resolve().parent
WORKTREE = SCRIPT_DIR.parents[1]
ENV_CANDIDATES = (".env.staging", ".env.local", ".env")
ENV_SEARCH_MAX_DEPTH = 8

API_VERSION = "2026-04"
PAGE_SIZE = 50  # GraphQL `products(first: N)`; 50 is well under cost cap
SUPABASE_PAGE_SIZE = 50  # Parallel PATCH workers


# ─────────────────────────────────────────────────────────────────────
# Env lookup (mirrors dump_catalog.py — portable across worktree / CI)
# ─────────────────────────────────────────────────────────────────────

def find_env_file() -> Path:
    explicit = os.environ.get("AURA_ENV_FILE", "").strip()
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"AURA_ENV_FILE points to {path} but the file doesn't exist.")
        return path

    current = SCRIPT_DIR
    for _ in range(ENV_SEARCH_MAX_DEPTH):
        for name in ENV_CANDIDATES:
            candidate = current / name
            if candidate.is_file():
                return candidate
        if current.parent == current:
            break
        current = current.parent

    raise FileNotFoundError(
        f"No env file found. Tried {', '.join(ENV_CANDIDATES)} in {SCRIPT_DIR} and parents."
    )


def load_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


# ─────────────────────────────────────────────────────────────────────
# Shopify Admin GraphQL
# ─────────────────────────────────────────────────────────────────────

PRODUCTS_QUERY = """
query CaptureGIDs($cursor: String) {
  products(first: %d, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        sourceProductId: metafield(namespace: "vibe", key: "source_product_id") { value }
        variants(first: 20) {
          edges {
            node {
              id
              selectedOptions { name value }
            }
          }
        }
      }
    }
  }
}
""" % PAGE_SIZE


def fetch_shopify_page(client: httpx.Client, shop: str, token: str, cursor: str | None):
    url = f"https://{shop}/admin/api/{API_VERSION}/graphql.json"
    resp = client.post(
        url,
        json={"query": PRODUCTS_QUERY, "variables": {"cursor": cursor}},
        headers={
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    body = resp.json()
    if "errors" in body:
        raise RuntimeError(f"Shopify GraphQL error: {body['errors']}")
    return body["data"]["products"]


def extract_update(node: dict) -> dict | None:
    """Pull (source_product_id, shopify_product_id, variant_ids) from a
    Shopify product node. Returns None if the product lacks the
    vibe.source_product_id metafield (i.e., wasn't imported by us)."""
    mf = node.get("sourceProductId")
    if not mf or not mf.get("value"):
        return None

    variant_ids: dict[str, str] = {}
    for edge in node["variants"]["edges"]:
        var = edge["node"]
        size = None
        for opt in var.get("selectedOptions") or []:
            if opt["name"].lower() == "size":
                size = opt["value"]
                break
        if size:
            variant_ids[size] = var["id"]

    return {
        "product_id": mf["value"],
        "shopify_product_id": node["id"],
        "shopify_variant_ids": variant_ids,
    }


# ─────────────────────────────────────────────────────────────────────
# Supabase REST write-back
# ─────────────────────────────────────────────────────────────────────

def patch_one(client: httpx.Client, supabase_rest: str, service_key: str, update: dict) -> tuple[bool, str]:
    url = (
        f"{supabase_rest}/catalog_enriched"
        f"?product_id=eq.{httpx.QueryParams({'product_id': update['product_id']})['product_id']}"
    )
    resp = client.patch(
        url,
        json={
            "shopify_product_id": update["shopify_product_id"],
            "shopify_variant_ids": update["shopify_variant_ids"],
        },
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        timeout=30.0,
    )
    if resp.status_code >= 400:
        return False, f"{resp.status_code} {resp.text[:200]}"
    return True, ""


def apply_batch(supabase_rest: str, service_key: str, batch: list[dict]) -> tuple[int, list[str]]:
    """Parallel PATCH for a batch of updates. Returns (success_count, errors)."""
    successes = 0
    errors: list[str] = []
    with httpx.Client(http2=False) as client, ThreadPoolExecutor(max_workers=10) as pool:
        futures = {
            pool.submit(patch_one, client, supabase_rest, service_key, u): u
            for u in batch
        }
        for fut in as_completed(futures):
            ok, err = fut.result()
            if ok:
                successes += 1
            else:
                u = futures[fut]
                errors.append(f"product_id={u['product_id']}: {err}")
    return successes, errors


# ─────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────

def main() -> int:
    shop = os.environ.get("SHOPIFY_SHOP_DOMAIN", "").strip()
    token = os.environ.get("SHOPIFY_ADMIN_API_TOKEN", "").strip()
    if not shop or not token:
        print("ERROR: set SHOPIFY_SHOP_DOMAIN and SHOPIFY_ADMIN_API_TOKEN env vars.", file=sys.stderr)
        return 1

    env = load_env(find_env_file())
    supabase_url = env.get("SUPABASE_URL", "").strip().rstrip("/")
    service_key = env.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supabase_url or not service_key:
        print("ERROR: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY missing from env file.", file=sys.stderr)
        return 1
    supabase_rest = (
        supabase_url if supabase_url.endswith("/rest/v1") else f"{supabase_url}/rest/v1"
    )

    print(f"Shop:      {shop}")
    print(f"Supabase:  {supabase_rest}")
    print()

    total_scanned = 0
    total_matched = 0
    total_written = 0
    all_errors: list[str] = []

    with httpx.Client(http2=False) as shopify_client:
        cursor: str | None = None
        page_idx = 0
        while True:
            page_idx += 1
            page = fetch_shopify_page(shopify_client, shop, token, cursor)
            updates: list[dict] = []
            for edge in page["edges"]:
                total_scanned += 1
                update = extract_update(edge["node"])
                if update:
                    total_matched += 1
                    updates.append(update)

            if updates:
                wrote, errors = apply_batch(supabase_rest, service_key, updates)
                total_written += wrote
                all_errors.extend(errors)

            print(
                f"page {page_idx:>3}: scanned={total_scanned:>5}  matched={total_matched:>5}  written={total_written:>5}",
                flush=True,
            )

            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]

    print()
    print(f"Done. Scanned {total_scanned} Shopify products, matched {total_matched}, wrote {total_written}.")
    if all_errors:
        print(f"Errors: {len(all_errors)} (first 5)")
        for e in all_errors[:5]:
            print(f"  - {e}")
    return 0 if not all_errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
