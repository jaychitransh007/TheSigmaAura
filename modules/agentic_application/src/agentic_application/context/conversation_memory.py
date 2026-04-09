from __future__ import annotations

from typing import Any, Dict, Iterable, List

from ..intent_registry import FollowUpIntent
from ..schemas import ConversationMemory, LiveContext


_FORMALITY_ORDER = [
    "casual",
    "smart_casual",
    "business_casual",
    "semi_formal",
    "formal",
    "ultra_formal",
]


def _dedupe_preserve_order(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _shift_formality(current: str | None, *, delta: int) -> str | None:
    if not current or current not in _FORMALITY_ORDER:
        return current
    index = _FORMALITY_ORDER.index(current)
    next_index = min(max(index + delta, 0), len(_FORMALITY_ORDER) - 1)
    return _FORMALITY_ORDER[next_index]


def _parse_previous_memory(previous_context: Dict[str, Any]) -> ConversationMemory:
    raw = dict(previous_context.get("memory") or {})
    last_live_context = dict(previous_context.get("last_live_context") or {})
    if not raw:
        raw = {
            "occasion_signal": previous_context.get("last_occasion"),
            "formality_hint": last_live_context.get("formality_hint"),
            "time_hint": last_live_context.get("time_hint"),
            "specific_needs": last_live_context.get("specific_needs") or [],
            # plan_type removed — direction_types are per-direction now
        }
    try:
        return ConversationMemory.model_validate(raw)
    except Exception:
        return ConversationMemory()


def build_conversation_memory(
    previous_context: Dict[str, Any] | None,
    live_context: LiveContext,
    *,
    current_intent: str | None = None,
    channel: str | None = None,
    wardrobe_item_count: int = 0,
) -> ConversationMemory:
    previous_context = dict(previous_context or {})
    prior = _parse_previous_memory(previous_context)
    recommendation_ids = [
        str(row.get("candidate_id") or "")
        for row in list(previous_context.get("last_recommendations") or [])
        if isinstance(row, dict)
    ]
    recommendation_ids = [value for value in recommendation_ids if value]

    occasion_signal = live_context.occasion_signal or prior.occasion_signal
    formality_hint = live_context.formality_hint or prior.formality_hint
    time_hint = live_context.time_hint or prior.time_hint

    if live_context.is_followup:
        specific_needs = _dedupe_preserve_order(
            [*prior.specific_needs, *live_context.specific_needs]
        )
        followup_count = prior.followup_count + 1
    else:
        specific_needs = _dedupe_preserve_order(live_context.specific_needs)
        followup_count = prior.followup_count

    if live_context.followup_intent == FollowUpIntent.INCREASE_FORMALITY:
        formality_hint = _shift_formality(formality_hint, delta=1)
    elif live_context.followup_intent == FollowUpIntent.DECREASE_FORMALITY:
        formality_hint = _shift_formality(formality_hint, delta=-1)

    recent_intents = _dedupe_preserve_order([*prior.recent_intents, str(current_intent or "").strip()])
    recent_channels = _dedupe_preserve_order([*prior.recent_channels, str(channel or "").strip()])

    return ConversationMemory(
        occasion_signal=occasion_signal,
        formality_hint=formality_hint,
        time_hint=time_hint,
        specific_needs=specific_needs,
        followup_count=followup_count,
        last_recommendation_ids=_dedupe_preserve_order(
            [*prior.last_recommendation_ids, *recommendation_ids]
        ),
        recent_intents=recent_intents,
        recent_channels=recent_channels,
        last_user_need=str(live_context.user_need or "").strip() or prior.last_user_need,
        wardrobe_item_count=max(int(prior.wardrobe_item_count or 0), int(wardrobe_item_count or 0)),
        wardrobe_memory_enabled=bool(prior.wardrobe_memory_enabled or wardrobe_item_count > 0),
    )


def apply_conversation_memory(
    live_context: LiveContext,
    memory: ConversationMemory,
) -> LiveContext:
    if not live_context.is_followup:
        return live_context

    return live_context.model_copy(
        update={
            "occasion_signal": live_context.occasion_signal or memory.occasion_signal,
            "formality_hint": live_context.formality_hint or memory.formality_hint,
            "time_hint": live_context.time_hint or memory.time_hint,
            "specific_needs": _dedupe_preserve_order(
                [*memory.specific_needs, *live_context.specific_needs]
            ),
        }
    )


__all__ = [
    "apply_conversation_memory",
    "build_conversation_memory",
]
