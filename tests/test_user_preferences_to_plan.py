"""Tests for _apply_user_preferences_to_plan (Phase 5x).

The orchestrator folds the planner's open-axis user preferences
(EmbellishmentLevel, ContrastLevel, NecklineType, ...) into every
QuerySpec.hard_attrs in the architect's plan after the architect runs.
This applies uniformly to engine plans (which already populate
hard_attrs) and LLM plans (which leave hard_attrs empty). User-explicit
values OVERRIDE any architect-derived value for the same attribute.
"""
from __future__ import annotations

import unittest

# sys.path setup is centralised in tests/conftest.py.
from agentic_application.orchestrator import _apply_user_preferences_to_plan
from agentic_application.schemas import (
    DirectionSpec,
    QuerySpec,
    RecommendationPlan,
)


def _plan_with_engine_attrs() -> RecommendationPlan:
    """Engine path: hard_attrs already populated from YAML provenance."""
    return RecommendationPlan(
        retrieval_count=5,
        directions=[
            DirectionSpec(
                direction_id="A",
                direction_type="paired",
                label="cool weather",
                queries=[
                    QuerySpec(
                        query_id="A1", role="top",
                        hard_filters={"gender_expression": "feminine"},
                        query_document="navy structured top",
                        hard_attrs={
                            "SleeveLength": ["full"],
                            "FabricWeight": ["medium"],
                        },
                    ),
                    QuerySpec(
                        query_id="A2", role="bottom",
                        hard_filters={"gender_expression": "feminine"},
                        query_document="cream tailored trouser",
                        hard_attrs={
                            "SleeveLength": ["full"],
                            "FabricWeight": ["medium"],
                        },
                    ),
                ],
            ),
        ],
    )


def _plan_with_empty_hard_attrs() -> RecommendationPlan:
    """LLM path: hard_attrs empty (LLM architect doesn't populate it)."""
    return RecommendationPlan(
        retrieval_count=5,
        directions=[
            DirectionSpec(
                direction_id="A",
                direction_type="paired",
                label="LLM",
                queries=[
                    QuerySpec(
                        query_id="A1", role="top",
                        hard_filters={}, query_document="t",
                    ),
                    QuerySpec(
                        query_id="A2", role="bottom",
                        hard_filters={}, query_document="b",
                    ),
                ],
            ),
        ],
    )


class ApplyUserPreferencesToPlanTests(unittest.TestCase):

    def test_noop_when_no_user_preferences(self):
        plan = _plan_with_engine_attrs()
        _apply_user_preferences_to_plan(plan, {})
        # All queries keep their engine-derived hard_attrs unchanged.
        for q in plan.directions[0].queries:
            self.assertEqual(
                q.hard_attrs,
                {"SleeveLength": ["full"], "FabricWeight": ["medium"]},
            )

    def test_noop_on_empty_dict(self):
        plan = _plan_with_engine_attrs()
        _apply_user_preferences_to_plan(plan, {})
        self.assertEqual(
            plan.directions[0].queries[0].hard_attrs.get("EmbellishmentLevel"),
            None,
        )

    def test_user_preference_added_to_engine_plan(self):
        plan = _plan_with_engine_attrs()
        _apply_user_preferences_to_plan(
            plan,
            {"EmbellishmentLevel": ["heavy", "statement"]},
        )
        # Engine attrs untouched, user attrs added on top.
        for q in plan.directions[0].queries:
            self.assertEqual(q.hard_attrs["SleeveLength"], ["full"])
            self.assertEqual(q.hard_attrs["FabricWeight"], ["medium"])
            self.assertEqual(
                q.hard_attrs["EmbellishmentLevel"], ["heavy", "statement"],
            )

    def test_user_preference_overrides_engine_attr(self):
        # User explicitly says "I want heavy fabric" — overrides the
        # engine's weather-derived "medium" choice.
        plan = _plan_with_engine_attrs()
        _apply_user_preferences_to_plan(
            plan,
            {"FabricWeight": ["heavy"]},
        )
        for q in plan.directions[0].queries:
            self.assertEqual(q.hard_attrs["FabricWeight"], ["heavy"])
            # Other engine attrs unchanged.
            self.assertEqual(q.hard_attrs["SleeveLength"], ["full"])

    def test_applies_to_llm_plan_with_empty_hard_attrs(self):
        plan = _plan_with_empty_hard_attrs()
        _apply_user_preferences_to_plan(
            plan,
            {
                "ContrastLevel": ["very_low", "low"],
                "FabricDrape": ["fluid"],
            },
        )
        for q in plan.directions[0].queries:
            self.assertEqual(q.hard_attrs["ContrastLevel"], ["very_low", "low"])
            self.assertEqual(q.hard_attrs["FabricDrape"], ["fluid"])

    def test_drops_empty_attribute_names(self):
        plan = _plan_with_empty_hard_attrs()
        _apply_user_preferences_to_plan(
            plan,
            {"": ["value"], "  ": ["value"], "RealAttr": ["x"]},
        )
        for q in plan.directions[0].queries:
            self.assertNotIn("", q.hard_attrs)
            self.assertNotIn("  ", q.hard_attrs)
            self.assertEqual(q.hard_attrs["RealAttr"], ["x"])

    def test_drops_empty_value_lists(self):
        plan = _plan_with_empty_hard_attrs()
        _apply_user_preferences_to_plan(
            plan,
            {"EmbellishmentLevel": [], "ContrastLevel": ["", "  "], "X": ["y"]},
        )
        for q in plan.directions[0].queries:
            self.assertNotIn("EmbellishmentLevel", q.hard_attrs)
            self.assertNotIn("ContrastLevel", q.hard_attrs)
            self.assertEqual(q.hard_attrs["X"], ["y"])

    def test_applies_across_multiple_directions(self):
        plan = RecommendationPlan(
            retrieval_count=5,
            directions=[
                DirectionSpec(
                    direction_id="A", direction_type="paired", label="A",
                    queries=[
                        QuerySpec(query_id="A1", role="top", hard_filters={}, query_document="t"),
                        QuerySpec(query_id="A2", role="bottom", hard_filters={}, query_document="b"),
                    ],
                ),
                DirectionSpec(
                    direction_id="B", direction_type="three_piece", label="B",
                    queries=[
                        QuerySpec(query_id="B1", role="top", hard_filters={}, query_document="t"),
                        QuerySpec(query_id="B2", role="bottom", hard_filters={}, query_document="b"),
                        QuerySpec(query_id="B3", role="outerwear", hard_filters={}, query_document="o"),
                    ],
                ),
            ],
        )
        _apply_user_preferences_to_plan(
            plan, {"NecklineType": ["v_neck"]},
        )
        # Both directions, all queries, get the override.
        for d in plan.directions:
            for q in d.queries:
                self.assertEqual(q.hard_attrs["NecklineType"], ["v_neck"])


if __name__ == "__main__":
    unittest.main()
