from __future__ import annotations

import re
from typing import List, Optional, Tuple

from ..schemas import LiveContext


# Ordered longest-first for phrase-priority matching.
# Each entry: (phrase, occasion_signal, formality_hint, time_hint)
_OCCASION_PHRASES: List[Tuple[str, str, str, Optional[str]]] = [
    ("black tie", "black_tie", "ultra_formal", "evening"),
    ("business casual", "business_casual", "business_casual", None),
    ("smart casual", "smart_casual", "smart_casual", None),
    ("work meeting", "work_meeting", "semi_formal", None),
    ("date night", "date_night", "smart_casual", "evening"),
    ("garden party", "garden_party", "smart_casual", "daytime"),
    ("cocktail party", "cocktail_party", "semi_formal", "evening"),
    ("job interview", "job_interview", "semi_formal", None),
    ("wedding", "wedding", "formal", None),
    ("office", "office", "business_casual", None),
    ("party", "party", "smart_casual", "evening"),
    ("festival", "festival", "casual", None),
    ("brunch", "brunch", "casual", "daytime"),
    ("trip", "trip", "casual", None),
    ("vacation", "vacation", "casual", None),
    ("formal", "formal", "formal", None),
    ("casual", "casual", "casual", None),
    ("work", "work", "business_casual", None),
    ("date", "date", "smart_casual", "evening"),
]

# Specific-needs extraction.
_NEED_PHRASES: List[Tuple[str, str]] = [
    ("look taller", "elongation"),
    ("look tall", "elongation"),
    ("look slimmer", "slimming"),
    ("look slim", "slimming"),
    ("look broader", "broadening"),
    ("look broad", "broadening"),
    ("look polished", "polish"),
    ("look formal", "authority"),
    ("comfortable", "comfort_priority"),
    ("professional", "authority"),
    ("approachable", "approachability"),
]

# Follow-up intent detection.
_FOLLOWUP_PHRASES: List[Tuple[str, str]] = [
    ("more bold", "increase_boldness"),
    ("bolder", "increase_boldness"),
    ("less formal", "decrease_formality"),
    ("more casual", "decrease_formality"),
    ("more formal", "increase_formality"),
    ("different color", "change_color"),
    ("another color", "change_color"),
    ("something different", "full_alternative"),
    ("something else", "full_alternative"),
    ("more options", "more_options"),
    ("show more", "more_options"),
    ("something similar", "similar_to_previous"),
    ("like that", "similar_to_previous"),
]


def _compile_phrase_pattern(phrase: str) -> re.Pattern[str]:
    tokens = [re.escape(token) for token in phrase.split()]
    return re.compile(r"\b" + r"\s+".join(tokens) + r"\b")


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(_compile_phrase_pattern(phrase).search(text))


def resolve_occasion(
    message: str,
    *,
    has_previous_recommendations: bool = False,
) -> LiveContext:
    """Extract structured live context from the user message. Rule-based only."""
    lowered = message.lower()

    # Occasion / formality / time
    occasion_signal: Optional[str] = None
    formality_hint: Optional[str] = None
    time_hint: Optional[str] = None

    for phrase, occ, form, time in _OCCASION_PHRASES:
        if _contains_phrase(lowered, phrase):
            occasion_signal = occ
            formality_hint = form
            if time:
                time_hint = time
            break

    # Specific needs (collect all matches)
    specific_needs: List[str] = []
    for phrase, need in _NEED_PHRASES:
        if _contains_phrase(lowered, phrase) and need not in specific_needs:
            specific_needs.append(need)

    # Follow-up intent (only if prior recommendations exist)
    is_followup = False
    followup_intent: Optional[str] = None
    if has_previous_recommendations:
        for phrase, intent in _FOLLOWUP_PHRASES:
            if _contains_phrase(lowered, phrase):
                is_followup = True
                followup_intent = intent
                break
        if not is_followup and re.search(r"\b(another|instead|more|different|similar)\b", lowered):
            is_followup = True
            followup_intent = "more_options"

    return LiveContext(
        user_need=message.strip(),
        occasion_signal=occasion_signal,
        formality_hint=formality_hint,
        time_hint=time_hint,
        specific_needs=specific_needs,
        is_followup=is_followup,
        followup_intent=followup_intent,
    )
