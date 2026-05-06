#!/usr/bin/env python3
"""Generate the bootstrap intent grid (Pre-launch Step 2 deliverable).

Outputs:
- ``ops/bootstrap/bootstrap_profile_pool.json`` — synthetic profile pool
- ``ops/bootstrap/bootstrap_grid.csv`` — grid cells with metadata
- stdout: cell count + estimated bootstrap cost

Coverage filter is opt-in and requires Supabase access — pass
``--with-coverage`` to query ``catalog_enriched`` for per-bucket SKU
counts and emit a coverage report. Without it, the grid is the
unfiltered enumeration and Step 3 (recipe bootstrap) re-checks coverage
at recipe-generation time per cell.

Determinism: the script is seeded; running twice with the same
``--seed`` and ``--profile-count`` produces byte-identical files.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (
    ROOT,
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from agentic_application.recipes.grid import (
    enumerate_grid,
    estimate_cost,
    write_grid_csv,
)
from agentic_application.recipes.profiles import generate_profile_pool


def _print_cost(cost: dict) -> None:
    print(f"\nCost estimate (bootstrap LLM spend, excludes try-on):")
    print(f"  Cells:           {cost['cell_count']:>8,}")
    print(f"  Cost per cell:   ${cost['cost_per_cell_usd']:.4f}")
    print(f"  Total estimated: ${cost['total_cost_usd']:>10,.2f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--out-dir", default="ops/bootstrap", help="Output directory (default: ops/bootstrap)")
    parser.add_argument("--profile-count", type=int, default=75, help="Profile pool size (default: 75)")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for deterministic output (default: 42)")
    parser.add_argument(
        "--intents",
        nargs="+",
        default=["occasion_recommendation", "pairing_request"],
        help="Intents to enumerate (default: occasion_recommendation pairing_request)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Profile pool ──────────────────────────────────────────────────────
    print(f"Generating profile pool (size={args.profile_count}, seed={args.seed})...")
    profiles = generate_profile_pool(target_size=args.profile_count, seed=args.seed)
    profile_path = out_dir / "bootstrap_profile_pool.json"
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump([p.to_dict() for p in profiles], f, indent=2)
        f.write("\n")
    print(f"  → {profile_path} ({len(profiles)} profiles)")

    # Grid ──────────────────────────────────────────────────────────────
    print(f"Enumerating grid for intents={args.intents}...")
    cells = enumerate_grid(profiles, intents=args.intents)
    grid_path = out_dir / "bootstrap_grid.csv"
    write_grid_csv(cells, grid_path)
    print(f"  → {grid_path} ({len(cells):,} cells)")

    # Cost ──────────────────────────────────────────────────────────────
    cost = estimate_cost(cells)
    _print_cost(cost)

    if cost["total_cost_usd"] > 20_000:
        print("\n⚠ WARNING: estimated cost exceeds the $10–20K budget in OPEN_TASKS.")
        print("  Consider trimming the occasion list or reducing profile count.")
    elif cost["total_cost_usd"] < 100:
        print("\n⚠ WARNING: estimated cost is unusually low — verify the grid was generated.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
