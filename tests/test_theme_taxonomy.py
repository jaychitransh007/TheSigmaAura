"""Tests for the Outfits tab theme taxonomy (May 1, 2026 plan).

The acceptance test reproduces the bug-report list verbatim — the
14 raw occasion strings the user found in their Outfits tab — and
asserts they collapse into the expected 5-bucket result.
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
    is_unmapped,
    theme_label,
    theme_description,
    theme_order,
    all_theme_keys,
)


class ThemeMappingBasics(unittest.TestCase):
    def test_eight_themes_defined(self) -> None:
        self.assertEqual(8, len(THEMES))

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


class AcceptanceFromBugReport(unittest.TestCase):
    """The exact list the staging user reported."""

    def test_user_reported_14_signals_collapse_to_5_themes(self) -> None:
        observations = [
            ("casual outing", "occasion_recommendation",  "casual"),
            ("general", "occasion_recommendation",        "style_sessions"),
            ("beach", "occasion_recommendation",          "travel"),
            ("casual", "occasion_recommendation",         "casual"),
            ("", "occasion_recommendation",               "style_sessions"),  # 'occasion recommendation' bucket
            ("traditional engagement", "occasion_recommendation", "wedding"),
            ("weekend outing", "occasion_recommendation", "casual"),
            ("evening", "occasion_recommendation",        "evening"),
            ("date night", "occasion_recommendation",     "date"),
            ("engagement wedding", "occasion_recommendation", "wedding"),
            ("wedding engagement", "occasion_recommendation", "wedding"),
            ("engagement", "occasion_recommendation",     "wedding"),
            ("date night", "occasion_recommendation",     "date"),    # duplicate
            ("", "pairing_request",                       "style_sessions"),  # 'pairing request' bucket
        ]
        themes_seen = set()
        for occasion, intent, expected in observations:
            actual = map_to_theme(occasion, intent)
            self.assertEqual(
                expected, actual,
                f"occasion={occasion!r} intent={intent!r}: expected {expected!r}, got {actual!r}",
            )
            themes_seen.add(actual)
        # 5 themes (the duplicate "date night" doesn't add a 6th):
        # wedding, casual, travel, date, evening, style_sessions
        self.assertEqual(
            {"wedding", "casual", "travel", "date", "evening", "style_sessions"},
            themes_seen,
        )


class WeddingPrecedence(unittest.TestCase):
    """Wedding sub-events outrank evening/casual cross-overs."""

    def test_engagement_evening_lands_in_wedding(self) -> None:
        self.assertEqual("wedding", map_to_theme("engagement evening party"))

    def test_wedding_cocktail_lands_in_wedding(self) -> None:
        self.assertEqual("wedding", map_to_theme("wedding cocktail party"))

    def test_sangeet_outranks_party(self) -> None:
        self.assertEqual("wedding", map_to_theme("sangeet party"))

    def test_traditional_engagement_lands_in_wedding(self) -> None:
        self.assertEqual("wedding", map_to_theme("traditional engagement"))


class FestiveAndDate(unittest.TestCase):
    def test_diwali_party_lands_in_festive(self) -> None:
        self.assertEqual("festive", map_to_theme("diwali party at home"))

    def test_eid_outranks_evening(self) -> None:
        self.assertEqual("festive", map_to_theme("eid evening dinner"))

    def test_anniversary_dinner_lands_in_date(self) -> None:
        self.assertEqual("date", map_to_theme("anniversary dinner"))

    def test_first_date_lands_in_date(self) -> None:
        self.assertEqual("date", map_to_theme("first date"))


class WorkAndCasualBoundaries(unittest.TestCase):
    def test_office_meeting_lands_in_work(self) -> None:
        self.assertEqual("work", map_to_theme("office meeting"))

    def test_daily_office_lands_in_work(self) -> None:
        self.assertEqual("work", map_to_theme("daily office"))

    def test_smart_casual_lands_in_casual(self) -> None:
        self.assertEqual("casual", map_to_theme("smart casual"))

    def test_brunch_lands_in_casual(self) -> None:
        self.assertEqual("casual", map_to_theme("sunday brunch"))


class TravelAndEvening(unittest.TestCase):
    def test_beach_lands_in_travel(self) -> None:
        self.assertEqual("travel", map_to_theme("beach holiday"))

    def test_airport_lands_in_travel(self) -> None:
        self.assertEqual("travel", map_to_theme("airport outfit"))

    def test_cocktail_party_alone_lands_in_evening(self) -> None:
        self.assertEqual("evening", map_to_theme("cocktail party"))


class FallthroughAndIntent(unittest.TestCase):
    def test_empty_signal_with_pairing_request_lands_in_style_sessions(self) -> None:
        self.assertEqual("style_sessions", map_to_theme("", intent="pairing_request"))

    def test_empty_signal_with_occasion_recommendation_lands_in_style_sessions(self) -> None:
        self.assertEqual("style_sessions", map_to_theme("", intent="occasion_recommendation"))

    def test_empty_signal_with_unknown_intent_lands_in_style_sessions(self) -> None:
        self.assertEqual("style_sessions", map_to_theme("", intent="some_made_up_intent"))

    def test_unknown_signal_falls_through(self) -> None:
        self.assertEqual("style_sessions", map_to_theme("xyz nonsense"))

    def test_general_lands_in_style_sessions(self) -> None:
        self.assertEqual("style_sessions", map_to_theme("general"))


class IsUnmappedHelper(unittest.TestCase):
    """is_unmapped distinguishes 'unrecognised content' from 'no content'."""

    def test_empty_signal_is_not_unmapped(self) -> None:
        self.assertFalse(is_unmapped(""))
        self.assertFalse(is_unmapped("   "))

    def test_unknown_content_is_unmapped(self) -> None:
        self.assertTrue(is_unmapped("strangenewword"))

    def test_recognised_signal_is_not_unmapped(self) -> None:
        self.assertFalse(is_unmapped("wedding"))
        self.assertFalse(is_unmapped("casual outing"))


class WhitespaceNormalization(unittest.TestCase):
    """Internal whitespace and casing collapse so 'date night' / 'Date  Night ' / 'date_night' all match."""

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
        self.assertEqual("Casual & Everyday", theme_label("casual"))
        # Unknown theme falls back to style_sessions label
        self.assertEqual("Style Sessions", theme_label("not_a_theme"))

    def test_theme_description_returns_a_string(self) -> None:
        self.assertTrue(theme_description("wedding"))
        self.assertTrue(theme_description("travel"))

    def test_theme_order_returns_int(self) -> None:
        self.assertEqual(1, theme_order("wedding"))
        self.assertEqual(99, theme_order("style_sessions"))

    def test_all_theme_keys_in_canonical_order(self) -> None:
        keys = all_theme_keys()
        self.assertEqual(8, len(keys))
        self.assertEqual("wedding", keys[0])
        self.assertEqual("style_sessions", keys[-1])


if __name__ == "__main__":
    unittest.main()
