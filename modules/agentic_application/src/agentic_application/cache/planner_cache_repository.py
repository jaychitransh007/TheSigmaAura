"""Postgres I/O for the planner output cache.

Mirrors ``ArchitectCacheRepository`` — same best-effort pattern, same
TTL strategy. The planner cache stores serialised ``CopilotPlanResult``
JSON; on hit, the orchestrator skips the planner LLM call entirely
(~7.7s saved on gpt-5-mini per turn).

Best-effort everywhere: get returns ``None`` on any failure (treated
as miss); put silently swallows write failures (caching is a perf
optimisation, never load-bearing).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from platform_core.supabase_rest import SupabaseRestClient

from ..schemas import CopilotPlanResult

_log = logging.getLogger(__name__)

_TABLE = "planner_output_cache"

# Matches architect cache TTL — 14 days, refreshed on access via
# last_used_at. Application-side check; we don't rely on a server-side
# cron alone.
_TTL_DAYS = 14


class PlannerCacheRepository:
    def __init__(self, client: SupabaseRestClient) -> None:
        self._client = client

    def get(self, *, tenant_id: str, cache_key: str) -> Optional[CopilotPlanResult]:
        """Return the cached plan result or None on miss / expiry / error.

        Best-effort: any exception → None (treated as miss).
        """
        try:
            rows = self._client.select_many(
                _TABLE,
                columns="cache_key,plan_result_json,last_used_at",
                filters={
                    "tenant_id": f"eq.{tenant_id or 'default'}",
                    "cache_key": f"eq.{cache_key}",
                },
                limit=1,
            )
        except Exception:  # noqa: BLE001 — best-effort lookup
            _log.warning(
                "planner_cache.get failed for key=%s", cache_key[:16], exc_info=True,
            )
            return None
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            return None
        row = rows[0]
        if not self._is_fresh(row.get("last_used_at")):
            return None
        try:
            result = CopilotPlanResult.model_validate(row["plan_result_json"])
        except Exception:  # noqa: BLE001 — schema drift
            _log.warning(
                "planner_cache.get parse failed for key=%s; treating as miss",
                cache_key[:16],
                exc_info=True,
            )
            return None
        return result

    def put(
        self,
        *,
        tenant_id: str,
        cache_key: str,
        plan_result: CopilotPlanResult,
        denormalised: Dict[str, Any],
    ) -> None:
        """Insert or refresh a cache entry. Never raises.

        ``hit_count`` is intentionally absent from the row payload so
        that on conflict the existing row's count survives — only
        plan_result_json + denormalised key fields get refreshed.
        """
        row = {
            **denormalised,
            "tenant_id": tenant_id or "default",
            "cache_key": cache_key,
            "plan_result_json": plan_result.model_dump(mode="json"),
        }
        try:
            self._client.upsert_many(_TABLE, [row], on_conflict="tenant_id,cache_key")
        except Exception:  # noqa: BLE001 — best-effort write
            _log.warning(
                "planner_cache.put failed for key=%s; miss is uncached",
                cache_key[:16],
                exc_info=True,
            )

    def touch(self, *, tenant_id: str, cache_key: str) -> None:
        """Atomically bump hit_count + refresh last_used_at via the
        ``planner_cache_touch`` RPC. Never raises. If the RPC is
        missing (migration not yet applied), the exception handler
        swallows it — touch is best-effort metrics, not load-bearing."""
        try:
            self._client.rpc(
                "planner_cache_touch",
                {
                    "p_tenant_id": tenant_id or "default",
                    "p_cache_key": cache_key,
                },
            )
        except Exception:  # noqa: BLE001
            _log.debug(
                "planner_cache.touch failed for key=%s", cache_key[:16], exc_info=True,
            )

    @staticmethod
    def _is_fresh(last_used_at_raw: Any) -> bool:
        """True if the entry's last_used_at is within the TTL window.

        Accepts ISO 8601 strings (PostgREST) or datetimes (test fixtures).
        Mirrors ``ArchitectCacheRepository._is_fresh``.
        """
        if last_used_at_raw is None:
            return False
        if isinstance(last_used_at_raw, datetime):
            ts = last_used_at_raw
        else:
            try:
                s = str(last_used_at_raw).replace("Z", "+00:00")
                ts = datetime.fromisoformat(s)
            except ValueError:
                return False
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=_TTL_DAYS)
        return ts >= cutoff
