import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from agentic_application.context_gate import (
    ContextGateResult,
    evaluate,
    _THRESHOLD,
    _MAX_CONSECUTIVE_BLOCKS,
)
from agentic_application.schemas import (
    CombinedContext,
    ConversationMemory,
    LiveContext,
    UserContext,
)


def _make_context(
    message: str,
    *,
    occasion_signal: str | None = None,
    formality_hint: str | None = None,
    time_hint: str | None = None,
    specific_needs: list[str] | None = None,
    is_followup: bool = False,
    followup_intent: str | None = None,
    memory: ConversationMemory | None = None,
) -> CombinedContext:
    live = LiveContext(
        user_need=message,
        occasion_signal=occasion_signal,
        formality_hint=formality_hint,
        time_hint=time_hint,
        specific_needs=specific_needs or [],
        is_followup=is_followup,
        followup_intent=followup_intent,
    )
    user = UserContext(user_id="test-user", gender="male")
    return CombinedContext(
        user=user,
        live=live,
        conversation_memory=memory,
    )


class TestContextGateScoring(unittest.TestCase):
    """Test signal scoring for various input combinations."""

    def test_vague_message_blocks(self):
        """A vague message like 'I need an outfit' should be blocked."""
        ctx = _make_context("I need something nice")
        result = evaluate(ctx)
        self.assertFalse(result.sufficient)
        self.assertLess(result.score, _THRESHOLD)
        self.assertIsNotNone(result.missing_signal)
        self.assertTrue(len(result.question) > 0)
        self.assertTrue(len(result.quick_replies) > 0)

    def test_occasion_gives_2_points(self):
        ctx = _make_context("I need something for a wedding")
        result = evaluate(ctx)
        # "wedding" → occasion (2.0) + category via "outfit" not present
        # but "wedding" is in occasion keywords → 2.0 pts
        self.assertGreaterEqual(result.score, 2.0)

    def test_occasion_plus_category_passes(self):
        """Occasion (2.0) + category (1.0) = 3.0, meets threshold."""
        ctx = _make_context("I need a dress for a wedding")
        result = evaluate(ctx)
        self.assertTrue(result.sufficient)
        self.assertGreaterEqual(result.score, _THRESHOLD)

    def test_occasion_signal_from_live_context(self):
        """Pre-resolved occasion_signal in LiveContext counts."""
        ctx = _make_context(
            "help me pick something",
            occasion_signal="date_night",
            formality_hint="smart_casual",
        )
        result = evaluate(ctx)
        # occasion (2.0) + formality (1.0) = 3.0
        self.assertTrue(result.sufficient)

    def test_memory_signals_count(self):
        """Signals in conversation_memory contribute to the score."""
        memory = ConversationMemory(
            occasion_signal="office",
            formality_hint="business_casual",
        )
        ctx = _make_context("show me more options", memory=memory)
        result = evaluate(ctx)
        # Memory has occasion + formality → contributes to score
        # Plus followup_bonus since memory has occasion_signal
        self.assertGreaterEqual(result.score, 2.0)

    def test_all_signals_high_score(self):
        """A very specific request should score well above threshold."""
        ctx = _make_context(
            "I need a minimalist summer dress for a casual brunch",
            occasion_signal="brunch",
            formality_hint="casual",
            time_hint="daytime",
            specific_needs=["comfort_priority"],
        )
        result = evaluate(ctx)
        self.assertTrue(result.sufficient)
        self.assertGreater(result.score, _THRESHOLD)

    def test_category_keyword_in_message(self):
        """Mentioning a garment category adds 1.0 pts."""
        ctx = _make_context("I want a jacket")
        result = evaluate(ctx)
        self.assertGreaterEqual(result.score, 1.0)

    def test_style_keyword_in_message(self):
        """Style keyword adds 0.5 pts."""
        ctx = _make_context("something minimalist")
        result = evaluate(ctx)
        self.assertGreaterEqual(result.score, 0.5)

    def test_season_keyword_in_message(self):
        """Season keyword adds 0.5 pts."""
        ctx = _make_context("something for summer")
        result = evaluate(ctx)
        self.assertGreaterEqual(result.score, 0.5)


class TestContextGateBypass(unittest.TestCase):
    """Test bypass rules (gate always passes)."""

    def test_surprise_me_bypasses(self):
        ctx = _make_context("surprise me")
        result = evaluate(ctx)
        self.assertTrue(result.sufficient)
        self.assertIsNotNone(result.bypass_reason)
        self.assertIn("bypass_phrase", result.bypass_reason)

    def test_just_show_me_bypasses(self):
        ctx = _make_context("just show me something")
        result = evaluate(ctx)
        self.assertTrue(result.sufficient)
        self.assertIn("bypass_phrase", result.bypass_reason)

    def test_anything_works_bypasses(self):
        ctx = _make_context("anything works, I'm easy")
        result = evaluate(ctx)
        self.assertTrue(result.sufficient)

    def test_followup_turn_bypasses(self):
        """Follow-up refinements should always pass the gate."""
        ctx = _make_context(
            "show me something more casual",
            is_followup=True,
            followup_intent="decrease_formality",
        )
        result = evaluate(ctx)
        self.assertTrue(result.sufficient)
        self.assertEqual(result.bypass_reason, "followup_turn")

    def test_you_pick_bypasses(self):
        ctx = _make_context("you pick for me")
        result = evaluate(ctx)
        self.assertTrue(result.sufficient)


class TestMaxConsecutiveBlocks(unittest.TestCase):
    """Test the max-consecutive-blocks cap."""

    def test_first_block_allowed(self):
        ctx = _make_context("help me")
        result = evaluate(ctx, consecutive_gate_blocks=0)
        self.assertFalse(result.sufficient)

    def test_second_block_allowed(self):
        ctx = _make_context("umm not sure")
        result = evaluate(ctx, consecutive_gate_blocks=1)
        self.assertFalse(result.sufficient)

    def test_third_block_force_passes(self):
        """After 2 consecutive blocks, force-pass to avoid frustration."""
        ctx = _make_context("I don't know")
        result = evaluate(ctx, consecutive_gate_blocks=2)
        self.assertTrue(result.sufficient)
        self.assertEqual(result.bypass_reason, "max_consecutive_blocks")

    def test_beyond_max_still_passes(self):
        ctx = _make_context("whatever")
        result = evaluate(ctx, consecutive_gate_blocks=5)
        self.assertTrue(result.sufficient)


class TestQuestionSelection(unittest.TestCase):
    """Test that the highest-value missing signal is picked."""

    def test_occasion_asked_first(self):
        """When nothing is known, occasion is the first question."""
        ctx = _make_context("help me look good")
        result = evaluate(ctx)
        self.assertFalse(result.sufficient)
        self.assertEqual(result.missing_signal, "occasion")

    def test_category_asked_when_occasion_present(self):
        """If occasion is known, ask about category next."""
        ctx = _make_context(
            "something for work",
            occasion_signal="office",
        )
        result = evaluate(ctx)
        # occasion (2.0) + followup_bonus won't trigger since no memory
        # score = 2.0, below 3.0
        if not result.sufficient:
            self.assertEqual(result.missing_signal, "category")

    def test_only_one_question(self):
        """Gate should never ask multiple questions."""
        ctx = _make_context("hello")
        result = evaluate(ctx)
        self.assertFalse(result.sufficient)
        # Only one question string, not multiple
        self.assertNotIn("\n", result.question)

    def test_quick_replies_provided(self):
        ctx = _make_context("I need help")
        result = evaluate(ctx)
        self.assertFalse(result.sufficient)
        self.assertGreater(len(result.quick_replies), 0)
        self.assertLessEqual(len(result.quick_replies), 5)


class TestSufficientContextPassesThrough(unittest.TestCase):
    """Test that sufficient context passes through without questions."""

    def test_specific_request_passes(self):
        ctx = _make_context(
            "I need a formal outfit for a wedding",
            occasion_signal="wedding",
            formality_hint="formal",
        )
        result = evaluate(ctx)
        self.assertTrue(result.sufficient)
        self.assertEqual(result.question, "")
        self.assertEqual(result.quick_replies, [])
        self.assertIsNone(result.missing_signal)

    def test_sufficient_no_bypass_reason(self):
        """When passing by score, bypass_reason should be None."""
        ctx = _make_context(
            "I need a casual dress for brunch",
            occasion_signal="brunch",
            formality_hint="casual",
        )
        result = evaluate(ctx)
        self.assertTrue(result.sufficient)
        self.assertIsNone(result.bypass_reason)


class TestMultiTurnAccumulation(unittest.TestCase):
    """Test that signals from prior turns accumulate via memory,
    so the gate doesn't keep asking the same question."""

    def test_occasion_from_memory_prevents_re_asking(self):
        """Turn 1 blocked on occasion. User replied 'date night'.
        On turn 2 the memory carries occasion_signal='date_night'.
        Gate should NOT ask about occasion again."""
        memory = ConversationMemory(
            occasion_signal="date_night",
            formality_hint="smart_casual",
        )
        # Turn 2 message is just the reply — no occasion keyword in it
        ctx = _make_context("yes that sounds good", memory=memory)
        result = evaluate(ctx)
        # Memory has occasion (2.0) + formality (1.0) + followup_bonus (1.0) = 4.0
        self.assertTrue(result.sufficient)

    def test_accumulated_memory_passes_gate(self):
        """Memory from prior gate-blocked turn has occasion.
        Current turn adds a category keyword. Should pass easily."""
        memory = ConversationMemory(occasion_signal="wedding")
        ctx = _make_context("I need a dress", memory=memory)
        result = evaluate(ctx)
        # occasion from memory (2.0) + category keyword (1.0) + followup_bonus (1.0) = 4.0
        self.assertTrue(result.sufficient)

    def test_conversation_history_text_scanned(self):
        """Keywords in prior conversation history should contribute to scoring."""
        ctx = _make_context("show me options")
        # Add prior user message with occasion keyword in conversation_history
        ctx = ctx.model_copy(update={
            "conversation_history": [
                {"role": "user", "content": "I have a wedding coming up"},
                {"role": "assistant", "content": "What kind of piece?"},
            ]
        })
        result = evaluate(ctx)
        # "wedding" found in history → occasion (2.0)
        self.assertGreaterEqual(result.score, 2.0)

    def test_different_question_on_second_block(self):
        """If occasion is already in memory, gate should ask a different
        question, not the same one."""
        memory = ConversationMemory(occasion_signal="office")
        ctx = _make_context("hmm not sure what else", memory=memory)
        result = evaluate(ctx)
        if not result.sufficient:
            # Should NOT ask about occasion since it's already known
            self.assertNotEqual(result.missing_signal, "occasion")


if __name__ == "__main__":
    unittest.main()
