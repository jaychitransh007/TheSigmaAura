from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from user_profiler.config import get_api_key

from ..intent_registry import Action, Intent, intent_enum_values, action_enum_values
from ..schemas import (
    CopilotActionParameters,
    CopilotPlanResult,
    CopilotResolvedContext,
    UserContext,
)

_log = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+")


def _load_prompt() -> str:
    prompt_dir = Path(__file__).resolve()
    for base in [prompt_dir.parent] + list(prompt_dir.parents):
        candidate = base / "prompt" / "copilot_planner.md"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()
    raise FileNotFoundError("Could not locate prompt/copilot_planner.md")


_PLAN_JSON_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "name": "copilot_plan",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "intent",
            "intent_confidence",
            "action",
            "context_sufficient",
            "assistant_message",
            "follow_up_suggestions",
            "resolved_context",
            "action_parameters",
        ],
        "properties": {
            "intent": {
                "type": "string",
                "enum": intent_enum_values(),
            },
            "intent_confidence": {"type": "number"},
            "action": {
                "type": "string",
                "enum": action_enum_values(),
            },
            "context_sufficient": {"type": "boolean"},
            "assistant_message": {"type": "string"},
            "follow_up_suggestions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "resolved_context": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "occasion_signal",
                    "formality_hint",
                    "time_hint",
                    "specific_needs",
                    "is_followup",
                    "followup_intent",
                    "style_goal",
                    "source_preference",
                    "target_product_type",
                    "weather_context",
                    "time_of_day",
                ],
                "properties": {
                    "occasion_signal": {"type": ["string", "null"]},
                    "formality_hint": {"type": ["string", "null"]},
                    "time_hint": {"type": ["string", "null"]},
                    "specific_needs": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "is_followup": {"type": "boolean"},
                    "followup_intent": {"type": ["string", "null"]},
                    "style_goal": {"type": "string"},
                    "source_preference": {
                        "type": "string",
                        "enum": ["auto", "wardrobe", "catalog"],
                    },
                    "target_product_type": {"type": "string"},
                    "weather_context": {"type": "string"},
                    "time_of_day": {"type": "string"},
                },
            },
            "action_parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "purchase_intent",
                    "target_piece",
                    "detected_colors",
                    "detected_garments",
                    "product_urls",
                    "feedback_event_type",
                    "wardrobe_item_title",
                ],
                "properties": {
                    "purchase_intent": {"type": "boolean"},
                    "target_piece": {"type": ["string", "null"]},
                    "detected_colors": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "detected_garments": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "product_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "feedback_event_type": {"type": ["string", "null"]},
                    "wardrobe_item_title": {"type": ["string", "null"]},
                },
            },
        },
    },
}


def _nested_value(payload: Dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, dict):
        return str(value.get("value") or "").strip()
    return str(value or "").strip()


def build_planner_input(
    *,
    message: str,
    user_context: UserContext,
    conversation_history: List[Dict[str, str]],
    previous_context: Dict[str, Any],
    profile_confidence_pct: int,
    has_person_image: bool,
    has_attached_image: bool = False,
) -> Dict[str, Any]:
    derived = dict(user_context.derived_interpretations or {})
    style_pref = dict(user_context.style_preference or {})

    wardrobe_items = list(user_context.wardrobe_items or [])
    top_items = [
        {
            "title": str(item.get("title") or ""),
            "garment_category": str(item.get("garment_category") or ""),
            "primary_color": str(item.get("primary_color") or ""),
        }
        for item in wardrobe_items[:5]
    ]

    previous_recs = previous_context.get("last_recommendations")
    previous_recs_summary: Optional[List[Dict[str, Any]]] = None
    if isinstance(previous_recs, list) and previous_recs:
        previous_recs_summary = [
            {
                "rank": rec.get("rank"),
                "title": rec.get("title"),
                "primary_colors": rec.get("primary_colors", []),
                "garment_categories": rec.get("garment_categories", []),
            }
            for rec in previous_recs[:3]
        ]

    url_detected = None
    url_match = _URL_RE.search(message)
    if url_match:
        url_detected = url_match.group(0)

    return {
        "user_message": message.strip(),
        "conversation_history": conversation_history[-4:],
        "user_profile": {
            "gender": user_context.gender,
            "seasonal_color_group": _nested_value(derived, "SeasonalColorGroup") or None,
            "base_colors": (derived.get("BaseColors") or {}).get("value") or [],
            "accent_colors": (derived.get("AccentColors") or {}).get("value") or [],
            "avoid_colors": (derived.get("AvoidColors") or {}).get("value") or [],
            "contrast_level": _nested_value(derived, "ContrastLevel") or None,
            "frame_structure": _nested_value(derived, "FrameStructure") or None,
            "height_category": _nested_value(derived, "HeightCategory") or None,
            "primary_archetype": str(style_pref.get("primaryArchetype") or "") or None,
            "secondary_archetype": str(style_pref.get("secondaryArchetype") or "") or None,
            "profile_richness": user_context.profile_richness,
        },
        "wardrobe_summary": {
            "count": len(wardrobe_items),
            "top_items": top_items,
        },
        "previous_recommendations": previous_recs_summary,
        "previous_occasion": str(previous_context.get("last_occasion") or "") or None,
        "previous_intent": str(previous_context.get("last_intent") or "") or None,
        "profile_confidence_pct": profile_confidence_pct,
        "has_person_image": has_person_image,
        "has_attached_image": has_attached_image,
        "url_detected": url_detected,
    }


class CopilotPlanner:
    def __init__(self, model: str = "gpt-5.4") -> None:
        self._client = OpenAI(api_key=get_api_key())
        self._model = model
        self._system_prompt = _load_prompt()

    def plan(self, planner_input: Dict[str, Any]) -> CopilotPlanResult:
        response = self._client.responses.create(
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": self._system_prompt}],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(planner_input, indent=2, default=str),
                        }
                    ],
                },
            ],
            text={"format": _PLAN_JSON_SCHEMA},
        )

        raw = json.loads(getattr(response, "output_text", "") or "{}")
        return self._parse_result(raw)

    def _parse_result(self, raw: Dict[str, Any]) -> CopilotPlanResult:
        resolved_raw = raw.get("resolved_context") or {}
        resolved = CopilotResolvedContext(
            occasion_signal=resolved_raw.get("occasion_signal"),
            formality_hint=resolved_raw.get("formality_hint"),
            time_hint=resolved_raw.get("time_hint"),
            specific_needs=resolved_raw.get("specific_needs") or [],
            is_followup=bool(resolved_raw.get("is_followup")),
            followup_intent=resolved_raw.get("followup_intent"),
            style_goal=str(resolved_raw.get("style_goal") or ""),
            source_preference=str(resolved_raw.get("source_preference") or "auto"),
            target_product_type=str(resolved_raw.get("target_product_type") or ""),
            weather_context=str(resolved_raw.get("weather_context") or ""),
            time_of_day=str(resolved_raw.get("time_of_day") or ""),
        )

        params_raw = raw.get("action_parameters") or {}
        action_params = CopilotActionParameters(
            purchase_intent=bool(params_raw.get("purchase_intent")),
            target_piece=params_raw.get("target_piece"),
            detected_colors=params_raw.get("detected_colors") or [],
            detected_garments=params_raw.get("detected_garments") or [],
            product_urls=params_raw.get("product_urls") or [],
            feedback_event_type=params_raw.get("feedback_event_type"),
            wardrobe_item_title=params_raw.get("wardrobe_item_title"),
        )

        return CopilotPlanResult(
            intent=str(raw.get("intent") or Intent.OCCASION_RECOMMENDATION),
            intent_confidence=float(raw.get("intent_confidence") or 0.0),
            action=str(raw.get("action") or Action.RESPOND_DIRECTLY),
            context_sufficient=bool(raw.get("context_sufficient", True)),
            assistant_message=str(raw.get("assistant_message") or ""),
            follow_up_suggestions=list(raw.get("follow_up_suggestions") or []),
            resolved_context=resolved,
            action_parameters=action_params,
        )
