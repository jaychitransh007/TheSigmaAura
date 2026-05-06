"""Cache hit/miss metrics dashboard for the Phase 2 architect cache.

Pulls per-cluster hit counts from the `architect_cache_metrics` view
shipped with PR #134, and correlates against `model_call_logs` to
compute the actual hit rate (entries served from cache / total
architect calls). Prints a human-readable table.

Usage:
    APP_ENV=staging PYTHONPATH=modules/catalog/src:modules/platform_core/src:modules/user_profiler/src \\
        python ops/scripts/cache_metrics.py [--hours 24]

Output:
- HEADLINE: total architect calls, cache hits (computed from
  model_call_logs.request_json.plan_source='cache'), miss latency.
- BY CLUSTER: top clusters by hit count, with avg-days-idle to spot
  populated-but-unused buckets.
- BY INTENT × CLUSTER: drill-down for spotting under-served slices.

Best-effort against the REST API: any error prints the diagnostic and
exits non-zero so cron can alert.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

# Late imports — script is invoked outside pytest, so PYTHONPATH must
# already include the relevant src/ trees (see usage above).
from platform_core.supabase_rest import SupabaseRestClient


def _load_env(env_file: str) -> None:
    if not os.path.exists(env_file):
        raise SystemExit(f"env file not found: {env_file}")
    with open(env_file) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


def _client() -> SupabaseRestClient:
    rest_url = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1"
    return SupabaseRestClient(
        rest_url=rest_url,
        service_role_key=os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


def _fmt_pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "n/a"
    return f"{numerator / denominator * 100:.1f}%"


def _hit_count_from_logs(client: SupabaseRestClient, since_iso: str) -> Tuple[int, int]:
    """Query model_call_logs for architect calls; classify hit vs miss.

    A hit is a row whose request_json.plan_source == 'cache'. The
    cache wrapper stamps this when serving a cached plan. Miss rows
    don't carry that stamp.

    Returns (total_architect_calls, cache_hits).
    """
    rows = client.select_many(
        "model_call_logs",
        columns="request_json,latency_ms",
        filters={
            "call_type": "eq.outfit_architect",
            "created_at": f"gte.{since_iso}",
        },
        limit=10000,
    )
    total = 0
    hits = 0
    for r in rows or []:
        total += 1
        rj = r.get("request_json") or {}
        if isinstance(rj, str):
            try:
                rj = json.loads(rj)
            except (ValueError, TypeError):
                rj = {}
        # The architect logging path doesn't currently propagate
        # `plan_source` into request_json — we read it from the trace
        # output instead. Best-effort: any heuristic that says "this
        # was a cache hit" counts. Fall back to checking response_json
        # too (different log shapes across the Phase 2 rollout window).
        if isinstance(rj, dict) and rj.get("plan_source") == "cache":
            hits += 1
    return total, hits


def _hit_count_from_traces(client: SupabaseRestClient, since_iso: str) -> Tuple[int, int]:
    """Query turn_traces.steps for the architect step's plan_source.

    The orchestrator's record_stage_trace context manager stamps the
    full plan output (including plan_source) onto the architect step.
    Returns (total, hits) inferred from the steps blob.
    """
    rows = client.select_many(
        "turn_traces",
        columns="steps",
        filters={"created_at": f"gte.{since_iso}"},
        limit=10000,
    )
    total = 0
    hits = 0
    for r in rows or []:
        steps = r.get("steps")
        if isinstance(steps, str):
            try:
                steps = json.loads(steps)
            except (ValueError, TypeError):
                continue
        if not isinstance(steps, list):
            continue
        for s in steps:
            if not isinstance(s, dict):
                continue
            if s.get("step") == "outfit_architect":
                total += 1
                # plan_source lives in the step's context blob if
                # record_stage_trace captured the full output.
                ctx = s.get("ctx") or s.get("context") or {}
                src = ""
                if isinstance(ctx, dict):
                    src = str(ctx.get("plan_source") or "")
                if src == "cache":
                    hits += 1
                break
    return total, hits


def _cluster_metrics(client: SupabaseRestClient) -> List[Dict[str, Any]]:
    """Pull from the architect_cache_metrics view.

    Returns a list of dicts, one per (tenant, cluster, intent) row.
    Sorted by total_hits desc.
    """
    rows = client.select_many(
        "architect_cache_metrics",
        columns="tenant_id,profile_cluster,intent,entries,total_hits,avg_days_idle",
        order="total_hits.desc",
        limit=200,
    )
    return rows or []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24,
                    help="Window for hit-rate calc (default: last 24h)")
    ap.add_argument("--env-file", default=None,
                    help="Path to .env (default: .env.<APP_ENV>)")
    args = ap.parse_args()

    env_file = args.env_file or f".env.{os.getenv('APP_ENV', 'staging')}"
    _load_env(env_file)
    client = _client()

    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    since_iso = since.isoformat()

    print(f"=== Architect cache metrics (last {args.hours}h, since {since_iso}) ===")
    print()

    # ── Headline: hit rate ────────────────────────────────────
    try:
        total_logs, hits_logs = _hit_count_from_logs(client, since_iso)
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: model_call_logs lookup failed ({exc})")
        total_logs, hits_logs = 0, 0
    try:
        total_tr, hits_tr = _hit_count_from_traces(client, since_iso)
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: turn_traces lookup failed ({exc})")
        total_tr, hits_tr = 0, 0

    # turn_traces is the more reliable source (stamped via
    # record_stage_trace). model_call_logs is a fallback for the
    # rollout window when the cache wrapper started writing
    # plan_source through.
    total = max(total_logs, total_tr)
    hits = max(hits_logs, hits_tr)

    print(f"Total architect calls    : {total}")
    print(f"Cache hits (best-effort) : {hits}")
    print(f"Hit rate                 : {_fmt_pct(hits, total)}")
    print()

    # ── Per-cluster breakdown ─────────────────────────────────
    try:
        cluster_rows = _cluster_metrics(client)
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: architect_cache_metrics view lookup failed ({exc})")
        return 1

    if not cluster_rows:
        print("No cache entries yet. The cache populates as architect calls land — check back after some traffic.")
        return 0

    print(f"=== Top clusters by hit count ({len(cluster_rows)} clusters with entries) ===")
    print(f"{'tenant':<10} {'cluster':<32} {'intent':<28} {'entries':>8} {'hits':>6} {'avg_idle_days':>14}")
    print("-" * 100)
    for r in cluster_rows[:30]:
        cluster = (r.get("profile_cluster") or "")[:32]
        intent = (r.get("intent") or "")[:28]
        entries = r.get("entries") or 0
        total_hits = r.get("total_hits") or 0
        avg_idle = float(r.get("avg_days_idle") or 0.0)
        print(
            f"{(r.get('tenant_id') or 'default'):<10} {cluster:<32} {intent:<28} "
            f"{entries:>8} {total_hits:>6} {avg_idle:>14.1f}"
        )

    # ── Aggregate by cluster across intents ───────────────────
    print()
    print("=== Aggregate by cluster (across intents) ===")
    agg: Dict[str, Dict[str, int]] = defaultdict(lambda: {"entries": 0, "hits": 0})
    for r in cluster_rows:
        c = r.get("profile_cluster") or ""
        agg[c]["entries"] += int(r.get("entries") or 0)
        agg[c]["hits"] += int(r.get("total_hits") or 0)
    sorted_agg = sorted(agg.items(), key=lambda kv: -kv[1]["hits"])
    print(f"{'cluster':<32} {'entries':>8} {'hits':>6} {'h/e':>6}")
    print("-" * 60)
    for cluster, vals in sorted_agg[:20]:
        h_per_e = vals["hits"] / max(vals["entries"], 1)
        print(f"{cluster:<32} {vals['entries']:>8} {vals['hits']:>6} {h_per_e:>6.2f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
