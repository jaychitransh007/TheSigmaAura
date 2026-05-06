"""Unit tests for the Phase 2.3 composer output cache.

Coverage:
- architect_direction_id is stable across identical plans, distinct
  for different plans
- retrieval_fingerprint is stable for the same SKU set (regardless
  of order across sets), distinct when the set changes
- Composer cache key reflects all 5 inputs (tenant, direction id,
  retrieval fp, cluster, prompt version)
- Repository: hit / miss / TTL / parse-fail / lookup-error / write-error
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
from agentic_application.cache.composer_cache_key import (
    architect_direction_id,
    build_composer_cache_key,
    denormalised_key_fields,
    retrieval_fingerprint,
)
from agentic_application.cache.composer_cache_repository import (
    ComposerCacheRepository,
)
from agentic_application.schemas import (
    ComposedOutfit,
    ComposerResult,
    DirectionSpec,
    QuerySpec,
    RecommendationPlan,
    RetrievedProduct,
    RetrievedSet,
)


def _plan(label: str = "Sharp Navy") -> RecommendationPlan:
    return RecommendationPlan(
        directions=[
            DirectionSpec(
                direction_id="A",
                direction_type="paired",
                label=label,
                queries=[QuerySpec(query_id="A1", role="top", query_document="navy blazer")],
            )
        ]
    )


def _retrieved_set(sku_ids: list[str], direction_id: str = "A") -> RetrievedSet:
    return RetrievedSet(
        direction_id=direction_id,
        query_id="A1",
        role="top",
        products=[
            RetrievedProduct(product_id=pid, similarity=0.9, metadata={}, enriched_data={})
            for pid in sku_ids
        ],
    )


class ArchitectDirectionIdTests(unittest.TestCase):

    def test_identical_plans_same_id(self) -> None:
        a = _plan("Sharp Navy")
        b = _plan("Sharp Navy")
        self.assertEqual(architect_direction_id(a), architect_direction_id(b))

    def test_different_plans_different_ids(self) -> None:
        self.assertNotEqual(
            architect_direction_id(_plan("Sharp Navy")),
            architect_direction_id(_plan("Soft Cream")),
        )

    def test_id_is_hex_sha1_length(self) -> None:
        out = architect_direction_id(_plan())
        self.assertEqual(len(out), 40)
        int(out, 16)  # raises if not hex


class RetrievalFingerprintTests(unittest.TestCase):

    def test_same_skus_same_fingerprint(self) -> None:
        a = retrieval_fingerprint([_retrieved_set(["sku1", "sku2", "sku3"])])
        b = retrieval_fingerprint([_retrieved_set(["sku1", "sku2", "sku3"])])
        self.assertEqual(a, b)

    def test_order_independent(self) -> None:
        # Same SKU set returned in different order across multiple
        # RetrievedSets — fingerprint should still match.
        a = retrieval_fingerprint([_retrieved_set(["sku3", "sku1", "sku2"])])
        b = retrieval_fingerprint([_retrieved_set(["sku2", "sku3", "sku1"])])
        self.assertEqual(a, b)

    def test_different_skus_different_fingerprint(self) -> None:
        self.assertNotEqual(
            retrieval_fingerprint([_retrieved_set(["sku1", "sku2"])]),
            retrieval_fingerprint([_retrieved_set(["sku1", "sku3"])]),
        )

    def test_empty_returns_stable_value(self) -> None:
        # Edge case: no products. Fingerprint of empty SKU list is
        # well-defined (sha1 of empty string).
        a = retrieval_fingerprint([])
        b = retrieval_fingerprint([])
        self.assertEqual(a, b)
        self.assertEqual(len(a), 40)

    def test_blank_pids_skipped(self) -> None:
        # Defensive: stray RetrievedProduct with blank product_id
        # shouldn't fragment the fingerprint or crash the hash.
        clean = retrieval_fingerprint([_retrieved_set(["sku1", "sku2"])])
        with_blank = retrieval_fingerprint([
            RetrievedSet(
                direction_id="A",
                query_id="A1",
                role="top",
                products=[
                    RetrievedProduct(product_id="sku1", similarity=0.9, metadata={}, enriched_data={}),
                    RetrievedProduct(product_id="", similarity=0.8, metadata={}, enriched_data={}),
                    RetrievedProduct(product_id="sku2", similarity=0.7, metadata={}, enriched_data={}),
                ],
            )
        ])
        self.assertEqual(clean, with_blank)


class ComposerCacheKeyTests(unittest.TestCase):

    def setUp(self) -> None:
        self.cluster = ProfileCluster("feminine", "autumn", "hourglass")

    def _key(self, **overrides) -> str:
        kwargs = {
            "tenant_id": "default",
            "architect_direction_id_value": "arch-id-1",
            "retrieval_fingerprint_value": "fp-1",
            "cluster": self.cluster,
            "composer_prompt_version": "comp-v1",
        }
        kwargs.update(overrides)
        return build_composer_cache_key(**kwargs)

    def test_same_inputs_same_key(self) -> None:
        self.assertEqual(self._key(), self._key())

    def test_distinct_direction_id_distinct_keys(self) -> None:
        # Different architect output → different cache slot.
        self.assertNotEqual(
            self._key(architect_direction_id_value="arch-id-1"),
            self._key(architect_direction_id_value="arch-id-2"),
        )

    def test_distinct_retrieval_fp_distinct_keys(self) -> None:
        # Same architect direction + different SKUs returned (e.g.
        # catalog refresh) → cache miss, no stale references served.
        self.assertNotEqual(
            self._key(retrieval_fingerprint_value="fp-1"),
            self._key(retrieval_fingerprint_value="fp-2"),
        )

    def test_distinct_cluster_distinct_keys(self) -> None:
        # PR #131 review — different body shapes within the same
        # direction get different item picks for body harmony.
        self.assertNotEqual(
            self._key(cluster=ProfileCluster("feminine", "autumn", "hourglass")),
            self._key(cluster=ProfileCluster("feminine", "autumn", "pear")),
        )

    def test_distinct_tenant_distinct_keys(self) -> None:
        self.assertNotEqual(
            self._key(tenant_id="default"),
            self._key(tenant_id="acme_corp"),
        )

    def test_distinct_prompt_version_distinct_keys(self) -> None:
        self.assertNotEqual(
            self._key(composer_prompt_version="comp-v1"),
            self._key(composer_prompt_version="comp-v2"),
        )

    def test_denormalised_fields_match_inputs(self) -> None:
        fields = denormalised_key_fields(
            tenant_id="default",
            architect_direction_id_value="arch-id-1",
            retrieval_fingerprint_value="fp-1",
            cluster=self.cluster,
            composer_prompt_version="comp-v1",
            composer_model="gpt-5.2",
        )
        for k in (
            "tenant_id", "architect_direction_id", "retrieval_fingerprint",
            "profile_cluster", "composer_prompt_version", "composer_model",
        ):
            self.assertIn(k, fields)
        self.assertEqual(fields["profile_cluster"], "feminine|autumn|hourglass")


class RepositoryGetTests(unittest.TestCase):

    def setUp(self) -> None:
        self.client = Mock()
        self.repo = ComposerCacheRepository(self.client)

    def _outfit_dump(self) -> dict:
        return ComposedOutfit(
            composer_id="C1",
            direction_id="A",
            direction_type="paired",
            item_ids=["sku1", "sku2"],
            rationale="navy + white reads sharp",
        ).model_dump(mode="json")

    def test_miss_returns_none(self) -> None:
        self.client.select_many.return_value = []
        self.assertIsNone(self.repo.get(tenant_id="default", cache_key="abc"))

    def test_non_list_response_treated_as_miss(self) -> None:
        self.client.select_many.return_value = Mock()
        self.assertIsNone(self.repo.get(tenant_id="default", cache_key="abc"))

    def test_lookup_exception_swallowed(self) -> None:
        self.client.select_many.side_effect = RuntimeError("network down")
        self.assertIsNone(self.repo.get(tenant_id="default", cache_key="abc"))

    def test_hit_returns_result_with_attempt_count_one(self) -> None:
        fresh = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        self.client.select_many.return_value = [{
            "cache_key": "abc",
            "outfits_json": {
                "outfits": [self._outfit_dump()],
                "overall_assessment": "strong",
                "pool_unsuitable": False,
            },
            "last_used_at": fresh,
        }]
        result = self.repo.get(tenant_id="default", cache_key="abc")
        self.assertIsNotNone(result)
        self.assertEqual(len(result.outfits), 1)
        self.assertEqual(result.attempt_count, 1)
        self.assertEqual(result.raw_response, "")

    def test_expired_entry_treated_as_miss(self) -> None:
        stale = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        self.client.select_many.return_value = [{
            "cache_key": "abc",
            "outfits_json": {"outfits": [self._outfit_dump()], "overall_assessment": "moderate", "pool_unsuitable": False},
            "last_used_at": stale,
        }]
        self.assertIsNone(self.repo.get(tenant_id="default", cache_key="abc"))

    def test_unparseable_payload_treated_as_miss(self) -> None:
        self.client.select_many.return_value = [{
            "cache_key": "abc",
            "outfits_json": {"unexpected": "shape"},
            "last_used_at": datetime.now(timezone.utc).isoformat(),
        }]
        self.assertIsNone(self.repo.get(tenant_id="default", cache_key="abc"))


class RepositoryPutTests(unittest.TestCase):

    def setUp(self) -> None:
        self.client = Mock()
        self.repo = ComposerCacheRepository(self.client)

    def test_put_calls_upsert(self) -> None:
        result = ComposerResult(
            outfits=[ComposedOutfit(
                composer_id="C1", direction_id="A", direction_type="paired",
                item_ids=["sku1"], rationale="solid",
            )],
            overall_assessment="strong",
        )
        self.repo.put(
            tenant_id="default",
            cache_key="abc",
            result=result,
            denormalised={"architect_direction_id": "arch-id-1"},
        )
        self.client.upsert_many.assert_called_once()
        args, kwargs = self.client.upsert_many.call_args
        self.assertEqual(args[0], "composer_outfit_cache")
        self.assertEqual(kwargs["on_conflict"], "tenant_id,cache_key")
        rows = args[1]
        self.assertEqual(rows[0]["cache_key"], "abc")
        self.assertEqual(rows[0]["architect_direction_id"], "arch-id-1")
        # outfits_json carries the structured payload, not raw_response.
        self.assertIn("outfits", rows[0]["outfits_json"])
        self.assertEqual(rows[0]["outfits_json"]["overall_assessment"], "strong")

    def test_put_does_not_overwrite_hit_count(self) -> None:
        # Review of PR #134: same fix as architect cache. hit_count
        # must NOT be in the upsert payload — on conflict the
        # existing row's accumulated count survives.
        self.repo.put(
            tenant_id="default",
            cache_key="abc",
            result=ComposerResult(),
            denormalised={},
        )
        rows = self.client.upsert_many.call_args[0][1]
        self.assertNotIn("hit_count", rows[0])

    def test_put_swallows_exceptions(self) -> None:
        self.client.upsert_many.side_effect = RuntimeError("oops")
        # Must not raise.
        self.repo.put(
            tenant_id="default",
            cache_key="abc",
            result=ComposerResult(),
            denormalised={},
        )

    def test_touch_calls_atomic_rpc(self) -> None:
        # Review of PR #134: same fix as architect cache.
        self.repo.touch(tenant_id="default", cache_key="abc")
        self.client.rpc.assert_called_once_with(
            "composer_cache_touch",
            {"p_tenant_id": "default", "p_cache_key": "abc"},
        )

    def test_touch_swallows_exceptions(self) -> None:
        self.client.rpc.side_effect = RuntimeError("oops")
        self.repo.touch(tenant_id="default", cache_key="abc")


if __name__ == "__main__":
    unittest.main()
