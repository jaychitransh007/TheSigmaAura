"""Tests for _apply_change_color_avoidance (May 8 2026).

When the user's follow-up intent is `change_color`, the orchestrator
removes the prior recommendation's primary_colors from the engine's
resolved PrimaryColor hard_attr so retrieval surfaces different
colors. Tests the contract:

- No-op for any intent other than change_color
- No-op when previous_recommendations is empty
- Strips prior colors from PrimaryColor when intent + prior recs both present
- Preserves the original list when stripping would empty it (else
  retrieval would penalize EVERY item)
- Case-insensitive matching
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# CI runs python -m unittest discover (not pytest); inline sys.path bootstrap.
_ROOT = Path(__file__).resolve().parents[1]
for _p in (
    _ROOT,
    _ROOT / "modules" / "agentic_application" / "src",
    _ROOT / "modules" / "platform_core" / "src",
):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from agentic_application.orchestrator import _apply_change_color_avoidance
from agentic_application.schemas import (
    DirectionSpec,
    QuerySpec,
    RecommendationPlan,
)


def _plan_with_primary_colors(primary_colors: list[str]) -> RecommendationPlan:
    return RecommendationPlan(
        retrieval_count=5,
        directions=[
            DirectionSpec(
                direction_id="A",
                direction_type="paired",
                label="L",
                queries=[
                    QuerySpec(
                        query_id="A1", role="top",
                        hard_filters={},
                        query_document="t",
                        hard_attrs={"PrimaryColor": list(primary_colors)},
                    ),
                    QuerySpec(
                        query_id="A2", role="bottom",
                        hard_filters={},
                        query_document="b",
                        hard_attrs={"PrimaryColor": list(primary_colors)},
                    ),
                ],
            ),
        ],
    )


class ApplyChangeColorAvoidanceTests(unittest.TestCase):

    def test_noop_for_other_intent(self):
        plan = _plan_with_primary_colors(["navy", "cream", "charcoal"])
        _apply_change_color_avoidance(
            plan,
            previous_recommendations=[{"primary_colors": ["navy"]}],
            followup_intent="more_options",  # not change_color
        )
        for q in plan.directions[0].queries:
            self.assertEqual(q.hard_attrs["PrimaryColor"], ["navy", "cream", "charcoal"])

    def test_noop_on_empty_prior_recs(self):
        plan = _plan_with_primary_colors(["navy", "cream"])
        _apply_change_color_avoidance(
            plan,
            previous_recommendations=[],
            followup_intent="change_color",
        )
        for q in plan.directions[0].queries:
            self.assertEqual(q.hard_attrs["PrimaryColor"], ["navy", "cream"])

    def test_noop_on_none_prior_recs(self):
        plan = _plan_with_primary_colors(["navy", "cream"])
        _apply_change_color_avoidance(
            plan,
            previous_recommendations=None,
            followup_intent="change_color",
        )
        for q in plan.directions[0].queries:
            self.assertEqual(q.hard_attrs["PrimaryColor"], ["navy", "cream"])

    def test_strips_prior_colors_when_intent_and_recs_present(self):
        plan = _plan_with_primary_colors(["navy", "cream", "charcoal", "olive"])
        _apply_change_color_avoidance(
            plan,
            previous_recommendations=[
                {"primary_colors": ["navy", "cream"]},
            ],
            followup_intent="change_color",
        )
        for q in plan.directions[0].queries:
            self.assertEqual(q.hard_attrs["PrimaryColor"], ["charcoal", "olive"])

    def test_case_insensitive_matching(self):
        plan = _plan_with_primary_colors(["Navy", "Cream", "Charcoal"])
        _apply_change_color_avoidance(
            plan,
            previous_recommendations=[
                {"primary_colors": ["NAVY", "cream"]},
            ],
            followup_intent="change_color",
        )
        for q in plan.directions[0].queries:
            self.assertEqual(q.hard_attrs["PrimaryColor"], ["Charcoal"])

    def test_preserves_original_when_stripping_would_empty(self):
        # If filtering removes ALL allowed colors, leave the original
        # list — empty hard_attrs would penalize every catalog item.
        plan = _plan_with_primary_colors(["navy", "cream"])
        _apply_change_color_avoidance(
            plan,
            previous_recommendations=[
                {"primary_colors": ["navy", "cream", "charcoal"]},  # superset
            ],
            followup_intent="change_color",
        )
        for q in plan.directions[0].queries:
            self.assertEqual(q.hard_attrs["PrimaryColor"], ["navy", "cream"])

    def test_skips_queries_without_primarycolor_attr(self):
        # If a query has no PrimaryColor in hard_attrs, the helper
        # leaves it alone (doesn't add an empty list).
        plan = RecommendationPlan(
            retrieval_count=5,
            directions=[
                DirectionSpec(
                    direction_id="A", direction_type="paired", label="L",
                    queries=[
                        QuerySpec(
                            query_id="A1", role="top", hard_filters={},
                            query_document="t",
                            hard_attrs={},  # no PrimaryColor
                        ),
                    ],
                ),
            ],
        )
        _apply_change_color_avoidance(
            plan,
            previous_recommendations=[{"primary_colors": ["navy"]}],
            followup_intent="change_color",
        )
        self.assertNotIn("PrimaryColor", plan.directions[0].queries[0].hard_attrs)


if __name__ == "__main__":
    unittest.main()
