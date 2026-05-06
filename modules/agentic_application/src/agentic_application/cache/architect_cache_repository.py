"""Postgres I/O for the architect output cache.

Thin wrapper around ``SupabaseRestClient`` so the orchestrator's cache
wrapper stays clean. No business logic — just get / put / TTL filter.

Cache get is best-effort: if the lookup throws (network, schema drift,
JSON parse fail), the wrapper logs and treats it as a miss. Cache put
is also best-effort — a write failure must NEVER take down the user-
facing turn.

The repository deserialises the cached JSONB into a ``RecommendationPlan``
and re-stamps ``plan_source = 'cache'`` on the way out so trace logs
make hit/miss visually obvious.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from platform_core.supabase_rest import SupabaseRestClient

from ..schemas import RecommendationPlan

_log = logging.getLogger(__name__)

_TABLE = "architect_direction_cache"

# Hits older than this aren't served. Matches docs/phase_2_cache_design.md
# (TTL: 14 days, refreshed on access). Application-side check; we don't
# rely on a server-side cron alone — that way pre-cron deploys still
# never serve genuinely-stale outputs.
_TTL_DAYS = 14


class ArchitectCacheRepository:
    def __init__(self, client: SupabaseRestClient) -> None:
        self._client = client

    def get(self, *, tenant_id: str, cache_key: str) -> Optional[RecommendationPlan]:
        """Return the cached plan or None on miss / expiry / error.

        Best-effort: any exception → None (treated as miss). The
        wrapper catches and logs; we don't want a database hiccup to
        propagate as a failed turn.
        """
        try:
            rows = self._client.select_many(
                _TABLE,
                columns="cache_key,direction_json,last_used_at",
                filters={
                    "tenant_id": f"eq.{tenant_id or 'default'}",
                    "cache_key": f"eq.{cache_key}",
                },
                limit=1,
            )
        except Exception:  # noqa: BLE001 — best-effort lookup
            _log.warning("architect_cache.get failed for key=%s", cache_key[:16], exc_info=True)
            return None
        # Defensive against mocks / unexpected REST shapes — treat
        # anything not iterable-as-list-of-dicts as a miss.
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            return None
        row = rows[0]
        if not self._is_fresh(row.get("last_used_at")):
            return None
        try:
            plan = RecommendationPlan.model_validate(row["direction_json"])
        except Exception:  # noqa: BLE001 — schema drift
            _log.warning(
                "architect_cache.get parse failed for key=%s; treating as miss",
                cache_key[:16],
                exc_info=True,
            )
            return None
        # Stamp the source so traces / logs make hit visible.
        plan.plan_source = "cache"
        return plan

    def put(
        self,
        *,
        tenant_id: str,
        cache_key: str,
        plan: RecommendationPlan,
        denormalised: Dict[str, Any],
    ) -> None:
        """Insert or refresh a cache entry. Never raises.

        On primary-key conflict (concurrent miss → both write same
        key), the upsert overwrites only the columns we include in
        the row dict. ``hit_count`` is intentionally NOT in the
        payload so that on conflict the existing row's hit_count
        survives — only direction_json + denormalised key fields
        get refreshed (review of PR #134).
        """
        row = {
            **denormalised,
            "tenant_id": tenant_id or "default",
            "cache_key": cache_key,
            "direction_json": plan.model_dump(mode="json"),
            # NOTE: hit_count is intentionally absent. Schema default
            # (0) populates new rows; conflicting rows keep their
            # accumulated count.
        }
        try:
            self._client.upsert_many(_TABLE, [row], on_conflict="tenant_id,cache_key")
        except Exception:  # noqa: BLE001 — best-effort write
            _log.warning(
                "architect_cache.put failed for key=%s; cache miss is uncached",
                cache_key[:16],
                exc_info=True,
            )

    def touch(self, *, tenant_id: str, cache_key: str) -> None:
        """Atomically bump hit_count + refresh last_used_at. Never raises.

        Calls the ``architect_cache_touch`` RPC (added in
        20260514020000_cache_touch_rpcs.sql) so the increment is a
        single server-side UPDATE — no read-modify-write race across
        concurrent hits, no client-side hit_count drift (review of
        PR #134).

        If the RPC is missing (migration not yet applied) the
        exception handler swallows it. Touch is best-effort metrics,
        not load-bearing — a missing RPC just means hit_count stays
        at 0 until the migration lands.
        """
        try:
            self._client.rpc(
                "architect_cache_touch",
                {
                    "p_tenant_id": tenant_id or "default",
                    "p_cache_key": cache_key,
                },
            )
        except Exception:  # noqa: BLE001
            _log.debug("architect_cache.touch failed for key=%s", cache_key[:16], exc_info=True)

    @staticmethod
    def _is_fresh(last_used_at_raw: Any) -> bool:
        """True if the entry's last_used_at is within the TTL window.

        Accepts ISO 8601 strings (PostgREST) or datetimes (test fixtures).
        """
        if last_used_at_raw is None:
            return False
        if isinstance(last_used_at_raw, datetime):
            ts = last_used_at_raw
        else:
            try:
                # Handle both Z-suffix and +00:00 forms.
                s = str(last_used_at_raw).replace("Z", "+00:00")
                ts = datetime.fromisoformat(s)
            except ValueError:
                return False
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=_TTL_DAYS)
        return ts >= cutoff
