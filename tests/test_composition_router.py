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
    route_recommendation_plan,
)
from agentic_application.orchestrator import AgenticOrchestrator
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

    def test_one_widening_per_attr_across_two_attrs_is_acceptable(self):
        """Spec §9 #4 is per-attribute: ≥2 widenings on a *single*
        attribute trips the gate. Two attributes with one widening each
        should still pass — the engine picked one acceptable value per
        attribute, semantic drift is bounded."""
        prov = (
            ProvenanceEntry(
                attribute="FabricDrape",
                final_flatters=("soft_structured",),
                contributing_sources=("body_shape:Hourglass",),
                status="hard_widened",
                dropped_softs=(),
                widened_hards=("weather_fabric",),
            ),
            ProvenanceEntry(
                attribute="ColorValue",
                final_flatters=("mid",),
                contributing_sources=("seasonal:Soft Autumn",),
                status="hard_widened",
                dropped_softs=(),
                widened_hards=("weather_color",),
            ),
        )
        result = CompositionResult(
            direction=DirectionSpec(
                direction_id="A",
                direction_type="paired",
                label="t",
                queries=[QuerySpec(query_id="A1", role="top", query_document="x")],
            ),
            confidence=0.8,
            needs_disambiguation=False,
            provenance=prov,
            fallback_reason=None,
            yaml_gaps=(),
        )
        ok, reason = is_engine_acceptable(result)
        self.assertTrue(ok)
        self.assertIsNone(reason)


class BoolFromConfigTests(unittest.TestCase):
    """Boundary coercion for ``composition_engine_enabled`` reads from
    a ``Mock`` config (which existing orchestrator tests pass). Mocks
    are truthy by default; without this helper an unrelated test that
    passes ``config=Mock()`` would silently turn the engine on. The
    helper only accepts real ``bool`` values."""

    def test_mock_attribute_falls_back_to_default(self):
        from unittest.mock import Mock as _Mock

        cfg = _Mock()
        out = AgenticOrchestrator._bool_from_config(
            cfg, "composition_engine_enabled", False
        )
        self.assertFalse(out)

    def test_real_true_passes_through(self):
        cfg = type("C", (), {"composition_engine_enabled": True})()
        out = AgenticOrchestrator._bool_from_config(
            cfg, "composition_engine_enabled", False
        )
        self.assertTrue(out)

    def test_real_false_passes_through(self):
        cfg = type("C", (), {"composition_engine_enabled": False})()
        out = AgenticOrchestrator._bool_from_config(
            cfg, "composition_engine_enabled", True
        )
        self.assertFalse(out)

    def test_truthy_non_bool_falls_back(self):
        # Truthy strings / ints are NOT promoted to True — the env
        # loader does the string→bool coerce; the orchestrator only
        # trusts real booleans.
        for v in ("true", 1, [True], {"x": 1}):
            cfg = type("C", (), {"composition_engine_enabled": v})()
            out = AgenticOrchestrator._bool_from_config(
                cfg, "composition_engine_enabled", False
            )
            self.assertFalse(out, f"value {v!r} should not coerce to True")

    def test_missing_attribute_falls_back(self):
        cfg = type("C", (), {})()
        out = AgenticOrchestrator._bool_from_config(
            cfg, "composition_engine_enabled", True
        )
        self.assertTrue(out)


class RouteHappyPathTests(unittest.TestCase):
    """End-to-end router → engine integration with the real StyleGraph."""

    @classmethod
    def setUpClass(cls):
        cls.graph = load_style_graph()

    def test_disabled_flag_skips_engine_entirely(self):
        llm = Mock(return_value=_llm_plan())
        decision = route_recommendation_plan(
            combined_context=_ctx(),
            architect_plan_callable=llm,
            enabled=False,
            graph=self.graph,
        )
        self.assertFalse(decision.used_engine)
        self.assertEqual(decision.fallback_reason, "engine_disabled")
        self.assertIsNone(decision.engine_confidence)
        self.assertEqual(decision.plan.plan_source, "llm")
        llm.assert_called_once()

    def test_anchor_falls_back_to_llm_without_running_engine(self):
        llm = Mock(return_value=_llm_plan())
        decision = route_recommendation_plan(
            combined_context=_ctx(anchor_garment={"product_id": "x"}),
            architect_plan_callable=llm,
            enabled=True,
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
            enabled=True,
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
                enabled=True,
                graph=self.graph,
            )
        self.assertTrue(decision.used_engine)
        self.assertEqual(decision.fallback_reason, None)
        self.assertEqual(decision.plan.plan_source, "engine")
        self.assertEqual(decision.plan.directions[0].label, "engine stub")
        self.assertEqual(decision.engine_confidence, 0.95)
        llm.assert_not_called()


class MetricsHelperTests(unittest.TestCase):
    """The two new Phase-4 metric helpers don't crash on the no-op
    backend (when prometheus_client is absent) and emit a single
    increment per call when it's installed."""

    def test_router_decision_helper_is_safe_without_prometheus(self):
        # Always callable — the metrics module degrades to a _NoOp
        # fallback if prometheus_client isn't installed.
        from platform_core.metrics import observe_composition_router_decision

        observe_composition_router_decision(used_engine=True, fallback_reason=None)
        observe_composition_router_decision(
            used_engine=False, fallback_reason="yaml_gap"
        )

    def test_yaml_load_failure_helper_is_safe_without_prometheus(self):
        from platform_core.metrics import observe_composition_yaml_load_failure

        observe_composition_yaml_load_failure()

    def test_router_decision_increments_counter_when_prometheus_installed(self):
        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            self.skipTest("prometheus_client not installed")

        from platform_core.metrics import (
            aura_composition_router_decision_total,
            observe_composition_router_decision,
        )

        before = aura_composition_router_decision_total.labels(
            used_engine="true", fallback_reason="none"
        )._value.get()
        observe_composition_router_decision(used_engine=True, fallback_reason=None)
        after = aura_composition_router_decision_total.labels(
            used_engine="true", fallback_reason="none"
        )._value.get()
        self.assertEqual(after - before, 1)

    def test_none_fallback_reason_coerces_to_string_label(self):
        # Prometheus rejects None labels; the helper must coerce to
        # the literal string "none" so engine-accepted decisions still
        # produce a valid metric.
        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            self.skipTest("prometheus_client not installed")

        from platform_core.metrics import (
            aura_composition_router_decision_total,
            observe_composition_router_decision,
        )

        observe_composition_router_decision(used_engine=True, fallback_reason=None)
        # The "none" label series exists.
        labels = aura_composition_router_decision_total.labels(
            used_engine="true", fallback_reason="none"
        )
        self.assertIsNotNone(labels)


class EngineLatencyTimingTests(unittest.TestCase):
    """The router measures compose_direction's wall-clock time and
    surfaces it in RouterDecision.engine_ms so the orchestrator can
    feed the existing aura_turn_duration_seconds histogram under
    stage="composition_engine"."""

    @classmethod
    def setUpClass(cls):
        cls.graph = load_style_graph()

    def test_engine_ms_is_set_when_engine_runs(self):
        decision = route_recommendation_plan(
            combined_context=_ctx(seasonal="not_in_yaml"),  # forces YAML gap → fallback, but engine still ran
            architect_plan_callable=Mock(return_value=_llm_plan()),
            enabled=True,
            graph=self.graph,
        )
        self.assertIsNotNone(decision.engine_ms)
        self.assertIsInstance(decision.engine_ms, int)
        self.assertGreaterEqual(decision.engine_ms, 0)

    def test_engine_ms_is_none_on_disabled_flag(self):
        decision = route_recommendation_plan(
            combined_context=_ctx(),
            architect_plan_callable=Mock(return_value=_llm_plan()),
            enabled=False,
            graph=self.graph,
        )
        self.assertIsNone(decision.engine_ms)

    def test_engine_ms_is_none_when_eligibility_blocks(self):
        # Anchor garment skips the engine entirely — no compose call,
        # no timing.
        decision = route_recommendation_plan(
            combined_context=_ctx(anchor_garment={"product_id": "x"}),
            architect_plan_callable=Mock(return_value=_llm_plan()),
            enabled=True,
            graph=self.graph,
        )
        self.assertIsNone(decision.engine_ms)


if __name__ == "__main__":
    unittest.main()
