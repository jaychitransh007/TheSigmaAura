from __future__ import annotations

import re
from typing import Any, Dict, List

from .schemas import IntentClassification


_URL_RE = re.compile(r"https?://\S+")

_STYLE_PHRASES = (
    "what style",
    "which style",
    "style would look good",
    "style suits me",
    "what suits me",
)
_EXPLANATION_PHRASES = (
    "why did you",
    "why this",
    "why these",
    "why that",
    "why recommend",
    "explain this",
    "explain why",
)
_FEEDBACK_PHRASES = ("i like", "i don't like", "i dont like", "i dislike", "love this", "hate this")
_WARDROBE_PHRASES = ("add to wardrobe", "save this to wardrobe", "save this in my wardrobe", "my wardrobe")
_PAIRING_PHRASES = ("what goes with", "pair with", "pair this", "what can i wear with")
_OUTFIT_CHECK_PHRASES = ("outfit check", "how does this look", "how do i look", "what do you think of this outfit")
_TRYON_PHRASES = ("try this on me", "show this on me", "virtual try on", "virtual try-on")
_GARMENT_ON_ME_PHRASES = ("look on me", "look like on me", "would this suit me", "how will this look on me")
_CAPSULE_PHRASES = ("capsule", "packing list", "pack for", "trip outfits", "travel outfits", "workweek outfits")
_SHOPPING_PHRASES = ("should i buy", "buy or skip", "worth buying", "worth it")


def classify(
    message: str,
    *,
    previous_context: Dict[str, Any] | None = None,
) -> IntentClassification:
    previous_context = dict(previous_context or {})
    lowered = str(message or "").strip().lower()
    has_url = bool(_URL_RE.search(lowered))
    has_previous_recommendations = bool(previous_context.get("last_recommendations"))

    if _has_phrase(lowered, _TRYON_PHRASES):
        return IntentClassification(
            primary_intent="virtual_tryon_request",
            confidence=0.97,
            reason_codes=["tryon_phrase"],
        )

    if _has_phrase(lowered, _EXPLANATION_PHRASES) and has_previous_recommendations:
        return IntentClassification(
            primary_intent="explanation_request",
            confidence=0.96,
            reason_codes=["explanation_phrase", "has_previous_recommendations"],
        )

    if _has_phrase(lowered, _STYLE_PHRASES):
        return IntentClassification(
            primary_intent="style_discovery",
            confidence=0.95,
            reason_codes=["style_phrase"],
        )

    if _has_phrase(lowered, _FEEDBACK_PHRASES) and has_previous_recommendations:
        return IntentClassification(
            primary_intent="feedback_submission",
            confidence=0.88,
            reason_codes=["feedback_phrase", "has_previous_recommendations"],
        )

    if _has_phrase(lowered, _WARDROBE_PHRASES):
        return IntentClassification(
            primary_intent="wardrobe_ingestion",
            confidence=0.9,
            reason_codes=["wardrobe_phrase"],
        )

    if _has_phrase(lowered, _PAIRING_PHRASES):
        secondary = ["shopping_decision"] if has_url else []
        reasons = ["pairing_phrase"]
        if has_url:
            reasons.append("url_present")
        return IntentClassification(
            primary_intent="pairing_request",
            confidence=0.92,
            secondary_intents=secondary,
            reason_codes=reasons,
        )

    if _has_phrase(lowered, _OUTFIT_CHECK_PHRASES):
        return IntentClassification(
            primary_intent="outfit_check",
            confidence=0.9,
            reason_codes=["outfit_check_phrase"],
        )

    if _has_phrase(lowered, _GARMENT_ON_ME_PHRASES):
        return IntentClassification(
            primary_intent="garment_on_me_request",
            confidence=0.9,
            reason_codes=["garment_on_me_phrase"],
        )

    if _has_phrase(lowered, _CAPSULE_PHRASES):
        return IntentClassification(
            primary_intent="capsule_or_trip_planning",
            confidence=0.9,
            reason_codes=["capsule_or_trip_phrase"],
        )

    if has_url or _has_phrase(lowered, _SHOPPING_PHRASES):
        reasons = ["shopping_phrase"] if _has_phrase(lowered, _SHOPPING_PHRASES) else []
        if has_url:
            reasons.append("url_present")
        return IntentClassification(
            primary_intent="shopping_decision",
            confidence=0.89 if has_url else 0.92,
            reason_codes=reasons or ["shopping_default"],
        )

    return IntentClassification(
        primary_intent="occasion_recommendation",
        confidence=0.62,
        reason_codes=["default_recommendation_path"],
    )


def _has_phrase(text: str, phrases: List[str] | tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)
