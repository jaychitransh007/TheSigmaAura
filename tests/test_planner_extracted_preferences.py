"""Tests for the planner's extracted_preferences parsing (Phase 5x).

The planner emits an array of {attribute, values} pairs (strict-mode
JSON schema can't express arbitrary-key objects). _parse_result folds
that array into a dict on CopilotResolvedContext.extracted_preferences.
This test pins the parsing edge cases:

- Array of pairs → dict keyed by attribute
- Empty / malformed entries dropped
- Empty-string values within a list dropped
- Whitespace stripped from attribute and values
- Empty array → empty dict
- Missing key → empty dict (legacy planner output compat)
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

# sys.path setup is centralised in tests/conftest.py.
from agentic_application.agents.copilot_planner import CopilotPlanner


def _planner() -> CopilotPlanner:
    """Construct a minimal CopilotPlanner without exercising LLM init.

    _parse_result is a pure method on the instance; we only need the
    instance binding, not the real LLM client/prompt-loading machinery.
    """
    return CopilotPlanner.__new__(CopilotPlanner)


def _raw(extracted_preferences):
    return {
        "intent": "occasion_recommendation",
        "intent_confidence": 0.9,
        "action": "run_recommendation_pipeline",
        "context_sufficient": True,
        "assistant_message": "",
        "follow_up_suggestions": [],
        "resolved_context": {
            "occasion_signal": None,
            "formality_hint": None,
            "time_hint": None,
            "specific_needs": [],
            "is_followup": False,
            "followup_intent": None,
            "style_goal": "",
            "source_preference": "auto",
            "target_product_type": "",
            "weather_context": "",
            "time_of_day": "",
            "extracted_preferences": extracted_preferences,
        },
        "action_parameters": {
            "purchase_intent": False,
            "target_piece": None,
            "detected_colors": [],
            "detected_garments": [],
            "product_urls": [],
            "feedback_event_type": None,
            "wardrobe_item_title": None,
        },
    }


class ExtractedPreferencesParseTests(unittest.TestCase):

    def test_array_of_pairs_folds_into_dict(self):
        result = _planner()._parse_result(_raw([
            {"attribute": "EmbellishmentLevel", "values": ["heavy", "statement"]},
            {"attribute": "ContrastLevel", "values": ["very_low", "low"]},
        ]))
        prefs = result.resolved_context.extracted_preferences
        self.assertEqual(prefs["EmbellishmentLevel"], ["heavy", "statement"])
        self.assertEqual(prefs["ContrastLevel"], ["very_low", "low"])

    def test_empty_array_yields_empty_dict(self):
        result = _planner()._parse_result(_raw([]))
        self.assertEqual(result.resolved_context.extracted_preferences, {})

    def test_missing_key_yields_empty_dict(self):
        # Legacy planner output without the new field — must not crash.
        raw = _raw([])
        del raw["resolved_context"]["extracted_preferences"]
        result = _planner()._parse_result(raw)
        self.assertEqual(result.resolved_context.extracted_preferences, {})

    def test_drops_empty_attribute_names(self):
        result = _planner()._parse_result(_raw([
            {"attribute": "", "values": ["x"]},
            {"attribute": "  ", "values": ["x"]},
            {"attribute": "Real", "values": ["y"]},
        ]))
        prefs = result.resolved_context.extracted_preferences
        self.assertNotIn("", prefs)
        self.assertNotIn("  ", prefs)
        self.assertEqual(prefs["Real"], ["y"])

    def test_drops_empty_value_lists(self):
        result = _planner()._parse_result(_raw([
            {"attribute": "EmbellishmentLevel", "values": []},
            {"attribute": "ContrastLevel", "values": ["", "  "]},
            {"attribute": "Keep", "values": ["v"]},
        ]))
        prefs = result.resolved_context.extracted_preferences
        self.assertNotIn("EmbellishmentLevel", prefs)
        self.assertNotIn("ContrastLevel", prefs)
        self.assertEqual(prefs["Keep"], ["v"])

    def test_strips_whitespace(self):
        result = _planner()._parse_result(_raw([
            {"attribute": "  EmbellishmentLevel  ", "values": ["  heavy  ", "statement"]},
        ]))
        prefs = result.resolved_context.extracted_preferences
        self.assertEqual(prefs["EmbellishmentLevel"], ["heavy", "statement"])

    def test_skips_malformed_entries(self):
        result = _planner()._parse_result(_raw([
            "not a dict",  # malformed
            {"attribute": "Good", "values": ["x"]},
            {"values": ["orphan"]},  # missing attribute
            {"attribute": "BadValues", "values": "not a list"},
        ]))
        prefs = result.resolved_context.extracted_preferences
        self.assertEqual(prefs, {"Good": ["x"]})


if __name__ == "__main__":
    unittest.main()
