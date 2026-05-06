"""Tests for empty-intersection relaxation (Phase 4.7c).

Includes verbatim re-runs of spec §6.2 (soft-relax saves it) and §6.3
(hard widening), plus coverage of the soft-drop ordering, hard-widen
ordering, the avoid-preservation invariant, and the omit terminal."""
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

from agentic_application.composition.reduction import AttributeContribution
from agentic_application.composition.relaxation import (
    DEFAULT_HARD_WIDEN_ORDER,
    DEFAULT_SOFT_DROP_ORDER,
    ClassifiedContribution,
    RelaxedReduction,
    reduce_with_relaxation,
)


def hard(kind: str, source: str, flatters: tuple[str, ...], avoid: tuple[str, ...]) -> ClassifiedContribution:
    return ClassifiedContribution(
        contribution=AttributeContribution(source=source, flatters=flatters, avoid=avoid),
        source_kind=kind,
        tier="hard",
    )


def soft(kind: str, source: str, flatters: tuple[str, ...], avoid: tuple[str, ...]) -> ClassifiedContribution:
    return ClassifiedContribution(
        contribution=AttributeContribution(source=source, flatters=flatters, avoid=avoid),
        source_kind=kind,
        tier="soft",
    )


class CleanPathTests(unittest.TestCase):
    def test_naive_reduction_clean_when_intersection_nonempty(self):
        out = reduce_with_relaxation(
            "FabricDrape",
            [
                hard("body_shape", "Hourglass", ("fluid", "soft_structured"), ()),
                hard("frame_structure", "Light/Narrow", ("fluid", "soft_structured"), ()),
            ],
        )
        self.assertEqual(out.outcome.status, "clean")
        self.assertEqual(out.outcome.dropped_softs, ())
        self.assertEqual(out.outcome.widened_hards, ())
        self.assertEqual(out.reduction.final_flatters, ("fluid", "soft_structured"))


class SoftDropTests(unittest.TestCase):
    def test_section_6_2_soft_relax_saves_it(self):
        """Spec §6.2 EmbellishmentLevel: occasion (hard) and archetype
        (soft) intersect to ∅. Drop archetype → final = {minimal, subtle}."""
        out = reduce_with_relaxation(
            "EmbellishmentLevel",
            [
                hard(
                    "occasion_signal",
                    "daily_office_mnc",
                    ("minimal", "subtle"),
                    ("maximalist",),
                ),
                soft(
                    "archetype",
                    "glamorous",
                    ("moderate", "statement"),
                    ("minimal",),
                ),
            ],
        )
        self.assertEqual(out.outcome.status, "soft_relaxed")
        self.assertEqual(out.outcome.dropped_softs, ("archetype",))
        self.assertEqual(out.outcome.widened_hards, ())
        # archetype's avoid (minimal) goes too because the WHOLE soft
        # contributor was dropped — so minimal survives in the final.
        self.assertIn("minimal", out.reduction.final_flatters)

    def test_soft_drops_skip_kinds_with_no_contribution(self):
        # No time_of_day contribution exists — relaxation should skip it
        # silently and try archetype next.
        out = reduce_with_relaxation(
            "EmbellishmentLevel",
            [
                hard(
                    "occasion_signal",
                    "daily_office_mnc",
                    ("minimal", "subtle"),
                    (),
                ),
                soft("archetype", "glamorous", ("moderate", "statement"), ()),
            ],
        )
        self.assertEqual(out.outcome.status, "soft_relaxed")
        # time_of_day should NOT appear in dropped_softs (we never had one).
        self.assertEqual(out.outcome.dropped_softs, ("archetype",))

    def test_soft_drop_order_is_ascending_precedence(self):
        # Both time_of_day AND archetype clash with hard occasion.
        # time_of_day should be tried FIRST per §4.3.
        out = reduce_with_relaxation(
            "ColorValue",
            [
                hard(
                    "occasion_signal",
                    "daily_office_mnc",
                    ("light", "mid"),
                    (),
                ),
                soft("time_of_day", "evening", ("dark",), ()),
                soft("archetype", "glamorous", ("dark", "very_dark"), ()),
            ],
        )
        # time_of_day dropped first → still empty → archetype dropped.
        self.assertEqual(out.outcome.status, "soft_relaxed")
        self.assertEqual(out.outcome.dropped_softs, ("time_of_day", "archetype"))
        self.assertEqual(out.reduction.final_flatters, ("light", "mid"))

    def test_default_soft_order_matches_spec(self):
        self.assertEqual(
            DEFAULT_SOFT_DROP_ORDER,
            ("time_of_day", "archetype", "risk_tolerance", "style_goal", "weather_color"),
        )


class HardWidenTests(unittest.TestCase):
    def test_section_6_3_resolves_via_soft_drop_not_widen(self):
        """Spec §6.3 NecklineType: archetype clashes with body+occasion.
        Drop archetype (soft) → {v_neck, scoop}. Widening NOT needed."""
        out = reduce_with_relaxation(
            "NecklineType",
            [
                hard(
                    "body_shape",
                    "Inverted Triangle",
                    ("v_neck", "scoop", "soft_v"),
                    ("boat", "off_shoulder", "square"),
                ),
                soft(
                    "archetype",
                    "ultra_conservative",
                    ("crew", "mock", "high"),
                    ("v_neck", "scoop", "deep_v"),
                ),
                hard(
                    "occasion_signal",
                    "cocktail_event",
                    ("v_neck", "scoop", "halter"),
                    ("crew", "mock", "high"),
                ),
            ],
        )
        # archetype.avoid (v_neck, scoop, deep_v) gets dropped along with
        # the soft contributor itself.
        self.assertEqual(out.outcome.status, "soft_relaxed")
        self.assertEqual(out.outcome.dropped_softs, ("archetype",))
        self.assertEqual(out.outcome.widened_hards, ())
        self.assertEqual(out.reduction.final_flatters, ("v_neck", "scoop"))

    def test_hard_widen_when_softs_exhausted(self):
        # Two hards intersect to empty, no softs to drop. Widening
        # weather_fabric (the weakest hard per the default order) zeros
        # its flatters and lets the other hard's flatters through.
        out = reduce_with_relaxation(
            "FabricDrape",
            [
                hard("body_shape", "Hourglass", ("fluid", "soft_structured"), ()),
                hard("weather_fabric", "cool_dry", ("rigid",), ()),
            ],
        )
        self.assertEqual(out.outcome.status, "hard_widened")
        self.assertEqual(out.outcome.dropped_softs, ())
        self.assertEqual(out.outcome.widened_hards, ("weather_fabric",))
        # weather_fabric's flatters dropped → body_shape's flatters
        # become the final.
        self.assertEqual(
            out.reduction.final_flatters,
            ("fluid", "soft_structured"),
        )

    def test_hard_widen_preserves_avoids(self):
        # weather_fabric.avoid is preserved across widening: even after
        # zeroing its flatters, sleek must NOT slip into the final set.
        out = reduce_with_relaxation(
            "FabricDrape",
            [
                hard("body_shape", "Apple", ("fluid", "sleek"), ()),
                hard("weather_fabric", "cool_dry", ("rigid",), ("sleek",)),
            ],
        )
        self.assertEqual(out.outcome.status, "hard_widened")
        self.assertEqual(out.outcome.widened_hards, ("weather_fabric",))
        self.assertNotIn("sleek", out.reduction.final_flatters)
        self.assertIn("sleek", out.reduction.final_avoid)

    def test_default_hard_order_matches_spec(self):
        self.assertEqual(
            DEFAULT_HARD_WIDEN_ORDER,
            (
                "weather_fabric",
                "formality_hint",
                "occasion_signal",
                "seasonal_color_group",
                "frame_structure",
                "body_shape",
            ),
        )


class OmittedTerminalTests(unittest.TestCase):
    def test_omit_when_all_phases_exhaust(self):
        # Two hards with disjoint flatters AND mutual avoids — even
        # widening one of them leaves the other's flatters blocked by the
        # widened source's avoid (which we preserve).
        out = reduce_with_relaxation(
            "PatternType",
            [
                hard("body_shape", "Pear", ("solid",), ("floral",)),
                hard(
                    "occasion_signal",
                    "diwali",
                    ("floral",),
                    ("solid",),
                ),
            ],
        )
        # Step 1: naive reduction — solid ∩ floral = ∅.
        # Step 2: no softs to drop.
        # Step 3a: widen weather_fabric → no contribution, skip.
        # Step 3b: widen formality_hint → no contribution, skip.
        # Step 3c: widen occasion_signal → flatters zeroed, avoid (solid)
        #          preserved → only contributor with flatters is body_shape
        #          (solid), but solid is in avoid → final empty.
        # Step 3d: widen seasonal_color_group → skip.
        # Step 3e: widen frame_structure → skip.
        # Step 3f: widen body_shape → flatters zeroed, both avoids
        #          preserved → no opinionated source → final empty.
        # Result: omitted.
        self.assertEqual(out.outcome.status, "omitted")
        self.assertEqual(out.reduction.final_flatters, ())
        # Provenance still tracks what was attempted.
        self.assertIn("occasion_signal", out.outcome.widened_hards)
        self.assertIn("body_shape", out.outcome.widened_hards)


class ProvenanceTests(unittest.TestCase):
    def test_returned_object_is_frozen(self):
        out = reduce_with_relaxation("FabricDrape", [])
        self.assertIsInstance(out, RelaxedReduction)
        with self.assertRaises(Exception):
            out.outcome = None  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
