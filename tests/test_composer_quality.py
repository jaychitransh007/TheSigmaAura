"""Tests for composer quality comparators + shadow-mode router (Phase 5e).

Covers:
- compare_composer_outputs: per-direction Jaccard, type match, coverage,
  unmatched ids, overall_assessment match, pool_unsuitable match
- aggregate_composer_eval: median + binary rates over N comparisons
- route_composer_plan(shadow=True): LLM authoritative, engine runs in
  parallel, comparison surfaced via decision envelope
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "style_engine" / "src",
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from agentic_application.composition.composer_router import (
    ComposerRouterDecision,
    route_composer_plan,
)
from agentic_application.composition.quality import (
    ComposerComparison,
    ComposerDirectionComparison,
    ComposerEvalSummary,
    aggregate_composer_eval,
    compare_composer_outputs,
)
from agentic_application.composition.yaml_loader import load_style_graph
from agentic_application.schemas import (
    CombinedContext,
    ComposedOutfit,
    ComposerResult,
    DirectionSpec,
    LiveContext,
    QuerySpec,
    RecommendationPlan,
    RetrievedProduct,
    RetrievedSet,
    UserContext,
)


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────


def _outfit(composer_id: str, direction_id: str, item_ids: list[str], direction_type: str = "paired") -> ComposedOutfit:
    return ComposedOutfit(
        composer_id=composer_id,
        direction_id=direction_id,
        direction_type=direction_type,
        item_ids=item_ids,
        rationale="r",
        name=f"name {composer_id}",
    )


def _result(outfits: list[ComposedOutfit], assessment: str = "moderate", pool_unsuitable: bool = False) -> ComposerResult:
    return ComposerResult(
        outfits=outfits,
        overall_assessment=assessment,
        pool_unsuitable=pool_unsuitable,
        raw_response="{}",
    )


# ─────────────────────────────────────────────────────────────────────────
# compare_composer_outputs
# ─────────────────────────────────────────────────────────────────────────


class CompareComposerOutputsTests(unittest.TestCase):

    def test_identical_outputs_score_perfect(self):
        outfits = [
            _outfit("E1", "A", ["T1", "B1"]),
            _outfit("E2", "A", ["T2", "B2"]),
        ]
        engine = _result(outfits)
        llm = _result([
            _outfit("C1", "A", ["T1", "B1"]),  # composer_id differs but item_ids match
            _outfit("C2", "A", ["T2", "B2"]),
        ])
        cmp = compare_composer_outputs(engine, llm)
        self.assertEqual(cmp.coverage, 1.0)
        self.assertEqual(cmp.aggregate_item_ids_jaccard, 1.0)
        self.assertEqual(cmp.direction_type_match_rate, 1.0)
        self.assertTrue(cmp.overall_assessment_match)
        self.assertTrue(cmp.pool_unsuitable_match)

    def test_partial_item_overlap(self):
        engine = _result([_outfit("E1", "A", ["T1", "B1"])])
        llm = _result([_outfit("C1", "A", ["T1", "B2"])])  # 1 of 3 items shared
        cmp = compare_composer_outputs(engine, llm)
        # Engine items: {T1, B1}; LLM items: {T1, B2}; intersection {T1}, union {T1,B1,B2}
        # Jaccard 1/3
        self.assertAlmostEqual(cmp.aggregate_item_ids_jaccard, 1 / 3, places=6)

    def test_disjoint_items_score_zero(self):
        engine = _result([_outfit("E1", "A", ["T1", "B1"])])
        llm = _result([_outfit("C1", "A", ["T9", "B9"])])
        cmp = compare_composer_outputs(engine, llm)
        self.assertEqual(cmp.aggregate_item_ids_jaccard, 0.0)

    def test_engine_misses_one_direction(self):
        engine = _result([_outfit("E1", "A", ["T1", "B1"])])
        llm = _result([
            _outfit("C1", "A", ["T1", "B1"]),
            _outfit("C2", "B", ["T2", "B2"]),
        ])
        cmp = compare_composer_outputs(engine, llm)
        self.assertAlmostEqual(cmp.coverage, 0.5, places=6)
        self.assertEqual(cmp.unmatched_direction_ids, ("B",))

    def test_direction_type_mismatch(self):
        engine = _result([_outfit("E1", "A", ["T1", "B1"], direction_type="paired")])
        llm = _result([_outfit("C1", "A", ["T1", "B1"], direction_type="three_piece")])
        cmp = compare_composer_outputs(engine, llm)
        self.assertEqual(cmp.direction_type_match_rate, 0.0)

    def test_overall_assessment_mismatch(self):
        engine = _result([_outfit("E1", "A", ["T1", "B1"])], assessment="strong")
        llm = _result([_outfit("C1", "A", ["T1", "B1"])], assessment="weak")
        cmp = compare_composer_outputs(engine, llm)
        self.assertFalse(cmp.overall_assessment_match)

    def test_pool_unsuitable_match(self):
        engine = _result([], pool_unsuitable=True)
        llm = _result([], pool_unsuitable=True)
        cmp = compare_composer_outputs(engine, llm)
        self.assertTrue(cmp.pool_unsuitable_match)
        # No common directions → coverage 0, aggregate Jaccard 0.
        self.assertEqual(cmp.coverage, 0.0)
        self.assertEqual(cmp.aggregate_item_ids_jaccard, 0.0)

    def test_per_direction_breakdown(self):
        engine = _result([
            _outfit("E1", "A", ["T1", "B1"]),
            _outfit("E2", "B", ["T2", "B2"]),
        ])
        llm = _result([
            _outfit("C1", "A", ["T1", "B1"]),
            _outfit("C2", "B", ["T9", "B9"]),  # disjoint for B
        ])
        cmp = compare_composer_outputs(engine, llm)
        per_dir = {d.direction_id: d for d in cmp.directions}
        self.assertEqual(per_dir["A"].item_ids_jaccard, 1.0)
        self.assertEqual(per_dir["B"].item_ids_jaccard, 0.0)


# ─────────────────────────────────────────────────────────────────────────
# aggregate_composer_eval
# ─────────────────────────────────────────────────────────────────────────


class AggregateComposerEvalTests(unittest.TestCase):

    def test_empty_returns_zero_summary(self):
        s = aggregate_composer_eval([])
        self.assertEqual(s.cell_count, 0)
        self.assertEqual(s.median_item_ids_jaccard, 0.0)
        self.assertEqual(s.direction_type_match_rate, 0.0)

    def test_single_perfect_comparison(self):
        comparisons = [
            ComposerComparison(
                coverage=1.0,
                direction_type_match_rate=1.0,
                aggregate_item_ids_jaccard=1.0,
                overall_assessment_match=True,
                pool_unsuitable_match=True,
                engine_outfit_count_total=3,
                llm_outfit_count_total=3,
                directions=(),
                unmatched_direction_ids=(),
            )
        ]
        s = aggregate_composer_eval(comparisons)
        self.assertEqual(s.cell_count, 1)
        self.assertEqual(s.median_item_ids_jaccard, 1.0)
        self.assertEqual(s.overall_assessment_match_rate, 1.0)

    def test_median_not_mean_on_jaccard(self):
        # 3 cells: 0.0, 0.5, 1.0 → median 0.5, mean 0.5. Use distinct values
        # to verify median: 0.0, 0.0, 1.0 → median 0.0 (mean 0.33).
        def make(j: float) -> ComposerComparison:
            return ComposerComparison(
                coverage=1.0,
                direction_type_match_rate=1.0,
                aggregate_item_ids_jaccard=j,
                overall_assessment_match=True,
                pool_unsuitable_match=True,
                engine_outfit_count_total=0,
                llm_outfit_count_total=0,
                directions=(),
                unmatched_direction_ids=(),
            )
        s = aggregate_composer_eval([make(0.0), make(0.0), make(1.0)])
        self.assertEqual(s.median_item_ids_jaccard, 0.0)


# ─────────────────────────────────────────────────────────────────────────
# Shadow-mode router
# ─────────────────────────────────────────────────────────────────────────


def _user() -> UserContext:
    return UserContext(
        user_id="u1",
        gender="feminine",
        analysis_attributes={"BodyShape": {"value": "Hourglass"}},
        derived_interpretations={
            "FrameStructure": "Light and Narrow",
            "PaletteAnchors": ["navy", "cream", "charcoal", "ivory"],
        },
        style_preference={"riskTolerance": "balanced"},
    )


def _live() -> LiveContext:
    return LiveContext(
        user_need="office outfit",
        occasion_signal="daily_office_mnc",
        formality_hint="smart_casual",
    )


def _ctx() -> CombinedContext:
    return CombinedContext(user=_user(), live=_live())


def _plan() -> RecommendationPlan:
    return RecommendationPlan(
        retrieval_count=5,
        directions=[
            DirectionSpec(
                direction_id="A", direction_type="paired", label="Daily Office",
                queries=[
                    QuerySpec(query_id="A1", role="top", hard_filters={}, query_document="navy"),
                    QuerySpec(query_id="A2", role="bottom", hard_filters={}, query_document="cream"),
                ],
            ),
        ],
    )


def _varied_sets() -> list[RetrievedSet]:
    def _rp(idx: int, role: str, color: str) -> RetrievedProduct:
        return RetrievedProduct(
            product_id=f"{role[0].upper()}{idx}",
            similarity=1.0,
            enriched_data=dict(
                FormalityLevel="smart_casual",
                PrimaryColor=color,
                ContrastLevel="medium",
                PatternType="solid",
                EmbellishmentLevel="minimal",
                FitType=("tailored" if role == "top" else "regular"),
                FabricDrape=("crisp" if role == "top" else "soft_structured"),
                FabricTexture="smooth",
                FabricWeight="light",
                GarmentSubtype=("shirt" if role == "top" else "trouser"),
            ),
        )

    tops = [_rp(i + 1, "top", c) for i, c in enumerate(["navy", "charcoal", "ivory"])]
    bottoms = [_rp(i + 1, "bottom", c) for i, c in enumerate(["cream", "ivory", "charcoal"])]
    return [
        RetrievedSet(direction_id="A", query_id="A1", role="top", products=tops),
        RetrievedSet(direction_id="A", query_id="A2", role="bottom", products=bottoms),
    ]


def _llm_callable_with_outfits():
    """Mock LLM that returns a known result so shadow-mode comparison can run."""
    return MagicMock(return_value=_result([
        _outfit("C1", "A", ["T1", "B1"]),
    ]))


class ShadowModeTests(unittest.TestCase):

    def test_shadow_disabled_and_off_routes_to_llm_only(self):
        # enabled=False, shadow=False → just the LLM, no engine.
        llm = _llm_callable_with_outfits()
        decision = route_composer_plan(
            plan=_plan(), retrieved_sets=[], combined_context=_ctx(),
            composer_callable=llm, enabled=False, shadow=False,
        )
        self.assertFalse(decision.used_engine)
        self.assertEqual(decision.fallback_reason, "engine_disabled")
        self.assertIsNone(decision.shadow_comparison)
        llm.assert_called_once()

    def test_shadow_runs_engine_in_parallel_returns_llm(self):
        llm = _llm_callable_with_outfits()
        decision = route_composer_plan(
            plan=_plan(), retrieved_sets=_varied_sets(), combined_context=_ctx(),
            composer_callable=llm, enabled=False, shadow=True,
            graph=load_style_graph(),
        )
        self.assertFalse(decision.used_engine)  # LLM is authoritative in shadow
        # composer_result is the LLM's result.
        self.assertEqual(decision.composer_result.outfits[0].composer_id, "C1")
        # Engine ran (confidence + ms populated).
        self.assertIsNotNone(decision.engine_confidence)
        self.assertIsNotNone(decision.engine_ms)
        # Comparison surfaced.
        self.assertIsNotNone(decision.shadow_comparison)
        self.assertIn("comparison", decision.shadow_comparison)
        llm.assert_called_once()

    def test_shadow_comparison_is_json_serializable(self):
        # The shadow_comparison payload is intended for tool_trace
        # persistence, so the comparison field must be a dict (not a
        # frozen dataclass). Round-trip through json.dumps as a guard.
        import json as _json
        llm = _llm_callable_with_outfits()
        decision = route_composer_plan(
            plan=_plan(), retrieved_sets=_varied_sets(), combined_context=_ctx(),
            composer_callable=llm, enabled=False, shadow=True,
            graph=load_style_graph(),
        )
        self.assertIsNotNone(decision.shadow_comparison)
        # `comparison` must be a dict (asdict-flattened), not a dataclass.
        self.assertIsInstance(decision.shadow_comparison["comparison"], dict)
        # Whole envelope must JSON-serialise without a custom encoder.
        _json.dumps(decision.shadow_comparison)

    def test_enabled_wins_over_shadow(self):
        # When both enabled and shadow=True, enabled wins (production path).
        llm = _llm_callable_with_outfits()
        decision = route_composer_plan(
            plan=_plan(), retrieved_sets=_varied_sets(), combined_context=_ctx(),
            composer_callable=llm, enabled=True, shadow=True,
            graph=load_style_graph(),
        )
        # Engine accepted → used_engine=True, no shadow comparison.
        self.assertTrue(decision.used_engine)
        self.assertIsNone(decision.shadow_comparison)
        # LLM never called on engine-accept path.
        llm.assert_not_called()

    def test_shadow_engine_decline_no_comparison(self):
        # Sparse pool: engine declines. Shadow surfaces None for comparison
        # (fallback_reason="shadow:pool_too_sparse").
        sparse = [
            RetrievedSet(
                direction_id="A", query_id="A1", role="top",
                products=[
                    RetrievedProduct(
                        product_id="T1",
                        enriched_data={"FormalityLevel": "smart_casual", "PrimaryColor": "navy", "GarmentSubtype": "shirt"},
                    ),
                ],
            ),
            RetrievedSet(
                direction_id="A", query_id="A2", role="bottom",
                products=[
                    RetrievedProduct(
                        product_id=f"B{i}",
                        enriched_data={"FormalityLevel": "smart_casual", "PrimaryColor": "cream", "GarmentSubtype": "trouser"},
                    ) for i in range(2)
                ],
            ),
        ]
        llm = _llm_callable_with_outfits()
        decision = route_composer_plan(
            plan=_plan(), retrieved_sets=sparse, combined_context=_ctx(),
            composer_callable=llm, enabled=False, shadow=True,
            graph=load_style_graph(),
        )
        self.assertFalse(decision.used_engine)
        self.assertTrue(decision.fallback_reason.startswith("shadow:"))
        # Engine ran (ms/confidence populated) but produced no result, so
        # shadow_comparison is None.
        self.assertIsNotNone(decision.engine_confidence)
        self.assertIsNone(decision.shadow_comparison)
        llm.assert_called_once()


if __name__ == "__main__":
    unittest.main()
