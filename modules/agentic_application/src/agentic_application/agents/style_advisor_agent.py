"""Style Advisor Agent — Phase 12C.

LLM-backed advisory agent that generates open-ended style discovery and
explanation responses. Replaces the inline planner-text generation that
used to live inside ``copilot_planner.md`` for ``style_discovery`` and
``explanation_request`` intents.

The advisor is a complement to the orchestrator's deterministic
topical helpers (``_detect_style_advice_topic`` /
``_build_style_advice_response``), not a replacement. The orchestrator's
handler picks between them:

- Topical questions (collar, color, pattern, silhouette, archetype) →
  the deterministic helper produces the answer (fast, free, evidence-
  backed, regression-tested in Phase 11).
- Everything else (open-ended discovery, explanation) → this agent.

Two modes:

- ``discovery``  — open-ended style questions like "what defines my
                   style?" or "what should I prioritize when shopping?"
- ``explanation`` — "why did you recommend that?" against a prior turn's
                    recommendation summary.
"""

from __future__ import annotations

import json
import logging
from functools import cached_property
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from user_profiler.config import get_api_key

_log = logging.getLogger(__name__)


def _load_prompt() -> str:
    prompt_dir = Path(__file__).resolve()
    for base in [prompt_dir.parent] + list(prompt_dir.parents):
        candidate = base / "prompt" / "style_advisor.md"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()
    raise FileNotFoundError("Could not locate prompt/style_advisor.md")


_ADVICE_JSON_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "name": "style_advice",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "assistant_message",
            "bullet_points",
            "cited_attributes",
            "dominant_directions",
        ],
        "properties": {
            "assistant_message": {"type": "string"},
            "bullet_points": {
                "type": "array",
                "items": {"type": "string"},
            },
            "cited_attributes": {
                "type": "array",
                "items": {"type": "string"},
            },
            "dominant_directions": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    },
}


class StyleAdvice:
    """Structured advisory result."""

    def __init__(self, raw: Dict[str, Any]) -> None:
        self.assistant_message: str = str(raw.get("assistant_message") or "").strip()
        self.bullet_points: List[str] = [
            str(b).strip() for b in (raw.get("bullet_points") or []) if str(b).strip()
        ]
        self.cited_attributes: List[str] = [
            str(a).strip() for a in (raw.get("cited_attributes") or []) if str(a).strip()
        ]
        self.dominant_directions: List[str] = [
            str(d).strip() for d in (raw.get("dominant_directions") or []) if str(d).strip()
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assistant_message": self.assistant_message,
            "bullet_points": self.bullet_points,
            "cited_attributes": self.cited_attributes,
            "dominant_directions": self.dominant_directions,
        }

    def render_assistant_message(self) -> str:
        """Combine the prose answer with the actionable bullets for the chat UI."""
        parts: List[str] = []
        if self.assistant_message:
            parts.append(self.assistant_message)
        if self.bullet_points:
            bullet_lines = "\n".join(f"• {bullet}" for bullet in self.bullet_points)
            parts.append(bullet_lines)
        return "\n\n".join(parts).strip()


def _nested_value(payload: Dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, dict):
        return str(value.get("value") or "").strip()
    return str(value or "").strip()


def _build_user_profile_payload(user_context: Any) -> Dict[str, Any]:
    derived = dict(getattr(user_context, "derived_interpretations", {}) or {})
    style_pref = dict(getattr(user_context, "style_preference", {}) or {})
    analysis = dict(getattr(user_context, "analysis_attributes", {}) or {})
    return {
        "gender": getattr(user_context, "gender", ""),
        "seasonal_color_group": _nested_value(derived, "SeasonalColorGroup") or None,
        "sub_season": _nested_value(derived, "SubSeason") or None,
        "skin_hair_contrast": _nested_value(derived, "SkinHairContrast") or None,
        "base_colors": (derived.get("BaseColors") or {}).get("value") or [],
        "accent_colors": (derived.get("AccentColors") or {}).get("value") or [],
        "avoid_colors": (derived.get("AvoidColors") or {}).get("value") or [],
        "contrast_level": _nested_value(derived, "ContrastLevel") or None,
        "frame_structure": _nested_value(derived, "FrameStructure") or None,
        "height_category": _nested_value(derived, "HeightCategory") or None,
        "body_shape": _nested_value(analysis, "BodyShape") or None,
        "risk_tolerance": str(style_pref.get("riskTolerance") or "") or None,
    }


def _planner_entities_payload(plan_resolved_context: Any, plan_action_parameters: Any) -> Dict[str, Any]:
    """Surface the planner's extracted entities the advisor cares about."""
    rc = plan_resolved_context
    return {
        "occasion_signal": getattr(rc, "occasion_signal", None),
        "formality_hint": getattr(rc, "formality_hint", None),
        "time_hint": getattr(rc, "time_hint", None),
        "time_of_day": str(getattr(rc, "time_of_day", "") or ""),
        "weather_context": str(getattr(rc, "weather_context", "") or ""),
        "target_product_type": str(getattr(rc, "target_product_type", "") or ""),
        "specific_needs": list(getattr(rc, "specific_needs", []) or []),
        "is_followup": bool(getattr(rc, "is_followup", False)),
        "followup_intent": getattr(rc, "followup_intent", None),
    }


class StyleAdvisorAgent:
    """LLM advisor for open-ended style_discovery and explanation_request."""

    def __init__(self, model: str = "gpt-5.5") -> None:
        # May 1, 2026: upgraded from gpt-5.4 to gpt-5.5 alongside the
        # planner / architect / user-analysis migration. Style Advisor
        # produces free-form prose for style_discovery and explanation_request
        # turns where voice quality is directly user-visible — the bigger
        # model preserves the stylist tone the product positioning depends on.
        #
        # Lazy OpenAI client (see CopilotPlanner for the pattern).
        self._model = model
        self._system_prompt = _load_prompt()
        # Item 4 (May 1, 2026): orchestrator picks this up post-call.
        self.last_usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    @cached_property
    def _client(self) -> OpenAI:
        return OpenAI(api_key=get_api_key())

    def advise(
        self,
        *,
        mode: str,
        query: str,
        user_context: Any,
        plan_resolved_context: Any,
        plan_action_parameters: Any,
        conversation_memory: Optional[Dict[str, Any]] = None,
        previous_recommendation_focus: Optional[Dict[str, Any]] = None,
        profile_confidence_pct: int = 0,
    ) -> StyleAdvice:
        """Generate a structured advisory response.

        ``mode`` must be ``"discovery"`` or ``"explanation"``. The
        orchestrator routes the call based on which intent it is
        dispatching. ``previous_recommendation_focus`` is required for
        explanation mode (the agent answers "why did you recommend X?"
        against this payload).
        """
        if mode not in ("discovery", "explanation"):
            raise ValueError(f"StyleAdvisorAgent mode must be 'discovery' or 'explanation', got {mode!r}")

        payload = {
            "mode": mode,
            "query": query.strip(),
            "user_profile": _build_user_profile_payload(user_context),
            "planner_entities": _planner_entities_payload(plan_resolved_context, plan_action_parameters),
            "conversation_memory": conversation_memory or {},
            "previous_recommendation_focus": previous_recommendation_focus,
            "profile_confidence_pct": int(profile_confidence_pct or 0),
        }

        from platform_core.cost_estimator import extract_token_usage
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
                            "text": json.dumps(payload, indent=2, default=str),
                        }
                    ],
                },
            ],
            text={"format": _ADVICE_JSON_SCHEMA},
        )
        self.last_usage = extract_token_usage(response)
        raw_text = getattr(response, "output_text", "") or "{}"
        raw = json.loads(raw_text)
        return StyleAdvice(raw)
