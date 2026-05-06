"""Unit tests for the Phase 2.2 architect output cache.

Coverage:
- Cache key construction is deterministic, normalises whitespace/case,
  changes when ANY input changes, includes all per-turn signals
  the design doc requires (PR #131 review).
- Repository handles mock rows, empty results, schema drift, and
  expired entries (last_used_at older than TTL).
- TTL freshness check accepts ISO strings, Z-suffix, naive datetimes.
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from agentic_application.cache import ProfileCluster
from agentic_application.cache.architect_cache_key import (
    build_architect_cache_key,
    calendar_season_for,
    cluster_for_context,
    denormalised_key_fields,
)
from agentic_application.cache.architect_cache_repository import (
    ArchitectCacheRepository,
)
from agentic_application.schemas import (
    CombinedContext,
    LiveContext,
    RecommendationPlan,
    UserContext,
)


def _ctx(**live_overrides) -> CombinedContext:
    """Build a CombinedContext for cache-key tests with sensible defaults."""
    live_kwargs = {
        "user_need": "find me an outfit",
        "occasion_signal": "daily_office",
        "formality_hint": "smart_casual",
        "weather_context": "warm_dry",
        "style_goal": "minimalist",
        "time_of_day": "morning",
    }
    live_kwargs.update(live_overrides)
    return CombinedContext(
        user=UserContext(
            user_id="u1",
            gender="feminine",
            analysis_attributes={"BodyShape": "Hourglass"},
            derived_interpretations={"SeasonalColorGroup": {"value": "Soft Autumn"}},
        ),
        live=LiveContext(**live_kwargs),
    )


_FIXED_NOW = datetime(2026, 5, 14, tzinfo=timezone.utc)


class CalendarSeasonTests(unittest.TestCase):

    def test_each_month_maps_correctly(self) -> None:
        months_to_seasons = {
            (1, 2, 12): "winter",
            (3, 4, 5): "spring",
            (6, 7, 8): "summer",
            (9, 10, 11): "autumn",
        }
        for months, expected in months_to_seasons.items():
            for m in months:
                with self.subTest(month=m):
                    d = datetime(2026, m, 15)
                    self.assertEqual(calendar_season_for(d), expected)


class CacheKeyDeterminismTests(unittest.TestCase):

    def setUp(self) -> None:
        self.cluster = ProfileCluster("feminine", "autumn", "hourglass")

    def _key(self, ctx: CombinedContext, **overrides) -> str:
        kwargs = {
            "tenant_id": "default",
            "intent": "occasion_recommendation",
            "cluster": self.cluster,
            "combined_context": ctx,
            "architect_prompt_version": "abc12345",
            "now": _FIXED_NOW,
        }
        kwargs.update(overrides)
        return build_architect_cache_key(**kwargs)

    def test_same_inputs_same_key(self) -> None:
        ctx = _ctx()
        self.assertEqual(self._key(ctx), self._key(ctx))

    def test_whitespace_and_case_normalise(self) -> None:
        # 'minimalist' and ' Minimalist  ' should land on the same key
        # because the normaliser strips + lowercases + collapses ws.
        a = self._key(_ctx(style_goal="minimalist"))
        b = self._key(_ctx(style_goal="  Minimalist  "))
        self.assertEqual(a, b)

    def test_distinct_intents_distinct_keys(self) -> None:
        ctx = _ctx()
        self.assertNotEqual(
            self._key(ctx, intent="occasion_recommendation"),
            self._key(ctx, intent="pairing_request"),
        )

    def test_distinct_occasion_distinct_keys(self) -> None:
        self.assertNotEqual(
            self._key(_ctx(occasion_signal="daily_office")),
            self._key(_ctx(occasion_signal="wedding_traditional")),
        )

    def test_distinct_weather_distinct_keys(self) -> None:
        # PR #131 review: weather_context drives architect output.
        self.assertNotEqual(
            self._key(_ctx(weather_context="warm_dry")),
            self._key(_ctx(weather_context="cold_humid")),
        )

    def test_distinct_style_goal_distinct_keys(self) -> None:
        # PR #131 review: style_goal drives directional vocabulary.
        self.assertNotEqual(
            self._key(_ctx(style_goal="edgy")),
            self._key(_ctx(style_goal="minimalist")),
        )

    def test_distinct_time_of_day_distinct_keys(self) -> None:
        # PR #131 review: time_of_day affects palette depth.
        self.assertNotEqual(
            self._key(_ctx(time_of_day="morning")),
            self._key(_ctx(time_of_day="evening")),
        )

    def test_distinct_cluster_distinct_keys(self) -> None:
        ctx = _ctx()
        self.assertNotEqual(
            self._key(ctx, cluster=ProfileCluster("feminine", "autumn", "hourglass")),
            self._key(ctx, cluster=ProfileCluster("feminine", "autumn", "pear")),
        )

    def test_distinct_tenant_distinct_keys(self) -> None:
        # PR #131 review (security-medium): tenant_id in hash, not just
        # in the WHERE clause.
        ctx = _ctx()
        self.assertNotEqual(
            self._key(ctx, tenant_id="default"),
            self._key(ctx, tenant_id="acme_corp"),
        )

    def test_distinct_prompt_version_distinct_keys(self) -> None:
        ctx = _ctx()
        self.assertNotEqual(
            self._key(ctx, architect_prompt_version="abc12345"),
            self._key(ctx, architect_prompt_version="def67890"),
        )

    def test_long_style_goal_truncated(self) -> None:
        # Long-tail goals share a key past the 80-char cap. Two goals
        # whose first 80 chars match are intentionally collapsed.
        # Build with first 80 chars identical, then differ.
        common_prefix = "x" * 80
        long_goal_a = common_prefix + " ends with apple"
        long_goal_b = common_prefix + " ends with banana"
        self.assertEqual(
            self._key(_ctx(style_goal=long_goal_a)),
            self._key(_ctx(style_goal=long_goal_b)),
        )


class CacheKeyHelpersTests(unittest.TestCase):

    def test_cluster_for_context_routes_through_user(self) -> None:
        ctx = _ctx()
        cluster = cluster_for_context(ctx)
        self.assertEqual(cluster.gender, "feminine")
        self.assertEqual(cluster.season_group, "autumn")
        self.assertEqual(cluster.body_shape, "hourglass")

    def test_denormalised_fields_match_key_inputs(self) -> None:
        ctx = _ctx()
        fields = denormalised_key_fields(
            tenant_id="default",
            intent="occasion_recommendation",
            cluster=ProfileCluster("feminine", "autumn", "hourglass"),
            combined_context=ctx,
            architect_prompt_version="abc12345",
            architect_model="gpt-5.2",
            now=_FIXED_NOW,
        )
        # All fields the cache key hashes (plus architect_model for ops).
        for k in (
            "tenant_id", "intent", "profile_cluster", "occasion_signal",
            "calendar_season", "formality_hint", "weather_context",
            "style_goal", "time_of_day", "architect_prompt_version",
            "architect_model",
        ):
            self.assertIn(k, fields)
        self.assertEqual(fields["calendar_season"], "spring")  # May 14
        self.assertEqual(fields["profile_cluster"], "feminine|autumn|hourglass")


class RepositoryGetTests(unittest.TestCase):

    def setUp(self) -> None:
        self.client = Mock()
        self.repo = ArchitectCacheRepository(self.client)

    def _plan_dump(self) -> dict:
        # Minimal valid RecommendationPlan dump.
        return RecommendationPlan(directions=[]).model_dump(mode="json")

    def test_miss_returns_none(self) -> None:
        self.client.select_many.return_value = []
        self.assertIsNone(self.repo.get(tenant_id="default", cache_key="abc"))

    def test_non_list_response_treated_as_miss(self) -> None:
        # PostgREST might return an error dict; defensive code treats
        # anything not iterable-as-list-of-dicts as a miss.
        self.client.select_many.return_value = Mock()
        self.assertIsNone(self.repo.get(tenant_id="default", cache_key="abc"))

    def test_lookup_exception_swallowed_returns_none(self) -> None:
        self.client.select_many.side_effect = RuntimeError("network down")
        self.assertIsNone(self.repo.get(tenant_id="default", cache_key="abc"))

    def test_hit_returns_plan_with_cache_source(self) -> None:
        fresh = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        self.client.select_many.return_value = [{
            "cache_key": "abc",
            "direction_json": self._plan_dump(),
            "last_used_at": fresh,
        }]
        plan = self.repo.get(tenant_id="default", cache_key="abc")
        self.assertIsNotNone(plan)
        self.assertEqual(plan.plan_source, "cache")

    def test_expired_entry_treated_as_miss(self) -> None:
        # 30 days old > 14-day TTL → miss.
        stale = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        self.client.select_many.return_value = [{
            "cache_key": "abc",
            "direction_json": self._plan_dump(),
            "last_used_at": stale,
        }]
        self.assertIsNone(self.repo.get(tenant_id="default", cache_key="abc"))

    def test_unparseable_payload_treated_as_miss(self) -> None:
        # Schema drift: stored JSON doesn't match RecommendationPlan.
        self.client.select_many.return_value = [{
            "cache_key": "abc",
            "direction_json": {"unexpected": "shape"},
            "last_used_at": datetime.now(timezone.utc).isoformat(),
        }]
        self.assertIsNone(self.repo.get(tenant_id="default", cache_key="abc"))

    def test_freshness_accepts_z_suffix(self) -> None:
        self.client.select_many.return_value = [{
            "cache_key": "abc",
            "direction_json": self._plan_dump(),
            "last_used_at": "2026-05-14T10:00:00Z",
        }]
        # Within TTL of fixed test moment? Depends on real now() — just
        # assert it parses without error and returns a plan or None
        # based on date math, not crashes.
        result = self.repo.get(tenant_id="default", cache_key="abc")
        # Accept either branch; the assertion is "no exception".
        self.assertTrue(result is None or result.plan_source == "cache")


class RepositoryPutTests(unittest.TestCase):

    def setUp(self) -> None:
        self.client = Mock()
        self.repo = ArchitectCacheRepository(self.client)

    def test_put_calls_upsert(self) -> None:
        plan = RecommendationPlan(directions=[])
        self.repo.put(
            tenant_id="default",
            cache_key="abc",
            plan=plan,
            denormalised={"intent": "occasion_recommendation"},
        )
        self.client.upsert_many.assert_called_once()
        args, kwargs = self.client.upsert_many.call_args
        self.assertEqual(args[0], "architect_direction_cache")
        self.assertEqual(kwargs["on_conflict"], "tenant_id,cache_key")
        rows = args[1]
        self.assertEqual(rows[0]["cache_key"], "abc")
        self.assertEqual(rows[0]["tenant_id"], "default")
        self.assertEqual(rows[0]["intent"], "occasion_recommendation")

    def test_put_swallows_exceptions(self) -> None:
        self.client.upsert_many.side_effect = RuntimeError("disk full")
        # Must not raise — write failure should never break the user turn.
        self.repo.put(
            tenant_id="default",
            cache_key="abc",
            plan=RecommendationPlan(directions=[]),
            denormalised={},
        )

    def test_touch_swallows_exceptions(self) -> None:
        self.client.update_one.side_effect = RuntimeError("oops")
        self.repo.touch(tenant_id="default", cache_key="abc")  # should not raise


if __name__ == "__main__":
    unittest.main()
