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
            # May 3 2026: outfit_assembly retired → outfit_composer.
            ("outfit_composer", "started"),
            ("visual_evaluation", "completed"),
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
        ("outfit_composer", "completed"),
        ("outfit_rater", "completed"),
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
        assert generate_stage_message("outfit_composer", "completed", {"outfit_count": 7}) == ""
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
        "direction_types,expected_fragment",
        [
            (["paired"], "two-piece pairings"),
            (["complete"], "complete sets"),
            (["complete", "paired", "three_piece"], "complete sets"),
        ],
    )
    def test_direction_types_produce_distinct_descriptions(self, direction_types, expected_fragment):
        msg = generate_stage_message("outfit_architect", "completed", {
            "direction_types": direction_types,
            "direction_count": 3,
        })
        assert expected_fragment in msg
        assert "3" in msg

    def test_without_direction_count(self):
        msg = generate_stage_message("outfit_architect", "completed", {
            "direction_types": ["paired", "three_piece"],
        })
        assert "two-piece pairings" in msg
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


class TestVisualEvaluationStarted:
    """May 3, 2026: stage renamed from `outfit_evaluation` to
    `visual_evaluation` when the legacy text evaluator was retired and
    the LLM Composer + Rater + visual_evaluator became the canonical
    pipeline."""

    def test_all_factors(self):
        msg = generate_stage_message("visual_evaluation", "started", {
            "has_body_data": True,
            "has_color_season": True,
            "has_style_pref": True,
        })
        assert "body type" in msg
        assert "color season" in msg
        assert "style preferences" in msg

    def test_single_factor(self):
        msg = generate_stage_message("visual_evaluation", "started", {
            "has_body_data": True,
        })
        assert "body type" in msg
        assert "and" not in msg

    def test_two_factors(self):
        msg = generate_stage_message("visual_evaluation", "started", {
            "has_body_data": True,
            "has_color_season": True,
        })
        assert "body type" in msg
        assert "color season" in msg

    def test_no_factors_fallback(self):
        msg = generate_stage_message("visual_evaluation", "started")
        assert "overall fit and style" in msg

    def test_target_count_appears_when_provided(self):
        msg = generate_stage_message("visual_evaluation", "started", {
            "has_body_data": True,
            "target_count": 3,
        })
        assert "3 looks" in msg


class TestOutfitRaterStarted:
    """The Rater is the new LLM scoring stage between Composer and
    visual evaluator (May 3, 2026)."""

    def test_with_count(self):
        msg = generate_stage_message("outfit_rater", "started", {"composed_count": 7})
        assert "7" in msg
        assert "Rating" in msg

    def test_without_count_falls_back(self):
        msg = generate_stage_message("outfit_rater", "started")
        assert msg
        assert "Rating" in msg


