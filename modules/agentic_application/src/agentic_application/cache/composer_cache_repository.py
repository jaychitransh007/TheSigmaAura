"""Postgres I/O for the composer output cache.

Mirrors ``ArchitectCacheRepository`` — same best-effort pattern, same
TTL window, same get/put/touch surface. Stores ComposerResult JSON
keyed by (tenant_id, cache_key).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from platform_core.supabase_rest import SupabaseRestClient

from ..schemas import ComposedOutfit, ComposerResult

_log = logging.getLogger(__name__)

_TABLE = "composer_outfit_cache"
_TTL_DAYS = 14


class ComposerCacheRepository:
    def __init__(self, client: SupabaseRestClient) -> None:
        self._client = client

    def get(self, *, tenant_id: str, cache_key: str) -> Optional[ComposerResult]:
        try:
            rows = self._client.select_many(
                _TABLE,
                columns="cache_key,outfits_json,last_used_at",
                filters={
                    "tenant_id": f"eq.{tenant_id or 'default'}",
                    "cache_key": f"eq.{cache_key}",
                },
                limit=1,
            )
        except Exception:  # noqa: BLE001
            _log.warning("composer_cache.get failed for key=%s", cache_key[:16], exc_info=True)
            return None
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            return None
        row = rows[0]
        if not self._is_fresh(row.get("last_used_at")):
            return None
        try:
            payload = row["outfits_json"]
            if not isinstance(payload, dict) or "outfits" not in payload:
                # Required structural marker missing → treat as a
                # parse failure rather than serving an empty result.
                # An empty outfit list IS a valid cache hit (composer
                # legitimately decided pool was unsuitable), but the
                # payload must still be shaped like ComposerResult.
                return None
            outfits_raw = payload.get("outfits") or []
            outfits = [ComposedOutfit.model_validate(o) for o in outfits_raw]
        except Exception:  # noqa: BLE001
            _log.warning(
                "composer_cache.get parse failed for key=%s; treating as miss",
                cache_key[:16],
                exc_info=True,
            )
            return None
        # Surface a marker on cached results: empty raw_response and
        # attempt_count=1 make the trace log visibly say "single hit,
        # no retries" without inventing a new field.
        return ComposerResult(
            outfits=outfits,
            overall_assessment=str(payload.get("overall_assessment") or "moderate"),
            pool_unsuitable=bool(payload.get("pool_unsuitable", False)),
            raw_response="",
            usage={},
            attempt_count=1,
        )

    def put(
        self,
        *,
        tenant_id: str,
        cache_key: str,
        result: ComposerResult,
        denormalised: Dict[str, Any],
    ) -> None:
        # Store only the fields that survive across calls — outfits +
        # overall_assessment + pool_unsuitable. Skip raw_response /
        # usage / attempt_count (those are per-call artefacts).
        # hit_count intentionally absent so upsert-on-conflict
        # preserves the existing row's count (review of PR #134).
        outfits_payload = {
            "outfits": [o.model_dump(mode="json") for o in result.outfits],
            "overall_assessment": result.overall_assessment,
            "pool_unsuitable": result.pool_unsuitable,
        }
        row = {
            **denormalised,
            "tenant_id": tenant_id or "default",
            "cache_key": cache_key,
            "outfits_json": outfits_payload,
        }
        try:
            self._client.upsert_many(_TABLE, [row], on_conflict="tenant_id,cache_key")
        except Exception:  # noqa: BLE001
            _log.warning(
                "composer_cache.put failed for key=%s",
                cache_key[:16],
                exc_info=True,
            )

    def touch(self, *, tenant_id: str, cache_key: str) -> None:
        """Atomically bump hit_count + refresh last_used_at. Never raises.

        Calls the ``composer_cache_touch`` RPC (added in
        20260514020000_cache_touch_rpcs.sql) — single server-side
        UPDATE, no race on concurrent hits (review of PR #134).
        """
        try:
            self._client.rpc(
                "composer_cache_touch",
                {
                    "p_tenant_id": tenant_id or "default",
                    "p_cache_key": cache_key,
                },
            )
        except Exception:  # noqa: BLE001
            _log.debug("composer_cache.touch failed for key=%s", cache_key[:16], exc_info=True)

    @staticmethod
    def _is_fresh(last_used_at_raw: Any) -> bool:
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
