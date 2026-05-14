#!/usr/bin/env python3
"""Dump catalog_enriched to CSV for TheSigmaVibe seeding.

One-shot. Pulls every column of every row so we can profile the data
locally and design the Shopify import without DB round-trips.

Usage:
    python3 scripts/seed_thesigmavibe_catalog/dump_catalog.py

Env-file lookup:
    1. $AURA_ENV_FILE (explicit override) — used as-is if set.
    2. Otherwise walk up from this script's directory looking for any of
       .env.staging, .env.local, .env (in that order). Stops at the
       first match. Works whether the script lives in a git worktree,
       the main checkout, a CI clone, or anywhere else.
"""
import csv
import json
import os
import sys
from pathlib import Path

import httpx

SCRIPT_DIR = Path(__file__).resolve().parent
WORKTREE = SCRIPT_DIR.parents[1]  # scripts/<name>/dump.py → 2 up to repo root
PAGE_SIZE = 1000
ENV_CANDIDATES = (".env.staging", ".env.local", ".env")
ENV_SEARCH_MAX_DEPTH = 8


def find_env_file() -> Path:
    explicit = os.environ.get("AURA_ENV_FILE", "").strip()
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(
                f"AURA_ENV_FILE points to {path} but the file doesn't exist."
            )
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
        "No env file found. Tried "
        f"{', '.join(ENV_CANDIDATES)} in {SCRIPT_DIR} and parents (up to "
        f"{ENV_SEARCH_MAX_DEPTH} levels). Set AURA_ENV_FILE explicitly to "
        "override."
    )


OUTPUT = WORKTREE / "data" / "catalog_enriched_full.csv"


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


def main() -> int:
    try:
        env_file = find_env_file()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not env_file.exists():
        print(f"ERROR: env file not found at {env_file}", file=sys.stderr)
        return 1

    env = load_env(env_file)
    base = env["SUPABASE_URL"].rstrip("/")
    if not base.endswith("/rest/v1"):
        base = f"{base}/rest/v1"
    service_key = env["SUPABASE_SERVICE_ROLE_KEY"]

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"Dumping catalog_enriched → {OUTPUT}", flush=True)

    offset = 0
    written = 0
    writer: csv.DictWriter | None = None

    with httpx.Client(timeout=60.0, headers=headers) as client, \
         open(OUTPUT, "w", encoding="utf-8", newline="") as out_file:
        while True:
            resp = client.get(
                f"{base}/catalog_enriched",
                params={
                    "select": "*",
                    "order": "product_id.asc",
                    "limit": str(PAGE_SIZE),
                    "offset": str(offset),
                },
            )
            resp.raise_for_status()
            page = resp.json()
            if not page:
                break

            if writer is None:
                fieldnames = list(page[0].keys())
                writer = csv.DictWriter(out_file, fieldnames=fieldnames)
                writer.writeheader()

            for row in page:
                for k, v in list(row.items()):
                    if isinstance(v, (dict, list)):
                        row[k] = json.dumps(v, separators=(",", ":"))
                writer.writerow(row)
                written += 1

            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
            if offset % 5000 == 0:
                print(f"  ... {written} rows", flush=True)

    print(f"Done. {written} rows → {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
