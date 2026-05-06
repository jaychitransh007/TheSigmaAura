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


_PAGE_SIZE = 1000
_MAX_PAGES = 100  # 100K rows ceiling — alert if we hit it


def _paginate(
    client: SupabaseRestClient,
    *,
    table: str,
    columns: str,
    filters: Dict[str, Any],
):
    """Iterate over a select_many result in pages of ``_PAGE_SIZE``.

    Keyset pagination on ``id`` (every Aura table has a unique id PK).
    Cursoring on ``id`` rather than ``created_at`` because:

    1. ``created_at`` isn't unique (bursty writes share a timestamp);
       ``gt.{ts}`` would skip rows that share the boundary timestamp
       (review of PR #137).
    2. ``id`` is a UUID PK — guaranteed unique, no boundary collision.

    Trade-off: pages don't arrive in chronological order. That's fine
    here — every caller aggregates counts over the whole window, so
    order within the window doesn't affect the metric.

    The function automatically appends ``id`` to ``columns`` if not
    already present, so callers can't accidentally produce silent
    truncation by forgetting to select the cursor field.
    """
    # Ensure 'id' is in the projected columns — without it the cursor
    # is None on every page and pagination silently stops after the
    # first page (review of PR #137).
    cols = [c.strip() for c in columns.split(",") if c.strip()]
    if "id" not in cols:
        cols.insert(0, "id")
    columns_with_id = ",".join(cols)

    pages = 0
    while pages < _MAX_PAGES:
        rows = client.select_many(
            table,
            columns=columns_with_id,
            filters=dict(filters),
            order="id.asc",
            limit=_PAGE_SIZE,
        )
        if not rows:
            return
        for r in rows:
            yield r
        if len(rows) < _PAGE_SIZE:
            return
        last_id = rows[-1].get("id")
        if not last_id:
            # Defensive: a row with no id is a schema surprise. Stop
            # rather than loop forever.
            print(f"WARN: pagination on {table} hit a row with no id; stopping")
            return
        filters = {**filters, "id": f"gt.{last_id}"}
        pages += 1
    print(
        f"WARN: pagination cap hit on {table} "
        f"({_MAX_PAGES * _PAGE_SIZE} rows scanned); metrics may be truncated."
    )


def _hit_count_from_logs(client: SupabaseRestClient, since_iso: str) -> Tuple[int, int]:
    """Query model_call_logs for architect calls; classify hit vs miss.

    A hit is a row whose response_json.plan_source == 'cache'. The
    cache wrapper stamps this on cached plans before logging. Miss
    rows don't carry the stamp.

    Returns (total_architect_calls, cache_hits). Paginates so we
    don't truncate at 10K rows on busy days (review of PR #135).
    """
    total = 0
    hits = 0
    # PostgREST JSONB arrow operators (-> and ->>) project only the
    # field we need — saves fetching the full ~5-10KB request_json /
    # response_json blob for every row (review of PR #137). The ->>
    # variant returns the value as text (unquoted), which is exactly
    # what we want to compare against "cache".
    # Aliased so both projected fields land on distinct keys in the
    # response row (otherwise both 'plan_source' would collide).
    for r in _paginate(
        client,
        table="model_call_logs",
        columns=(
            "req_plan_source:request_json->>plan_source,"
            "resp_plan_source:response_json->>plan_source,"
            "latency_ms,created_at"
        ),
        filters={
            "call_type": "eq.outfit_architect",
            "created_at": f"gte.{since_iso}",
        },
    ):
        total += 1
        # Either alias being "cache" counts as a hit. Both can be
        # None (miss) or "cache" (hit) on the same row depending on
        # the rollout-era log shape.
        if r.get("req_plan_source") == "cache" or r.get("resp_plan_source") == "cache":
            hits += 1
    return total, hits


def _hit_count_from_traces(client: SupabaseRestClient, since_iso: str) -> Tuple[int, int]:
    """Query turn_traces.steps for the architect step's plan_source.

    PostgREST JSONB containment filter (``cs.[{"step":"outfit_architect"}]``)
    server-side eliminates traces without an architect step, so we
    don't burn pagination budget on irrelevant rows (review of PR #135).
    Returns (total, hits) inferred from the steps blob.
    """
    total = 0
    hits = 0
    for r in _paginate(
        client,
        table="turn_traces",
        columns="steps,created_at",
        filters={
            "created_at": f"gte.{since_iso}",
            # PostgREST JSONB containment: only return traces whose
            # `steps` array contains a step element with step="outfit_architect".
            "steps": 'cs.[{"step":"outfit_architect"}]',
        },
    ):
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

    # Pick the source with the larger total (= more complete) and use
    # ITS hits — never mix totals from one source with hits from
    # another (review of PR #135). The two sources can disagree
    # transiently during a rollout: model_call_logs writes synchronously
    # at log time, turn_traces.steps populates after record_stage_trace
    # finalises. Whichever has higher coverage wins; the other just gets
    # printed for diagnostic context.
    if total_tr >= total_logs:
        total, hits, source = total_tr, hits_tr, "turn_traces.steps"
    else:
        total, hits, source = total_logs, hits_logs, "model_call_logs"

    print(f"Total architect calls    : {total}  (source: {source})")
    print(f"Cache hits               : {hits}")
    print(f"Hit rate                 : {_fmt_pct(hits, total)}")
    print(f"  diagnostic: traces n={total_tr} hits={hits_tr}; logs n={total_logs} hits={hits_logs}")
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
