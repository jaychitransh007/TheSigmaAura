"""Tests for the per-attribute reduction (Phase 4.7b).

Cover the algorithm exhaustively at the per-attribute layer so the
relaxation + orchestration layers (4.7c, 4.7d) can build on a known-good
foundation. Includes a verbatim re-run of spec §6.1's FabricDrape
worked example."""
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

from agentic_application.composition.reduction import (
    AttributeContribution,
    AttributeReduction,
    reduce_attribute,
)


class ReduceAttributeTests(unittest.TestCase):

    def test_no_contributions_yields_empty_reduction(self):
        out = reduce_attribute("FabricDrape", [])
        self.assertEqual(out.final_flatters, ())
        self.assertEqual(out.final_avoid, ())
        self.assertEqual(out.intersect_flatters, ())
        self.assertEqual(out.contributing_sources, ())
        self.assertEqual(out.avoid_only_sources, ())

    def test_single_source_returns_dedup_flatters_minus_avoid(self):
        out = reduce_attribute(
            "FabricDrape",
            [AttributeContribution(
                source="body_shape:Hourglass",
                flatters=("fluid", "soft_structured", "fluid"),  # dedup test
                avoid=("rigid",),
            )],
        )
        self.assertEqual(out.final_flatters, ("fluid", "soft_structured"))
        self.assertEqual(out.final_avoid, ("rigid",))
        self.assertEqual(out.contributing_sources, ("body_shape:Hourglass",))

    def test_intersect_keeps_first_source_ordering(self):
        # Position-0-is-strongest: order comes from the FIRST opinionated
        # source, even if a later source lists values in a different order.
        out = reduce_attribute(
            "SilhouetteType",
            [
                AttributeContribution(
                    source="body_shape:Pear",
                    flatters=("a_line", "fitted", "wrap", "peplum"),
                    avoid=(),
                ),
                AttributeContribution(
                    source="archetype:classic",
                    flatters=("wrap", "a_line", "tapered"),
                    avoid=(),
                ),
            ],
        )
        # Intersection in first source's order: a_line, wrap.
        self.assertEqual(out.final_flatters, ("a_line", "wrap"))

    def test_avoid_unions_across_all_sources(self):
        out = reduce_attribute(
            "FabricDrape",
            [
                AttributeContribution(
                    source="A", flatters=("fluid",), avoid=("rigid", "sculpted"),
                ),
                AttributeContribution(
                    source="B", flatters=("fluid",), avoid=("sculpted", "draped"),
                ),
            ],
        )
        # Order-preserving union across the two avoid lists.
        self.assertEqual(out.final_avoid, ("rigid", "sculpted", "draped"))

    def test_avoid_wins_over_flatters(self):
        # archetype says fluid is avoid, body_shape says fluid is flatters
        # → fluid is dropped from final_flatters but it WAS in the
        # intersect_flatters (which the relaxation layer uses).
        out = reduce_attribute(
            "FabricDrape",
            [
                AttributeContribution(
                    source="body_shape", flatters=("fluid", "soft_structured"), avoid=(),
                ),
                AttributeContribution(
                    source="archetype", flatters=("soft_structured",), avoid=("fluid",),
                ),
            ],
        )
        self.assertEqual(out.intersect_flatters, ("soft_structured",))
        self.assertEqual(out.final_flatters, ("soft_structured",))
        self.assertIn("fluid", out.final_avoid)

    def test_avoid_only_source_constrains_avoid_but_not_intersect(self):
        # A source with no flatters opinion but an avoid contribution
        # should NOT force final_flatters empty by intersection — it just
        # narrows the avoid set.
        out = reduce_attribute(
            "FabricDrape",
            [
                AttributeContribution(
                    source="body_shape:Hourglass",
                    flatters=("fluid", "soft_structured"),
                    avoid=(),
                ),
                AttributeContribution(
                    source="weather:hot_humid",
                    flatters=(),
                    avoid=("rigid", "sculpted"),
                ),
            ],
        )
        self.assertEqual(out.final_flatters, ("fluid", "soft_structured"))
        self.assertIn("rigid", out.final_avoid)
        # avoid_only source is reported separately for provenance.
        self.assertEqual(out.avoid_only_sources, ("weather:hot_humid",))
        self.assertEqual(out.contributing_sources, ("body_shape:Hourglass",))

    def test_empty_intersection_returns_empty_final(self):
        # No common values across opinionated sources.
        out = reduce_attribute(
            "FabricDrape",
            [
                AttributeContribution(
                    source="A", flatters=("fluid",), avoid=(),
                ),
                AttributeContribution(
                    source="B", flatters=("rigid",), avoid=(),
                ),
            ],
        )
        self.assertEqual(out.intersect_flatters, ())
        self.assertEqual(out.final_flatters, ())
        # Both sources still reported as contributing — relaxation will
        # decide which one to drop.
        self.assertEqual(out.contributing_sources, ("A", "B"))

    def test_spec_section_6_1_worked_example_fabric_drape(self):
        """Verbatim §6.1 of docs/composition_semantics.md.

        Daily-office, feminine, Hourglass + Light-and-Narrow + Soft
        Autumn + Modern Professional. Reduction over FabricDrape:

            body_shape (Hourglass)         flatters: [fluid, soft_structured]   avoid: [rigid, oversized]
            frame_structure (Light/Narrow) flatters: [fluid, soft_structured, lightweight]
                                           avoid: [heavy, sculpted]
            archetype (modern_professional) flatters: [structured, soft_structured]
                                            avoid: [draped, distressed]
            occasion (daily_office_mnc)    no FabricDrape opinion

        Expected final = {soft_structured}.
        """
        out = reduce_attribute(
            "FabricDrape",
            [
                AttributeContribution(
                    source="body_shape:Hourglass",
                    flatters=("fluid", "soft_structured"),
                    avoid=("rigid", "oversized"),
                ),
                AttributeContribution(
                    source="frame_structure:Light_and_Narrow",
                    flatters=("fluid", "soft_structured", "lightweight"),
                    avoid=("heavy", "sculpted"),
                ),
                AttributeContribution(
                    source="archetype:modern_professional",
                    flatters=("structured", "soft_structured"),
                    avoid=("draped", "distressed"),
                ),
            ],
        )
        self.assertEqual(out.final_flatters, ("soft_structured",))
        self.assertEqual(
            set(out.final_avoid),
            {"rigid", "oversized", "heavy", "sculpted", "draped", "distressed"},
        )
        self.assertEqual(
            out.contributing_sources,
            (
                "body_shape:Hourglass",
                "frame_structure:Light_and_Narrow",
                "archetype:modern_professional",
            ),
        )

    def test_reduction_is_a_frozen_dataclass(self):
        out = reduce_attribute("FabricDrape", [])
        with self.assertRaises(Exception):
            out.final_flatters = ("foo",)  # type: ignore[misc]
        self.assertIsInstance(out, AttributeReduction)


if __name__ == "__main__":
    unittest.main()
