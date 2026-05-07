"""Phase 5x.4a observability tests.

Pins the new observability hooks added on top of Phase 5x:

- ``observe_hard_attr_penalty_cap_hit("retrieval"|"tuple")`` fires
  when cumulative hard-attr penalty would have exceeded the cap.
- ``observe_user_preference_override(attr)`` fires when
  ``_apply_user_preferences_to_plan`` overrides an architect-derived
  hard_attrs value.
- ``_resolve_composer_origin_model`` returns the right sentinel
  (cache | composer_engine | <llm_model>) parallel to the architect.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

# sys.path setup is centralised in tests/conftest.py.
from agentic_application.agents.catalog_search_agent import (
    _HARD_ATTR_PENALTY,
    _HARD_ATTR_PENALTY_CAP,
    _apply_hard_attr_penalty,
)
from agentic_application.composition.pairing import (
    HARD_ATTR_TUPLE_PENALTY,
    HARD_ATTR_TUPLE_PENALTY_CAP,
    Item,
    TupleContext,
    score_tuple,
)
from agentic_application.composition.yaml_loader import load_style_graph
from agentic_application.orchestrator import (
    COMPOSER_MODEL_CACHE,
    COMPOSER_MODEL_ENGINE,
    _apply_user_preferences_to_plan,
    _resolve_composer_origin_model,
)
from agentic_application.schemas import (
    DirectionSpec,
    QuerySpec,
    RecommendationPlan,
)


_GRAPH = load_style_graph()


class _P:
    """Mutable similarity stand-in for RetrievedProduct."""
    def __init__(self, pid, sim, enriched):
        self.product_id = pid
        self.similarity = sim
        self.enriched_data = enriched


class CapHitTelemetryTests(unittest.TestCase):

    def test_retrieval_cap_hit_fires_observer(self):
        # 6 violations × 0.10 = 0.60 raw, would exceed cap=0.40 → fires.
        products = [_P("p", 0.90, {
            "SleeveLength": "short", "FabricWeight": "very_heavy",
            "EmbellishmentLevel": "minimal", "ContrastLevel": "very_high",
            "PatternType": "abstract", "FitEase": "oversized",
        })]
        hard_attrs = {
            "SleeveLength": ["full"], "FabricWeight": ["light"],
            "EmbellishmentLevel": ["heavy"], "ContrastLevel": ["low"],
            "PatternType": ["solid"], "FitEase": ["fitted"],
        }
        with patch(
            "platform_core.metrics.observe_hard_attr_penalty_cap_hit"
        ) as obs:
            _apply_hard_attr_penalty(products, hard_attrs, retrieval_count=10)
        obs.assert_called_with("retrieval")

    def test_retrieval_under_cap_does_not_fire(self):
        # 2 violations × 0.10 = 0.20 — under cap, no fire.
        products = [_P("p", 0.90, {
            "SleeveLength": "short", "FabricWeight": "very_heavy",
        })]
        hard_attrs = {"SleeveLength": ["full"], "FabricWeight": ["light"]}
        with patch(
            "platform_core.metrics.observe_hard_attr_penalty_cap_hit"
        ) as obs:
            _apply_hard_attr_penalty(products, hard_attrs, retrieval_count=10)
        obs.assert_not_called()

    def test_tuple_cap_hit_fires_observer(self):
        # 5 violations on a paired tuple via FitEase + 4 other axes.
        # 5 × 0.10 = 0.50 > cap 0.40 → fire.
        violator = dict(
            item_id="x", slot="top", formality="smart_casual",
            dominant_color="navy", contrast_level="medium",
            pattern_type="solid", pattern_scale="micro",
            embellishment_level="minimal", fabric_drape="soft_structured",
            fabric_texture="smooth", fabric_weight="light",
            sleeve_length="full", fit_type="tailored", fit_ease="oversized",
            color_saturation="high", color_temperature="cool", color_value="dark",
        )
        items = (
            Item(**{**violator, "item_id": "T"}),
            Item(**{**violator, "item_id": "B", "slot": "bottom",
                    "dominant_color": "cream"}),
        )
        ctx = TupleContext(
            formality_hint="smart_casual",
            hard_attrs={
                "FitEase": frozenset({"fitted"}),
                "ColorSaturation": frozenset({"muted"}),
                "ColorTemperature": frozenset({"warm"}),
                "ColorValue": frozenset({"light"}),
                "FabricDrape": frozenset({"fluid"}),
            },
        )
        with patch(
            "platform_core.metrics.observe_hard_attr_penalty_cap_hit"
        ) as obs:
            score_tuple(items, ctx, _GRAPH)
        obs.assert_called_with("tuple")


class OverrideTelemetryTests(unittest.TestCase):

    def _plan_with_engine_attrs(self):
        return RecommendationPlan(
            retrieval_count=5,
            directions=[
                DirectionSpec(
                    direction_id="A", direction_type="paired", label="L",
                    queries=[
                        QuerySpec(
                            query_id="A1", role="top", hard_filters={},
                            query_document="t",
                            hard_attrs={"FabricWeight": ["medium"]},
                        ),
                        QuerySpec(
                            query_id="A2", role="bottom", hard_filters={},
                            query_document="b",
                            hard_attrs={"FabricWeight": ["medium"]},
                        ),
                    ],
                ),
            ],
        )

    def test_override_observer_fires_for_overridden_attribute(self):
        plan = self._plan_with_engine_attrs()
        with patch(
            "platform_core.metrics.observe_user_preference_override"
        ) as obs:
            _apply_user_preferences_to_plan(
                plan, {"FabricWeight": ["heavy"]},
            )
        obs.assert_called_with("FabricWeight")

    def test_override_observer_fires_for_attr_only_in_non_first_direction(self):
        # PR #180 review: baseline_keys must aggregate across ALL
        # directions, not just the first one. Different directions
        # can in principle resolve different hard_attrs (e.g.,
        # weather contributes SleeveLength in direction A but the
        # occasion contributes EmbellishmentLevel in direction B).
        # The override observer should fire for either case.
        plan = RecommendationPlan(
            retrieval_count=5,
            directions=[
                # First direction: only FabricWeight
                DirectionSpec(
                    direction_id="A", direction_type="paired", label="A",
                    queries=[
                        QuerySpec(
                            query_id="A1", role="top", hard_filters={},
                            query_document="t",
                            hard_attrs={"FabricWeight": ["medium"]},
                        ),
                    ],
                ),
                # Second direction: only EmbellishmentLevel — NOT in
                # the first direction. The old code (first-direction
                # only) would have missed this override.
                DirectionSpec(
                    direction_id="B", direction_type="paired", label="B",
                    queries=[
                        QuerySpec(
                            query_id="B1", role="top", hard_filters={},
                            query_document="t",
                            hard_attrs={"EmbellishmentLevel": ["minimal"]},
                        ),
                    ],
                ),
            ],
        )
        with patch(
            "platform_core.metrics.observe_user_preference_override"
        ) as obs:
            _apply_user_preferences_to_plan(
                plan, {"EmbellishmentLevel": ["heavy"]},
            )
        obs.assert_called_with("EmbellishmentLevel")

    def test_override_observer_does_not_fire_for_new_attribute(self):
        # User-explicit EmbellishmentLevel doesn't override any
        # architect-derived value, so the override observer must NOT
        # fire. The attribute still lands in hard_attrs (additive).
        plan = self._plan_with_engine_attrs()
        with patch(
            "platform_core.metrics.observe_user_preference_override"
        ) as obs:
            _apply_user_preferences_to_plan(
                plan, {"EmbellishmentLevel": ["heavy"]},
            )
        obs.assert_not_called()
        # Confirm the merge itself still happened.
        self.assertEqual(
            plan.directions[0].queries[0].hard_attrs["EmbellishmentLevel"],
            ["heavy"],
        )


class ComposerOriginResolverTests(unittest.TestCase):

    def test_cache_hit_returns_cache_sentinel(self):
        self.assertEqual(
            _resolve_composer_origin_model(
                cache_hit=True, router_decision=None, llm_model="gpt-5.2",
            ),
            COMPOSER_MODEL_CACHE,
        )

    def test_engine_accept_returns_engine_sentinel(self):
        decision = SimpleNamespace(used_engine=True, fallback_reason=None)
        self.assertEqual(
            _resolve_composer_origin_model(
                cache_hit=False, router_decision=decision, llm_model="gpt-5.2",
            ),
            COMPOSER_MODEL_ENGINE,
        )

    def test_llm_path_returns_llm_model(self):
        decision = SimpleNamespace(used_engine=False, fallback_reason="engine_disabled")
        self.assertEqual(
            _resolve_composer_origin_model(
                cache_hit=False, router_decision=decision, llm_model="gpt-5.2",
            ),
            "gpt-5.2",
        )

    def test_none_router_decision_falls_through_to_llm(self):
        # Non-cache + no router decision (composer_engine flag off) →
        # LLM path. The architect's resolver tolerates None for the
        # cache-hit branch; the composer parallel must mirror that.
        self.assertEqual(
            _resolve_composer_origin_model(
                cache_hit=False, router_decision=None, llm_model="gpt-5.2",
            ),
            "gpt-5.2",
        )


if __name__ == "__main__":
    unittest.main()
