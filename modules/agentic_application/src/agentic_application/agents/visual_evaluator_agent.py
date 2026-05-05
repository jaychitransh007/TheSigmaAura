"""Visual Evaluator Agent — Phase 12B.

Vision-grounded scoring agent that replaces the legacy text-only
``OutfitEvaluator`` and the legacy ``OutfitCheckAgent``. Both upstream
callers funnel into the same per-candidate scoring shape so the response
formatter can render them consistently.

Key design points:
- **Per-candidate** call (not batched). Vision needs each rendered image.
  For occasion_recommendation / pairing_request the orchestrator runs
  N parallel calls (one per top-N candidate) via ThreadPoolExecutor.
- **9 dimension scores** including the new ``weather_time_pct``.
- **8 archetype scores** describing the outfit's aesthetic profile.
- **Optional outfit_check / single_garment fields** populated only when
  ``mode`` is ``"outfit_check"`` or ``"single_garment"``.
- Returns a single ``EvaluatedRecommendation`` so it slots into the
  existing schema layer; the orchestrator collects these into a list for
  multi-candidate flows.
"""

from __future__ import annotations

import json
import logging
from functools import cached_property
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from user_profiler.config import get_api_key
from user_profiler.service import _image_to_input_url

from ..schemas import EvaluatedRecommendation, OutfitCandidate

_log = logging.getLogger(__name__)


def _load_prompt() -> str:
    prompt_dir = Path(__file__).resolve()
    for base in [prompt_dir.parent] + list(prompt_dir.parents):
        candidate = base / "prompt" / "visual_evaluator.md"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()
    raise FileNotFoundError("Could not locate prompt/visual_evaluator.md")


_EVAL_JSON_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "name": "visual_evaluation",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "candidate_id",
            "match_score",
            "title",
            "reasoning",
            "body_note",
            "color_note",
            "style_note",
            "occasion_note",
            "body_harmony_pct",
            "color_suitability_pct",
            "style_fit_pct",
            "risk_tolerance_pct",
            "occasion_pct",
            "comfort_boundary_pct",
            "specific_needs_pct",
            "pairing_coherence_pct",
            "weather_time_pct",
            "classic_pct",
            "dramatic_pct",
            "romantic_pct",
            "natural_pct",
            "minimalist_pct",
            "creative_pct",
            "sporty_pct",
            "edgy_pct",
            "item_ids",
            "overall_verdict",
            "overall_note",
            "strengths",
            "improvements",
        ],
        "properties": {
            "candidate_id": {"type": "string"},
            "match_score": {"type": "number"},
            "title": {"type": "string"},
            "reasoning": {"type": "string"},
            "body_note": {"type": "string"},
            "color_note": {"type": "string"},
            "style_note": {"type": "string"},
            "occasion_note": {"type": "string"},
            # Phase 12B follow-ups (April 9 2026):
            # - The 5 always-evaluated dimensions stay strict integers.
            # - 4 dimensions are nullable (`["integer", "null"]`):
            #   * `occasion_pct` — null when live_context.occasion_signal is null
            #   * `weather_time_pct` — null when live_context.weather_context AND time_of_day are empty
            #   * `specific_needs_pct` — null when live_context.specific_needs is empty
            #   * `pairing_coherence_pct` — null when intent is garment_evaluation /
            #     style_discovery / explanation_request (no outfit being paired)
            # OpenAI structured-outputs strict mode requires every property
            # in `required`, so optionality is expressed via the
            # `["integer", "null"]` union here rather than dropping keys.
            "body_harmony_pct": {"type": "integer"},
            "color_suitability_pct": {"type": "integer"},
            "style_fit_pct": {"type": "integer"},
            "risk_tolerance_pct": {"type": "integer"},
            "occasion_pct": {"type": ["integer", "null"]},
            "comfort_boundary_pct": {"type": "integer"},
            "specific_needs_pct": {"type": ["integer", "null"]},
            "pairing_coherence_pct": {"type": ["integer", "null"]},
            "weather_time_pct": {"type": ["integer", "null"]},
            "classic_pct": {"type": "integer"},
            "dramatic_pct": {"type": "integer"},
            "romantic_pct": {"type": "integer"},
            "natural_pct": {"type": "integer"},
            "minimalist_pct": {"type": "integer"},
            "creative_pct": {"type": "integer"},
            "sporty_pct": {"type": "integer"},
            "edgy_pct": {"type": "integer"},
            "item_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "overall_verdict": {
                "type": "string",
                "enum": [
                    "",
                    "great_choice",
                    "good_with_tweaks",
                    "consider_changes",
                    "needs_rethink",
                ],
            },
            "overall_note": {"type": "string"},
            "strengths": {
                "type": "array",
                "items": {"type": "string"},
            },
            "improvements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["area", "suggestion", "reason", "swap_source", "swap_detail"],
                    "properties": {
                        "area": {"type": "string"},
                        "suggestion": {"type": "string"},
                        "reason": {"type": "string"},
                        "swap_source": {"type": "string", "enum": ["wardrobe", "catalog", ""]},
                        "swap_detail": {"type": "string"},
                    },
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


def _build_user_profile_payload(user_context: Any) -> Dict[str, Any]:
    derived = dict(getattr(user_context, "derived_interpretations", {}) or {})
    style_pref = dict(getattr(user_context, "style_preference", {}) or {})
    analysis = dict(getattr(user_context, "analysis_attributes", {}) or {})

    wardrobe_items = list(getattr(user_context, "wardrobe_items", []) or [])
    wardrobe_summary = [
        {
            "title": str(item.get("title") or ""),
            "garment_category": str(item.get("garment_category") or ""),
            "garment_subtype": str(item.get("garment_subtype") or ""),
            "primary_color": str(item.get("primary_color") or ""),
            "occasion_fit": str(item.get("occasion_fit") or ""),
            "formality_level": str(item.get("formality_level") or ""),
        }
        for item in wardrobe_items[:15]
    ]

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
        "wardrobe_items": wardrobe_summary,
    }


def _candidate_payload(candidate: OutfitCandidate) -> Dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "candidate_type": candidate.candidate_type,
        "items": [
            {
                "product_id": str(item.get("product_id", "")),
                "title": str(item.get("title", "")),
                "garment_category": str(item.get("garment_category", "")),
                "garment_subtype": str(item.get("garment_subtype", "")),
                "primary_color": str(item.get("primary_color", "")),
                "formality_level": str(item.get("formality_level", "")),
                "occasion_fit": str(item.get("occasion_fit", "")),
                "pattern_type": str(item.get("pattern_type", "")),
                "fit_type": str(item.get("fit_type", "")),
                "volume_profile": str(item.get("volume_profile", "")),
                "silhouette_type": str(item.get("silhouette_type", "")),
                "role": str(item.get("role", "")),
            }
            for item in (candidate.items or [])
        ],
        "fashion_score": int(getattr(candidate, "fashion_score", 0) or 0),
        "rater_rationale": str(getattr(candidate, "rater_rationale", "") or ""),
    }


def _live_context_payload(live_context: Any) -> Dict[str, Any]:
    if live_context is None:
        return {}
    return {
        "occasion_signal": getattr(live_context, "occasion_signal", None),
        "formality_hint": getattr(live_context, "formality_hint", None),
        "time_hint": getattr(live_context, "time_hint", None),
        "time_of_day": getattr(live_context, "time_of_day", "") or "",
        "weather_context": getattr(live_context, "weather_context", "") or "",
        "style_goal": getattr(live_context, "style_goal", "") or "",
        "specific_needs": list(getattr(live_context, "specific_needs", []) or []),
        "is_followup": bool(getattr(live_context, "is_followup", False)),
        "followup_intent": getattr(live_context, "followup_intent", None),
    }


def _body_context_summary(user_context: Any) -> Dict[str, Any]:
    derived = dict(getattr(user_context, "derived_interpretations", {}) or {})
    analysis = dict(getattr(user_context, "analysis_attributes", {}) or {})
    return {
        "height_category": _nested_value(derived, "HeightCategory") or "",
        "frame_structure": _nested_value(derived, "FrameStructure") or "",
        "body_shape": _nested_value(analysis, "BodyShape") or "",
    }


class VisualEvaluatorAgent:
    """Vision-grounded per-candidate evaluator.

    Replaces both ``OutfitEvaluator`` (text-only, batched) and
    ``OutfitCheckAgent`` (vision, single-result). Callers run one
    instance per candidate. For occasion_recommendation / pairing_request
    the orchestrator parallelizes via a ThreadPoolExecutor.
    """

    def __init__(self, model: str = "gpt-5-mini") -> None:
        # May 1, 2026: moved from gpt-5.4 to gpt-5-mini. The evaluator
        # emits structured per-candidate scores against a tight JSON
        # schema (9 evaluation pcts + 8 archetype pcts); the schema
        # constraint forces output into a narrow corridor where mini
        # performs well. Runs 3-5x in parallel post-try-on so the
        # latency saving compounds. Score noise affects ranking-within-
        # pool only — retrieval is upstream and unaffected.
        #
        # Lazy OpenAI client (see CopilotPlanner for the pattern).
        self._model = model
        self._system_prompt = _load_prompt()
        # Item 4 (May 1, 2026): orchestrator picks this up post-call.
        self.last_usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    @cached_property
    def _client(self) -> OpenAI:
        return OpenAI(api_key=get_api_key())

    def evaluate_candidate(
        self,
        *,
        candidate: OutfitCandidate,
        image_path: str,
        user_context: Any,
        live_context: Any,
        intent: str,
        mode: str = "recommendation",
        previous_recommendation_focus: Optional[Dict[str, Any]] = None,
        candidate_delta: Optional[Dict[str, Any]] = None,
        profile_confidence_pct: int = 0,
    ) -> EvaluatedRecommendation:
        """Score one candidate against the user profile + context.

        ``image_path`` should be the rendered try-on (recommendation /
        pairing / garment_evaluation) or the user-provided photo
        (outfit_check). Empty image_path is allowed but degrades the
        scoring quality — the agent will fall back to attribute-only
        reasoning and the prompt explicitly discourages that.

        ``mode`` selects which optional output fields are populated:
            "recommendation"  → strengths/improvements/overall_* empty
            "single_garment"  → all populated, single-piece framing
            "outfit_check"    → all populated, outfit-rating framing
        """
        payload = {
            "mode": mode,
            "intent": intent,
            "user_profile": _build_user_profile_payload(user_context),
            "candidate": _candidate_payload(candidate),
            "live_context": _live_context_payload(live_context),
            "previous_recommendation_focus": previous_recommendation_focus or None,
            "candidate_delta": candidate_delta or None,
            "body_context_summary": _body_context_summary(user_context),
            "profile_confidence_pct": int(profile_confidence_pct or 0),
        }

        user_content: List[Dict[str, Any]] = [
            {
                "type": "input_text",
                "text": json.dumps(payload, indent=2, default=str),
            }
        ]
        if image_path:
            try:
                image_url = _image_to_input_url(image_path)
                user_content.append({"type": "input_image", "image_url": image_url})
            except Exception:
                _log.warning(
                    "Could not attach image to visual evaluator: %s", image_path, exc_info=True
                )

        from platform_core.cost_estimator import extract_token_usage
        # reasoning_effort="minimal" — VisualEvaluator scores 17 dims +
        # 4 short notes per candidate against a strict schema. Vision
        # grounding does the work; the model doesn't need extended
        # chain-of-thought to fill the structured slots.
        response = self._client.responses.create(
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": self._system_prompt}],
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
            reasoning={"effort": "minimal"},
            text={"format": _EVAL_JSON_SCHEMA},
        )
        self.last_usage = extract_token_usage(response)
        raw_text = getattr(response, "output_text", "") or "{}"
        raw = json.loads(raw_text)
        return _to_evaluated_recommendation(raw, candidate)


def _to_evaluated_recommendation(
    raw: Dict[str, Any],
    candidate: OutfitCandidate,
) -> EvaluatedRecommendation:
    """Convert the agent's raw JSON into a normalized EvaluatedRecommendation."""

    def _clamp_pct(key: str) -> int:
        return max(0, min(100, int(raw.get(key, 0) or 0)))

    def _optional_pct(key: str) -> Optional[int]:
        """Return clamped int if present + non-null, else None.

        Phase 12B follow-ups (April 9 2026): the 4 context-gated dimensions
        (pairing_coherence_pct, occasion_pct, weather_time_pct,
        specific_needs_pct) are nullable in the JSON schema. When the
        model returns null because the gating condition isn't met
        (occasion_signal absent, weather/time absent, specific_needs
        empty, or — for pairing — intent is garment_evaluation /
        style_discovery / explanation_request), we preserve None all
        the way through to the OutfitCard so the frontend can drop the
        radar slice and the purchase verdict can skip it in the average.
        Coercing null → 0 here would re-introduce the bug we're fixing.
        """
        if key not in raw:
            return None
        value = raw.get(key)
        if value is None:
            return None
        try:
            return max(0, min(100, int(value)))
        except (TypeError, ValueError):
            return None

    valid_item_ids = {str(item.get("product_id", "")) for item in candidate.items if item.get("product_id")}
    raw_item_ids = [str(iid) for iid in (raw.get("item_ids") or []) if iid]
    validated_item_ids = [iid for iid in raw_item_ids if iid in valid_item_ids]
    if not validated_item_ids:
        validated_item_ids = sorted(valid_item_ids)

    return EvaluatedRecommendation(
        candidate_id=str(raw.get("candidate_id") or candidate.candidate_id),
        rank=0,  # Set by the orchestrator after collecting all candidates
        match_score=max(0.0, min(1.0, float(raw.get("match_score", 0.0) or 0.0))),
        title=str(raw.get("title", "")),
        reasoning=str(raw.get("reasoning", "")),
        body_note=str(raw.get("body_note", "")),
        color_note=str(raw.get("color_note", "")),
        style_note=str(raw.get("style_note", "")),
        occasion_note=str(raw.get("occasion_note", "")),
        body_harmony_pct=_clamp_pct("body_harmony_pct"),
        color_suitability_pct=_clamp_pct("color_suitability_pct"),
        style_fit_pct=_clamp_pct("style_fit_pct"),
        risk_tolerance_pct=_clamp_pct("risk_tolerance_pct"),
        comfort_boundary_pct=_clamp_pct("comfort_boundary_pct"),
        # 4 context-gated dimensions — preserve None when the model
        # returns null. pairing_coherence_pct joined this group when
        # the intent-gating rule landed (April 9 2026): garment_evaluation,
        # style_discovery, and explanation_request return null because
        # there is no outfit being paired in those turns.
        occasion_pct=_optional_pct("occasion_pct"),
        specific_needs_pct=_optional_pct("specific_needs_pct"),
        pairing_coherence_pct=_optional_pct("pairing_coherence_pct"),
        weather_time_pct=_optional_pct("weather_time_pct"),
        classic_pct=_clamp_pct("classic_pct"),
        dramatic_pct=_clamp_pct("dramatic_pct"),
        romantic_pct=_clamp_pct("romantic_pct"),
        natural_pct=_clamp_pct("natural_pct"),
        minimalist_pct=_clamp_pct("minimalist_pct"),
        creative_pct=_clamp_pct("creative_pct"),
        sporty_pct=_clamp_pct("sporty_pct"),
        edgy_pct=_clamp_pct("edgy_pct"),
        item_ids=validated_item_ids,
        overall_verdict=str(raw.get("overall_verdict", "")),
        overall_note=str(raw.get("overall_note", "")),
        strengths=[str(s) for s in (raw.get("strengths") or []) if s],
        improvements=[dict(i) for i in (raw.get("improvements") or []) if isinstance(i, dict)],
    )
