"""Tests for _apply_full_alternative_rotation and
_apply_increase_boldness (May 8 2026).

Both helpers are post-architect transforms that adjust the engine's
clean plan based on follow-up intent. They run in
_handle_planner_pipeline alongside _apply_change_color_avoidance.
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

from agentic_application.orchestrator import (
    _apply_full_alternative_rotation,
    _apply_increase_boldness,
)
from agentic_application.schemas import (
    DirectionSpec,
    QuerySpec,
    RecommendationPlan,
)


def _plan(direction_type: str, hard_attrs: dict | None = None) -> RecommendationPlan:
    return RecommendationPlan(
        retrieval_count=5,
        directions=[
            DirectionSpec(
                direction_id="A",
                direction_type=direction_type,
                label="L",
                queries=[
                    QuerySpec(
                        query_id="A1", role="top",
                        hard_filters={},
                        query_document="t",
                        hard_attrs=dict(hard_attrs or {}),
                    ),
                ],
            ),
        ],
    )


class FullAlternativeRotationTests(unittest.TestCase):

    def test_noop_for_other_intent(self):
        plan = _plan("paired")
        _apply_full_alternative_rotation(plan, "more_options")
        self.assertEqual(plan.directions[0].direction_type, "paired")

    def test_noop_on_empty_intent(self):
        plan = _plan("paired")
        _apply_full_alternative_rotation(plan, "")
        self.assertEqual(plan.directions[0].direction_type, "paired")

    def test_paired_rotates_to_three_piece(self):
        plan = _plan("paired")
        _apply_full_alternative_rotation(plan, "full_alternative")
        self.assertEqual(plan.directions[0].direction_type, "three_piece")

    def test_three_piece_rotates_to_paired(self):
        plan = _plan("three_piece")
        _apply_full_alternative_rotation(plan, "full_alternative")
        self.assertEqual(plan.directions[0].direction_type, "paired")

    def test_complete_rotates_to_paired(self):
        plan = _plan("complete")
        _apply_full_alternative_rotation(plan, "full_alternative")
        self.assertEqual(plan.directions[0].direction_type, "paired")

    def test_unknown_direction_type_left_unchanged(self):
        # Defensive — if engine ever emits a direction_type outside
        # the rotation map, we leave it alone rather than guessing.
        plan = _plan("custom_unknown_type")
        _apply_full_alternative_rotation(plan, "full_alternative")
        self.assertEqual(plan.directions[0].direction_type, "custom_unknown_type")

    def test_applies_to_all_directions(self):
        plan = RecommendationPlan(
            retrieval_count=5,
            directions=[
                DirectionSpec(
                    direction_id="A", direction_type="paired", label="A",
                    queries=[QuerySpec(query_id="A1", role="top", hard_filters={}, query_document="t")],
                ),
                DirectionSpec(
                    direction_id="B", direction_type="three_piece", label="B",
                    queries=[QuerySpec(query_id="B1", role="top", hard_filters={}, query_document="t")],
                ),
            ],
        )
        _apply_full_alternative_rotation(plan, "full_alternative")
        self.assertEqual(plan.directions[0].direction_type, "three_piece")
        self.assertEqual(plan.directions[1].direction_type, "paired")


class IncreaseBoldnessTests(unittest.TestCase):

    def test_noop_for_other_intent(self):
        plan = _plan("paired", hard_attrs={"ContrastLevel": ["medium"]})
        _apply_increase_boldness(plan, "more_options")
        self.assertEqual(plan.directions[0].queries[0].hard_attrs["ContrastLevel"], ["medium"])

    def test_contrast_level_bumps_up_one_notch(self):
        plan = _plan("paired", hard_attrs={"ContrastLevel": ["low", "medium"]})
        _apply_increase_boldness(plan, "increase_boldness")
        self.assertEqual(
            plan.directions[0].queries[0].hard_attrs["ContrastLevel"],
            ["medium", "high"],
        )

    def test_contrast_saturated_at_very_high(self):
        plan = _plan("paired", hard_attrs={"ContrastLevel": ["very_high"]})
        _apply_increase_boldness(plan, "increase_boldness")
        self.assertEqual(
            plan.directions[0].queries[0].hard_attrs["ContrastLevel"],
            ["very_high"],
        )

    def test_color_saturation_bumps_up(self):
        plan = _plan("paired", hard_attrs={"ColorSaturation": ["muted", "low"]})
        _apply_increase_boldness(plan, "increase_boldness")
        self.assertEqual(
            plan.directions[0].queries[0].hard_attrs["ColorSaturation"],
            ["low", "medium"],
        )

    def test_embellishment_added_when_absent(self):
        plan = _plan("paired", hard_attrs={"ContrastLevel": ["medium"]})
        _apply_increase_boldness(plan, "increase_boldness")
        ha = plan.directions[0].queries[0].hard_attrs
        self.assertIn("EmbellishmentLevel", ha)
        self.assertEqual(ha["EmbellishmentLevel"], ["moderate", "heavy", "statement"])

    def test_embellishment_preserved_when_engine_already_set(self):
        # Engine knows the occasion; if it emitted EmbellishmentLevel
        # already, respect that — don't blast it with the boldness preset.
        plan = _plan("paired", hard_attrs={"EmbellishmentLevel": ["minimal"]})
        _apply_increase_boldness(plan, "increase_boldness")
        self.assertEqual(
            plan.directions[0].queries[0].hard_attrs["EmbellishmentLevel"],
            ["minimal"],
        )

    def test_unknown_values_pass_through(self):
        # Defensive — out-of-vocab ContrastLevel values get left alone
        # (the shift map default is identity).
        plan = _plan("paired", hard_attrs={"ContrastLevel": ["custom_unknown"]})
        _apply_increase_boldness(plan, "increase_boldness")
        self.assertEqual(
            plan.directions[0].queries[0].hard_attrs["ContrastLevel"],
            ["custom_unknown"],
        )


if __name__ == "__main__":
    unittest.main()
