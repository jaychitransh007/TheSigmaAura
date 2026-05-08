"""Tests for the composer router (Phase 5d).

Covers eligibility gates, engine acceptance / fall-through, flag-off
short-circuit, error containment, and ComposerRouterDecision shape.
The LLM compose() callable is mocked so tests don't hit OpenAI.
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
    extract_tuple_context,
    is_engine_eligible,
    route_composer_plan,
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


def _user(**overrides) -> UserContext:
    base = dict(
        user_id="u1",
        gender="feminine",
        analysis_attributes={"BodyShape": {"value": "Hourglass"}},
        derived_interpretations={
            "FrameStructure": "Light and Narrow",
            "SeasonalColorGroup": "Soft Autumn",
            "PaletteAnchors": ["navy", "cream", "charcoal"],
        },
        style_preference={"riskTolerance": "balanced"},
    )
    base.update(overrides)
    return UserContext(**base)


def _live(**overrides) -> LiveContext:
    base = dict(
        user_need="find me an office outfit",
        occasion_signal="daily_office_mnc",
        formality_hint="smart_casual",
    )
    base.update(overrides)
    return LiveContext(**base)


def _ctx(*, user=None, live=None, previous_recommendations=None) -> CombinedContext:
    return CombinedContext(
        user=user or _user(),
        live=live or _live(),
        previous_recommendations=previous_recommendations,
    )


def _plan(plan_source: str = "llm") -> RecommendationPlan:
    return RecommendationPlan(
        retrieval_count=5,
        directions=[
            DirectionSpec(
                direction_id="A", direction_type="paired", label="Daily Office",
                queries=[
                    QuerySpec(query_id="A1", role="top", hard_filters={}, query_document="navy structured top"),
                    QuerySpec(query_id="A2", role="bottom", hard_filters={}, query_document="cream tailored trouser"),
                ],
            ),
        ],
        plan_source=plan_source,
    )


def _llm_result() -> ComposerResult:
    """A minimal valid LLM ComposerResult for fall-through tests."""
    return ComposerResult(
        outfits=[
            ComposedOutfit(
                composer_id="C1", direction_id="A", direction_type="paired",
                item_ids=["T1", "B1"], rationale="LLM rationale", name="LLM Name",
            ),
        ],
        overall_assessment="moderate",
        raw_response="{}",
        usage={"input_tokens": 100, "output_tokens": 50},
    )


def _llm_callable():
    """Mock LLM thunk; tracks invocations for assertion."""
    return MagicMock(return_value=_llm_result())


def _varied_pool_sets(direction_id: str = "A") -> list[RetrievedSet]:
    """3x3 varied pool — same shape as the engine tests."""
    def _rp(idx: str, role: str, color: str) -> RetrievedProduct:
        return RetrievedProduct(
            product_id=f"{role[0].upper()}{idx}",
            similarity=1.0,
            enriched_data=dict(
                FormalityLevel="smart_casual",
                PrimaryColor=color,
                ContrastLevel="medium",
                PatternType="solid",
                PatternScale="micro",
                EmbellishmentLevel="minimal",
                ColorSaturation="medium",
                FitType=("tailored" if role == "top" else "regular"),
                FabricDrape=("crisp" if role == "top" else "soft_structured"),
                FabricTexture="smooth",
                FabricWeight="light",
                GarmentSubtype=("shirt" if role == "top" else "trouser"),
            ),
        )

    tops = [_rp(str(i + 1), "top", c) for i, c in enumerate(["navy", "charcoal", "ivory"])]
    bottoms = [_rp(str(i + 1), "bottom", c) for i, c in enumerate(["cream", "ivory", "charcoal"])]
    return [
        RetrievedSet(direction_id=direction_id, query_id=f"{direction_id}1", role="top", products=tops),
        RetrievedSet(direction_id=direction_id, query_id=f"{direction_id}2", role="bottom", products=bottoms),
    ]


# ─────────────────────────────────────────────────────────────────────────
# is_engine_eligible
# ─────────────────────────────────────────────────────────────────────────


class IsEngineEligibleTests(unittest.TestCase):

    def test_clean_recommendation_request_eligible(self):
        ok, reason = is_engine_eligible(_ctx(), _plan())
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_pool_injected_anchor_ineligible(self):
        """T2 (May 8 follow-up): top/bottom anchors enter the composer
        pool via orchestrator injection — engine can't yet score
        fixed-slot tuples. Outerwear-style anchors are eligible
        (separate test below)."""
        live = _live()
        live.anchor_garment = {"id": "A1", "garment_category": "top"}  # pyright: ignore
        ok, reason = is_engine_eligible(_ctx(live=live), _plan())
        self.assertFalse(ok)
        self.assertEqual(reason, "anchor_pool_injected")

    def test_render_prepended_anchor_eligible(self):
        """T2: outerwear / dress / co_ord anchors stay out of the pool —
        composer engine sees a top+bottom-only pool, identical in shape
        to an occasion turn — eligible."""
        for category in ("outerwear", "blazer", "jacket", "coat", "dress"):
            live = _live()
            live.anchor_garment = {"id": "A1", "garment_category": category}  # pyright: ignore
            ok, reason = is_engine_eligible(_ctx(live=live), _plan())
            self.assertTrue(ok, f"category={category!r} should be eligible")
            self.assertIsNone(reason)

    def test_followup_request_ineligible(self):
        live = _live()
        live.is_followup = True  # pyright: ignore
        ok, reason = is_engine_eligible(_ctx(live=live), _plan())
        self.assertFalse(ok)
        self.assertEqual(reason, "followup_request")

    def test_followup_with_decrease_formality_eligible(self):
        # Mirrors the architect router relaxation. Composer engine
        # accepts formality follow-ups so it can score against the
        # adjusted formality_hint.
        live = _live()
        live.is_followup = True  # pyright: ignore
        live.followup_intent = "decrease_formality"  # pyright: ignore
        ok, reason = is_engine_eligible(_ctx(live=live), _plan())
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_followup_with_full_alternative_eligible(self):
        # May 8 2026: full_alternative is now engine-friendly via
        # post-architect direction_type rotation in the orchestrator.
        live = _live()
        live.is_followup = True  # pyright: ignore
        live.followup_intent = "full_alternative"  # pyright: ignore
        ok, reason = is_engine_eligible(_ctx(live=live), _plan())
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_followup_with_increase_boldness_eligible(self):
        live = _live()
        live.is_followup = True  # pyright: ignore
        live.followup_intent = "increase_boldness"  # pyright: ignore
        ok, reason = is_engine_eligible(_ctx(live=live), _plan())
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_followup_with_change_color_eligible(self):
        live = _live()
        live.is_followup = True  # pyright: ignore
        live.followup_intent = "change_color"  # pyright: ignore
        ok, reason = is_engine_eligible(_ctx(live=live), _plan())
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_followup_with_more_options_eligible(self):
        # Mirror of the architect router test (PR #191). Composer
        # engine accepts more_options follow-ups; orchestrator's
        # prev_rec_ids exclusion handles "show different products."
        live = _live()
        live.is_followup = True  # pyright: ignore
        live.followup_intent = "more_options"  # pyright: ignore
        ok, reason = is_engine_eligible(_ctx(live=live), _plan())
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_engine_friendly_followup_with_prior_recs_still_eligible(self):
        # PR #191 review: composer router relaxation must mirror the
        # architect router's. Engine-friendly follow-up with prior
        # recs in context should bypass the has_previous_recommendations
        # gate. Without this check the composer engine would silently
        # decline every follow-up (since follow-ups always carry prior
        # recs), undoing the architect-side enablement.
        live = _live()
        live.is_followup = True  # pyright: ignore
        live.followup_intent = "decrease_formality"  # pyright: ignore
        ok, reason = is_engine_eligible(
            _ctx(live=live, previous_recommendations=[{"composer_id": "X1"}]),
            _plan(),
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_previous_recommendations_ineligible(self):
        ok, reason = is_engine_eligible(
            _ctx(previous_recommendations=[{"composer_id": "X1"}]), _plan()
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "has_previous_recommendations")

    def test_architect_cache_plan_still_eligible(self):
        # Earlier drafts had an architect_plan_from_cache gate; that was
        # a copy-paste from the architect router and was wrong here.
        # The composer engine accepts plans from any source — LLM,
        # architect engine, or architect cache — they're all the same
        # RecommendationPlan shape.
        ok, reason = is_engine_eligible(_ctx(), _plan(plan_source="cache"))
        self.assertTrue(ok)
        self.assertIsNone(reason)


# ─────────────────────────────────────────────────────────────────────────
# extract_tuple_context
# ─────────────────────────────────────────────────────────────────────────


class ExtractTupleContextTests(unittest.TestCase):

    def test_full_context_extracted(self):
        ctx = extract_tuple_context(_ctx())
        self.assertEqual(ctx.formality_hint, "smart_casual")
        self.assertEqual(ctx.occasion_signal, "daily_office_mnc")
        self.assertEqual(ctx.body_shape, "Hourglass")
        self.assertEqual(ctx.palette_anchors, ("navy", "cream", "charcoal"))

    def test_missing_palette_anchors_yields_empty_tuple(self):
        user = _user(derived_interpretations={"FrameStructure": "Light and Narrow"})
        ctx = extract_tuple_context(_ctx(user=user))
        self.assertEqual(ctx.palette_anchors, ())

    def test_palette_anchors_in_value_dict_shape_extracted(self):
        user = _user(
            derived_interpretations={"PaletteAnchors": {"value": ["navy", "cream"]}},
        )
        ctx = extract_tuple_context(_ctx(user=user))
        self.assertEqual(ctx.palette_anchors, ("navy", "cream"))

    def test_body_shape_bare_string_extracted(self):
        user = _user(analysis_attributes={"BodyShape": "Pear"})
        ctx = extract_tuple_context(_ctx(user=user))
        self.assertEqual(ctx.body_shape, "Pear")


# ─────────────────────────────────────────────────────────────────────────
# route_composer_plan — flag and eligibility paths
# ─────────────────────────────────────────────────────────────────────────


class RouteFlagAndEligibilityTests(unittest.TestCase):

    def test_flag_off_invokes_llm_immediately(self):
        llm = _llm_callable()
        decision = route_composer_plan(
            plan=_plan(),
            retrieved_sets=[],
            combined_context=_ctx(),
            composer_callable=llm,
            enabled=False,
        )
        self.assertFalse(decision.used_engine)
        self.assertEqual(decision.fallback_reason, "engine_disabled")
        self.assertIsNone(decision.engine_confidence)
        self.assertIsNone(decision.engine_ms)
        llm.assert_called_once()

    def test_eligibility_failure_short_circuits_to_llm(self):
        # Use pool-injected anchor (top/bottom) — still ineligible
        # post-T2, the most stable ineligibility cause.
        live = _live()
        live.anchor_garment = {"id": "A1", "garment_category": "top"}  # pyright: ignore
        llm = _llm_callable()
        decision = route_composer_plan(
            plan=_plan(),
            retrieved_sets=[],
            combined_context=_ctx(live=live),
            composer_callable=llm,
            enabled=True,
        )
        self.assertFalse(decision.used_engine)
        self.assertEqual(decision.fallback_reason, "anchor_pool_injected")
        self.assertIsNone(decision.engine_confidence)
        llm.assert_called_once()

    def test_eligibility_pool_injected_anchor(self):
        live = _live()
        live.anchor_garment = {"id": "A1", "garment_category": "bottom"}  # pyright: ignore
        llm = _llm_callable()
        decision = route_composer_plan(
            plan=_plan(),
            retrieved_sets=[],
            combined_context=_ctx(live=live),
            composer_callable=llm,
            enabled=True,
        )
        self.assertFalse(decision.used_engine)
        self.assertEqual(decision.fallback_reason, "anchor_pool_injected")
        llm.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────
# route_composer_plan — engine paths
# ─────────────────────────────────────────────────────────────────────────


class RouteEnginePathTests(unittest.TestCase):

    def test_engine_accepts_with_varied_pool(self):
        llm = _llm_callable()
        decision = route_composer_plan(
            plan=_plan(),
            retrieved_sets=_varied_pool_sets("A"),
            combined_context=_ctx(),
            composer_callable=llm,
            enabled=True,
            graph=load_style_graph(),
        )
        self.assertTrue(decision.used_engine)
        self.assertIsNone(decision.fallback_reason)
        self.assertIsNotNone(decision.engine_confidence)
        # LLM never called.
        llm.assert_not_called()
        # composer_result outfits all carry engine-prefixed composer_ids.
        self.assertGreater(len(decision.composer_result.outfits), 0)
        for o in decision.composer_result.outfits:
            self.assertTrue(o.composer_id.startswith("E"))
        # provenance_summary populated with engine-side counts.
        self.assertIn("total_tuples", decision.provenance_summary)
        self.assertIn("kept", decision.provenance_summary)
        # engine_ms populated.
        self.assertIsNotNone(decision.engine_ms)
        self.assertGreaterEqual(decision.engine_ms, 0)

    def test_engine_declines_falls_through_to_llm(self):
        # Sparse pool: only 1 top, 2 bottoms → engine fails eligibility,
        # returns composer_result=None with fallback_reason="pool_too_sparse".
        sparse_sets = [
            RetrievedSet(
                direction_id="A", query_id="A1", role="top",
                products=[
                    RetrievedProduct(product_id="T1", enriched_data=dict(
                        FormalityLevel="smart_casual", PrimaryColor="navy",
                        GarmentSubtype="shirt",
                    )),
                ],
            ),
            RetrievedSet(
                direction_id="A", query_id="A2", role="bottom",
                products=[
                    RetrievedProduct(product_id="B1", enriched_data=dict(
                        FormalityLevel="smart_casual", PrimaryColor="cream",
                        GarmentSubtype="trouser",
                    )),
                    RetrievedProduct(product_id="B2", enriched_data=dict(
                        FormalityLevel="smart_casual", PrimaryColor="cream",
                        GarmentSubtype="trouser",
                    )),
                ],
            ),
        ]
        llm = _llm_callable()
        decision = route_composer_plan(
            plan=_plan(),
            retrieved_sets=sparse_sets,
            combined_context=_ctx(),
            composer_callable=llm,
            enabled=True,
            graph=load_style_graph(),
        )
        self.assertFalse(decision.used_engine)
        self.assertEqual(decision.fallback_reason, "pool_too_sparse")
        # LLM was called as the fallback.
        llm.assert_called_once()
        # composer_result is the LLM's, not the engine's.
        self.assertEqual(decision.composer_result.outfits[0].composer_id, "C1")
        # Engine confidence still surfaced for ops audit.
        self.assertIsNotNone(decision.engine_confidence)


class RouteEngineErrorContainmentTests(unittest.TestCase):

    def test_engine_raise_falls_through_to_llm(self):
        # Pass a badly-shaped retrieved_sets that breaks the projection
        # path, simulating an unexpected engine error mid-call. The
        # router's broad except should catch it and return the LLM
        # result with fallback_reason="engine_error".
        llm = _llm_callable()
        # Construct a RetrievedSet whose role is invalid; the engine
        # tolerates this, but if we pass a clearly bad object pretending
        # to be a RetrievedSet, projection raises AttributeError.
        bad_set = MagicMock()
        bad_set.direction_id = "A"
        bad_set.role = "top"
        # bad_set.products = [bad_product] where bad_product lacks
        # the attributes RetrievedProduct exposes — accessing
        # product_id raises AttributeError on MagicMock side-effect.
        bad_product = MagicMock()
        type(bad_product).product_id = property(lambda _self: (_ for _ in ()).throw(RuntimeError("simulated")))
        bad_set.products = [bad_product]

        decision = route_composer_plan(
            plan=_plan(),
            retrieved_sets=[bad_set],
            combined_context=_ctx(),
            composer_callable=llm,
            enabled=True,
            graph=load_style_graph(),
        )
        self.assertFalse(decision.used_engine)
        self.assertEqual(decision.fallback_reason, "engine_error")
        llm.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────
# ComposerRouterDecision contract
# ─────────────────────────────────────────────────────────────────────────


class DecisionShapeTests(unittest.TestCase):

    def test_decision_is_frozen(self):
        d = ComposerRouterDecision(
            composer_result=_llm_result(),
            used_engine=False,
            fallback_reason="engine_disabled",
            engine_confidence=None,
        )
        with self.assertRaises(Exception):  # FrozenInstanceError
            d.used_engine = True  # pyright: ignore

    def test_default_yaml_gaps_empty(self):
        d = ComposerRouterDecision(
            composer_result=_llm_result(),
            used_engine=False,
            fallback_reason="engine_disabled",
            engine_confidence=None,
        )
        self.assertEqual(d.yaml_gaps, ())
        self.assertEqual(d.provenance_summary, {})
        self.assertIsNone(d.engine_ms)


if __name__ == "__main__":
    unittest.main()
