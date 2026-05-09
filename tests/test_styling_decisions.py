"""Tests for composition.styling_decisions — DupattaDrape and LayeringStructure
derivation functions.

Source of stylist intent: ``knowledge/knowledge_v2/bodyframe_stylist_revision_patchset_v_1.md``
and ``knowledge/STYLIST_NOTES.md`` cross-cutting decisions #2 and #25.
"""
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

from agentic_application.composition.styling_decisions import (
    DUPATTA_DRAPE_VALUES,
    LAYERING_STRUCTURE_VALUES,
    derive_dupatta_drape,
    recommend_layering_structures,
)


class DupattaDrapeTests(unittest.TestCase):
    def test_pear_recommends_single_shoulder_first(self):
        # Stylist: Pear benefits from single-shoulder drape that draws
        # attention upward, away from heavier hips.
        result = derive_dupatta_drape("Pear")
        self.assertEqual(result[0], "single_shoulder")
        self.assertIn("vertical_fall", result)

    def test_apple_recommends_side_fall_first(self):
        # Stylist: Side fall drapes soften the midsection.
        result = derive_dupatta_drape("Apple")
        self.assertEqual(result[0], "side_fall")

    def test_diamond_recommends_side_fall_or_vertical(self):
        # Stylist: Diamond needs vertical continuity + side softening.
        result = derive_dupatta_drape("Diamond")
        self.assertEqual(set(result), {"side_fall", "vertical_fall"})

    def test_hourglass_prefers_open_u_drape(self):
        # Hourglass's waist is the asset — open-u drape lets it show.
        result = derive_dupatta_drape("Hourglass")
        self.assertEqual(result[0], "open_u_drape")

    def test_rectangle_prefers_single_shoulder(self):
        # Rectangle needs visual interest; single-shoulder adds that.
        result = derive_dupatta_drape("Rectangle")
        self.assertEqual(result[0], "single_shoulder")

    def test_inverted_triangle_prefers_vertical_fall(self):
        # Inverted Triangle: keep visual weight away from broad shoulder.
        result = derive_dupatta_drape("Inverted Triangle")
        self.assertEqual(result[0], "vertical_fall")

    def test_unknown_body_shape_returns_empty(self):
        # Unknown shape → empty tuple, caller falls back to generic
        # presentation. Engine should never crash on missing data.
        self.assertEqual(derive_dupatta_drape("Hexagon"), ())

    def test_empty_body_shape_returns_empty(self):
        self.assertEqual(derive_dupatta_drape(""), ())

    def test_none_body_shape_returns_empty(self):
        self.assertEqual(derive_dupatta_drape(None), ())

    def test_all_recommended_values_are_canonical(self):
        # Every value the function emits must be in the canonical set —
        # otherwise downstream consumers can't validate.
        canonical = set(DUPATTA_DRAPE_VALUES)
        for shape in (
            "Pear", "Apple", "Diamond", "Hourglass",
            "Rectangle", "Inverted Triangle", "Trapezoid",
        ):
            for value in derive_dupatta_drape(shape):
                self.assertIn(
                    value, canonical,
                    f"{shape}: emitted {value!r} not in DUPATTA_DRAPE_VALUES",
                )

    def test_canonical_set_size(self):
        # Pin the canonical set so accidental additions force a test
        # update + a stylist-source re-check.
        self.assertEqual(len(DUPATTA_DRAPE_VALUES), 4)
        self.assertEqual(
            set(DUPATTA_DRAPE_VALUES),
            {"vertical_fall", "single_shoulder", "open_u_drape", "side_fall"},
        )


class LayeringStructureTests(unittest.TestCase):
    def test_apple_prefers_open_front(self):
        # Apple needs vertical balancing; open-front layer creates that.
        result = recommend_layering_structures("Apple")
        self.assertEqual(result[0], "open_front")
        self.assertIn("longline_jacket", result)

    def test_diamond_prefers_open_front(self):
        # Diamond benefits identically — vertical continuity + waist relief.
        result = recommend_layering_structures("Diamond")
        self.assertEqual(result[0], "open_front")
        self.assertIn("longline_jacket", result)

    def test_pear_prefers_cape_overlay(self):
        # Pear: broaden upper body, draw eye up.
        result = recommend_layering_structures("Pear")
        self.assertEqual(result, ("cape_overlay",))

    def test_inverted_triangle_prefers_longline_jacket(self):
        # Vertical line away from broad shoulder.
        result = recommend_layering_structures("Inverted Triangle")
        self.assertEqual(result, ("longline_jacket",))

    def test_masculine_user_gets_soft_overshirt(self):
        # ``soft_overshirt`` is the male.yaml-specific addition; should
        # be appended (not prepended) to the body-shape defaults.
        result = recommend_layering_structures("Apple", gender="masculine")
        self.assertEqual(result[-1], "soft_overshirt")
        self.assertEqual(result[0], "open_front")

    def test_male_alias_also_gets_soft_overshirt(self):
        result = recommend_layering_structures("Apple", gender="male")
        self.assertIn("soft_overshirt", result)

    def test_feminine_user_does_not_get_soft_overshirt(self):
        # soft_overshirt is intentionally male-side per the stylist patch.
        result = recommend_layering_structures("Apple", gender="feminine")
        self.assertNotIn("soft_overshirt", result)

    def test_no_gender_does_not_get_soft_overshirt(self):
        result = recommend_layering_structures("Apple")
        self.assertNotIn("soft_overshirt", result)

    def test_gender_case_insensitive(self):
        result = recommend_layering_structures("Apple", gender="MASCULINE")
        self.assertIn("soft_overshirt", result)
        result = recommend_layering_structures("Apple", gender="  Male  ")
        self.assertIn("soft_overshirt", result)

    def test_unknown_body_shape_returns_empty(self):
        self.assertEqual(recommend_layering_structures("Hexagon"), ())

    def test_unknown_body_shape_with_masculine_still_empty(self):
        # Even masculine users get nothing when body shape is unknown —
        # don't surface soft_overshirt without a body-shape anchor.
        self.assertEqual(
            recommend_layering_structures("Hexagon", gender="masculine"),
            (),
        )

    def test_empty_body_shape_returns_empty(self):
        self.assertEqual(recommend_layering_structures(""), ())

    def test_none_body_shape_returns_empty(self):
        self.assertEqual(recommend_layering_structures(None), ())

    def test_all_recommended_values_are_canonical(self):
        canonical = set(LAYERING_STRUCTURE_VALUES)
        for shape in (
            "Pear", "Apple", "Diamond", "Hourglass",
            "Rectangle", "Inverted Triangle", "Trapezoid",
        ):
            for gender in (None, "masculine", "feminine"):
                for value in recommend_layering_structures(shape, gender=gender):
                    self.assertIn(
                        value, canonical,
                        f"{shape}/{gender}: emitted {value!r} "
                        f"not in LAYERING_STRUCTURE_VALUES",
                    )

    def test_canonical_set_size(self):
        self.assertEqual(len(LAYERING_STRUCTURE_VALUES), 4)
        self.assertEqual(
            set(LAYERING_STRUCTURE_VALUES),
            {"open_front", "cape_overlay", "longline_jacket", "soft_overshirt"},
        )


if __name__ == "__main__":
    unittest.main()
