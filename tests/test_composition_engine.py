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
    _build_hard_attrs,
    _classify_attr_tier,
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

    def test_unknown_body_shape_records_gap(self):
        result = compose_direction(
            inputs=_baseline_inputs(body_shape="NotARealShape"),
            graph=self.graph,
            user=_user(),
        )
        self.assertIn("body_shape:NotARealShape", result.yaml_gaps)
        # body_shape is load-bearing across many attributes; losing it
        # cascades into omits/relaxes that drop confidence below the
        # threshold even with the per-gap-only penalty. The fallback
        # reason should still tag the original gap-driven cause.
        if result.fallback_reason is not None:
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

    def test_single_seasonal_gap_no_longer_auto_falls_through(self):
        # Layer 1: a single-axis gap (here seasonal_color_group)
        # subtracts 0.20 from confidence (was: binary 0.45 + immediate
        # fall-through). 1.0 - 0.20 = 0.80 ≥ threshold 0.50, so the
        # engine should KEEP the direction — no auto-fall-through.
        result = compose_direction(
            inputs=_baseline_inputs(seasonal_color_group="not_a_subseason"),
            graph=self.graph,
            user=_user(),
        )
        self.assertIn("seasonal_color_group:not_a_subseason", result.yaml_gaps)
        self.assertGreaterEqual(result.confidence, CONFIDENCE_THRESHOLD)
        self.assertIsNone(result.fallback_reason)
        self.assertIsNotNone(result.direction)

    def test_multiple_axis_gaps_still_fall_through(self):
        # 3 simultaneous gaps: 1.0 - 3*0.20 = 0.40, below threshold.
        # Multi-gap turns still get the LLM, just not on a single gap.
        result = compose_direction(
            inputs=_baseline_inputs(
                seasonal_color_group="not_a_subseason",
                weather_context="not_a_weather",
                occasion_signal="not_in_yaml",
            ),
            graph=self.graph,
            user=_user(),
        )
        self.assertGreaterEqual(len(result.yaml_gaps), 3)
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
            [self._entry("clean")], yaml_gap_count=0
        )
        self.assertEqual(score, 1.0)

    def test_per_soft_drop_subtracts_0_10(self):
        score = _compute_confidence(
            [self._entry("soft_relaxed", softs=1)], yaml_gap_count=0
        )
        self.assertAlmostEqual(score, 1.0 - SOFT_DROP_PENALTY)

    def test_per_hard_widen_subtracts_0_20(self):
        score = _compute_confidence(
            [self._entry("hard_widened", hards=1)], yaml_gap_count=0
        )
        self.assertAlmostEqual(score, 1.0 - HARD_WIDEN_PENALTY)

    def test_per_omitted_subtracts_0_30(self):
        score = _compute_confidence(
            [self._entry("omitted")], yaml_gap_count=0
        )
        self.assertAlmostEqual(score, 1.0 - ATTR_OMIT_PENALTY)

    def test_one_yaml_gap_subtracts_0_20(self):
        # Layer 1: per-gap penalty replaces the binary 0.45 penalty.
        score = _compute_confidence(
            [self._entry("clean")], yaml_gap_count=1
        )
        self.assertAlmostEqual(score, 1.0 - YAML_GAP_PENALTY)

    def test_three_yaml_gaps_drop_below_threshold(self):
        score = _compute_confidence(
            [self._entry("clean")], yaml_gap_count=3
        )
        self.assertAlmostEqual(score, 1.0 - 3 * YAML_GAP_PENALTY)
        self.assertLess(score, 0.50)  # below CONFIDENCE_THRESHOLD

    def test_clamped_to_floor_zero(self):
        score = _compute_confidence(
            [self._entry("hard_widened", hards=10)], yaml_gap_count=2
        )
        self.assertEqual(score, 0.0)

    def test_clamped_to_ceiling_one(self):
        score = _compute_confidence([], yaml_gap_count=0)
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


class HardAttrTierTests(unittest.TestCase):
    """Verify the §3.3 tier classification and hard_attrs extraction.
    Used by _build_query_specs to populate QuerySpec.hard_attrs which
    flows into the SQL ORDER-BY penalty term."""

    def _entry(self, attr: str, flatters: tuple[str, ...], sources: tuple[str, ...]) -> ProvenanceEntry:
        return ProvenanceEntry(
            attribute=attr,
            final_flatters=flatters,
            contributing_sources=sources,
            status="clean",
            dropped_softs=(),
            widened_hards=(),
        )

    def test_classify_hard_when_any_contributor_is_hard(self):
        # Mixed contributors — body_shape (hard) + archetype (soft) → hard wins.
        tier = _classify_attr_tier(("archetype:modern_professional", "body_shape:Hourglass"))
        self.assertEqual(tier, "hard")

    def test_classify_soft_when_all_contributors_are_soft(self):
        tier = _classify_attr_tier(("archetype:glamorous", "risk_tolerance:expressive", "time_of_day:evening"))
        self.assertEqual(tier, "soft")

    def test_classify_none_when_no_contributors(self):
        self.assertIsNone(_classify_attr_tier(()))

    def test_weather_fabric_is_hard(self):
        # The fabric-related weather subset is hard per §3.3.
        tier = _classify_attr_tier(("weather_fabric:high_altitude_cool",))
        self.assertEqual(tier, "hard")

    def test_seasonal_color_is_hard(self):
        tier = _classify_attr_tier(("seasonal:Soft Autumn",))
        self.assertEqual(tier, "hard")

    def test_formality_hint_is_hard(self):
        tier = _classify_attr_tier(("formality_hint:smart_casual",))
        self.assertEqual(tier, "hard")

    def test_build_hard_attrs_includes_only_hard_tier(self):
        # SleeveLength comes from weather (hard) → included.
        # FabricTexture comes only from archetype (soft) → excluded.
        # FormalityLevel comes from formality_hint (hard) → included.
        provenance = (
            self._entry(
                "SleeveLength", ("three_quarter", "full"),
                ("weather_fabric:high_altitude_cool",),
            ),
            self._entry(
                "FabricTexture", ("smooth",),
                ("archetype:modern_professional",),
            ),
            self._entry(
                "FormalityLevel", ("smart_casual",),
                ("formality_hint:smart_casual",),
            ),
        )
        out = _build_hard_attrs(provenance)
        self.assertEqual(out, {
            "SleeveLength": ["three_quarter", "full"],
            "FormalityLevel": ["smart_casual"],
        })
        self.assertNotIn("FabricTexture", out)

    def test_build_hard_attrs_skips_empty_flatters(self):
        # An attribute that ended up with no flatters (omitted) shouldn't
        # appear — empty allowed-list would penalize EVERY item.
        provenance = (
            self._entry("EmbellishmentLevel", (), ("body_shape:Hourglass",)),
        )
        self.assertEqual(_build_hard_attrs(provenance), {})

    def test_compose_direction_emits_hard_attrs_on_query_spec(self):
        # End-to-end: compose_direction populates query_specs[*].hard_attrs
        # with HARD-tier reduced flatters from real YAML inputs.
        graph = load_style_graph()
        result = compose_direction(
            inputs=_baseline_inputs(weather_context="high_altitude_cool"),
            graph=graph,
            user=_user(),
        )
        self.assertIsNotNone(result.direction)
        # At least one query carries hard_attrs.
        any_hard_attrs = any(q.hard_attrs for q in result.direction.queries)
        self.assertTrue(any_hard_attrs, "expected hard_attrs to be populated from hard-tier sources")
        # SleeveLength from high_altitude_cool weather should be present.
        for q in result.direction.queries:
            if "SleeveLength" in q.hard_attrs:
                # Engine reduced sleeve length; should NOT include sleeveless / cap / short.
                disallowed = {"sleeveless", "cap", "short"}
                self.assertFalse(
                    disallowed & set(q.hard_attrs["SleeveLength"]),
                    f"SleeveLength flatters leaked disallowed values: {q.hard_attrs['SleeveLength']}",
                )

    def test_weather_fabric_contribution_is_hard_tier_in_provenance(self):
        # REGRESSION (turn 575e2fe0): the source label stored in
        # AttributeContribution carried the caller's prefix ("weather:")
        # rather than the per-attribute kind ("weather_fabric"), so
        # _classify_attr_tier saw "weather" — not in _HARD_SOURCE_KINDS —
        # and mis-classified attributes ONLY contributed by weather as
        # soft. SleeveLength fell out of hard_attrs entirely; short-sleeve
        # shirts surfaced for "Manali trip." This test pins the per-
        # attribute source-label rewrite in _add_mapping.
        graph = load_style_graph()
        result = compose_direction(
            inputs=_baseline_inputs(weather_context="high_altitude_cool"),
            graph=graph,
            user=_user(),
        )
        # SleeveLength in this scenario is contributed only by weather.
        # If hard_attrs picks it up, the tier classifier saw a hard
        # source label.
        sleeve_in_hard = any(
            "SleeveLength" in q.hard_attrs for q in result.direction.queries
        )
        self.assertTrue(
            sleeve_in_hard,
            "SleeveLength must appear in hard_attrs when weather is the "
            "sole opinionated source (weather_fabric tier-aware label).",
        )
        # And the values must be what high_altitude_cool's weather YAML
        # specifies — three_quarter / full only, none of sleeveless / cap / short.
        for q in result.direction.queries:
            if "SleeveLength" in q.hard_attrs:
                self.assertEqual(
                    set(q.hard_attrs["SleeveLength"]) & {"three_quarter", "full"},
                    set(q.hard_attrs["SleeveLength"]),
                    "SleeveLength flatters should be exactly the high_altitude_cool values",
                )


if __name__ == "__main__":
    unittest.main()
