"""Tests for _apply_target_product_type_to_plan (May 8 2026).

When the planner extracts a specific garment subtype, bind it as
a hard ``garment_subtype`` filter on every QuerySpec in the plan
so retrieval is forced to honour the user's specific-garment ask
regardless of architect path.
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

from agentic_application.orchestrator import _apply_target_product_type_to_plan
from agentic_application.schemas import (
    DirectionSpec,
    QuerySpec,
    RecommendationPlan,
)


def _plan(*, hard_filters: dict | None = None) -> RecommendationPlan:
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
                        hard_filters=dict(hard_filters or {}),
                        query_document="t",
                    ),
                    QuerySpec(
                        query_id="A2", role="bottom",
                        hard_filters=dict(hard_filters or {}),
                        query_document="b",
                    ),
                ],
            ),
        ],
    )


class ApplyTargetProductTypeToPlanTests(unittest.TestCase):

    def test_noop_on_empty_target(self):
        plan = _plan(hard_filters={"gender_expression": "feminine"})
        _apply_target_product_type_to_plan(plan, "")
        for q in plan.directions[0].queries:
            self.assertNotIn("garment_subtype", q.hard_filters)

    def test_noop_on_whitespace_target(self):
        plan = _plan()
        _apply_target_product_type_to_plan(plan, "   ")
        for q in plan.directions[0].queries:
            self.assertNotIn("garment_subtype", q.hard_filters)

    def test_binds_lowercased_subtype_to_every_query(self):
        plan = _plan(hard_filters={"gender_expression": "feminine"})
        _apply_target_product_type_to_plan(plan, "Shirt")
        for q in plan.directions[0].queries:
            self.assertEqual(q.hard_filters["garment_subtype"], "shirt")
            # Existing filters preserved.
            self.assertEqual(q.hard_filters["gender_expression"], "feminine")

    def test_does_not_override_existing_subtype_filter(self):
        # Architect-emitted subtype filter is more specific; preserve it.
        plan = _plan(hard_filters={"garment_subtype": "blazer"})
        _apply_target_product_type_to_plan(plan, "shirt")
        for q in plan.directions[0].queries:
            self.assertEqual(q.hard_filters["garment_subtype"], "blazer")

    def test_applies_across_multiple_directions(self):
        plan = RecommendationPlan(
            retrieval_count=5,
            directions=[
                DirectionSpec(
                    direction_id="A", direction_type="paired", label="A",
                    queries=[
                        QuerySpec(query_id="A1", role="top", hard_filters={}, query_document="t"),
                    ],
                ),
                DirectionSpec(
                    direction_id="B", direction_type="paired", label="B",
                    queries=[
                        QuerySpec(query_id="B1", role="top", hard_filters={}, query_document="t"),
                    ],
                ),
            ],
        )
        _apply_target_product_type_to_plan(plan, "dress")
        for d in plan.directions:
            for q in d.queries:
                self.assertEqual(q.hard_filters["garment_subtype"], "dress")


if __name__ == "__main__":
    unittest.main()
