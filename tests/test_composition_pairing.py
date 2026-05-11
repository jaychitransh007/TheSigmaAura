"""Tests for the composer engine's pairing-rule evaluator (Phase 5b).

Covers each of the 8 evaluators dispatched by ``evaluate_constraint``,
the public helpers (``is_statement``, ``bridal_exception_active``), the
top-level ``score_tuple`` orchestration, and the four worked examples
in ``docs/composer_semantics.md`` §9.

Tests use the real ``load_style_graph()`` since the YAMLs are stable;
items are constructed minimally — only the fields the rule under test
examines, defaults for the rest.
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

from agentic_application.composition.pairing import (
    ALL_CATEGORIES,
    BASE_SCORE,
    HARD_CATEGORIES,
    SOFT_CATEGORIES,
    SOFT_PENALTY,
    Item,
    TupleContext,
    TupleScore,
    Violation,
    bridal_exception_active,
    evaluate_constraint,
    is_statement,
    score_tuple,
)
from agentic_application.composition.yaml_loader import load_style_graph


# ─────────────────────────────────────────────────────────────────────────
# Test fixtures
# ─────────────────────────────────────────────────────────────────────────


def _graph():
    """Load the canonical style graph once per test (cached internally)."""
    return load_style_graph()


def _smart_casual_top(**overrides) -> Item:
    """A clean, neutral top — passes every hard rule by default. Tests
    that exercise specific failure modes override one field at a time."""
    base = dict(
        item_id="T1",
        slot="top",
        formality="smart_casual",
        dominant_color="navy",
        contrast_level="medium",
        pattern_type="solid",
        pattern_scale="micro",
        embellishment_level="minimal",
        color_saturation="medium",
        fit_type="tailored",
        fabric_drape="crisp",
        fabric_texture="smooth",
        fabric_weight="light",
        cultural_register="western",
        subtype="shirt",
    )
    base.update(overrides)
    return Item(**base)


def _smart_casual_bottom(**overrides) -> Item:
    base = dict(
        item_id="B1",
        slot="bottom",
        formality="smart_casual",
        dominant_color="cream",
        contrast_level="medium",
        pattern_type="solid",
        pattern_scale="micro",
        embellishment_level="minimal",
        color_saturation="medium",
        fit_type="regular",
        fabric_drape="soft_structured",
        fabric_texture="smooth",
        fabric_weight="light",
        cultural_register="western",
        subtype="trouser",
    )
    base.update(overrides)
    return Item(**base)


def _structured_outerwear(**overrides) -> Item:
    base = dict(
        item_id="OW1",
        slot="outerwear",
        formality="smart_casual",
        dominant_color="charcoal",
        contrast_level="medium",
        pattern_type="solid",
        pattern_scale="micro",
        embellishment_level="minimal",
        color_saturation="medium",
        fit_type="tailored",
        fabric_drape="crisp",
        fabric_texture="smooth",
        fabric_weight="medium",
        cultural_register="western",
        subtype="blazer",
    )
    base.update(overrides)
    return Item(**base)


def _ctx(**overrides) -> TupleContext:
    base = dict(
        formality_hint="smart_casual",
        occasion_signal="daily_office_mnc",
        palette_anchors=("navy", "cream", "charcoal"),
        body_shape="Hourglass",
        intent="recommendation_request",
    )
    base.update(overrides)
    return TupleContext(**base)


# ─────────────────────────────────────────────────────────────────────────
# is_statement
# ─────────────────────────────────────────────────────────────────────────


class IsStatementTests(unittest.TestCase):

    def test_minimal_embellishment_is_not_statement(self):
        self.assertFalse(is_statement(_smart_casual_top()))

    def test_moderate_embellishment_is_statement(self):
        self.assertTrue(is_statement(_smart_casual_top(embellishment_level="moderate")))

    def test_heavy_embellishment_is_statement(self):
        self.assertTrue(is_statement(_smart_casual_top(embellishment_level="heavy")))

    def test_statement_embellishment_is_statement(self):
        self.assertTrue(is_statement(_smart_casual_top(embellishment_level="statement")))

    def test_large_pattern_scale_is_statement(self):
        self.assertTrue(
            is_statement(_smart_casual_top(pattern_type="floral", pattern_scale="large"))
        )

    def test_oversized_pattern_scale_is_statement(self):
        self.assertTrue(is_statement(_smart_casual_top(pattern_scale="oversized")))

    def test_micro_pattern_scale_is_not_statement(self):
        self.assertFalse(
            is_statement(_smart_casual_top(pattern_type="floral", pattern_scale="micro"))
        )

    def test_very_high_color_saturation_is_statement(self):
        self.assertTrue(is_statement(_smart_casual_top(color_saturation="very_high")))

    def test_animal_pattern_medium_scale_is_statement(self):
        self.assertTrue(
            is_statement(
                _smart_casual_top(pattern_type="animal", pattern_scale="medium")
            )
        )

    def test_animal_pattern_micro_scale_is_not_statement(self):
        # animal+micro doesn't trigger because pattern_scale clause requires medium+
        self.assertFalse(
            is_statement(_smart_casual_top(pattern_type="animal", pattern_scale="micro"))
        )

    def test_floral_medium_scale_alone_is_not_statement(self):
        # floral isn't in {animal, ethnic, abstract}, so medium scale isn't enough.
        self.assertFalse(
            is_statement(_smart_casual_top(pattern_type="floral", pattern_scale="medium"))
        )


# ─────────────────────────────────────────────────────────────────────────
# bridal_exception_active
# ─────────────────────────────────────────────────────────────────────────


class BridalExceptionActiveTests(unittest.TestCase):

    def test_ceremonial_plus_wedding_ceremony_active(self):
        self.assertTrue(
            bridal_exception_active(
                _ctx(formality_hint="ceremonial", occasion_signal="wedding_ceremony"),
                _graph(),
            )
        )

    def test_ceremonial_plus_sangeet_active(self):
        self.assertTrue(
            bridal_exception_active(
                _ctx(formality_hint="ceremonial", occasion_signal="sangeet"),
                _graph(),
            )
        )

    def test_ceremonial_alone_not_active(self):
        # ceremonial formality alone doesn't trigger if occasion isn't bridal.
        self.assertFalse(
            bridal_exception_active(
                _ctx(formality_hint="ceremonial", occasion_signal="diwali"),
                _graph(),
            )
        )

    def test_bridal_occasion_without_ceremonial_not_active(self):
        # Hypothetical: someone tagging "wedding_ceremony" at smart_casual.
        # Defensive guard — we require both signals.
        self.assertFalse(
            bridal_exception_active(
                _ctx(formality_hint="smart_casual", occasion_signal="wedding_ceremony"),
                _graph(),
            )
        )

    def test_unknown_occasion_not_active(self):
        self.assertFalse(
            bridal_exception_active(
                _ctx(formality_hint="ceremonial", occasion_signal="totally_made_up"),
                _graph(),
            )
        )


# ─────────────────────────────────────────────────────────────────────────
# evaluate_constraint dispatch + unknown-category guard
# ─────────────────────────────────────────────────────────────────────────


class EvaluateConstraintTests(unittest.TestCase):

    def test_unknown_category_raises(self):
        with self.assertRaises(ValueError):
            evaluate_constraint("not_a_real_category", (_smart_casual_top(),), _ctx(), _graph())

    def test_all_known_categories_dispatch(self):
        # Sanity: every category in ALL_CATEGORIES is wired in the dispatch table.
        items = (_smart_casual_top(), _smart_casual_bottom())
        for cat in ALL_CATEGORIES:
            # Should not raise.
            evaluate_constraint(cat, items, _ctx(), _graph())


# ─────────────────────────────────────────────────────────────────────────
# Per-category evaluators
# ─────────────────────────────────────────────────────────────────────────


class FormalityAlignmentTests(unittest.TestCase):

    def test_same_formality_passes(self):
        violations = evaluate_constraint(
            "formality_alignment",
            (_smart_casual_top(), _smart_casual_bottom()),
            _ctx(),
            _graph(),
        )
        self.assertEqual(violations, ())

    def test_one_step_apart_passes(self):
        violations = evaluate_constraint(
            "formality_alignment",
            (
                _smart_casual_top(formality="smart_casual"),
                _smart_casual_bottom(formality="semi_formal"),
            ),
            _ctx(),
            _graph(),
        )
        self.assertEqual(violations, ())

    def test_two_steps_apart_violates(self):
        violations = evaluate_constraint(
            "formality_alignment",
            (
                _smart_casual_top(formality="casual"),
                _smart_casual_bottom(formality="formal"),
            ),
            _ctx(),
            _graph(),
        )
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule, "formality_within_one_step")
        self.assertTrue(violations[0].is_hard)

    def test_ceremonial_plus_casual_violates(self):
        violations = evaluate_constraint(
            "formality_alignment",
            (
                _smart_casual_top(formality="ceremonial"),
                _smart_casual_bottom(formality="casual"),
            ),
            _ctx(),
            _graph(),
        )
        self.assertEqual(len(violations), 1)

    def test_missing_formality_skipped(self):
        # Defensive: empty formality means "no opinion"; rule abstains.
        violations = evaluate_constraint(
            "formality_alignment",
            (_smart_casual_top(formality=""), _smart_casual_bottom()),
            _ctx(),
            _graph(),
        )
        self.assertEqual(violations, ())


class ColorStoryTests(unittest.TestCase):

    def test_two_colors_passes_max_dominant(self):
        violations = evaluate_constraint(
            "color_story",
            (_smart_casual_top(), _smart_casual_bottom()),
            _ctx(),
            _graph(),
        )
        self.assertEqual(violations, ())

    def test_four_distinct_colors_violates_max_dominant(self):
        items = (
            _smart_casual_top(dominant_color="navy"),
            _smart_casual_bottom(dominant_color="cream"),
            _structured_outerwear(dominant_color="rust"),
            Item(item_id="X1", slot="top", formality="smart_casual",
                 dominant_color="emerald", contrast_level="medium",
                 pattern_type="solid"),
        )
        violations = evaluate_constraint("color_story", items, _ctx(), _graph())
        rules_hit = {v.rule for v in violations}
        self.assertIn("max_dominant_colors", rules_hit)

    # ─────────────────────────────────────────────────────────────────────
    # metallic_neutral_exception (Phase 4.3 / PR 4c.3). Items whose
    # dominant_color is a metallic-neutral (gold / champagne / antique
    # gold / bronze / etc.) OR whose fabric_texture is "metallic" are
    # excluded from the max_dominant_colors count — they function as
    # neutral support rather than competing dominant hues. Critical for
    # Indian festive / bridal outfits where zari, gota patti, and
    # antique-gold embroidery would otherwise blow the 3-color cap.
    # ─────────────────────────────────────────────────────────────────────

    def test_metallic_neutral_color_excluded_from_dominant_count(self):
        # Without exception: 4 distinct colors → would violate.
        # With exception: gold is metallic-neutral → excluded → 3 colors
        # which is exactly the cap → no violation.
        items = (
            _smart_casual_top(dominant_color="navy"),
            _smart_casual_bottom(dominant_color="cream"),
            _structured_outerwear(dominant_color="rust"),
            Item(item_id="DUP", slot="top", formality="smart_casual",
                 dominant_color="gold", contrast_level="medium",
                 pattern_type="solid"),
        )
        violations = evaluate_constraint("color_story", items, _ctx(), _graph())
        self.assertFalse(any(v.rule == "max_dominant_colors" for v in violations))

    def test_metallic_fabric_texture_excluded_from_dominant_count(self):
        # Item has non-metallic-neutral color (red) but its fabric_texture
        # is "metallic" — engine treats the surface as the dominant
        # signal and excludes the slot from the color count.
        items = (
            _smart_casual_top(dominant_color="navy"),
            _smart_casual_bottom(dominant_color="cream"),
            _structured_outerwear(dominant_color="rust"),
            Item(item_id="DUP", slot="top", formality="smart_casual",
                 dominant_color="red", contrast_level="medium",
                 pattern_type="solid", fabric_texture="metallic"),
        )
        violations = evaluate_constraint("color_story", items, _ctx(), _graph())
        self.assertFalse(any(v.rule == "max_dominant_colors" for v in violations))

    def test_metallic_neutral_exception_does_not_save_truly_over_cap(self):
        # 5 distinct non-metallic colors → still violates even after the
        # exception excludes a metallic slot. Exception is a budget
        # rebate, not an unbounded override.
        items = (
            _smart_casual_top(dominant_color="navy"),
            _smart_casual_bottom(dominant_color="cream"),
            _structured_outerwear(dominant_color="rust"),
            Item(item_id="X1", slot="top", formality="smart_casual",
                 dominant_color="emerald", contrast_level="medium",
                 pattern_type="solid"),
            Item(item_id="X2", slot="bottom", formality="smart_casual",
                 dominant_color="violet", contrast_level="medium",
                 pattern_type="solid"),
            Item(item_id="DUP", slot="top", formality="smart_casual",
                 dominant_color="gold", contrast_level="medium",
                 pattern_type="solid"),
        )
        violations = evaluate_constraint("color_story", items, _ctx(), _graph())
        rules_hit = {v.rule for v in violations}
        self.assertIn("max_dominant_colors", rules_hit)

    def test_two_metallic_neutrals_both_excluded(self):
        # Both gold + champagne are metallic-neutrals — both excluded —
        # 2 dominant colors remain → no violation.
        items = (
            _smart_casual_top(dominant_color="navy"),
            _smart_casual_bottom(dominant_color="cream"),
            Item(item_id="DUP1", slot="top", formality="smart_casual",
                 dominant_color="gold", contrast_level="medium",
                 pattern_type="solid"),
            Item(item_id="DUP2", slot="top", formality="smart_casual",
                 dominant_color="champagne", contrast_level="medium",
                 pattern_type="solid"),
        )
        violations = evaluate_constraint("color_story", items, _ctx(), _graph())
        self.assertFalse(any(v.rule == "max_dominant_colors" for v in violations))

    def test_no_palette_anchor_violates(self):
        # User's anchors = (navy, cream); items use neither.
        items = (
            _smart_casual_top(dominant_color="emerald"),
            _smart_casual_bottom(dominant_color="rust"),
        )
        violations = evaluate_constraint(
            "color_story", items, _ctx(palette_anchors=("navy", "cream")), _graph()
        )
        self.assertTrue(any(v.rule == "palette_anchor_required" for v in violations))

    def test_palette_anchor_present_in_at_least_one_slot_passes(self):
        items = (
            _smart_casual_top(dominant_color="navy"),  # in anchors
            _smart_casual_bottom(dominant_color="rust"),  # not in anchors
        )
        violations = evaluate_constraint(
            "color_story", items, _ctx(palette_anchors=("navy",)), _graph()
        )
        self.assertFalse(any(v.rule == "palette_anchor_required" for v in violations))

    def test_no_anchors_in_ctx_skips_palette_check(self):
        # When caller provides no palette_anchors, the rule abstains.
        items = (
            _smart_casual_top(dominant_color="emerald"),
            _smart_casual_bottom(dominant_color="rust"),
        )
        violations = evaluate_constraint(
            "color_story", items, _ctx(palette_anchors=()), _graph()
        )
        self.assertFalse(any(v.rule == "palette_anchor_required" for v in violations))

    def test_palette_anchor_skipped_when_any_item_lacks_color(self):
        # Skip-if-empty: an item with no dominant_color might itself be
        # an anchor color; the rule abstains rather than reporting a
        # false-positive violation.
        items = (
            _smart_casual_top(dominant_color="emerald"),  # not an anchor
            _smart_casual_bottom(dominant_color=""),       # color unknown
        )
        violations = evaluate_constraint(
            "color_story", items, _ctx(palette_anchors=("navy", "cream")), _graph()
        )
        self.assertFalse(any(v.rule == "palette_anchor_required" for v in violations))

    def test_high_plus_low_contrast_violates(self):
        items = (
            _smart_casual_top(contrast_level="high"),
            _smart_casual_bottom(contrast_level="low"),
        )
        violations = evaluate_constraint("color_story", items, _ctx(), _graph())
        self.assertTrue(any(v.rule == "contrast_alignment" for v in violations))


class PatternMixingTests(unittest.TestCase):

    def test_zero_patterns_passes(self):
        violations = evaluate_constraint(
            "pattern_mixing",
            (_smart_casual_top(pattern_type="solid"), _smart_casual_bottom(pattern_type="solid")),
            _ctx(),
            _graph(),
        )
        self.assertEqual(violations, ())

    def test_one_pattern_passes(self):
        violations = evaluate_constraint(
            "pattern_mixing",
            (
                _smart_casual_top(pattern_type="floral", pattern_scale="small"),
                _smart_casual_bottom(pattern_type="solid"),
            ),
            _ctx(),
            _graph(),
        )
        self.assertEqual(violations, ())

    def test_two_patterns_compatible_scales_with_same_color_passes(self):
        items = (
            _smart_casual_top(pattern_type="floral", pattern_scale="micro", dominant_color="navy"),
            _smart_casual_bottom(pattern_type="checks", pattern_scale="medium", dominant_color="navy"),
        )
        violations = evaluate_constraint("pattern_mixing", items, _ctx(), _graph())
        self.assertEqual(violations, ())

    def test_two_large_scale_patterns_violate(self):
        # large+large is not in the YAML's compatibility_matrix.
        items = (
            _smart_casual_top(pattern_type="floral", pattern_scale="large", dominant_color="navy"),
            _smart_casual_bottom(pattern_type="checks", pattern_scale="large", dominant_color="navy"),
        )
        violations = evaluate_constraint("pattern_mixing", items, _ctx(), _graph())
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule, "two_patterns_scale")

    def test_two_patterns_no_color_or_contrast_link_violates(self):
        items = (
            _smart_casual_top(
                pattern_type="floral", pattern_scale="micro",
                dominant_color="emerald", contrast_level="high",
            ),
            _smart_casual_bottom(
                pattern_type="checks", pattern_scale="medium",
                dominant_color="rust", contrast_level="low",
            ),
        )
        violations = evaluate_constraint("pattern_mixing", items, _ctx(), _graph())
        self.assertTrue(any(v.rule == "two_patterns_color_family" for v in violations))

    def test_two_patterns_color_family_skipped_when_metadata_missing(self):
        # Skip-if-empty: when an item is missing dominant_color OR
        # contrast_level, we can't confirm there's no link.
        items = (
            _smart_casual_top(
                pattern_type="floral", pattern_scale="micro",
                dominant_color="",  # missing
                contrast_level="high",
            ),
            _smart_casual_bottom(
                pattern_type="checks", pattern_scale="medium",
                dominant_color="rust", contrast_level="low",
            ),
        )
        violations = evaluate_constraint("pattern_mixing", items, _ctx(), _graph())
        self.assertFalse(any(v.rule == "two_patterns_color_family" for v in violations))

    def test_three_patterns_violates(self):
        items = (
            _smart_casual_top(pattern_type="floral", pattern_scale="micro"),
            _smart_casual_bottom(pattern_type="checks", pattern_scale="small"),
            _structured_outerwear(pattern_type="abstract", pattern_scale="small"),
        )
        violations = evaluate_constraint("pattern_mixing", items, _ctx(), _graph())
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule, "three_patterns")


class ScaleBalanceTests(unittest.TestCase):

    def test_zero_statement_passes(self):
        violations = evaluate_constraint(
            "scale_balance",
            (_smart_casual_top(), _smart_casual_bottom()),
            _ctx(),
            _graph(),
        )
        self.assertEqual(violations, ())

    def test_one_statement_passes(self):
        violations = evaluate_constraint(
            "scale_balance",
            (
                _smart_casual_top(embellishment_level="heavy"),
                _smart_casual_bottom(embellishment_level="minimal"),
            ),
            _ctx(),
            _graph(),
        )
        self.assertEqual(violations, ())

    def test_two_statement_violates(self):
        violations = evaluate_constraint(
            "scale_balance",
            (
                _smart_casual_top(embellishment_level="heavy"),
                _smart_casual_bottom(embellishment_level="statement"),
            ),
            _ctx(),
            _graph(),
        )
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule, "one_statement_per_outfit")

    def test_two_statement_passes_under_bridal_exception(self):
        violations = evaluate_constraint(
            "scale_balance",
            (
                _smart_casual_top(formality="ceremonial", embellishment_level="heavy"),
                _smart_casual_bottom(formality="ceremonial", embellishment_level="statement"),
            ),
            _ctx(formality_hint="ceremonial", occasion_signal="wedding_ceremony"),
            _graph(),
        )
        self.assertEqual(violations, ())

    # ─────────────────────────────────────────────────────────────────────
    # distributed_statement_exception (Phase 4.3 / PR 4c.1a — pairing engine
    # matcher for the stylist's "coordinated multi-statement Indianwear"
    # carve-out). Allows two statement slots iff all items share a single
    # color_temperature family AND no item is individually heavy/statement
    # embellishment.
    # ─────────────────────────────────────────────────────────────────────

    def test_distributed_statement_exception_warm_family_moderate_passes(self):
        """Two moderate-embellishment items sharing warm color_temperature
        — the coordinated-Indianwear case the stylist flagged."""
        violations = evaluate_constraint(
            "scale_balance",
            (
                _smart_casual_top(
                    embellishment_level="moderate", color_temperature="warm",
                ),
                _smart_casual_bottom(
                    embellishment_level="moderate", color_temperature="warm",
                ),
            ),
            _ctx(),
            _graph(),
        )
        self.assertEqual(violations, ())

    def test_distributed_statement_exception_blocked_by_heavy_item(self):
        """Even with same color_temperature, a single heavy/statement item
        makes the exception ineligible — at least one zone is too loud."""
        violations = evaluate_constraint(
            "scale_balance",
            (
                _smart_casual_top(
                    embellishment_level="heavy", color_temperature="warm",
                ),
                _smart_casual_bottom(
                    embellishment_level="moderate", color_temperature="warm",
                ),
            ),
            _ctx(),
            _graph(),
        )
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule, "one_statement_per_outfit")

    def test_distributed_statement_exception_blocked_by_mixed_temperatures(self):
        """Statement items in different color_temperature families compete
        rather than coordinate — exception doesn't apply."""
        violations = evaluate_constraint(
            "scale_balance",
            (
                _smart_casual_top(
                    embellishment_level="moderate", color_temperature="warm",
                ),
                _smart_casual_bottom(
                    embellishment_level="moderate", color_temperature="cool",
                ),
            ),
            _ctx(),
            _graph(),
        )
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule, "one_statement_per_outfit")

    def test_distributed_statement_exception_skipped_on_missing_color_temp(self):
        """Conservative: if any item lacks color_temperature, exception
        can't be confirmed — fall through to the base rule."""
        violations = evaluate_constraint(
            "scale_balance",
            (
                _smart_casual_top(
                    embellishment_level="moderate", color_temperature="",
                ),
                _smart_casual_bottom(
                    embellishment_level="moderate", color_temperature="warm",
                ),
            ),
            _ctx(),
            _graph(),
        )
        self.assertEqual(len(violations), 1)


class SilhouetteBalanceTests(unittest.TestCase):

    def test_all_fitted_non_hourglass_violates(self):
        items = (
            _smart_casual_top(fit_type="slim"),
            _smart_casual_bottom(fit_type="tailored"),
        )
        violations = evaluate_constraint(
            "silhouette_balance", items, _ctx(body_shape="Pear"), _graph()
        )
        self.assertTrue(any(v.rule == "no_all_fitted" for v in violations))
        self.assertTrue(all(not v.is_hard for v in violations))

    def test_all_fitted_hourglass_exception_passes(self):
        items = (
            _smart_casual_top(fit_type="slim"),
            _smart_casual_bottom(fit_type="tailored"),
        )
        violations = evaluate_constraint(
            "silhouette_balance", items, _ctx(body_shape="Hourglass"), _graph()
        )
        self.assertFalse(any(v.rule == "no_all_fitted" for v in violations))

    def test_all_relaxed_apple_exception_passes(self):
        items = (
            _smart_casual_top(fit_type="loose"),
            _smart_casual_bottom(fit_type="boxy"),
        )
        violations = evaluate_constraint(
            "silhouette_balance", items, _ctx(body_shape="Apple"), _graph()
        )
        self.assertFalse(any(v.rule == "no_all_relaxed" for v in violations))

    def test_all_relaxed_diamond_exception_passes(self):
        items = (
            _smart_casual_top(fit_type="loose"),
            _smart_casual_bottom(fit_type="relaxed"),
        )
        violations = evaluate_constraint(
            "silhouette_balance", items, _ctx(body_shape="Diamond"), _graph()
        )
        self.assertFalse(any(v.rule == "no_all_relaxed" for v in violations))

    def test_all_relaxed_pear_violates(self):
        items = (
            _smart_casual_top(fit_type="loose"),
            _smart_casual_bottom(fit_type="boxy"),
        )
        violations = evaluate_constraint(
            "silhouette_balance", items, _ctx(body_shape="Pear"), _graph()
        )
        self.assertTrue(any(v.rule == "no_all_relaxed" for v in violations))

    def test_fluid_outerwear_violates(self):
        items = (
            _smart_casual_top(),
            _smart_casual_bottom(),
            _structured_outerwear(fabric_drape="fluid"),
        )
        violations = evaluate_constraint("silhouette_balance", items, _ctx(), _graph())
        self.assertTrue(any(v.rule == "structured_outerwear_anchor" for v in violations))

    def test_fitted_relaxed_pair_passes(self):
        items = (
            _smart_casual_top(fit_type="tailored"),
            _smart_casual_bottom(fit_type="relaxed"),
        )
        violations = evaluate_constraint("silhouette_balance", items, _ctx(), _graph())
        self.assertEqual(violations, ())


class FabricCompatibilityTests(unittest.TestCase):

    def test_compatible_textures_pass(self):
        items = (
            _smart_casual_top(fabric_texture="smooth"),
            _smart_casual_bottom(fabric_texture="textured"),
        )
        violations = evaluate_constraint("fabric_compatibility", items, _ctx(), _graph())
        # smooth + textured is in the matrix.
        self.assertFalse(any(v.rule == "texture_mixing" for v in violations))

    def test_sheen_plus_metallic_violates(self):
        # Per YAML: sheen does not list metallic as compatible.
        items = (
            _smart_casual_top(fabric_texture="sheen"),
            _smart_casual_bottom(fabric_texture="metallic"),
        )
        violations = evaluate_constraint("fabric_compatibility", items, _ctx(), _graph())
        self.assertTrue(any(v.rule == "texture_mixing" for v in violations))
        self.assertTrue(all(not v.is_hard for v in violations))

    def test_heavy_plus_very_light_violates(self):
        items = (
            _smart_casual_top(fabric_weight="very_light"),
            _smart_casual_bottom(fabric_weight="heavy"),
        )
        violations = evaluate_constraint("fabric_compatibility", items, _ctx(), _graph())
        self.assertTrue(any(v.rule == "weight_pairing" for v in violations))

    def test_compatible_weights_pass(self):
        items = (
            _smart_casual_top(fabric_weight="light"),
            _smart_casual_bottom(fabric_weight="medium"),
        )
        violations = evaluate_constraint("fabric_compatibility", items, _ctx(), _graph())
        self.assertFalse(any(v.rule == "weight_pairing" for v in violations))

    # ─────────────────────────────────────────────────────────────────────
    # sheen_hierarchy (Phase 4.3 / PR 4c.2). At most one sheen-bearing
    # surface (sheen / metallic / embroidered fabric_texture) per outfit
    # outside the bridal exception.
    # ─────────────────────────────────────────────────────────────────────

    def test_single_sheen_item_passes(self):
        items = (
            _smart_casual_top(fabric_texture="sheen"),
            _smart_casual_bottom(fabric_texture="matte"),
        )
        violations = evaluate_constraint("fabric_compatibility", items, _ctx(), _graph())
        self.assertFalse(any(v.rule == "sheen_hierarchy" for v in violations))

    def test_two_sheen_items_violate_outside_bridal(self):
        items = (
            _smart_casual_top(fabric_texture="sheen"),
            _smart_casual_bottom(fabric_texture="embroidered"),
        )
        violations = evaluate_constraint("fabric_compatibility", items, _ctx(), _graph())
        sheen_v = [v for v in violations if v.rule == "sheen_hierarchy"]
        self.assertEqual(len(sheen_v), 1)
        self.assertFalse(sheen_v[0].is_hard)

    def test_metallic_counts_as_sheen(self):
        items = (
            _smart_casual_top(fabric_texture="metallic"),
            _smart_casual_bottom(fabric_texture="embroidered"),
        )
        violations = evaluate_constraint("fabric_compatibility", items, _ctx(), _graph())
        self.assertTrue(any(v.rule == "sheen_hierarchy" for v in violations))

    def test_sheen_hierarchy_bypassed_under_bridal_exception(self):
        items = (
            _smart_casual_top(formality="ceremonial", fabric_texture="sheen"),
            _smart_casual_bottom(formality="ceremonial", fabric_texture="embroidered"),
        )
        violations = evaluate_constraint(
            "fabric_compatibility",
            items,
            _ctx(formality_hint="ceremonial", occasion_signal="wedding_ceremony"),
            _graph(),
        )
        self.assertFalse(any(v.rule == "sheen_hierarchy" for v in violations))

    def test_non_sheen_textures_dont_count(self):
        items = (
            _smart_casual_top(fabric_texture="smooth"),
            _smart_casual_bottom(fabric_texture="textured"),
        )
        violations = evaluate_constraint("fabric_compatibility", items, _ctx(), _graph())
        self.assertFalse(any(v.rule == "sheen_hierarchy" for v in violations))


class CulturalCoherenceTests(unittest.TestCase):

    def test_all_traditional_passes(self):
        items = (
            _smart_casual_top(cultural_register="indian_traditional"),
            _smart_casual_bottom(cultural_register="indian_traditional"),
        )
        violations = evaluate_constraint("cultural_coherence", items, _ctx(), _graph())
        self.assertEqual(violations, ())

    def test_all_western_passes(self):
        violations = evaluate_constraint(
            "cultural_coherence",
            (_smart_casual_top(), _smart_casual_bottom()),  # default western
            _ctx(),
            _graph(),
        )
        self.assertEqual(violations, ())

    def test_traditional_plus_western_no_bridge_violates(self):
        items = (
            _smart_casual_top(cultural_register="indian_traditional"),
            _smart_casual_bottom(cultural_register="western"),
        )
        violations = evaluate_constraint("cultural_coherence", items, _ctx(), _graph())
        self.assertTrue(any(v.rule == "indo_western_fusion" for v in violations))

    def test_indo_western_fusion_skipped_when_register_missing(self):
        # Skip-if-empty: a 3-slot tuple with one register missing might
        # have an indo_western bridge in the unknown slot, so the rule
        # can't confirm the violation.
        items = (
            _smart_casual_top(cultural_register="indian_traditional"),
            _smart_casual_bottom(cultural_register="western"),
            _structured_outerwear(cultural_register=""),  # unknown
        )
        violations = evaluate_constraint("cultural_coherence", items, _ctx(), _graph())
        self.assertFalse(any(v.rule == "indo_western_fusion" for v in violations))

    def test_traditional_plus_western_with_fusion_bridge_passes(self):
        items = (
            _smart_casual_top(cultural_register="indian_traditional"),
            _smart_casual_bottom(cultural_register="western"),
            _structured_outerwear(cultural_register="indo_western"),
        )
        violations = evaluate_constraint("cultural_coherence", items, _ctx(), _graph())
        self.assertFalse(any(v.rule == "indo_western_fusion" for v in violations))

    def test_heavy_traditional_plus_western_double_violates(self):
        items = (
            _smart_casual_top(
                cultural_register="indian_traditional", embellishment_level="heavy"
            ),
            _smart_casual_bottom(cultural_register="western"),
        )
        violations = evaluate_constraint("cultural_coherence", items, _ctx(), _graph())
        rules_hit = {v.rule for v in violations}
        self.assertIn("indo_western_fusion", rules_hit)
        self.assertIn("heavy_traditional_no_western_fusion", rules_hit)


class BridalSpecificTests(unittest.TestCase):

    def test_bridal_specific_is_no_op_without_bridal_role(self):
        # Default ctx.bridal_role is "" — guest_vs_bridal_separation
        # doesn't fire, matching pre-Phase-4.3 behaviour. Other subtype
        # rules (bridal_lehenga_pairing etc.) remain no-ops here too —
        # they're practically covered by formality_alignment.
        items = (
            _smart_casual_top(formality="ceremonial", subtype="lehenga"),
            _smart_casual_bottom(formality="ceremonial", subtype="choli"),
        )
        violations = evaluate_constraint(
            "bridal_specific",
            items,
            _ctx(formality_hint="ceremonial", occasion_signal="wedding_ceremony"),
            _graph(),
        )
        self.assertEqual(violations, ())

    # ─────────────────────────────────────────────────────────────────────
    # guest_vs_bridal_separation (Phase 4.3 / PR 4c.1b). When the user is
    # attending a wedding-context occasion as a guest, their tuples can't
    # carry items at bridal-participant embellishment levels (heavy /
    # statement per YAML).
    # ─────────────────────────────────────────────────────────────────────

    def test_guest_with_heavy_item_at_bridal_occasion_violates(self):
        items = (
            _smart_casual_top(formality="ceremonial", embellishment_level="heavy"),
            _smart_casual_bottom(formality="ceremonial", embellishment_level="minimal"),
        )
        violations = evaluate_constraint(
            "bridal_specific",
            items,
            _ctx(
                formality_hint="ceremonial",
                occasion_signal="wedding_ceremony",
                bridal_role="guest",
            ),
            _graph(),
        )
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule, "guest_vs_bridal_separation")

    def test_attendee_treated_as_guest_for_separation(self):
        # ``attendee`` is the default non-bridal-party role; same cap applies.
        items = (
            _smart_casual_top(formality="ceremonial", embellishment_level="statement"),
            _smart_casual_bottom(formality="ceremonial", embellishment_level="minimal"),
        )
        violations = evaluate_constraint(
            "bridal_specific",
            items,
            _ctx(
                formality_hint="ceremonial",
                occasion_signal="wedding_ceremony",
                bridal_role="attendee",
            ),
            _graph(),
        )
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule, "guest_vs_bridal_separation")

    def test_bride_bypasses_separation(self):
        items = (
            _smart_casual_top(formality="ceremonial", embellishment_level="statement"),
            _smart_casual_bottom(formality="ceremonial", embellishment_level="heavy"),
        )
        violations = evaluate_constraint(
            "bridal_specific",
            items,
            _ctx(
                formality_hint="ceremonial",
                occasion_signal="wedding_ceremony",
                bridal_role="bride",
            ),
            _graph(),
        )
        self.assertEqual(violations, ())

    def test_groom_bypasses_separation(self):
        items = (
            _smart_casual_top(formality="ceremonial", embellishment_level="heavy"),
            _smart_casual_bottom(formality="ceremonial", embellishment_level="moderate"),
        )
        violations = evaluate_constraint(
            "bridal_specific",
            items,
            _ctx(
                formality_hint="ceremonial",
                occasion_signal="wedding_ceremony",
                bridal_role="groom",
            ),
            _graph(),
        )
        self.assertEqual(violations, ())

    def test_guest_with_only_moderate_passes(self):
        # moderate is NOT in the cap (heavy + statement only) — passes.
        items = (
            _smart_casual_top(formality="ceremonial", embellishment_level="moderate"),
            _smart_casual_bottom(formality="ceremonial", embellishment_level="minimal"),
        )
        violations = evaluate_constraint(
            "bridal_specific",
            items,
            _ctx(
                formality_hint="ceremonial",
                occasion_signal="wedding_ceremony",
                bridal_role="guest",
            ),
            _graph(),
        )
        self.assertEqual(violations, ())

    def test_guest_at_non_bridal_occasion_no_op(self):
        # bridal_role set, but occasion isn't a bridal-role occasion —
        # rule shouldn't fire. is_bridal_role_occasion gates this.
        items = (
            _smart_casual_top(formality="smart_casual", embellishment_level="heavy"),
            _smart_casual_bottom(formality="smart_casual", embellishment_level="minimal"),
        )
        violations = evaluate_constraint(
            "bridal_specific",
            items,
            _ctx(
                formality_hint="smart_casual",
                occasion_signal="daily_office_mnc",
                bridal_role="guest",
            ),
            _graph(),
        )
        self.assertEqual(violations, ())


# ─────────────────────────────────────────────────────────────────────────
# score_tuple — orchestration
# ─────────────────────────────────────────────────────────────────────────


class ScoreTupleTests(unittest.TestCase):

    def test_clean_tuple_scores_one(self):
        result = score_tuple(
            (_smart_casual_top(), _smart_casual_bottom()), _ctx(), _graph()
        )
        self.assertFalse(result.dropped)
        self.assertEqual(result.base_score, BASE_SCORE)
        self.assertEqual(result.violations, ())
        self.assertIsNone(result.drop_reason)
        self.assertTrue(result.is_kept)

    def test_empty_tuple_drops_with_reason(self):
        result = score_tuple((), _ctx(), _graph())
        self.assertTrue(result.dropped)
        self.assertEqual(result.drop_reason, "empty_tuple")
        self.assertEqual(result.base_score, 0.0)

    def test_hard_violation_drops_short_circuit(self):
        # 2-step formality gap → formality_alignment fires first.
        result = score_tuple(
            (
                _smart_casual_top(formality="casual"),
                _smart_casual_bottom(formality="formal"),
            ),
            _ctx(),
            _graph(),
        )
        self.assertTrue(result.dropped)
        self.assertEqual(result.drop_reason, "formality_alignment")
        self.assertEqual(result.base_score, 0.0)
        # Violations carry only the hard one — no soft checks run after drop.
        self.assertEqual(len(result.violations), 1)
        self.assertTrue(result.violations[0].is_hard)

    def test_soft_violation_penalizes_score(self):
        # Force a single soft violation: fluid outerwear.
        result = score_tuple(
            (
                _smart_casual_top(),
                _smart_casual_bottom(),
                _structured_outerwear(fabric_drape="fluid"),
            ),
            _ctx(),
            _graph(),
        )
        self.assertFalse(result.dropped)
        self.assertEqual(len(result.violations), 1)
        self.assertAlmostEqual(result.base_score, BASE_SCORE - SOFT_PENALTY, places=6)

    def test_multiple_soft_violations_accumulate(self):
        # Force three soft violations: all-fitted (Pear, no exemption),
        # heavy_traditional + western, and indo_western_fusion mismatch.
        result = score_tuple(
            (
                _smart_casual_top(
                    fit_type="slim", cultural_register="indian_traditional",
                    embellishment_level="heavy",
                ),
                _smart_casual_bottom(fit_type="tailored", cultural_register="western"),
            ),
            _ctx(body_shape="Pear", palette_anchors=("navy", "cream")),
            _graph(),
        )
        self.assertFalse(result.dropped)
        # 3 soft violations: no_all_fitted, indo_western_fusion,
        # heavy_traditional_no_western_fusion. Score = 1.0 - 3*0.10 = 0.70.
        self.assertGreaterEqual(len(result.violations), 3)
        self.assertAlmostEqual(
            result.base_score, BASE_SCORE - SOFT_PENALTY * len(result.violations),
            places=6,
        )

    def test_hard_categories_in_correct_order(self):
        # All five hard categories defined.
        self.assertEqual(
            HARD_CATEGORIES,
            (
                "formality_alignment",
                "color_story",
                "pattern_mixing",
                "scale_balance",
                "bridal_specific",
            ),
        )

    def test_soft_categories_in_correct_order(self):
        self.assertEqual(
            SOFT_CATEGORIES,
            (
                "silhouette_balance",
                "fabric_compatibility",
                "cultural_coherence",
            ),
        )


# ─────────────────────────────────────────────────────────────────────────
# Worked examples from composer_semantics.md §9
# ─────────────────────────────────────────────────────────────────────────


class WorkedExampleTests(unittest.TestCase):
    """Verbatim re-runs of spec §9.1-§9.4. These guard the spec-engine
    contract: if these regress, the spec or the engine is wrong."""

    def test_9_1_clean_daily_office_paired(self):
        # Direction A paired, navy structured top + cream tailored trouser.
        # Body shape Hourglass. Spec §9.1 expects score=1.00.
        top = _smart_casual_top(
            item_id="T1",
            formality="smart_casual",
            dominant_color="navy",
            contrast_level="medium",
            pattern_type="solid",
            fabric_drape="crisp",
            fit_type="tailored",
        )
        bottom = _smart_casual_bottom(
            item_id="B1",
            formality="smart_casual",
            dominant_color="cream",
            contrast_level="medium",
            pattern_type="solid",
            fabric_drape="soft_structured",
            fit_type="tailored",
        )
        # User palette includes navy → palette_anchor satisfied.
        result = score_tuple(
            (top, bottom),
            _ctx(
                formality_hint="smart_casual",
                occasion_signal="daily_office_mnc",
                palette_anchors=("navy", "cream", "charcoal"),
                body_shape="Hourglass",
            ),
            _graph(),
        )
        self.assertFalse(result.dropped)
        self.assertEqual(result.base_score, 1.00)
        self.assertEqual(result.violations, ())

    def test_9_2_two_pattern_violation_drops(self):
        # Two large-scale patterns with no scale-matrix overlap → drop.
        # Per spec §9.2, large+large isn't in two_patterns matrix.
        top = _smart_casual_top(
            item_id="T2",
            pattern_type="floral", pattern_scale="large",
            dominant_color="navy", contrast_level="medium",
        )
        bottom = _smart_casual_bottom(
            item_id="B2",
            pattern_type="checks", pattern_scale="large",
            dominant_color="navy", contrast_level="medium",
        )
        result = score_tuple((top, bottom), _ctx(), _graph())
        self.assertTrue(result.dropped)
        self.assertEqual(result.drop_reason, "pattern_mixing")

    def test_9_3_bridal_exception_saves_three_statement_tuple(self):
        # Ceremonial wedding: 3 statement slots, all solid (statement via
        # embellishment alone, not pattern), exception applies, no drop.
        # Solid pattern_type sidesteps pattern_mixing entirely and lets us
        # test scale_balance's bridal exception in isolation.
        top = _smart_casual_top(
            item_id="T3",
            slot="top",
            formality="ceremonial",
            dominant_color="maroon",
            contrast_level="medium",
            pattern_type="solid",
            embellishment_level="statement",
            fabric_texture="embroidered",
            fabric_weight="medium",
            fabric_drape="soft_structured",
            cultural_register="indian_traditional",
            subtype="choli",
        )
        bottom = _smart_casual_bottom(
            item_id="B3",
            slot="bottom",
            formality="ceremonial",
            dominant_color="maroon",
            contrast_level="medium",
            pattern_type="solid",
            embellishment_level="statement",
            fabric_texture="embroidered",
            fabric_weight="medium",
            fabric_drape="soft_structured",
            cultural_register="indian_traditional",
            subtype="lehenga",
        )
        outerwear = _structured_outerwear(
            item_id="OW3",
            formality="ceremonial",
            dominant_color="maroon",
            contrast_level="medium",
            pattern_type="solid",
            embellishment_level="statement",
            fabric_texture="embroidered",
            fabric_weight="light",
            fabric_drape="soft_structured",
            cultural_register="indian_traditional",
            subtype="dupatta",
            fit_type="relaxed",  # avoid no_all_fitted soft penalty
        )
        # Without bridal exception: 3 statement slots → scale_balance drop.
        # With bridal exception: pass through scale_balance, no other hard
        # rules trip. Score may take soft penalty for fluid/embroidered
        # combos but should not be dropped.
        result = score_tuple(
            (top, bottom, outerwear),
            _ctx(
                formality_hint="ceremonial",
                occasion_signal="wedding_ceremony",
                palette_anchors=("maroon",),
                body_shape="Hourglass",
            ),
            _graph(),
        )
        self.assertFalse(result.dropped, msg=f"violations={result.violations}")
        self.assertGreaterEqual(result.base_score, 0.7)

    def test_9_3_without_bridal_exception_drops(self):
        # Same tuple, non-bridal context → scale_balance fires (3 statements).
        top = _smart_casual_top(
            item_id="T3",
            formality="smart_casual",
            pattern_type="solid",
            embellishment_level="statement",
        )
        bottom = _smart_casual_bottom(
            item_id="B3",
            formality="smart_casual",
            pattern_type="solid",
            embellishment_level="statement",
        )
        result = score_tuple(
            (top, bottom),
            _ctx(formality_hint="smart_casual", occasion_signal="daily_office_mnc"),
            _graph(),
        )
        self.assertTrue(result.dropped)
        self.assertEqual(result.drop_reason, "scale_balance")


# ─────────────────────────────────────────────────────────────────────────
# YAML extension — triggers_on field is loaded
# ─────────────────────────────────────────────────────────────────────────


class TriggersOnFieldTests(unittest.TestCase):

    def test_bridal_specific_triggers_on_loaded(self):
        graph = _graph()
        bridal = graph.pairing_rules["bridal_specific"]
        self.assertIn("wedding_ceremony", bridal.triggers_on)
        self.assertIn("sangeet", bridal.triggers_on)
        # All 6 expected occasions present.
        expected = {"wedding_ceremony", "sangeet", "mehendi", "haldi", "reception", "engagement"}
        self.assertEqual(set(bridal.triggers_on), expected)

    def test_other_groups_have_empty_triggers_on(self):
        graph = _graph()
        for name, group in graph.pairing_rules.items():
            if name == "bridal_specific":
                continue
            self.assertEqual(
                group.triggers_on, (),
                msg=f"unexpected triggers_on on {name}: {group.triggers_on}",
            )


class ObservabilityCounterTests(unittest.TestCase):
    """Phase 4.3 observability — score_tuple ticks
    aura_composer_rule_violation_total per violation; exception paths
    tick aura_composer_rule_exception_applied_total. These metrics let
    dashboards alert in real time without having to drill into
    distillation_traces JSON."""

    def setUp(self):
        from platform_core import metrics
        self._violation_metric = metrics.aura_composer_rule_violation_total
        self._exception_metric = metrics.aura_composer_rule_exception_applied_total

    def _violation_count(self, rule: str, is_hard: str) -> float:
        """Read the current counter value for (rule, is_hard). Counter
        values are monotonic; tests compare before/after deltas."""
        try:
            return self._violation_metric.labels(rule=rule, is_hard=is_hard)._value.get()
        except Exception:
            return 0.0

    def _exception_count(self, rule: str, exception: str) -> float:
        try:
            return self._exception_metric.labels(rule=rule, exception=exception)._value.get()
        except Exception:
            return 0.0

    def test_score_tuple_emits_violation_counter_on_hard_drop(self):
        """A hard short-circuit drop must tick the counter once with
        is_hard=true so dashboards can alert on the hard-rule rate."""
        before = self._violation_count("max_dominant_colors", "true")
        # 4 distinct non-metallic colors → max_dominant_colors fires hard.
        items = (
            _smart_casual_top(dominant_color="navy"),
            _smart_casual_bottom(dominant_color="cream"),
            _structured_outerwear(dominant_color="rust"),
            Item(item_id="X1", slot="top", formality="smart_casual",
                 dominant_color="emerald", contrast_level="medium",
                 pattern_type="solid"),
        )
        result = score_tuple(items, _ctx(), _graph())
        after = self._violation_count("max_dominant_colors", "true")
        self.assertTrue(result.dropped)
        self.assertEqual(after - before, 1.0)

    def test_score_tuple_emits_violation_counter_on_soft_violation(self):
        """A soft accumulation must tick the counter with is_hard=false."""
        before = self._violation_count("sheen_hierarchy", "false")
        items = (
            _smart_casual_top(fabric_texture="sheen"),
            _smart_casual_bottom(fabric_texture="metallic"),
        )
        result = score_tuple(items, _ctx(), _graph())
        after = self._violation_count("sheen_hierarchy", "false")
        # sheen_hierarchy fires soft → tuple survives but counter ticks.
        self.assertFalse(result.dropped)
        self.assertEqual(after - before, 1.0)

    def test_distributed_statement_exception_ticks_exception_counter(self):
        before = self._exception_count(
            "one_statement_per_outfit", "distributed_statement_exception",
        )
        items = (
            _smart_casual_top(
                embellishment_level="moderate", color_temperature="warm",
            ),
            _smart_casual_bottom(
                embellishment_level="moderate", color_temperature="warm",
            ),
        )
        evaluate_constraint("scale_balance", items, _ctx(), _graph())
        after = self._exception_count(
            "one_statement_per_outfit", "distributed_statement_exception",
        )
        self.assertEqual(after - before, 1.0)

    def test_metallic_neutral_exception_ticks_exception_counter(self):
        before = self._exception_count(
            "max_dominant_colors", "metallic_neutral_exception",
        )
        items = (
            _smart_casual_top(dominant_color="navy"),
            _smart_casual_bottom(dominant_color="cream"),
            Item(item_id="DUP", slot="top", formality="smart_casual",
                 dominant_color="gold", contrast_level="medium",
                 pattern_type="solid"),
        )
        evaluate_constraint("color_story", items, _ctx(), _graph())
        after = self._exception_count(
            "max_dominant_colors", "metallic_neutral_exception",
        )
        self.assertEqual(after - before, 1.0)


if __name__ == "__main__":
    unittest.main()
