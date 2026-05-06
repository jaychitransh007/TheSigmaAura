"""Tests for the composition engine top-level (Phase 4.7d).

Cover the orchestrator's contract: contribution collection across all 11
input axes, peer-conflict detection, YAML-gap fallback, confidence
formula, direction-type resolution from query_structure, and
DirectionSpec/QuerySpec packing. Spec §6 worked-example end-to-end
tests live in tests/test_composition_engine_examples.py (Phase 4.7f)."""
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

from agentic_application.composition.engine import (
    ATTR_OMIT_PENALTY,
    CONFIDENCE_THRESHOLD,
    HARD_WIDEN_PENALTY,
    SOFT_DROP_PENALTY,
    YAML_GAP_PENALTY,
    CompositionInputs,
    CompositionResult,
    ProvenanceEntry,
    _compute_confidence,
    _detect_peer_conflict,
    _resolve_body_frame_yaml,
    _time_of_day_to_garment_value,
    compose_direction,
)
from agentic_application.composition.reduction import AttributeContribution
from agentic_application.composition.relaxation import ClassifiedContribution
from agentic_application.composition.yaml_loader import load_style_graph
from agentic_application.schemas import DirectionSpec, QuerySpec, UserContext


def _baseline_inputs(**overrides) -> CompositionInputs:
    base = dict(
        gender="female",
        body_shape="Hourglass",
        frame_structure="Light and Narrow",
        seasonal_color_group="Soft Autumn",
        archetype="modern_professional",
        risk_tolerance="moderate",
        occasion_signal="daily_office_mnc",
        formality_hint="smart_casual",
        weather_context="warm_temperate",
        time_of_day="daytime",
    )
    base.update(overrides)
    return CompositionInputs(**base)


def _user(gender: str = "female") -> UserContext:
    return UserContext(user_id="t", gender=gender)


class ComposeDirectionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = load_style_graph()

    def test_returns_direction_spec_with_queries(self):
        result = compose_direction(
            inputs=_baseline_inputs(), graph=self.graph, user=_user()
        )
        self.assertIsInstance(result, CompositionResult)
        self.assertIsInstance(result.direction, DirectionSpec)
        self.assertEqual(result.direction.direction_id, "A")
        # daily_office_mnc default_structure is "paired" per query_structure.yaml.
        self.assertEqual(result.direction.direction_type, "paired")
        self.assertEqual(len(result.direction.queries), 2)
        roles = [q.role for q in result.direction.queries]
        self.assertEqual(roles, ["top", "bottom"])

    def test_direction_type_complete_emits_one_query(self):
        # cocktail_party defaults to complete in query_structure.yaml.
        result = compose_direction(
            inputs=_baseline_inputs(occasion_signal="cocktail_party"),
            graph=self.graph,
            user=_user(),
        )
        self.assertEqual(result.direction.direction_type, "complete")
        self.assertEqual(len(result.direction.queries), 1)
        self.assertEqual(result.direction.queries[0].role, "complete")

    def test_direction_type_three_piece_emits_three_queries(self):
        # interview defaults to three_piece.
        result = compose_direction(
            inputs=_baseline_inputs(occasion_signal="interview"),
            graph=self.graph,
            user=_user(),
        )
        self.assertEqual(result.direction.direction_type, "three_piece")
        self.assertEqual(len(result.direction.queries), 3)
        self.assertEqual(
            [q.role for q in result.direction.queries],
            ["top", "bottom", "outerwear"],
        )

    def test_query_specs_carry_global_hard_filters(self):
        result = compose_direction(
            inputs=_baseline_inputs(), graph=self.graph, user=_user("female")
        )
        for q in result.direction.queries:
            self.assertEqual(q.hard_filters.get("gender_expression"), "feminine")

    def test_provenance_one_entry_per_touched_attribute(self):
        result = compose_direction(
            inputs=_baseline_inputs(), graph=self.graph, user=_user()
        )
        # Every provenance entry has a contributing source kind in the
        # status enum we promised.
        self.assertGreater(len(result.provenance), 0)
        for p in result.provenance:
            self.assertIn(p.status, {"clean", "soft_relaxed", "hard_widened", "omitted"})
            self.assertIsInstance(p, ProvenanceEntry)


class PeerConflictTests(unittest.TestCase):
    def test_no_peer_conflict_when_kinds_overlap(self):
        contribs = [
            ClassifiedContribution(
                contribution=AttributeContribution(
                    source="archetype:x",
                    flatters=("a", "b"),
                    avoid=(),
                ),
                source_kind="archetype",
                tier="soft",
            ),
            ClassifiedContribution(
                contribution=AttributeContribution(
                    source="risk_tolerance:y",
                    flatters=("b", "c"),
                    avoid=(),
                ),
                source_kind="risk_tolerance",
                tier="soft",
            ),
        ]
        self.assertFalse(_detect_peer_conflict(contribs))

    def test_peer_conflict_when_disjoint(self):
        contribs = [
            ClassifiedContribution(
                contribution=AttributeContribution(
                    source="archetype:x", flatters=("a",), avoid=(),
                ),
                source_kind="archetype",
                tier="soft",
            ),
            ClassifiedContribution(
                contribution=AttributeContribution(
                    source="risk_tolerance:y", flatters=("b",), avoid=(),
                ),
                source_kind="risk_tolerance",
                tier="soft",
            ),
        ]
        self.assertTrue(_detect_peer_conflict(contribs))

    def test_no_peer_conflict_when_only_one_peer_present(self):
        contribs = [
            ClassifiedContribution(
                contribution=AttributeContribution(
                    source="archetype:x", flatters=("a",), avoid=(),
                ),
                source_kind="archetype",
                tier="soft",
            ),
        ]
        self.assertFalse(_detect_peer_conflict(contribs))


class YamlGapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = load_style_graph()

    def test_unknown_body_shape_marks_yaml_gap(self):
        result = compose_direction(
            inputs=_baseline_inputs(body_shape="NotARealShape"),
            graph=self.graph,
            user=_user(),
        )
        self.assertIn(
            "body_shape:NotARealShape", result.yaml_gaps,
        )
        self.assertEqual(result.fallback_reason, "yaml_gap")

    def test_unknown_occasion_marks_yaml_gap_and_falls_back_direction_type(self):
        result = compose_direction(
            inputs=_baseline_inputs(occasion_signal="not_in_yaml"),
            graph=self.graph,
            user=_user(),
        )
        # YAML gap on the occasion mapping itself.
        self.assertIn("occasion_signal:not_in_yaml", result.yaml_gaps)
        # query_structure also doesn't have it; the engine falls back to
        # the "fallback.default" entry, which is "paired".
        self.assertEqual(result.direction.direction_type, "paired")

    def test_yaml_gap_drops_confidence_below_threshold(self):
        result = compose_direction(
            inputs=_baseline_inputs(seasonal_color_group="not_a_subseason"),
            graph=self.graph,
            user=_user(),
        )
        self.assertLess(result.confidence, CONFIDENCE_THRESHOLD)
        self.assertEqual(result.fallback_reason, "yaml_gap")


class ConfidenceFormulaTests(unittest.TestCase):
    """Unit-test the confidence formula directly so the §8 coefficients
    are machine-verified rather than only spot-checked end-to-end."""

    def _entry(self, status: str, softs: int = 0, hards: int = 0) -> ProvenanceEntry:
        return ProvenanceEntry(
            attribute="X",
            final_flatters=("v",) if status != "omitted" else (),
            contributing_sources=(),
            status=status,
            dropped_softs=tuple(f"s{i}" for i in range(softs)),
            widened_hards=tuple(f"h{i}" for i in range(hards)),
        )

    def test_clean_no_gap_is_one(self):
        score = _compute_confidence(
            [self._entry("clean")], yaml_gap=False
        )
        self.assertEqual(score, 1.0)

    def test_per_soft_drop_subtracts_0_10(self):
        score = _compute_confidence(
            [self._entry("soft_relaxed", softs=1)], yaml_gap=False
        )
        self.assertAlmostEqual(score, 1.0 - SOFT_DROP_PENALTY)

    def test_per_hard_widen_subtracts_0_20(self):
        score = _compute_confidence(
            [self._entry("hard_widened", hards=1)], yaml_gap=False
        )
        self.assertAlmostEqual(score, 1.0 - HARD_WIDEN_PENALTY)

    def test_per_omitted_subtracts_0_30(self):
        score = _compute_confidence(
            [self._entry("omitted")], yaml_gap=False
        )
        self.assertAlmostEqual(score, 1.0 - ATTR_OMIT_PENALTY)

    def test_yaml_gap_subtracts_0_45(self):
        score = _compute_confidence(
            [self._entry("clean")], yaml_gap=True
        )
        self.assertAlmostEqual(score, 1.0 - YAML_GAP_PENALTY)

    def test_clamped_to_floor_zero(self):
        score = _compute_confidence(
            [self._entry("hard_widened", hards=10)], yaml_gap=True
        )
        self.assertEqual(score, 0.0)

    def test_clamped_to_ceiling_one(self):
        score = _compute_confidence([], yaml_gap=False)
        self.assertEqual(score, 1.0)


class HelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = load_style_graph()

    def test_resolve_body_frame_yaml_picks_correct_table(self):
        female = _resolve_body_frame_yaml(self.graph, "female")
        male = _resolve_body_frame_yaml(self.graph, "male")
        # Tables should be different objects.
        self.assertIsNot(female, male)
        # And unisex falls to female.
        unisex = _resolve_body_frame_yaml(self.graph, "unisex")
        self.assertIs(unisex, female)

    def test_time_of_day_translation(self):
        self.assertEqual(_time_of_day_to_garment_value("morning"), "day")
        self.assertEqual(_time_of_day_to_garment_value("daytime"), "day")
        self.assertEqual(_time_of_day_to_garment_value("evening"), "evening")
        self.assertEqual(_time_of_day_to_garment_value("night"), "evening")
        # Unknown values map to None (no contribution).
        self.assertIsNone(_time_of_day_to_garment_value("blizzard"))


if __name__ == "__main__":
    unittest.main()
