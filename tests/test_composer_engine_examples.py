"""Spec §9 worked-example tests for compose_outfits (Phase 5f).

Verbatim re-runs of the composer_semantics.md §9.1-§9.4 worked examples
against the full ``compose_outfits`` pipeline (not just the per-tuple
``score_tuple`` pieces, which are covered in test_composition_pairing).

These guard the spec-engine contract end-to-end. If any of these
regress, either the spec drifted or the engine drifted; both are
fixable but neither should happen silently.

Mirrors ``tests/test_composition_engine_examples.py`` for the architect.
"""
from __future__ import annotations

import unittest

# sys.path is set up in tests/conftest.py — no per-file boilerplate.
from agentic_application.composition.composer_engine import compose_outfits
from agentic_application.composition.pairing import TupleContext
from agentic_application.composition.yaml_loader import load_style_graph
from agentic_application.schemas import (
    DirectionSpec,
    QuerySpec,
    RecommendationPlan,
    RetrievedProduct,
    RetrievedSet,
)


def _graph():
    return load_style_graph()


def _rp(item_id: str, **enriched) -> RetrievedProduct:
    return RetrievedProduct(
        product_id=item_id, similarity=1.0, enriched_data=dict(enriched)
    )


def _paired_plan(direction_id: str = "A", label: str = "Daily Office") -> RecommendationPlan:
    return RecommendationPlan(
        retrieval_count=5,
        directions=[
            DirectionSpec(
                direction_id=direction_id,
                direction_type="paired",
                label=label,
                queries=[
                    QuerySpec(query_id=f"{direction_id}1", role="top", hard_filters={}, query_document=""),
                    QuerySpec(query_id=f"{direction_id}2", role="bottom", hard_filters={}, query_document=""),
                ],
            )
        ],
    )


class WorkedExample91Tests(unittest.TestCase):
    """Spec §9.1: Daily-office paired tuple, clean win.

    Inputs (Hourglass body, smart_casual office):
    - T1: structured navy blouse, smart_casual, navy, solid, crisp, tailored
    - B1: tailored cream trouser, smart_casual, cream, solid, structured, tailored
    Expected: tuple kept; engine produces outfit with this pairing.
    """

    def test_clean_navy_cream_paired_outfit_emitted(self):
        # Build a 2x2 pool with the §9.1 pair plus a contrasting alternative
        # (charcoal/ivory) so diversity has somewhere to go for picks 2+.
        plan = _paired_plan()
        sets = [
            RetrievedSet(direction_id="A", query_id="A1", role="top", products=[
                _rp("T1", FormalityLevel="smart_casual", PrimaryColor="navy",
                    ContrastLevel="medium", PatternType="solid",
                    EmbellishmentLevel="minimal", FitType="tailored",
                    FabricDrape="crisp", FabricTexture="smooth",
                    FabricWeight="light", GarmentSubtype="shirt"),
                _rp("T2", FormalityLevel="smart_casual", PrimaryColor="charcoal",
                    ContrastLevel="medium", PatternType="solid",
                    EmbellishmentLevel="minimal", FitType="tailored",
                    FabricDrape="crisp", FabricTexture="smooth",
                    FabricWeight="light", GarmentSubtype="shirt"),
            ]),
            RetrievedSet(direction_id="A", query_id="A2", role="bottom", products=[
                _rp("B1", FormalityLevel="smart_casual", PrimaryColor="cream",
                    ContrastLevel="medium", PatternType="solid",
                    EmbellishmentLevel="minimal", FitType="regular",
                    FabricDrape="soft_structured", FabricTexture="smooth",
                    FabricWeight="light", GarmentSubtype="trouser"),
                _rp("B2", FormalityLevel="smart_casual", PrimaryColor="ivory",
                    ContrastLevel="medium", PatternType="solid",
                    EmbellishmentLevel="minimal", FitType="regular",
                    FabricDrape="soft_structured", FabricTexture="smooth",
                    FabricWeight="light", GarmentSubtype="trouser"),
            ]),
        ]
        ctx = TupleContext(
            formality_hint="smart_casual",
            occasion_signal="daily_office_mnc",
            palette_anchors=("navy", "cream", "charcoal", "ivory"),
            body_shape="Hourglass",
            intent="recommendation_request",
        )
        result = compose_outfits(plan=plan, retrieved_sets=sets, ctx=ctx, graph=_graph())

        self.assertIsNotNone(result.composer_result, msg=f"fallback={result.fallback_reason}")
        # The §9.1 pair is among the picks.
        item_id_sets = {tuple(o.item_ids) for o in result.composer_result.outfits}
        self.assertIn(("T1", "B1"), item_id_sets, msg=f"§9.1 outfit missing; picks={item_id_sets}")


class WorkedExample92Tests(unittest.TestCase):
    """Spec §9.2: two-pattern violation drops the tuple.

    A pool where every (top, bottom) pair has both items at
    pattern_scale=large → pattern_mixing matrix forbids large+large.
    Every tuple should drop, fall-through fires.
    """

    def test_all_large_pattern_pairs_drop(self):
        plan = _paired_plan()
        sets = [
            RetrievedSet(direction_id="A", query_id="A1", role="top", products=[
                _rp(f"T{i}", FormalityLevel="smart_casual", PrimaryColor="navy",
                    ContrastLevel="medium", PatternType="floral", PatternScale="large",
                    EmbellishmentLevel="minimal", FitType="tailored",
                    FabricDrape="crisp", FabricTexture="smooth",
                    FabricWeight="light", GarmentSubtype="shirt")
                for i in range(1, 3)
            ]),
            RetrievedSet(direction_id="A", query_id="A2", role="bottom", products=[
                _rp(f"B{i}", FormalityLevel="smart_casual", PrimaryColor="navy",
                    ContrastLevel="medium", PatternType="checks", PatternScale="large",
                    EmbellishmentLevel="minimal", FitType="regular",
                    FabricDrape="soft_structured", FabricTexture="smooth",
                    FabricWeight="light", GarmentSubtype="trouser")
                for i in range(1, 3)
            ]),
        ]
        ctx = TupleContext(
            formality_hint="smart_casual",
            occasion_signal="daily_office_mnc",
            palette_anchors=("navy",),
            body_shape="Hourglass",
            intent="recommendation_request",
        )
        result = compose_outfits(plan=plan, retrieved_sets=sets, ctx=ctx, graph=_graph())

        # Every tuple drops on pattern_mixing. composer_result is None.
        self.assertIsNone(result.composer_result)
        # Engine had eligible pool, no skipped directions, but no picks
        # → fallback_reason="low_picks".
        self.assertEqual(result.fallback_reason, "low_picks")
        # Provenance: 4 tuples, all dropped on pattern_mixing.
        self.assertEqual(len(result.provenance), 4)
        for prov in result.provenance:
            self.assertTrue(prov.dropped)
            self.assertEqual(prov.drop_reason, "pattern_mixing")


class WorkedExample94Tests(unittest.TestCase):
    """Spec §9.4: pool too sparse → fall-through.

    Three-piece direction with outerwear pool of only 1 item triggers
    the §3.4 sparse-pool gate.
    """

    def test_three_piece_one_outerwear_falls_through(self):
        plan = RecommendationPlan(
            retrieval_count=5,
            directions=[
                DirectionSpec(
                    direction_id="A",
                    direction_type="three_piece",
                    label="Layered Office",
                    queries=[
                        QuerySpec(query_id="A1", role="top", hard_filters={}, query_document=""),
                        QuerySpec(query_id="A2", role="bottom", hard_filters={}, query_document=""),
                        QuerySpec(query_id="A3", role="outerwear", hard_filters={}, query_document=""),
                    ],
                ),
            ],
        )
        sets = [
            RetrievedSet(direction_id="A", query_id="A1", role="top", products=[
                _rp(f"T{i}", FormalityLevel="smart_casual", PrimaryColor="navy",
                    ContrastLevel="medium", PatternType="solid", FitType="tailored",
                    FabricDrape="crisp", FabricTexture="smooth",
                    FabricWeight="light", GarmentSubtype="shirt")
                for i in range(1, 3)
            ]),
            RetrievedSet(direction_id="A", query_id="A2", role="bottom", products=[
                _rp(f"B{i}", FormalityLevel="smart_casual", PrimaryColor="cream",
                    ContrastLevel="medium", PatternType="solid", FitType="regular",
                    FabricDrape="soft_structured", FabricTexture="smooth",
                    FabricWeight="light", GarmentSubtype="trouser")
                for i in range(1, 3)
            ]),
            RetrievedSet(direction_id="A", query_id="A3", role="outerwear", products=[
                _rp("OW1", FormalityLevel="smart_casual", PrimaryColor="charcoal",
                    ContrastLevel="medium", PatternType="solid", FitType="tailored",
                    FabricDrape="crisp", FabricTexture="smooth",
                    FabricWeight="medium", GarmentSubtype="blazer"),
            ]),
        ]
        ctx = TupleContext(
            formality_hint="smart_casual",
            occasion_signal="daily_office_mnc",
            palette_anchors=("navy", "cream", "charcoal"),
            body_shape="Hourglass",
            intent="recommendation_request",
        )
        result = compose_outfits(plan=plan, retrieved_sets=sets, ctx=ctx, graph=_graph())

        self.assertIsNone(result.composer_result)
        self.assertEqual(result.fallback_reason, "pool_too_sparse")
        # No tuples enumerated because direction was skipped pre-enumeration.
        self.assertEqual(len(result.provenance), 0)


class MaxItemsSchemaCapTests(unittest.TestCase):
    """Spec §7.4 + Phase 5f schema cap: LLM JSON schema enforces
    maxItems=10 on the outfits array. The engine targets MAX_OUTFITS=6
    via its own logic; this test guards the LLM-side bound."""

    def test_llm_schema_caps_outfits_at_10(self):
        from agentic_application.agents.outfit_composer import _build_composer_json_schema

        schema = _build_composer_json_schema(["A", "B", "C"])
        outfits_schema = schema["schema"]["properties"]["outfits"]
        self.assertEqual(outfits_schema.get("maxItems"), 10)


if __name__ == "__main__":
    unittest.main()
