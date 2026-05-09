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
    BRIDAL_ROLE_VALUES,
    DUPATTA_DRAPE_VALUES,
    LAYERING_STRUCTURE_VALUES,
    MOVEMENT_SECURITY_VALUES,
    SUPPORT_REQUIREMENT_VALUES,
    derive_dupatta_drape,
    derive_movement_security,
    derive_support_requirement,
    is_bridal_role_occasion,
    lookup_bridal_priority_rules,
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


class MovementSecurityTests(unittest.TestCase):
    def test_sangeet_requires_secure(self):
        # Stylist: sangeet is dance-heavy — outfit must support
        # rotational movement.
        self.assertEqual(derive_movement_security("sangeet"), "secure")

    def test_navratri_requires_secure(self):
        self.assertEqual(derive_movement_security("navratri"), "secure")

    def test_mehndi_requires_secure(self):
        self.assertEqual(derive_movement_security("mehndi"), "secure")

    def test_gala_dinner_allows_delicate(self):
        # Editorial / sit-down formal — low movement is fine.
        self.assertEqual(derive_movement_security("gala_dinner"), "delicate")

    def test_in_laws_meeting_allows_delicate(self):
        self.assertEqual(
            derive_movement_security("in_laws_first_meeting"), "delicate"
        )

    def test_default_is_moderate(self):
        # Unknown / common-case occasions land on moderate (safe default).
        self.assertEqual(derive_movement_security("daily_office_mnc"), "moderate")
        self.assertEqual(derive_movement_security("first_date"), "moderate")

    def test_empty_signal_is_moderate(self):
        self.assertEqual(derive_movement_security(""), "moderate")
        self.assertEqual(derive_movement_security(None), "moderate")

    def test_case_insensitive(self):
        self.assertEqual(derive_movement_security("SANGEET"), "secure")
        self.assertEqual(derive_movement_security("  Sangeet  "), "secure")

    def test_canonical_set(self):
        self.assertEqual(
            set(MOVEMENT_SECURITY_VALUES),
            {"secure", "moderate", "delicate"},
        )


class SupportRequirementTests(unittest.TestCase):
    def test_strapless_dress_is_high(self):
        # Garment subtype dominates — strapless is high regardless of occasion.
        self.assertEqual(
            derive_support_requirement(garment_subtype="strapless_dress"),
            "high",
        )

    def test_off_shoulder_blouse_is_high(self):
        self.assertEqual(
            derive_support_requirement(
                occasion_signal="daily_office_mnc",
                garment_subtype="off_shoulder_blouse",
            ),
            "high",  # garment dominates over occasion
        )

    def test_corset_is_high(self):
        self.assertEqual(
            derive_support_requirement(garment_subtype="corset"),
            "high",
        )

    def test_wedding_ceremony_is_medium(self):
        # Long ceremonial wear — extended-wear support required.
        self.assertEqual(
            derive_support_requirement(occasion_signal="wedding_ceremony"),
            "medium",
        )

    def test_sangeet_is_medium(self):
        self.assertEqual(
            derive_support_requirement(occasion_signal="sangeet"),
            "medium",
        )

    def test_daily_office_is_low(self):
        self.assertEqual(
            derive_support_requirement(occasion_signal="daily_office_mnc"),
            "low",
        )

    def test_default_is_low(self):
        self.assertEqual(derive_support_requirement(), "low")
        self.assertEqual(
            derive_support_requirement(occasion_signal=None, garment_subtype=None),
            "low",
        )

    def test_high_garment_overrides_low_occasion(self):
        # User wears strapless to office — schema still flags high
        # support need (the occasion may itself be inadvisable; that's
        # a different rule).
        self.assertEqual(
            derive_support_requirement(
                occasion_signal="coffee_meetup",
                garment_subtype="strapless_dress",
            ),
            "high",
        )

    def test_canonical_set(self):
        self.assertEqual(
            set(SUPPORT_REQUIREMENT_VALUES),
            {"low", "medium", "high"},
        )


class BridalRoleTests(unittest.TestCase):
    def test_wedding_ceremony_is_bridal_role_occasion(self):
        self.assertTrue(is_bridal_role_occasion("wedding_ceremony"))
        self.assertTrue(is_bridal_role_occasion("sangeet"))
        self.assertTrue(is_bridal_role_occasion("mehndi"))
        self.assertTrue(is_bridal_role_occasion("haldi"))
        self.assertTrue(is_bridal_role_occasion("reception"))
        self.assertTrue(is_bridal_role_occasion("engagement"))

    def test_daily_office_is_not_bridal_role_occasion(self):
        self.assertFalse(is_bridal_role_occasion("daily_office_mnc"))
        self.assertFalse(is_bridal_role_occasion("coffee_meetup"))

    def test_empty_signal_is_not_bridal_role_occasion(self):
        self.assertFalse(is_bridal_role_occasion(""))
        self.assertFalse(is_bridal_role_occasion(None))

    def test_case_insensitive(self):
        self.assertTrue(is_bridal_role_occasion("WEDDING_CEREMONY"))
        self.assertTrue(is_bridal_role_occasion("  Sangeet  "))

    def test_lookup_bride_role_returns_bride_rules(self):
        priority = {
            "bride": {"hard_flatters": {"OccasionFit": ["bridal"]}},
            "groom": {"hard_flatters": {"OccasionFit": ["ceremonial"]}},
            "guest": {"hard_avoid": {"OccasionFit": ["bridal"]}},
        }
        result = lookup_bridal_priority_rules("bride", priority)
        self.assertEqual(result, {"hard_flatters": {"OccasionFit": ["bridal"]}})

    def test_lookup_groom_role_returns_groom_rules(self):
        priority = {
            "bride": {"hard_flatters": {"a": 1}},
            "groom": {"hard_flatters": {"b": 2}},
        }
        self.assertEqual(
            lookup_bridal_priority_rules("groom", priority),
            {"hard_flatters": {"b": 2}},
        )

    def test_lookup_attendee_falls_back_to_guest(self):
        # ``attendee`` is the user-facing default; falls back to guest rules.
        priority = {
            "guest": {"hard_avoid": {"OccasionFit": ["bridal"]}},
        }
        result = lookup_bridal_priority_rules("attendee", priority)
        self.assertEqual(result, {"hard_avoid": {"OccasionFit": ["bridal"]}})

    def test_lookup_attendee_without_guest_block_returns_none(self):
        priority = {"bride": {"x": 1}}  # no guest block
        self.assertIsNone(lookup_bridal_priority_rules("attendee", priority))

    def test_lookup_unknown_role_returns_none(self):
        priority = {"bride": {"x": 1}, "guest": {"y": 2}}
        self.assertIsNone(
            lookup_bridal_priority_rules("photographer", priority)
        )

    def test_lookup_no_priority_block_returns_none(self):
        self.assertIsNone(lookup_bridal_priority_rules("bride", None))
        self.assertIsNone(lookup_bridal_priority_rules("bride", {}))

    def test_lookup_no_role_returns_none(self):
        priority = {"bride": {"x": 1}}
        self.assertIsNone(lookup_bridal_priority_rules(None, priority))
        self.assertIsNone(lookup_bridal_priority_rules("", priority))

    def test_lookup_case_insensitive_role(self):
        priority = {"bride": {"x": 1}}
        self.assertEqual(
            lookup_bridal_priority_rules("BRIDE", priority),
            {"x": 1},
        )

    def test_canonical_set(self):
        self.assertEqual(
            set(BRIDAL_ROLE_VALUES),
            {"bride", "groom", "guest", "attendee"},
        )


if __name__ == "__main__":
    unittest.main()
