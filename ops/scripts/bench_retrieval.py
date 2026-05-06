"""Benchmark match_catalog_item_embeddings RPC end-to-end.

Run against staging or local with a representative set of filters; reports
per-query and total wall-clock time so we can verify the Phase 1.2 RPC
rewrite (drop MATERIALIZED CTE, use iterative HNSW scan) actually drops
retrieval from ~2.9s to <500ms.

Usage:
    APP_ENV=staging python ops/scripts/bench_retrieval.py
    APP_ENV=local   python ops/scripts/bench_retrieval.py --runs 5

The script generates a 1536-dim query embedding once (deterministic
random), then issues N RPC calls in series with realistic filter mixes
sampled from the live filter dispatch in build_directional_filters /
extract_query_document_filters. Output: count, p50, p95, max per filter
profile and overall.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from typing import Any, Dict, List

# Reuse the production vector store wiring rather than re-implementing
# Supabase client setup. This guarantees we hit the same RPC the agent
# uses in production.
from catalog.retrieval.vector_store import SupabaseVectorStore


# Representative filter mixes spanning the 3-direction × 2-3-role fan-out
# the architect emits. Keep these in sync with build_directional_filters
# if that contract changes.
FILTER_PROFILES: List[Dict[str, Any]] = [
    {
        "name": "anchor_top_minimal",
        "filters": {"gender_expression": "female", "garment_category": "topwear"},
    },
    {
        "name": "anchor_top_full",
        "filters": {
            "gender_expression": "female",
            "garment_category": "topwear",
            "formality_level": "3",
            "occasion_fit": "social_casual",
            "time_of_day": "evening",
        },
    },
    {
        "name": "needs_bottomwear",
        "filters": {
            "gender_expression": "female",
            "garment_category": "bottomwear",
            "styling_completeness": "needs_topwear",
        },
    },
    {
        "name": "outerwear_three_piece",
        "filters": {
            "gender_expression": "female",
            "garment_category": "outerwear",
            "styling_completeness": ["needs_innerwear", "needs_topwear"],
        },
    },
    {
        "name": "high_selectivity",
        "filters": {
            "gender_expression": "female",
            "garment_category": "ethnic_wear",
            "garment_subtype": ["anarkali", "kurta_set", "lehenga_set"],
            "formality_level": "5",
            "occasion_fit": "wedding",
        },
    },
    {
        "name": "low_selectivity",
        "filters": {"gender_expression": "female"},
    },
]


def _deterministic_query_embedding(dim: int = 1536) -> List[float]:
    import random
    rng = random.Random(42)
    raw = [rng.gauss(0.0, 1.0) for _ in range(dim)]
    norm = sum(v * v for v in raw) ** 0.5 or 1.0
    return [v / norm for v in raw]


def _summarize(times_ms: List[float]) -> Dict[str, float]:
    if not times_ms:
        return {"n": 0}
    return {
        "n": len(times_ms),
        "p50_ms": round(statistics.median(times_ms), 1),
        "p95_ms": round(times_ms[max(0, int(0.95 * len(times_ms)) - 1)], 1) if len(times_ms) >= 5 else round(max(times_ms), 1),
        "max_ms": round(max(times_ms), 1),
        "mean_ms": round(statistics.mean(times_ms), 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3, help="Runs per filter profile (default: 3)")
    ap.add_argument("--match-count", type=int, default=20, help="match_count parameter (default: 20)")
    args = ap.parse_args()

    store = SupabaseVectorStore()
    query_embedding = _deterministic_query_embedding()

    print(f"Bench: {len(FILTER_PROFILES)} filter profiles × {args.runs} runs each, match_count={args.match_count}")
    print("-" * 80)

    all_times: List[float] = []
    rows_by_profile: List[Dict[str, Any]] = []

    for profile in FILTER_PROFILES:
        per_run_ms: List[float] = []
        last_count = 0
        for _ in range(args.runs):
            t0 = time.monotonic()
            try:
                rows = store.similarity_search(
                    query_embedding=query_embedding,
                    match_count=args.match_count,
                    filters=profile["filters"],
                )
                last_count = len(rows or [])
            except Exception as exc:  # noqa: BLE001 — bench script
                print(f"  [{profile['name']}] FAILED: {exc}")
                break
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            per_run_ms.append(elapsed_ms)
            all_times.append(elapsed_ms)

        summary = _summarize(per_run_ms)
        summary["name"] = profile["name"]
        summary["match_returned"] = last_count
        rows_by_profile.append(summary)
        print(
            f"  {profile['name']:<28} n={summary.get('n', 0):>2}  "
            f"p50={summary.get('p50_ms', 0):>6}ms  "
            f"p95={summary.get('p95_ms', 0):>6}ms  "
            f"returned={last_count}"
        )

    print("-" * 80)
    overall = _summarize(all_times)
    print(
        f"OVERALL  n={overall['n']}  p50={overall['p50_ms']}ms  "
        f"p95={overall['p95_ms']}ms  max={overall['max_ms']}ms  mean={overall['mean_ms']}ms"
    )
    print()
    print("Phase 1.2 acceptance: per-query p95 ≤ 100ms, overall mean ≤ 80ms.")

    if overall["p95_ms"] > 100:
        print(f"FAIL: p95={overall['p95_ms']}ms exceeds 100ms target.")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
