"""Unit tests for the May 11 2026 planner output cache.

Mirrors `test_architect_cache.py` — same coverage shape:
- Cache key determinism + normalisation + per-input discrimination
- Wardrobe count bucketing
- Repository get/put/touch with mock SupabaseRestClient
- TTL freshness check
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
from agentic_application.cache.planner_cache_key import (
    _normalise_user_message,
    _wardrobe_count_bucket,
    build_planner_cache_key,
    denormalised_key_fields,
)
from agentic_application.cache.planner_cache_repository import (
    PlannerCacheRepository,
)
from agentic_application.schemas import CopilotPlanResult


_CLUSTER = ProfileCluster("feminine", "autumn", "hourglass")


def _key(**overrides) -> str:
    kwargs = dict(
        tenant_id="default",
        user_message="Dress me for date night",
        cluster=_CLUSTER,
        previous_intent=None,
        previous_occasion=None,
        has_attached_image=False,
        has_person_image=True,
        wardrobe_count=5,
        planner_prompt_version="abc12345",
    )
    kwargs.update(overrides)
    return build_planner_cache_key(**kwargs)


class UserMessageNormaliseTests(unittest.TestCase):

    def test_lowercase(self):
        self.assertEqual(_normalise_user_message("DRESS ME"), "dress me")

    def test_whitespace_collapse(self):
        self.assertEqual(_normalise_user_message("  dress   me\tfor    night  "), "dress me for night")

    def test_trailing_punctuation_stripped(self):
        for s in ("dress me.", "dress me!", "dress me?", "dress me..."):
            with self.subTest(s=s):
                self.assertEqual(_normalise_user_message(s), "dress me")

    def test_mid_punctuation_preserved(self):
        self.assertEqual(_normalise_user_message("dress, me!"), "dress, me")

    def test_length_cap(self):
        long = "a" * 500
        norm = _normalise_user_message(long)
        self.assertEqual(len(norm), 200)
        self.assertEqual(norm, "a" * 200)

    def test_empty_or_none(self):
        self.assertEqual(_normalise_user_message(None), "")
        self.assertEqual(_normalise_user_message(""), "")
        self.assertEqual(_normalise_user_message("   "), "")


class WardrobeBucketTests(unittest.TestCase):

    def test_buckets(self):
        cases = [(0, "0"), (-1, "0"), (1, "1-5"), (5, "1-5"), (6, "6-20"), (20, "6-20"), (21, "21+"), (1000, "21+")]
        for count, expected in cases:
            with self.subTest(count=count):
                self.assertEqual(_wardrobe_count_bucket(count), expected)


class CacheKeyDeterminismTests(unittest.TestCase):

    def test_same_inputs_same_key(self):
        self.assertEqual(_key(), _key())

    def test_message_case_collapse(self):
        self.assertEqual(_key(user_message="Dress Me"), _key(user_message="dress me"))

    def test_trailing_punctuation_collapse(self):
        self.assertEqual(_key(user_message="dress me!"), _key(user_message="dress me"))

    def test_distinct_messages_distinct_keys(self):
        self.assertNotEqual(_key(user_message="dress me for date night"),
                            _key(user_message="dress me for office"))

    def test_distinct_cluster_distinct_keys(self):
        other = ProfileCluster("masculine", "winter", "rectangle")
        self.assertNotEqual(_key(cluster=_CLUSTER), _key(cluster=other))

    def test_distinct_previous_intent_distinct_keys(self):
        self.assertNotEqual(_key(previous_intent=None),
                            _key(previous_intent="occasion_recommendation"))

    def test_distinct_previous_occasion_distinct_keys(self):
        self.assertNotEqual(_key(previous_occasion="date_night"),
                            _key(previous_occasion="daily_office_mnc"))

    def test_distinct_attached_image_distinct_keys(self):
        self.assertNotEqual(_key(has_attached_image=False),
                            _key(has_attached_image=True))

    def test_distinct_person_image_distinct_keys(self):
        self.assertNotEqual(_key(has_person_image=False),
                            _key(has_person_image=True))

    def test_distinct_wardrobe_buckets_distinct_keys(self):
        # 0 / 1-5 / 6-20 / 21+ → 4 distinct keys
        keys = {_key(wardrobe_count=n) for n in (0, 3, 10, 50)}
        self.assertEqual(len(keys), 4)

    def test_same_wardrobe_bucket_same_key(self):
        # 3 and 5 both fall in "1-5"
        self.assertEqual(_key(wardrobe_count=3), _key(wardrobe_count=5))

    def test_distinct_prompt_version_distinct_keys(self):
        self.assertNotEqual(_key(planner_prompt_version="v1"),
                            _key(planner_prompt_version="v2"))

    def test_distinct_tenant_distinct_keys(self):
        self.assertNotEqual(_key(tenant_id="t1"), _key(tenant_id="t2"))


class DenormalisedFieldsTests(unittest.TestCase):

    def test_includes_all_inputs_plus_model(self):
        d = denormalised_key_fields(
            tenant_id="default",
            user_message="Dress Me For Date Night.",
            cluster=_CLUSTER,
            previous_intent="occasion_recommendation",
            previous_occasion="date_night",
            has_attached_image=False,
            has_person_image=True,
            wardrobe_count=7,
            planner_prompt_version="abc12345",
            planner_model="gpt-5-mini",
        )
        self.assertEqual(d["tenant_id"], "default")
        self.assertEqual(d["user_message_preview"], "Dress Me For Date Night.")
        self.assertEqual(d["user_message_norm"], "dress me for date night")
        self.assertEqual(d["profile_cluster"], str(_CLUSTER))
        self.assertEqual(d["previous_intent"], "occasion_recommendation")
        self.assertEqual(d["previous_occasion"], "date_night")
        self.assertEqual(d["has_attached_image"], False)
        self.assertEqual(d["has_person_image"], True)
        self.assertEqual(d["wardrobe_count_bucket"], "6-20")
        self.assertEqual(d["planner_prompt_version"], "abc12345")
        self.assertEqual(d["planner_model"], "gpt-5-mini")

    def test_preview_truncates_at_120_chars(self):
        d = denormalised_key_fields(
            tenant_id="default",
            user_message="x" * 500,
            cluster=_CLUSTER,
            previous_intent=None,
            previous_occasion=None,
            has_attached_image=False,
            has_person_image=False,
            wardrobe_count=0,
            planner_prompt_version="v1",
            planner_model="gpt-5-mini",
        )
        self.assertEqual(len(d["user_message_preview"]), 120)


def _plan_result(intent="occasion_recommendation") -> CopilotPlanResult:
    return CopilotPlanResult(intent=intent, intent_confidence=0.9)


class RepositoryGetTests(unittest.TestCase):

    def setUp(self):
        self.client = Mock()
        self.repo = PlannerCacheRepository(self.client)

    def test_miss_returns_none(self):
        self.client.select_many.return_value = []
        self.assertIsNone(self.repo.get(tenant_id="default", cache_key="abc"))

    def test_non_list_response_treated_as_miss(self):
        self.client.select_many.return_value = {"not": "a list"}
        self.assertIsNone(self.repo.get(tenant_id="default", cache_key="abc"))

    def test_lookup_exception_swallowed_returns_none(self):
        self.client.select_many.side_effect = RuntimeError("supabase down")
        self.assertIsNone(self.repo.get(tenant_id="default", cache_key="abc"))

    def test_hit_returns_plan_result(self):
        plan_json = _plan_result(intent="pairing_request").model_dump(mode="json")
        self.client.select_many.return_value = [{
            "cache_key": "abc",
            "plan_result_json": plan_json,
            "last_used_at": datetime.now(timezone.utc).isoformat(),
        }]
        result = self.repo.get(tenant_id="default", cache_key="abc")
        self.assertIsNotNone(result)
        self.assertEqual(result.intent, "pairing_request")

    def test_expired_entry_treated_as_miss(self):
        # last_used_at older than TTL (14 days)
        stale = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        self.client.select_many.return_value = [{
            "cache_key": "abc",
            "plan_result_json": _plan_result().model_dump(mode="json"),
            "last_used_at": stale,
        }]
        self.assertIsNone(self.repo.get(tenant_id="default", cache_key="abc"))

    def test_unparseable_payload_treated_as_miss(self):
        self.client.select_many.return_value = [{
            "cache_key": "abc",
            "plan_result_json": {"garbage": "not a CopilotPlanResult", "intent_confidence": "not_a_number"},
            "last_used_at": datetime.now(timezone.utc).isoformat(),
        }]
        self.assertIsNone(self.repo.get(tenant_id="default", cache_key="abc"))

    def test_freshness_accepts_z_suffix(self):
        # PostgREST often returns the Z form rather than +00:00
        fresh = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        self.client.select_many.return_value = [{
            "cache_key": "abc",
            "plan_result_json": _plan_result().model_dump(mode="json"),
            "last_used_at": fresh,
        }]
        result = self.repo.get(tenant_id="default", cache_key="abc")
        self.assertIsNotNone(result)


class RepositoryPutAndTouchTests(unittest.TestCase):

    def setUp(self):
        self.client = Mock()
        self.repo = PlannerCacheRepository(self.client)

    def test_put_calls_upsert(self):
        self.repo.put(
            tenant_id="default",
            cache_key="abc",
            plan_result=_plan_result(),
            denormalised={
                "user_message_norm": "dress me",
                "profile_cluster": str(_CLUSTER),
                "wardrobe_count_bucket": "1-5",
            },
        )
        self.assertTrue(self.client.upsert_many.called)
        call_args = self.client.upsert_many.call_args
        # The row payload should NOT include hit_count (preserved on conflict)
        row = call_args.kwargs.get("rows") or call_args.args[1][0] if call_args.args else None
        # The upsert call passes [row] as the second positional arg
        rows_arg = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("rows")
        self.assertEqual(len(rows_arg), 1)
        self.assertNotIn("hit_count", rows_arg[0])
        self.assertEqual(rows_arg[0]["cache_key"], "abc")
        self.assertIn("plan_result_json", rows_arg[0])

    def test_put_swallows_exceptions(self):
        self.client.upsert_many.side_effect = RuntimeError("write failed")
        # Should not raise
        self.repo.put(
            tenant_id="default",
            cache_key="abc",
            plan_result=_plan_result(),
            denormalised={},
        )

    def test_touch_calls_atomic_rpc(self):
        self.repo.touch(tenant_id="default", cache_key="abc")
        self.client.rpc.assert_called_once_with(
            "planner_cache_touch",
            {"p_tenant_id": "default", "p_cache_key": "abc"},
        )

    def test_touch_swallows_exceptions(self):
        self.client.rpc.side_effect = RuntimeError("rpc not found")
        # Should not raise
        self.repo.touch(tenant_id="default", cache_key="abc")


if __name__ == "__main__":
    unittest.main()
