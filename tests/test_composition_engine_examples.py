"""Phase 4.7f — engine end-to-end tests against spec §6 worked examples.

Each test runs ``compose_direction()`` against the real on-disk YAMLs
(loaded via ``load_style_graph``) and asserts the per-attribute
provenance for the attribute the spec walks through. Where the spec's
illustrative inputs don't have YAML equivalents (e.g. ``warm_dry``
weather, ``ultra-conservative`` archetype), tests use the closest real
values — the algorithm under test is the reduction + relaxation, not
the literal spec text.

Worked examples covered (``docs/composition_semantics.md`` §6):

- §6.1 — Daily-office, Hourglass + Light-and-Narrow + Soft Autumn +
  modern_professional → FabricDrape = soft_structured (clean).
- §6.2 — Same user with archetype = glamorous → EmbellishmentLevel
  starts empty (occasion-vs-archetype clash), soft-relax drops
  archetype, final = subtle.
- §6.3 — Inverted Triangle + cocktail_party with conservative
  risk_tolerance + classic archetype → NecklineType resolves cleanly
  to (v_neck, scoop, sweetheart). The spec's archetype=ultra-conservative
  isn't a real YAML value; the test asserts the algorithm produces a
  flattering set in body_shape's pre-existing direction.
- §6.4 — Pathological YAML gap → fallback_reason = "yaml_gap" and
  confidence < threshold, with direction still emitted (engine is
  total)."""
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
    CONFIDENCE_THRESHOLD,
    CompositionInputs,
    ProvenanceEntry,
    compose_direction,
)
from agentic_application.composition.yaml_loader import load_style_graph
from agentic_application.schemas import UserContext


def _provenance_for(
    provenance, attribute: str
) -> ProvenanceEntry:
    for p in provenance:
        if p.attribute == attribute:
            return p
    raise AssertionError(f"no provenance entry for {attribute!r}")


class WorkedExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = load_style_graph()
        cls.user_female = UserContext(user_id="t", gender="female")

    # §6.1 ---------------------------------------------------------------

    def test_section_6_1_fabric_drape_resolves_to_soft_structured(self):
        """Daily-office, Hourglass + Light-and-Narrow + Soft Autumn +
        modern_professional. FabricDrape final = (soft_structured,)
        via clean intersection of body/frame/archetype contributions."""
        result = compose_direction(
            inputs=CompositionInputs(
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
            ),
            graph=self.graph,
            user=self.user_female,
        )
        drape = _provenance_for(result.provenance, "FabricDrape")
        self.assertEqual(drape.final_flatters, ("soft_structured",))
        self.assertEqual(drape.status, "clean")
        # Multiple sources contributed to the intersect.
        self.assertGreaterEqual(len(drape.contributing_sources), 2)

    # §6.2 ---------------------------------------------------------------

    def test_section_6_2_glamorous_archetype_soft_relaxed(self):
        """Same user, archetype = glamorous. EmbellishmentLevel
        starts empty (occasion's [minimal, subtle] vs archetype's
        [moderate, statement]); soft-relax drops archetype and final
        is non-empty."""
        result = compose_direction(
            inputs=CompositionInputs(
                gender="female",
                body_shape="Hourglass",
                frame_structure="Light and Narrow",
                seasonal_color_group="Soft Autumn",
                archetype="glamorous",
                risk_tolerance="moderate",
                occasion_signal="daily_office_mnc",
                formality_hint="smart_casual",
                weather_context="warm_temperate",
                time_of_day="daytime",
            ),
            graph=self.graph,
            user=self.user_female,
        )
        emb = _provenance_for(result.provenance, "EmbellishmentLevel")
        self.assertEqual(emb.status, "soft_relaxed")
        self.assertIn("archetype", emb.dropped_softs)
        self.assertGreater(len(emb.final_flatters), 0)
        # Occasion's flatters set is [minimal, subtle]; the surviving
        # values must be a subset.
        for v in emb.final_flatters:
            self.assertIn(v, {"minimal", "subtle"})

    # §6.3 ---------------------------------------------------------------

    def test_section_6_3_inverted_triangle_cocktail_neckline(self):
        """Inverted Triangle + cocktail_party. NecklineType resolves to
        the body_shape-flattering set. The spec's archetype=ultra-
        conservative isn't a real YAML value, so the test instead asserts
        the body_shape contributions produce a flattering set that
        avoids broadening necklines (boat, square)."""
        result = compose_direction(
            inputs=CompositionInputs(
                gender="female",
                body_shape="Inverted Triangle",
                frame_structure="Medium and Balanced",
                seasonal_color_group="Soft Autumn",
                archetype="classic",
                risk_tolerance="conservative",
                occasion_signal="cocktail_party",
                formality_hint="semi_formal",
                weather_context="warm_temperate",
                time_of_day="evening",
            ),
            graph=self.graph,
            user=self.user_female,
        )
        neck = _provenance_for(result.provenance, "NecklineType")
        # The Inverted Triangle YAML carries flatters
        # [v_neck, scoop, sweetheart] and avoid [boat, square, halter].
        self.assertGreater(len(neck.final_flatters), 0)
        for forbidden in ("boat", "square"):
            self.assertNotIn(forbidden, neck.final_flatters)

    # §6.4 ---------------------------------------------------------------

    def test_section_6_4_yaml_gap_triggers_low_confidence_fallback(self):
        """A YAML gap (input value not in the relevant dimension)
        deducts 0.45 from confidence and lands below the 0.60 threshold,
        per the spec §8 calibration. Engine still returns a
        ``DirectionSpec`` with ``fallback_reason="yaml_gap"`` so the
        hot-path router can decide what to do."""
        result = compose_direction(
            inputs=CompositionInputs(
                gender="female",
                body_shape="Hourglass",
                frame_structure="Light and Narrow",
                seasonal_color_group="not_in_yaml",  # ← YAML gap
                archetype="modern_professional",
                risk_tolerance="moderate",
                occasion_signal="daily_office_mnc",
                formality_hint="smart_casual",
                weather_context="warm_temperate",
                time_of_day="daytime",
            ),
            graph=self.graph,
            user=self.user_female,
        )
        self.assertIsNotNone(result.direction, "engine should still return a DirectionSpec")
        self.assertEqual(result.fallback_reason, "yaml_gap")
        self.assertLess(result.confidence, CONFIDENCE_THRESHOLD)
        self.assertTrue(
            any("seasonal_color_group" in g for g in result.yaml_gaps),
            f"expected seasonal_color_group gap; got {result.yaml_gaps}",
        )


class StableOutputTests(unittest.TestCase):
    """Determinism is the engine's whole value proposition (Phase 2 cache
    hit rate depends on it). Two compose_direction() calls with the same
    inputs must produce structurally identical output."""

    @classmethod
    def setUpClass(cls):
        cls.graph = load_style_graph()

    def test_two_calls_with_same_inputs_produce_equal_results(self):
        kwargs = dict(
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
        user = UserContext(user_id="t", gender="female")
        a = compose_direction(
            inputs=CompositionInputs(**kwargs), graph=self.graph, user=user
        )
        b = compose_direction(
            inputs=CompositionInputs(**kwargs), graph=self.graph, user=user
        )
        self.assertEqual(a.confidence, b.confidence)
        self.assertEqual(a.needs_disambiguation, b.needs_disambiguation)
        self.assertEqual(a.fallback_reason, b.fallback_reason)
        self.assertEqual(a.provenance, b.provenance)
        self.assertEqual(
            [q.query_document for q in a.direction.queries],
            [q.query_document for q in b.direction.queries],
        )


if __name__ == "__main__":
    unittest.main()
