"""Tests for the Outfits tab theme taxonomy.

Covers the synonym-based occasion mapping and the formality fallback
that's applied when a session has no occasion signal.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user_profiler" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "user" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from agentic_application.services.theme_taxonomy import (
    THEMES,
    KEYWORDS,
    INTENT_FALLBACK,
    map_to_theme,
    map_formality_to_bucket,
    is_unmapped,
    theme_label,
    theme_description,
    theme_order,
    all_theme_keys,
)


class ThemeMappingBasics(unittest.TestCase):
    def test_all_themes_defined(self) -> None:
        # 8 occasion buckets + 3 formality buckets + 1 ultimate fallback
        self.assertEqual(12, len(THEMES))

    def test_every_theme_has_label_and_order(self) -> None:
        for key, meta in THEMES.items():
            self.assertIn("label", meta, key)
            self.assertIn("order", meta, key)
            self.assertTrue(str(meta["label"]).strip(), key)
            self.assertIsInstance(meta["order"], int)

    def test_keywords_only_map_to_real_themes(self) -> None:
        valid = set(THEMES.keys())
        for kw, theme_key in KEYWORDS:
            self.assertIn(theme_key, valid, f"keyword {kw!r} maps to unknown theme {theme_key!r}")

    def test_intent_fallback_only_maps_to_real_themes(self) -> None:
        valid = set(THEMES.keys())
        for intent, theme_key in INTENT_FALLBACK.items():
            self.assertIn(theme_key, valid, f"intent {intent!r} maps to unknown theme {theme_key!r}")


class OccasionMapping(unittest.TestCase):
    """Fine-grained occasion buckets — synonyms collapse, distinct
    occasions stay separate so Beach doesn't bury under Travel."""

    def test_beach_lands_in_beach_not_travel(self) -> None:
        self.assertEqual("beach", map_to_theme("beach"))
        self.assertEqual("beach", map_to_theme("beach holiday"))
        self.assertEqual("beach", map_to_theme("pool party"))
        self.assertEqual("beach", map_to_theme("resort wear"))

    def test_airport_lands_in_travel(self) -> None:
        self.assertEqual("travel", map_to_theme("airport outfit"))
        self.assertEqual("travel", map_to_theme("road trip"))
        self.assertEqual("travel", map_to_theme("weekend getaway"))

    def test_office_synonyms_collapse(self) -> None:
        self.assertEqual("office", map_to_theme("office meeting"))
        self.assertEqual("office", map_to_theme("daily office"))
        self.assertEqual("office", map_to_theme("business meeting"))
        self.assertEqual("office", map_to_theme("interview"))

    def test_party_renames_evening(self) -> None:
        self.assertEqual("party", map_to_theme("cocktail party"))
        self.assertEqual("party", map_to_theme("night out"))
        self.assertEqual("party", map_to_theme("evening"))

    def test_casual_synonyms_collapse(self) -> None:
        self.assertEqual("casual", map_to_theme("sunday brunch"))
        self.assertEqual("casual", map_to_theme("smart casual"))
        self.assertEqual("casual", map_to_theme("weekend outing"))
        self.assertEqual("casual", map_to_theme("daily wear"))


class PrecedenceRules(unittest.TestCase):
    """Specific event types outrank generic energy."""

    def test_engagement_evening_lands_in_wedding(self) -> None:
        self.assertEqual("wedding", map_to_theme("engagement evening party"))

    def test_wedding_cocktail_lands_in_wedding(self) -> None:
        self.assertEqual("wedding", map_to_theme("wedding cocktail party"))

    def test_sangeet_outranks_party(self) -> None:
        self.assertEqual("wedding", map_to_theme("sangeet party"))

    def test_eid_outranks_party(self) -> None:
        self.assertEqual("festive", map_to_theme("eid evening dinner"))

    def test_diwali_party_lands_in_festive(self) -> None:
        self.assertEqual("festive", map_to_theme("diwali party at home"))

    def test_anniversary_dinner_lands_in_date(self) -> None:
        self.assertEqual("date", map_to_theme("anniversary dinner"))


class FormalityFallback(unittest.TestCase):
    """When there's no occasion, formality_pct picks the bucket."""

    def test_high_formality_lands_in_smart_looks(self) -> None:
        self.assertEqual("smart_looks", map_formality_to_bucket(85))
        self.assertEqual("smart_looks", map_formality_to_bucket(100))
        self.assertEqual("smart_looks", map_formality_to_bucket(65))

    def test_mid_formality_lands_in_easy_everyday(self) -> None:
        self.assertEqual("easy_everyday", map_formality_to_bucket(50))
        self.assertEqual("easy_everyday", map_formality_to_bucket(35))
        self.assertEqual("easy_everyday", map_formality_to_bucket(64))

    def test_low_formality_lands_in_off_duty(self) -> None:
        self.assertEqual("off_duty", map_formality_to_bucket(0))
        self.assertEqual("off_duty", map_formality_to_bucket(20))
        self.assertEqual("off_duty", map_formality_to_bucket(34))

    def test_none_defaults_to_easy_everyday(self) -> None:
        self.assertEqual("easy_everyday", map_formality_to_bucket(None))


class FallthroughAndIntent(unittest.TestCase):
    def test_empty_signal_returns_style_sessions_sentinel(self) -> None:
        # The api layer overrides this with a formality bucket.
        self.assertEqual("style_sessions", map_to_theme("", intent="pairing_request"))
        self.assertEqual("style_sessions", map_to_theme("", intent="occasion_recommendation"))
        self.assertEqual("style_sessions", map_to_theme("", intent="some_made_up_intent"))

    def test_unknown_signal_falls_through(self) -> None:
        self.assertEqual("style_sessions", map_to_theme("xyz nonsense"))

    def test_general_lands_in_style_sessions(self) -> None:
        self.assertEqual("style_sessions", map_to_theme("general"))


class IsUnmappedHelper(unittest.TestCase):
    def test_empty_signal_is_not_unmapped(self) -> None:
        self.assertFalse(is_unmapped(""))
        self.assertFalse(is_unmapped("   "))

    def test_unknown_content_is_unmapped(self) -> None:
        self.assertTrue(is_unmapped("strangenewword"))

    def test_recognised_signal_is_not_unmapped(self) -> None:
        self.assertFalse(is_unmapped("wedding"))
        self.assertFalse(is_unmapped("casual outing"))
        self.assertFalse(is_unmapped("beach"))


class WhitespaceNormalization(unittest.TestCase):
    def test_uppercase_signal_matches(self) -> None:
        self.assertEqual("wedding", map_to_theme("ENGAGEMENT"))

    def test_internal_whitespace_collapses(self) -> None:
        self.assertEqual("date", map_to_theme("date    night"))

    def test_leading_trailing_whitespace_strips(self) -> None:
        self.assertEqual("date", map_to_theme("  date night  "))

    def test_underscored_form_matches(self) -> None:
        self.assertEqual("date", map_to_theme("date_night"))


class HelpersAndOrdering(unittest.TestCase):
    def test_theme_label_returns_human_string(self) -> None:
        self.assertEqual("Wedding & Engagement", theme_label("wedding"))
        self.assertEqual("Beach & Vacation", theme_label("beach"))
        self.assertEqual("Office & Professional", theme_label("office"))
        self.assertEqual("Weekend & Everyday", theme_label("casual"))
        self.assertEqual("Smart Looks", theme_label("smart_looks"))
        # Unknown theme falls back to style_sessions label
        self.assertEqual("Style Sessions", theme_label("not_a_theme"))

    def test_theme_description_returns_a_string(self) -> None:
        self.assertTrue(theme_description("wedding"))
        self.assertTrue(theme_description("beach"))
        self.assertTrue(theme_description("smart_looks"))

    def test_theme_order_returns_int(self) -> None:
        self.assertEqual(1, theme_order("wedding"))
        self.assertEqual(99, theme_order("style_sessions"))

    def test_all_theme_keys_in_canonical_order(self) -> None:
        keys = all_theme_keys()
        self.assertEqual(12, len(keys))
        self.assertEqual("wedding", keys[0])
        self.assertEqual("style_sessions", keys[-1])


if __name__ == "__main__":
    unittest.main()
