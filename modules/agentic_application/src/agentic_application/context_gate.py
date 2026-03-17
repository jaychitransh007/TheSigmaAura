"""Fast rule-based context gate that short-circuits the pipeline when
the user hasn't provided enough styling context for meaningful recommendations.

Runs between context_builder (stage 3) and outfit_architect (stage 4).
Scoring is pure Python — no LLM calls, <1ms.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .schemas import CombinedContext, ConversationMemory

# ---------------------------------------------------------------------------
# Signal keywords (reuse occasion_resolver phrase lists by reference)
# ---------------------------------------------------------------------------

_OCCASION_KEYWORDS: set[str] = {
    "black tie", "business casual", "smart casual", "work meeting",
    "date night", "garden party", "cocktail party", "job interview",
    "wedding", "office", "party", "festival", "brunch", "trip",
    "vacation", "formal", "casual", "work", "date", "dinner",
    "graduation", "prom", "funeral", "church", "gym", "beach",
    "concert", "meeting", "interview", "gala",
}

_CATEGORY_KEYWORDS: set[str] = {
    "outfit", "dress", "suit", "top", "bottom", "jeans", "shirt",
    "blouse", "skirt", "pants", "jacket", "coat", "shoes", "sneakers",
    "heels", "boots", "accessory", "bag", "scarf", "tie", "blazer",
    "cardigan", "sweater", "hoodie", "shorts", "jumpsuit", "romper",
}

_FORMALITY_KEYWORDS: set[str] = {
    "casual", "formal", "smart casual", "business casual",
    "semi formal", "dressy", "relaxed", "elegant", "polished",
}

_STYLE_KEYWORDS: set[str] = {
    "minimalist", "bold", "streetwear", "classic", "vintage", "retro",
    "preppy", "bohemian", "edgy", "sporty", "chic", "modern",
    "monochrome", "colorful", "neutral", "dark", "light", "bright",
}

_SEASON_KEYWORDS: set[str] = {
    "summer", "winter", "spring", "fall", "autumn", "warm", "cold",
    "hot", "rainy", "snowy", "humid",
}

_BYPASS_PHRASES: list[str] = [
    "just show me", "surprise me", "anything works", "show me anything",
    "whatever you think", "dealer's choice", "you pick", "you choose",
    "i don't care", "i dont care", "anything is fine", "up to you",
]

# ---------------------------------------------------------------------------
# Question templates (pick the single highest-value missing signal)
# ---------------------------------------------------------------------------

_QUESTIONS: dict[str, tuple[str, list[str]]] = {
    "occasion": (
        "What's the occasion? (e.g., date night, office meeting, casual weekend)",
        ["Date night", "Office meeting", "Casual weekend", "Wedding guest"],
    ),
    "category": (
        "What kind of piece are you looking for? (e.g., complete outfit, a top to pair with jeans)",
        ["Complete outfit", "Just a top", "Dress", "Casual basics"],
    ),
    "formality": (
        "How dressed up do you want to be? (casual, smart casual, formal)",
        ["Casual", "Smart casual", "Semi-formal", "Formal"],
    ),
    "style": (
        "Any style direction? (minimalist, bold colors, streetwear, classic)",
        ["Minimalist", "Bold colors", "Streetwear", "Classic"],
    ),
}

# Priority order for question selection (highest-value first)
_SIGNAL_PRIORITY: list[str] = ["occasion", "category", "formality", "style"]


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class ContextGateResult:
    sufficient: bool
    score: float
    missing_signal: Optional[str] = None
    question: str = ""
    quick_replies: List[str] = field(default_factory=list)
    bypass_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text_contains_any(text: str, keywords: set[str]) -> bool:
    """Check if lowered text contains any keyword phrase."""
    for kw in keywords:
        if kw in text:
            return True
    return False


def _has_bypass(text: str) -> Optional[str]:
    """Return the bypass phrase if user explicitly wants to skip clarification."""
    lowered = text.lower()
    for phrase in _BYPASS_PHRASES:
        if phrase in lowered:
            return phrase
    return None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_signals(combined: CombinedContext) -> tuple[float, list[str]]:
    """Return (total_score, list_of_present_signal_names)."""
    score = 0.0
    present: list[str] = []
    # Scan current message + all prior user messages from history
    text_parts = [combined.live.user_need]
    for turn in (combined.conversation_history or []):
        if turn.get("role") == "user":
            text_parts.append(turn.get("content", ""))
    lowered = " ".join(text_parts).lower()
    memory = combined.conversation_memory

    # Occasion identified (2.0 pts)
    has_occasion = bool(combined.live.occasion_signal)
    if not has_occasion and memory:
        has_occasion = bool(memory.occasion_signal)
    if not has_occasion:
        has_occasion = _text_contains_any(lowered, _OCCASION_KEYWORDS)
    if has_occasion:
        score += 2.0
        present.append("occasion")

    # Formality level set (1.0 pts)
    has_formality = bool(combined.live.formality_hint)
    if not has_formality and memory:
        has_formality = bool(memory.formality_hint)
    if not has_formality:
        has_formality = _text_contains_any(lowered, _FORMALITY_KEYWORDS)
    if has_formality:
        score += 1.0
        present.append("formality")

    # Specific need/category stated (1.0 pts)
    has_category = bool(combined.live.specific_needs)
    if not has_category and memory:
        has_category = bool(memory.specific_needs)
    if not has_category:
        has_category = _text_contains_any(lowered, _CATEGORY_KEYWORDS)
    if has_category:
        score += 1.0
        present.append("category")

    # Time/season context (0.5 pts)
    has_season = bool(combined.live.time_hint)
    if not has_season and memory:
        has_season = bool(memory.time_hint)
    if not has_season:
        has_season = _text_contains_any(lowered, _SEASON_KEYWORDS)
    if has_season:
        score += 0.5
        present.append("season")

    # Style preference expressed (0.5 pts)
    has_style = _text_contains_any(lowered, _STYLE_KEYWORDS)
    if not has_style and memory:
        has_style = bool(memory.specific_needs)
    if has_style:
        score += 0.5
        present.append("style")

    # Follow-up turn bonus (1.0 pts)
    if memory and (memory.occasion_signal or memory.formality_hint or memory.followup_count > 0):
        score += 1.0
        present.append("followup_bonus")

    return score, present


def _pick_question(present_signals: list[str]) -> tuple[str, str, list[str]]:
    """Pick the single highest-value missing signal and return
    (signal_name, question_text, quick_replies)."""
    for signal in _SIGNAL_PRIORITY:
        if signal not in present_signals:
            question, chips = _QUESTIONS[signal]
            return signal, question, chips
    # All signals present — fallback (shouldn't happen if threshold is set right)
    return "occasion", _QUESTIONS["occasion"][0], _QUESTIONS["occasion"][1]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_THRESHOLD = 3.0
_MAX_CONSECUTIVE_BLOCKS = 2


def evaluate(
    combined_context: CombinedContext,
    consecutive_gate_blocks: int = 0,
) -> ContextGateResult:
    """Evaluate whether the conversation has enough context to produce
    meaningful recommendations.

    Args:
        combined_context: The assembled context from stages 1-3.
        consecutive_gate_blocks: How many consecutive turns the gate has
            already blocked. After ``_MAX_CONSECUTIVE_BLOCKS`` the gate
            force-passes to avoid frustrating the user.

    Returns:
        A ``ContextGateResult`` indicating whether to proceed or short-circuit.
    """
    user_text = combined_context.live.user_need

    # --- Bypass: explicit "just show me" / "surprise me" ---
    bypass = _has_bypass(user_text)
    if bypass:
        return ContextGateResult(
            sufficient=True,
            score=_THRESHOLD,
            bypass_reason=f"bypass_phrase:{bypass}",
        )

    # --- Bypass: follow-up / refinement turn ---
    if combined_context.live.is_followup:
        return ContextGateResult(
            sufficient=True,
            score=_THRESHOLD,
            bypass_reason="followup_turn",
        )

    # --- Bypass: max consecutive blocks reached ---
    if consecutive_gate_blocks >= _MAX_CONSECUTIVE_BLOCKS:
        return ContextGateResult(
            sufficient=True,
            score=0.0,
            bypass_reason="max_consecutive_blocks",
        )

    # --- Score signals ---
    score, present = _score_signals(combined_context)

    if score >= _THRESHOLD:
        return ContextGateResult(sufficient=True, score=score)

    # Insufficient — pick a clarifying question
    missing_signal, question, chips = _pick_question(present)
    return ContextGateResult(
        sufficient=False,
        score=score,
        missing_signal=missing_signal,
        question=question,
        quick_replies=chips,
    )
