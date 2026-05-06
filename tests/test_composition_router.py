"""Tests for the hot-path router (Phase 4.9)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

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

from agentic_application.composition.router import (
    MAX_HARD_WIDENINGS_PER_ATTR,
    RouterDecision,
    _canonical_archetype,
    extract_engine_inputs,
    is_engine_acceptable,
    is_engine_eligible,
    is_user_in_rollout_bucket,
    route_recommendation_plan,
)
from agentic_application.composition.engine import (
    CompositionResult,
    ProvenanceEntry,
)
from agentic_application.composition.yaml_loader import load_style_graph
from agentic_application.schemas import (
    CombinedContext,
    DirectionSpec,
    LiveContext,
    QuerySpec,
    RecommendationPlan,
    UserContext,
)


def _ctx(
    *,
    is_followup: bool = False,
    anchor_garment=None,
    previous_recommendations=None,
    occasion_signal: str = "daily_office_mnc",
    formality_hint: str = "smart_casual",
    weather_context: str = "warm_temperate",
    time_of_day: str = "daytime",
    user_id: str = "u1",
    body_shape: str = "Hourglass",
    frame_structure: str = "Light and Narrow",
    seasonal: str = "Soft Autumn",
    risk_tolerance: str = "moderate",
    style_goal: str = "modern_professional",
    gender: str = "female",
) -> CombinedContext:
    return CombinedContext(
        user=UserContext(
            user_id=user_id,
            gender=gender,
            analysis_attributes={"BodyShape": body_shape},
            derived_interpretations={
                "FrameStructure": frame_structure,
                "SeasonalColorGroup": seasonal,
            },
            style_preference={"riskTolerance": risk_tolerance},
        ),
        live=LiveContext(
            user_need="placeholder",
            occasion_signal=occasion_signal,
            formality_hint=formality_hint,
            weather_context=weather_context,
            time_of_day=time_of_day,
            style_goal=style_goal,
            is_followup=is_followup,
            anchor_garment=anchor_garment,
        ),
        previous_recommendations=previous_recommendations,
    )


def _llm_plan(direction_id: str = "A") -> RecommendationPlan:
    return RecommendationPlan(
        retrieval_count=5,
        plan_source="llm",
        directions=[
            DirectionSpec(
                direction_id=direction_id,
                direction_type="paired",
                label="LLM stub",
                queries=[
                    QuerySpec(
                        query_id="A1",
                        role="top",
                        query_document="LLM-stub-doc",
                    )
                ],
            )
        ],
    )


class CanonicalArchetypeTests(unittest.TestCase):
    def test_known_canonical_passes_through(self):
        self.assertEqual(_canonical_archetype("modern_professional"), "modern_professional")
        self.assertEqual(_canonical_archetype("classic"), "classic")

    def test_freeform_with_dashes_normalizes(self):
        self.assertEqual(_canonical_archetype("Modern Professional"), "modern_professional")
        self.assertEqual(_canonical_archetype("trend-forward"), "trend_forward")

    def test_unknown_returns_none(self):
        # The architect prompt allows free-text style_goal; non-canonical
        # values should map to None so the engine treats archetype as
        # absent rather than crashing on a YAML lookup miss.
        self.assertIsNone(_canonical_archetype("old-money classic vibe"))
        self.assertIsNone(_canonical_archetype(""))


class ExtractInputsTests(unittest.TestCase):
    def test_pulls_required_axes_from_combined_context(self):
        ctx = _ctx()
        inputs = extract_engine_inputs(ctx)
        self.assertEqual(inputs.gender, "female")
        self.assertEqual(inputs.body_shape, "Hourglass")
        self.assertEqual(inputs.frame_structure, "Light and Narrow")
        self.assertEqual(inputs.seasonal_color_group, "Soft Autumn")
        self.assertEqual(inputs.archetype, "modern_professional")
        self.assertEqual(inputs.risk_tolerance, "moderate")
        self.assertEqual(inputs.occasion_signal, "daily_office_mnc")
        self.assertEqual(inputs.formality_hint, "smart_casual")
        self.assertEqual(inputs.weather_context, "warm_temperate")
        self.assertEqual(inputs.time_of_day, "daytime")

    def test_missing_risk_tolerance_defaults_to_moderate(self):
        ctx = _ctx(risk_tolerance="")
        inputs = extract_engine_inputs(ctx)
        self.assertEqual(inputs.risk_tolerance, "moderate")

    def test_dict_shaped_analysis_attribute_unwraps_value(self):
        # The architect's _extract_value supports both bare strings and
        # {"value": "..."} dicts; the router mirrors that.
        ctx = _ctx()
        ctx.user.analysis_attributes["BodyShape"] = {"value": "Pear"}
        inputs = extract_engine_inputs(ctx)
        self.assertEqual(inputs.body_shape, "Pear")


class EligibilityGateTests(unittest.TestCase):
    def test_clean_request_is_eligible(self):
        ok, reason = is_engine_eligible(_ctx())
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_anchor_garment_blocks(self):
        ok, reason = is_engine_eligible(
            _ctx(anchor_garment={"product_id": "p1"})
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "anchor_present")

    def test_followup_blocks(self):
        ok, reason = is_engine_eligible(_ctx(is_followup=True))
        self.assertFalse(ok)
        self.assertEqual(reason, "followup_request")

    def test_previous_recommendations_blocks(self):
        ok, reason = is_engine_eligible(
            _ctx(previous_recommendations=[{"outfit_id": "x"}])
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "has_previous_recommendations")


class AcceptanceTests(unittest.TestCase):
    def _result(
        self,
        *,
        confidence=0.9,
        needs_disamb=False,
        fallback_reason=None,
        widened=(),
        direction=True,
    ):
        prov = (
            ProvenanceEntry(
                attribute="FabricDrape",
                final_flatters=("soft_structured",),
                contributing_sources=("body_shape:Hourglass",),
                status="clean",
                dropped_softs=(),
                widened_hards=widened,
            ),
        )
        return CompositionResult(
            direction=DirectionSpec(
                direction_id="A",
                direction_type="paired",
                label="t",
                queries=[QuerySpec(query_id="A1", role="top", query_document="x")],
            ) if direction else None,
            confidence=confidence,
            needs_disambiguation=needs_disamb,
            provenance=prov,
            fallback_reason=fallback_reason,
            yaml_gaps=(),
        )

    def test_clean_high_confidence_is_acceptable(self):
        ok, reason = is_engine_acceptable(self._result(confidence=0.95))
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_low_confidence_rejected(self):
        ok, reason = is_engine_acceptable(self._result(confidence=0.3))
        self.assertFalse(ok)
        self.assertEqual(reason, "low_confidence")

    def test_self_reported_fallback_reason_propagates(self):
        ok, reason = is_engine_acceptable(
            self._result(fallback_reason="yaml_gap")
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "yaml_gap")

    def test_needs_disambiguation_rejected(self):
        ok, reason = is_engine_acceptable(self._result(needs_disamb=True))
        self.assertFalse(ok)
        self.assertEqual(reason, "needs_disambiguation")

    def test_no_direction_rejected(self):
        ok, reason = is_engine_acceptable(self._result(direction=False))
        self.assertFalse(ok)
        self.assertEqual(reason, "no_direction")

    def test_excessive_widening_rejected(self):
        ok, reason = is_engine_acceptable(
            self._result(widened=("a", "b"))  # ≥2 widenings on one attr
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "excessive_widening")
        self.assertGreaterEqual(MAX_HARD_WIDENINGS_PER_ATTR, 2)


class RolloutBucketTests(unittest.TestCase):
    def test_zero_pct_never_in_bucket(self):
        for u in ("a", "b", "c", "very-long-user-id-23"):
            self.assertFalse(is_user_in_rollout_bucket(u, 0))

    def test_hundred_pct_always_in_bucket(self):
        for u in ("a", "b", "c"):
            self.assertTrue(is_user_in_rollout_bucket(u, 100))

    def test_partial_pct_is_deterministic_per_user(self):
        for u in ("a1", "a2", "a3"):
            results = [is_user_in_rollout_bucket(u, 50) for _ in range(5)]
            self.assertEqual(len(set(results)), 1, f"user {u!r} oscillated")

    def test_partial_pct_distributes_roughly(self):
        # 10000 users at 30% should land somewhere in [25%, 35%].
        ins = sum(
            is_user_in_rollout_bucket(f"u{i}", 30) for i in range(10_000)
        )
        self.assertGreater(ins, 2_500)
        self.assertLess(ins, 3_500)


class RouteHappyPathTests(unittest.TestCase):
    """End-to-end router → engine integration with the real StyleGraph."""

    @classmethod
    def setUpClass(cls):
        cls.graph = load_style_graph()

    def test_rollout_zero_skips_engine_entirely(self):
        llm = Mock(return_value=_llm_plan())
        decision = route_recommendation_plan(
            combined_context=_ctx(),
            architect_plan_callable=llm,
            rollout_pct=0,
            graph=self.graph,
        )
        self.assertFalse(decision.used_engine)
        self.assertEqual(decision.fallback_reason, "rollout_skipped")
        self.assertIsNone(decision.engine_confidence)
        self.assertEqual(decision.plan.plan_source, "llm")
        llm.assert_called_once()

    def test_anchor_falls_back_to_llm_without_running_engine(self):
        llm = Mock(return_value=_llm_plan())
        decision = route_recommendation_plan(
            combined_context=_ctx(anchor_garment={"product_id": "x"}),
            architect_plan_callable=llm,
            rollout_pct=100,
            graph=self.graph,
        )
        self.assertFalse(decision.used_engine)
        self.assertEqual(decision.fallback_reason, "anchor_present")
        self.assertIsNone(decision.engine_confidence)
        llm.assert_called_once()

    def test_low_confidence_falls_back_with_engine_confidence_reported(self):
        # Force YAML gap → confidence < threshold → fallback to LLM.
        ctx = _ctx(seasonal="not_in_yaml")
        llm = Mock(return_value=_llm_plan())
        decision = route_recommendation_plan(
            combined_context=ctx,
            architect_plan_callable=llm,
            rollout_pct=100,
            graph=self.graph,
        )
        self.assertFalse(decision.used_engine)
        self.assertIn(
            decision.fallback_reason,
            {"yaml_gap", "low_confidence", "needs_disambiguation", "excessive_widening"},
        )
        # Confidence is reported even on fallback so ops can tell
        # "tried-but-rejected" apart from "never tried".
        self.assertIsNotNone(decision.engine_confidence)
        llm.assert_called_once()

    def test_engine_acceptance_does_not_call_llm(self):
        # Stub the engine to force acceptance — exercises the
        # use-engine path without depending on the calibration of
        # the §8 confidence formula on real YAMLs.
        from unittest.mock import patch

        accepted = CompositionResult(
            direction=DirectionSpec(
                direction_id="A",
                direction_type="paired",
                label="engine stub",
                queries=[QuerySpec(query_id="A1", role="top", query_document="x")],
            ),
            confidence=0.95,
            needs_disambiguation=False,
            provenance=(),
            fallback_reason=None,
            yaml_gaps=(),
        )
        llm = Mock(return_value=_llm_plan())
        with patch(
            "agentic_application.composition.router.compose_direction",
            return_value=accepted,
        ):
            decision = route_recommendation_plan(
                combined_context=_ctx(),
                architect_plan_callable=llm,
                rollout_pct=100,
                graph=self.graph,
            )
        self.assertTrue(decision.used_engine)
        self.assertEqual(decision.fallback_reason, None)
        self.assertEqual(decision.plan.plan_source, "engine")
        self.assertEqual(decision.plan.directions[0].label, "engine stub")
        self.assertEqual(decision.engine_confidence, 0.95)
        llm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
