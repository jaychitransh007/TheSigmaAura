from __future__ import annotations

import atexit
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from functools import cached_property
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
    # Only risk_tolerance is read; archetype was dropped May 2026.
    style_pref = dict(user_context.style_preference or {})
    risk_tolerance = str(style_pref.get("riskTolerance") or "").strip() or "balanced"

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
            "risk_tolerance": risk_tolerance,
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


_SHADOW_LOG = logging.getLogger("aura.planner.shadow")

# Phase 1.3 review (May 13 2026): pool sized for one shadow call per
# concurrent in-flight turn. 5 is an order-of-magnitude over Aura's
# current alpha turn rate (a handful per minute) and well below
# OpenAI's per-account RPM ceiling. Pool is created once per process,
# shared across all CopilotPlanner instances. Shadow mode is opt-in
# via AURA_PLANNER_SHADOW_MODEL; when no shadow is configured anywhere
# in the process, no threads ever get spun up.
_SHADOW_EXECUTOR: Optional[ThreadPoolExecutor] = None
_SHADOW_EXECUTOR_LOCK: Optional[Any] = None


def _get_shadow_executor() -> ThreadPoolExecutor:
    """Lazily construct a process-wide shadow executor. Idempotent."""
    global _SHADOW_EXECUTOR, _SHADOW_EXECUTOR_LOCK
    if _SHADOW_EXECUTOR is None:
        if _SHADOW_EXECUTOR_LOCK is None:
            import threading as _threading
            _SHADOW_EXECUTOR_LOCK = _threading.Lock()
        with _SHADOW_EXECUTOR_LOCK:
            if _SHADOW_EXECUTOR is None:
                _SHADOW_EXECUTOR = ThreadPoolExecutor(
                    max_workers=5,
                    thread_name_prefix="planner-shadow",
                )
                # Ensure the executor drains and shuts down cleanly on
                # process exit so daemon-style shadow calls don't get
                # silently aborted mid-flight.
                atexit.register(_SHADOW_EXECUTOR.shutdown, wait=False)
    return _SHADOW_EXECUTOR


class CopilotPlanner:
    def __init__(
        self,
        model: str = "gpt-5-mini",
        *,
        shadow_model: Optional[str] = None,
    ) -> None:
        # May 5, 2026: downgraded from gpt-5.5 to gpt-5-mini. Earlier
        # rationale (the planner is high-leverage so it gets the bigger
        # model) overweighted the routing-failure risk. With strict
        # JSON-schema enums the planner's task is structurally similar
        # to other gpt-5-mini callers in this codebase (Composer,
        # Rater, visual_evaluator) — fuzzy NL → constrained structured
        # output. The architecture-grade reasoning (body shape × palette
        # × occasion → catalog queries) lives in OutfitArchitect, which
        # stays on gpt-5.5. See docs/OPEN_TASKS.md for the offline
        # routing-accuracy eval that backs this change.
        #
        # Lazy OpenAI client: do NOT touch get_api_key() here so the
        # constructor stays env-free for tests that mock the agent.
        # The client materialises on first attribute access via the
        # cached_property below.
        self._model = model
        # Phase 1.3 latency push (May 13 2026): shadow mode. When
        # AURA_PLANNER_SHADOW_MODEL is set, every plan() call fires a
        # background OpenAI call against the shadow model with the same
        # input AFTER the production response has returned to the
        # caller. The shadow thread logs the production-vs-shadow diff
        # to the `aura.planner.shadow` logger so operators can review
        # routing-disagreement rates before promoting the shadow model
        # to production. Daemon thread is fire-and-forget — production
        # latency is unaffected. To support a non-OpenAI shadow vendor
        # (claude-haiku-4-5), add a vendor adapter and switch on
        # AURA_PLANNER_SHADOW_VENDOR; the shadow thread plumbing here
        # is vendor-agnostic.
        self._shadow_model = shadow_model or os.getenv("AURA_PLANNER_SHADOW_MODEL", "").strip() or None
        self._system_prompt = _load_prompt()
        # Item 4 (May 1, 2026): exposed for the orchestrator's log_model_call
        # site to pick up. Reset on every plan() entry so a stale read can't
        # mislabel a later turn.
        self.last_usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    @cached_property
    def _client(self) -> OpenAI:
        return OpenAI(api_key=get_api_key())

    def plan(self, planner_input: Dict[str, Any]) -> CopilotPlanResult:
        from platform_core.cost_estimator import extract_token_usage
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        # reasoning_effort="minimal" — closest to "no reasoning" the
        # gpt-5-mini API supports (per OpenAI docs, "none" works only
        # on gpt-5.1+; gpt-5-mini supports minimal/low/medium/high).
        # Planner is fuzzy-NL → strict-enum classification, doesn't
        # benefit from chain-of-thought. Cuts ~600 reasoning tokens
        # per call, drops latency from ~12s → ~3-4s expected.
        prod_t0 = time.monotonic()
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
            reasoning={"effort": "minimal"},
            text={"format": _PLAN_JSON_SCHEMA},
        )
        prod_latency_ms = int((time.monotonic() - prod_t0) * 1000)
        self.last_usage = extract_token_usage(response)

        raw = json.loads(getattr(response, "output_text", "") or "{}")
        result = self._parse_result(raw)

        if self._shadow_model:
            self._spawn_shadow(planner_input, result, prod_latency_ms)
        return result

    def _spawn_shadow(
        self,
        planner_input: Dict[str, Any],
        production_result: CopilotPlanResult,
        production_latency_ms: int,
    ) -> None:
        """Fire-and-forget shadow call; never blocks the caller.

        Submits to the process-wide ThreadPoolExecutor (review of PR #124)
        so we don't pay thread-creation overhead per turn or risk runaway
        thread counts under load.
        """
        _get_shadow_executor().submit(
            self._run_shadow,
            planner_input,
            production_result,
            production_latency_ms,
        )

    def _run_shadow(
        self,
        planner_input: Dict[str, Any],
        production_result: CopilotPlanResult,
        production_latency_ms: int,
    ) -> None:
        from platform_core.cost_estimator import extract_token_usage as _extract

        shadow_t0 = time.monotonic()
        try:
            response = self._client.responses.create(
                model=self._shadow_model,
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
                reasoning={"effort": "minimal"},
                text={"format": _PLAN_JSON_SCHEMA},
            )
        except Exception as exc:  # noqa: BLE001 — shadow path never raises
            _SHADOW_LOG.warning(
                "shadow_call_failed",
                extra={
                    "shadow_model": self._shadow_model,
                    "production_model": self._model,
                    "error": str(exc)[:500],
                },
            )
            return
        shadow_latency_ms = int((time.monotonic() - shadow_t0) * 1000)
        try:
            shadow_raw = json.loads(getattr(response, "output_text", "") or "{}")
            shadow_result = self._parse_result(shadow_raw)
        except Exception as exc:  # noqa: BLE001
            _SHADOW_LOG.warning(
                "shadow_parse_failed",
                extra={
                    "shadow_model": self._shadow_model,
                    "error": str(exc)[:200],
                },
            )
            return

        # extract_token_usage always returns a dict with int values for
        # the standard token keys — defensive coercions removed (review
        # of PR #124).
        shadow_usage = _extract(response)
        intent_match = production_result.intent == shadow_result.intent
        action_match = production_result.action == shadow_result.action
        _SHADOW_LOG.info(
            "shadow_compare",
            extra={
                "production_model": self._model,
                "shadow_model": self._shadow_model,
                "production_intent": production_result.intent,
                "shadow_intent": shadow_result.intent,
                "production_action": production_result.action,
                "shadow_action": shadow_result.action,
                "intent_match": intent_match,
                "action_match": action_match,
                "production_confidence": production_result.intent_confidence,
                "shadow_confidence": shadow_result.intent_confidence,
                "production_latency_ms": production_latency_ms,
                "shadow_latency_ms": shadow_latency_ms,
                "shadow_total_tokens": shadow_usage.get("total_tokens", 0),
                "user_message": str(planner_input.get("user_message", ""))[:200],
            },
        )

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
