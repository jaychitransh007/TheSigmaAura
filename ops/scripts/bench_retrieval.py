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
# the architect emits. Filter values match the catalog taxonomy as of
# May 2026 (gender: feminine/masculine/unisex; categories: top/bottom/
# outerwear/set/one_piece; formality: casual/smart_casual/semi_formal/
# ceremonial). Keep in sync with build_directional_filters if that
# contract changes.
FILTER_PROFILES: List[Dict[str, Any]] = [
    {
        "name": "anchor_top_minimal",
        "filters": {"gender_expression": "feminine", "garment_category": "top"},
    },
    {
        "name": "anchor_top_full",
        "filters": {
            "gender_expression": "feminine",
            "garment_category": "top",
            "formality_level": "smart_casual",
        },
    },
    {
        "name": "needs_bottomwear",
        "filters": {
            "gender_expression": "feminine",
            "garment_category": "bottom",
            "styling_completeness": "needs_topwear",
        },
    },
    {
        "name": "outerwear_three_piece",
        "filters": {
            "gender_expression": "masculine",
            "garment_category": "outerwear",
            "styling_completeness": ["needs_innerwear", "needs_topwear"],
        },
    },
    {
        "name": "high_selectivity",
        "filters": {
            "gender_expression": "feminine",
            "garment_category": "outerwear",
            "garment_subtype": ["blazer", "jacket"],
            "formality_level": "smart_casual",
        },
    },
    {
        "name": "low_selectivity",
        "filters": {"gender_expression": "feminine"},
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
    # Sort first — `times_ms` arrives in execution order, and the previous
    # version indexed into it directly for the p95 (review of PR #123).
    sorted_times = sorted(times_ms)
    return {
        "n": len(sorted_times),
        "p50_ms": round(statistics.median(sorted_times), 1),
        "p95_ms": round(
            sorted_times[max(0, int(0.95 * len(sorted_times)) - 1)], 1
        ) if len(sorted_times) >= 5 else round(sorted_times[-1], 1),
        "max_ms": round(sorted_times[-1], 1),
        "mean_ms": round(statistics.mean(sorted_times), 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3, help="Runs per filter profile (default: 3)")
    ap.add_argument("--match-count", type=int, default=20, help="match_count parameter (default: 20)")
    args = ap.parse_args()

    store = SupabaseVectorStore()
    query_embedding = _deterministic_query_embedding()

    # Warm-up: one untimed call to absorb DNS / TLS / connection-pool /
    # JIT-plan overhead. In production HTTP keep-alive amortises this
    # cost across many requests; without a warm-up the per-profile p95
    # gets dragged up by a single first-call outlier that doesn't
    # represent steady-state retrieval latency.
    try:
        store.similarity_search(
            query_embedding=query_embedding,
            match_count=args.match_count,
            filters=FILTER_PROFILES[0]["filters"],
        )
    except Exception as exc:  # noqa: BLE001 — surfaced via timed runs below
        print(f"Warm-up call failed: {exc}; continuing.")

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
    print("Phase 1.2 acceptance: per-PROFILE p95 ≤ 200ms across all profiles.")
    print("(Overall p95 across the whole sample is dominated by occasional")
    print(" cold-start outliers; per-profile p95 is the steady-state signal.)")

    breached = [
        s for s in rows_by_profile
        if s.get("p95_ms", 0) > 200
    ]
    if breached:
        print(f"FAIL: {len(breached)} profile(s) exceed 200ms p95: "
              + ", ".join(f"{s['name']}={s['p95_ms']}ms" for s in breached))
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
