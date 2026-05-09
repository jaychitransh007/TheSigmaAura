"""Smoke-test the Gemini-2.5-Flash catalog enrichment migration on a small sample.

Used to validate the end-to-end pipeline (canonical schema → Gemini
response_schema → API call → parse) before firing the full re-enrichment
on 14,296 catalog rows.

The runner reads N rows from one of three input sources, runs each
through Gemini, and writes parsed results to a JSONL file plus a
human-readable summary on stdout.

────────────────────────────────────────────────────────────────────────
Usage examples
────────────────────────────────────────────────────────────────────────

# 1. Pull N random rows from staging Supabase ``catalog_enriched``
APP_ENV=staging PYTHONPATH=modules/agentic_application/src:modules/catalog/src:modules/platform_core/src:modules/style_engine/src:modules/user/src:modules/user_profiler/src \\
    python ops/scripts/run_gemini_enrichment.py --limit 5 --source staging

# 2. Read from a CSV file (same shape the existing main pipeline uses —
#    description, images__0__src, images__1__src, url, etc.)
PYTHONPATH=... python ops/scripts/run_gemini_enrichment.py \\
    --input catalog_sample.csv --limit 10

# 3. Read from a JSONL file (one JSON object per line; same column names)
PYTHONPATH=... python ops/scripts/run_gemini_enrichment.py \\
    --input catalog_sample.jsonl

────────────────────────────────────────────────────────────────────────
Required environment
────────────────────────────────────────────────────────────────────────

GEMINI_API_KEY     — for vision calls (already set in .env.staging /
                     .env.local for the try-on path).

For ``--source staging`` only:
SUPABASE_URL                — staging REST endpoint
SUPABASE_SERVICE_ROLE_KEY   — staging service-role key
APP_ENV=staging             — picks the right .env file

────────────────────────────────────────────────────────────────────────
Output
────────────────────────────────────────────────────────────────────────

Default output: ``out/gemini_smoke_<unix_timestamp>.jsonl`` — one JSON
object per row containing the full Gemini-parsed payload + status +
custom_id. Inspect manually for correctness; spot-check the new
ShapeArchitecture axes (VolumePlacement, AsymmetryType,
AttachmentStructure, MotionBehavior).
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "modules" / "catalog" / "src"))
sys.path.insert(0, str(_REPO_ROOT / "modules" / "platform_core" / "src"))


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


def _load_rows_from_csv(path: str, limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if limit and i >= limit:
                break
            rows.append(row)
    return rows


def _load_rows_from_jsonl(path: str, limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _load_rows_from_staging(limit: int) -> list[dict[str, str]]:
    """Pull N random rows with both images populated from staging
    ``catalog_enriched``. Uses the existing Supabase REST client."""
    from platform_core.supabase_rest import SupabaseRestClient

    rest_url = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1"
    client = SupabaseRestClient(
        rest_url=rest_url,
        service_role_key=os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    # Pull a few extras so we can filter out rows missing images.
    overshoot = max(limit * 3, limit + 10)
    rows = client.select_many(
        "catalog_enriched",
        columns="id,product_id,source_row_number,description,images_0_src,images_1_src,url,title",
        filters={"limit": str(overshoot), "order": "created_at.desc"},
        limit=overshoot,
    )
    # The DB stores ``images_0_src`` / ``images_1_src`` (snake-case);
    # the runner expects ``images__0__src`` (the CSV pipeline shape).
    # Translate so the same row dict works for both code paths.
    out: list[dict[str, str]] = []
    for r in rows:
        if not r.get("images_0_src"):
            continue
        out.append({
            "id": r.get("id", ""),
            "product_id": r.get("product_id", ""),
            "source_row_number": r.get("source_row_number", ""),
            "description": r.get("description", "") or "",
            "url": r.get("url", "") or "",
            "store": r.get("title", "") or "",
            "images__0__src": r.get("images_0_src", "") or "",
            "images__1__src": r.get("images_1_src", "") or "",
        })
        if len(out) >= limit:
            break
    return out


def _summarise_results(results: list[dict[str, object]]) -> dict[str, int]:
    counts = {"ok": 0, "error": 0}
    error_breakdown: dict[str, int] = {}
    for r in results:
        status = str(r.get("row_status") or "error")
        counts[status] = counts.get(status, 0) + 1
        if status == "error":
            reason = str(r.get("error_reason") or "unknown")
            short = reason.split(":")[0]
            error_breakdown[short] = error_breakdown.get(short, 0) + 1
    counts["error_breakdown"] = error_breakdown  # type: ignore[assignment]
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test Gemini-2.5-Flash catalog enrichment.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--source",
        choices=("csv", "jsonl", "staging"),
        default="staging",
        help="Where to read input rows from (default: staging Supabase).",
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Input file path (required when --source is csv or jsonl).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="How many rows to enrich (default: 5).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSONL path. Default: out/gemini_smoke_<timestamp>.jsonl",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Verbose logging.",
    )
    args = parser.parse_args()

    _setup_logging(args.verbose)

    if args.source in ("csv", "jsonl") and not args.input:
        parser.error(f"--input is required when --source is {args.source}")

    if args.source == "csv":
        rows = _load_rows_from_csv(args.input, args.limit)
    elif args.source == "jsonl":
        rows = _load_rows_from_jsonl(args.input, args.limit)
    else:  # staging
        rows = _load_rows_from_staging(args.limit)

    if not rows:
        print("No rows to enrich. Check --input or staging connectivity.")
        return 2

    print(f"Loaded {len(rows)} rows for enrichment.")

    # Defer imports until after sys.path is set up + after we know we
    # have rows to process — keeps `--help` snappy and avoids failing
    # on missing GEMINI_API_KEY when the user just wants the help text.
    from catalog.enrichment.gemini_runner import GeminiEnrichmentRunner

    runner = GeminiEnrichmentRunner()
    print(f"Running on Gemini model: {runner._config.model}")
    print(
        f"Concurrency: {runner._config.max_concurrent_requests} "
        f"requests at a time"
    )
    print()

    t0 = time.monotonic()
    results = runner.enrich_rows(rows)
    elapsed = time.monotonic() - t0

    output_path = (
        args.output
        or str(_REPO_ROOT / "out" / f"gemini_smoke_{int(time.time())}.jsonl")
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    counts = _summarise_results(results)
    print(f"\n=== Summary (elapsed {elapsed:.1f}s) ===")
    print(f"  ok     : {counts['ok']}")
    print(f"  error  : {counts['error']}")
    if counts.get("error_breakdown"):
        print("\n  error breakdown:")
        for reason, n in sorted(
            counts["error_breakdown"].items(),  # type: ignore[union-attr]
            key=lambda x: -x[1],
        ):
            print(f"    {n:3d}  {reason}")
    print(f"\nResults written to: {output_path}")

    if counts["error"] > 0 and counts["ok"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
