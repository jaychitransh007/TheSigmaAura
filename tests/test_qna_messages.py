"""Unit tests for the QnA transparency template engine."""

import pytest

from agentic_application.intent_registry import Action, FollowUpIntent, Intent
from agentic_application.qna_messages import generate_stage_message


class TestStaticTemplates:
    """All user-facing static template keys return non-empty strings.

    Some `*_completed` templates are deliberately empty strings — that is a
    product signal meaning "don't surface this stage in the UI" (see
    TestIntentionallySilentStages below). Those are excluded from this
    parametrize list.
    """

    @pytest.mark.parametrize(
        "stage,detail",
        [
            ("validate_request", "started"),
            ("onboarding_gate", "started"),
            ("onboarding_gate", "blocked"),
            ("copilot_planner", "started"),
            ("user_context", "started"),
            ("context_builder", "started"),
            ("outfit_architect", "started"),
            ("catalog_search", "started"),
            ("outfit_assembly", "started"),
            ("outfit_evaluation", "completed"),
            ("response_formatting", "started"),
            ("virtual_tryon", "started"),
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


class TestIntentionallySilentStages:
    """Product contract: these stages deliberately return an empty message so
    the UI's `latestVisibleStage` helper skips them and the stage bar /
    thinking bubble don't churn on every micro-transition. Changing any of
    these to non-empty text is a UX regression — it brings back the
    "15 stacked bubbles per turn" problem."""

    SILENT_STAGES = [
        ("onboarding_gate", "completed"),
        ("user_context", "completed"),
        ("context_builder", "completed"),
        ("outfit_assembly", "completed"),
        ("response_formatting", "completed"),
        ("virtual_tryon", "completed"),
    ]

    @pytest.mark.parametrize("stage,detail", SILENT_STAGES)
    def test_silent_stage_returns_empty(self, stage, detail):
        assert generate_stage_message(stage, detail) == ""

    def test_silent_stages_degrade_with_context(self):
        """Passing context to a silent stage must still return empty, not
        crash or leak raw keys."""
        assert generate_stage_message("user_context", "completed", {"richness": "full"}) == ""
        assert generate_stage_message("outfit_assembly", "completed", {"candidate_count": 15}) == ""
        assert generate_stage_message("response_formatting", "completed", {"outfit_count": 3}) == ""


class TestCopilotPlannerCompleted:
    def test_returns_primary_intent(self):
        msg = generate_stage_message("copilot_planner", "completed", {
            "primary_intent": Intent.STYLE_DISCOVERY,
        })
        assert "style discovery" in msg

    def test_without_primary_intent(self):
        msg = generate_stage_message("copilot_planner", "completed")
        assert msg  # falls back to "Intent understood."


class TestOutfitArchitectCompleted:
    @pytest.mark.parametrize(
        "plan_type,expected_fragment",
        [
            ("paired_only", "coordinated top + bottom"),
            ("complete_only", "complete one-piece looks"),
            ("mixed", "a mix of complete and paired looks"),
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
        assert "a mix of complete and paired looks" in msg
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


