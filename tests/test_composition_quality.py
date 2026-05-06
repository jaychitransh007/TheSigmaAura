"""Tests for the engine-vs-LLM quality comparators (Phase 4.8)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

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

from agentic_application.composition.quality import (
    aggregate_eval,
    compare_directions,
    compare_plans,
    compare_queries,
)
from agentic_application.schemas import (
    DirectionSpec,
    QuerySpec,
    RecommendationPlan,
)


def _q(role: str, doc: str, **filters) -> QuerySpec:
    return QuerySpec(
        query_id=f"X-{role}",
        role=role,
        hard_filters=dict(filters),
        query_document=doc,
    )


def _direction(direction_id: str, direction_type: str, *queries: QuerySpec, label: str = "") -> DirectionSpec:
    return DirectionSpec(
        direction_id=direction_id,
        direction_type=direction_type,
        label=label or f"dir-{direction_id}",
        queries=list(queries),
    )


def _plan(*directions: DirectionSpec, source: str = "engine") -> RecommendationPlan:
    return RecommendationPlan(
        retrieval_count=5,
        directions=list(directions),
        plan_source=source,
    )


class CompareQueriesTests(unittest.TestCase):
    def test_identical_query_yields_perfect_match(self):
        a = _q("top", "PRIMARY_BRIEF: FabricDrape: fluid", gender_expression="feminine")
        b = _q("top", "PRIMARY_BRIEF: FabricDrape: fluid", gender_expression="feminine")
        cmp = compare_queries(a, b)
        self.assertEqual(cmp.query_document_jaccard, 1.0)
        self.assertEqual(cmp.hard_filters_jaccard, 1.0)

    def test_disjoint_queries_yield_zero_match(self):
        a = _q("top", "alpha beta gamma", gender_expression="feminine")
        b = _q("top", "delta epsilon zeta", gender_expression="masculine")
        cmp = compare_queries(a, b)
        self.assertEqual(cmp.query_document_jaccard, 0.0)
        self.assertEqual(cmp.hard_filters_jaccard, 0.0)

    def test_partial_token_overlap(self):
        a = _q("top", "foo bar baz")
        b = _q("top", "foo bar")
        cmp = compare_queries(a, b)
        # Jaccard {foo, bar, baz} ∩ {foo, bar} / {foo, bar, baz} = 2/3.
        self.assertAlmostEqual(cmp.query_document_jaccard, 2.0 / 3.0, places=5)

    def test_filter_value_list_expands(self):
        a = _q("top", "doc")
        a.hard_filters["styling_completeness"] = ["needs_topwear", "dual_dependency"]
        b = _q("top", "doc")
        b.hard_filters["styling_completeness"] = ["needs_topwear"]
        cmp = compare_queries(a, b)
        # Two filter pairs in a, one in b — Jaccard 1/2.
        self.assertAlmostEqual(cmp.hard_filters_jaccard, 0.5)


class CompareDirectionsTests(unittest.TestCase):
    def test_paired_by_role_not_query_id(self):
        engine = _direction(
            "A", "paired",
            _q("top", "alpha"),
            _q("bottom", "beta"),
        )
        llm = _direction(
            "A", "paired",
            _q("bottom", "beta"),  # different order
            _q("top", "alpha"),
        )
        cmp = compare_directions(engine, llm)
        self.assertTrue(cmp.direction_type_match)
        self.assertEqual({q.role for q in cmp.queries}, {"top", "bottom"})
        for q in cmp.queries:
            self.assertEqual(q.query_document_jaccard, 1.0)

    def test_direction_type_mismatch_recorded(self):
        engine = _direction("A", "paired", _q("top", "doc"))
        llm = _direction("A", "complete", _q("complete", "doc"))
        cmp = compare_directions(engine, llm)
        self.assertFalse(cmp.direction_type_match)
        # No common roles → no per-query comparisons.
        self.assertEqual(cmp.queries, ())


class ComparePlansTests(unittest.TestCase):
    def test_one_direction_engine_vs_three_directions_llm(self):
        # Realistic case: engine emits A only; LLM emits A/B/C.
        engine = _plan(
            _direction("A", "paired", _q("top", "alpha"), _q("bottom", "beta"))
        )
        llm = _plan(
            _direction("A", "paired", _q("top", "alpha"), _q("bottom", "beta")),
            _direction("B", "complete", _q("complete", "gamma")),
            _direction("C", "three_piece", _q("top", "delta"), _q("bottom", "epsilon")),
            source="llm",
        )
        cmp = compare_plans(engine, llm)
        # Coverage = 1/3 (engine only emitted A).
        self.assertAlmostEqual(cmp.coverage, 1.0 / 3.0, places=5)
        # Direction type match rate = 1/1 (only the paired A is paired).
        self.assertEqual(cmp.direction_type_match_rate, 1.0)
        # B + C are unmatched.
        self.assertEqual(cmp.unmatched_direction_ids, ("B", "C"))

    def test_aggregate_jaccards_average_across_paired_queries(self):
        engine = _plan(
            _direction("A", "paired",
                _q("top", "alpha beta"),       # vs LLM "alpha gamma" → 1/3
                _q("bottom", "delta"),         # vs LLM "delta" → 1.0
            )
        )
        llm = _plan(
            _direction("A", "paired",
                _q("top", "alpha gamma"),
                _q("bottom", "delta"),
            ),
            source="llm",
        )
        cmp = compare_plans(engine, llm)
        # Mean of (1/3, 1.0) = 2/3.
        self.assertAlmostEqual(
            cmp.aggregate_query_document_jaccard, 2.0 / 3.0, places=5
        )

    def test_no_overlap_yields_zero_coverage(self):
        engine = _plan(_direction("A", "paired", _q("top", "alpha")))
        llm = _plan(_direction("B", "paired", _q("top", "alpha")), source="llm")
        cmp = compare_plans(engine, llm)
        self.assertEqual(cmp.coverage, 0.0)
        self.assertEqual(cmp.directions, ())


class AggregateEvalTests(unittest.TestCase):
    def test_empty_eval_returns_zeros(self):
        out = aggregate_eval([])
        self.assertEqual(out.cell_count, 0)
        self.assertEqual(out.median_query_document_jaccard, 0.0)

    def test_median_robust_to_outliers(self):
        engine = _plan(_direction("A", "paired", _q("top", "alpha"), _q("bottom", "beta")))
        llm_match = _plan(
            _direction("A", "paired", _q("top", "alpha"), _q("bottom", "beta")),
            source="llm",
        )
        llm_disjoint = _plan(
            _direction("A", "paired", _q("top", "x"), _q("bottom", "y")),
            source="llm",
        )
        # 4 perfect-match cells + 1 catastrophe → median should remain 1.0.
        comps = [compare_plans(engine, llm_match) for _ in range(4)]
        comps.append(compare_plans(engine, llm_disjoint))
        out = aggregate_eval(comps)
        self.assertEqual(out.cell_count, 5)
        self.assertEqual(out.median_query_document_jaccard, 1.0)


if __name__ == "__main__":
    unittest.main()
