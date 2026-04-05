"""Unit tests for the QnA transparency template engine."""

import pytest

from agentic_application.intent_registry import Action, FollowUpIntent, Intent
from agentic_application.qna_messages import generate_stage_message


class TestStaticTemplates:
    """All static template keys return non-empty strings with minimal context."""

    @pytest.mark.parametrize(
        "stage,detail",
        [
            ("validate_request", "started"),
            ("onboarding_gate", "started"),
            ("onboarding_gate", "blocked"),
            ("onboarding_gate", "completed"),
            ("intent_router", "started"),
            ("user_context", "started"),
            ("context_builder", "started"),
            ("outfit_architect", "started"),
            ("catalog_search", "started"),
            ("outfit_assembly", "started"),
            ("outfit_evaluation", "completed"),
            ("response_formatting", "started"),
            ("virtual_tryon", "started"),
            ("virtual_tryon", "completed"),
            ("outfit_architect", "error"),
        ],
    )
    def test_static_templates_return_nonempty(self, stage, detail):
        msg = generate_stage_message(stage, detail)
        assert msg
        assert isinstance(msg, str)

    def test_unknown_stage_returns_empty(self):
        assert generate_stage_message("totally_unknown", "started") == ""

    def test_unknown_detail_returns_empty(self):
        assert generate_stage_message("validate_request", "unknown_detail") == ""


class TestUserContextCompleted:
    def test_with_richness(self):
        msg = generate_stage_message("user_context", "completed", {"richness": "full"})
        assert "full" in msg

    def test_without_richness_degrades(self):
        msg = generate_stage_message("user_context", "completed")
        assert msg  # should not crash


class TestContextBuilderCompleted:
    def test_returns_static_message(self):
        msg = generate_stage_message("context_builder", "completed")
        assert msg
        assert isinstance(msg, str)


class TestIntentRouterCompleted:
    def test_returns_primary_intent(self):
        msg = generate_stage_message("intent_router", "completed", {
            "primary_intent": Intent.STYLE_DISCOVERY,
        })
        assert "style discovery" in msg


class TestOutfitArchitectCompleted:
    @pytest.mark.parametrize(
        "plan_type,expected_fragment",
        [
            ("paired_only", "coordinated top + bottom"),
            ("complete_only", "complete one-piece outfits"),
            ("mixed", "a mix of complete and paired outfits"),
        ],
    )
    def test_plan_types_produce_distinct_descriptions(self, plan_type, expected_fragment):
        msg = generate_stage_message("outfit_architect", "completed", {
            "plan_type": plan_type,
            "direction_count": 3,
        })
        assert expected_fragment in msg
        assert "3" in msg

    def test_without_direction_count(self):
        msg = generate_stage_message("outfit_architect", "completed", {
            "plan_type": "mixed",
        })
        assert "a mix of complete and paired outfits" in msg
        assert "across" not in msg

    def test_empty_context(self):
        msg = generate_stage_message("outfit_architect", "completed")
        assert msg


class TestCatalogSearchCompleted:
    def test_with_counts(self):
        msg = generate_stage_message("catalog_search", "completed", {
            "product_count": 42,
            "set_count": 6,
        })
        assert "42" in msg
        assert "6" in msg

    def test_relaxed_search(self):
        msg = generate_stage_message("catalog_search", "completed", {
            "product_count": 10,
            "set_count": 3,
            "relaxed": True,
        })
        assert "broadened" in msg

    def test_empty_context(self):
        msg = generate_stage_message("catalog_search", "completed")
        assert msg


class TestOutfitAssemblyCompleted:
    def test_with_count(self):
        msg = generate_stage_message("outfit_assembly", "completed", {
            "candidate_count": 15,
        })
        assert "15" in msg

    def test_empty_context_degrades(self):
        msg = generate_stage_message("outfit_assembly", "completed")
        assert msg


class TestOutfitEvaluationStarted:
    def test_all_factors(self):
        msg = generate_stage_message("outfit_evaluation", "started", {
            "has_body_data": True,
            "has_color_season": True,
            "has_style_pref": True,
        })
        assert "body type" in msg
        assert "color season" in msg
        assert "style preferences" in msg

    def test_single_factor(self):
        msg = generate_stage_message("outfit_evaluation", "started", {
            "has_body_data": True,
        })
        assert "body type" in msg
        assert "and" not in msg

    def test_two_factors(self):
        msg = generate_stage_message("outfit_evaluation", "started", {
            "has_body_data": True,
            "has_color_season": True,
        })
        assert "body type" in msg
        assert "color season" in msg

    def test_no_factors_fallback(self):
        msg = generate_stage_message("outfit_evaluation", "started")
        assert "overall fit and style" in msg


class TestResponseFormattingCompleted:
    def test_with_count(self):
        msg = generate_stage_message("response_formatting", "completed", {
            "outfit_count": 3,
        })
        assert "3" in msg

    def test_empty_context_degrades(self):
        msg = generate_stage_message("response_formatting", "completed")
        assert msg
