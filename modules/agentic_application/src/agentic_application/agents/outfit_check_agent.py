from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from user_profiler.config import get_api_key
from user_profiler.service import _image_to_input_url

_log = logging.getLogger(__name__)


def _load_prompt() -> str:
    prompt_dir = Path(__file__).resolve()
    for base in [prompt_dir.parent] + list(prompt_dir.parents):
        candidate = base / "prompt" / "outfit_check.md"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()
    raise FileNotFoundError("Could not locate prompt/outfit_check.md")


_CHECK_JSON_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "name": "outfit_check_result",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "overall_verdict",
            "overall_note",
            "scores",
            "strengths",
            "improvements",
            "style_archetype_read",
        ],
        "properties": {
            "overall_verdict": {
                "type": "string",
                "enum": ["great_choice", "good_with_tweaks", "consider_changes", "needs_rethink"],
            },
            "overall_note": {"type": "string"},
            "scores": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "body_harmony_pct",
                    "color_suitability_pct",
                    "style_fit_pct",
                    "pairing_coherence_pct",
                    "occasion_pct",
                ],
                "properties": {
                    "body_harmony_pct": {"type": "integer"},
                    "color_suitability_pct": {"type": "integer"},
                    "style_fit_pct": {"type": "integer"},
                    "pairing_coherence_pct": {"type": "integer"},
                    "occasion_pct": {"type": "integer"},
                },
            },
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
                        "swap_source": {"type": "string", "enum": ["wardrobe", "catalog"]},
                        "swap_detail": {"type": "string"},
                    },
                },
            },
            "style_archetype_read": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "classic_pct", "dramatic_pct", "romantic_pct", "natural_pct",
                    "minimalist_pct", "creative_pct", "sporty_pct", "edgy_pct",
                ],
                "properties": {
                    "classic_pct": {"type": "integer"},
                    "dramatic_pct": {"type": "integer"},
                    "romantic_pct": {"type": "integer"},
                    "natural_pct": {"type": "integer"},
                    "minimalist_pct": {"type": "integer"},
                    "creative_pct": {"type": "integer"},
                    "sporty_pct": {"type": "integer"},
                    "edgy_pct": {"type": "integer"},
                },
            },
        },
    },
}


class OutfitCheckResult:
    """Structured result from the outfit check agent."""

    def __init__(self, raw: Dict[str, Any]) -> None:
        self.overall_verdict: str = raw.get("overall_verdict", "good_with_tweaks")
        self.overall_note: str = raw.get("overall_note", "")
        scores = raw.get("scores") or {}
        self.body_harmony_pct: int = max(0, min(100, int(scores.get("body_harmony_pct", 0))))
        self.color_suitability_pct: int = max(0, min(100, int(scores.get("color_suitability_pct", 0))))
        self.style_fit_pct: int = max(0, min(100, int(scores.get("style_fit_pct", 0))))
        self.pairing_coherence_pct: int = max(0, min(100, int(scores.get("pairing_coherence_pct", 0))))
        self.occasion_pct: int = max(0, min(100, int(scores.get("occasion_pct", 0))))
        self.strengths: List[str] = list(raw.get("strengths") or [])
        self.improvements: List[Dict[str, str]] = list(raw.get("improvements") or [])
        archetype = raw.get("style_archetype_read") or {}
        self.style_archetype_read: Dict[str, int] = {
            k: max(0, min(100, int(archetype.get(k, 0))))
            for k in [
                "classic_pct", "dramatic_pct", "romantic_pct", "natural_pct",
                "minimalist_pct", "creative_pct", "sporty_pct", "edgy_pct",
            ]
        }

    @property
    def overall_score_pct(self) -> int:
        return int(
            (
                self.body_harmony_pct
                + self.color_suitability_pct
                + self.style_fit_pct
                + self.pairing_coherence_pct
                + self.occasion_pct
            ) / 5
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_verdict": self.overall_verdict,
            "overall_note": self.overall_note,
            "overall_score_pct": self.overall_score_pct,
            "scores": {
                "body_harmony_pct": self.body_harmony_pct,
                "color_suitability_pct": self.color_suitability_pct,
                "style_fit_pct": self.style_fit_pct,
                "pairing_coherence_pct": self.pairing_coherence_pct,
                "occasion_pct": self.occasion_pct,
            },
            "strengths": self.strengths,
            "improvements": self.improvements,
            "style_archetype_read": self.style_archetype_read,
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
        }
        for item in wardrobe_items[:15]
    ]

    return {
        "gender": getattr(user_context, "gender", ""),
        "seasonal_color_group": _nested_value(derived, "SeasonalColorGroup") or None,
        "base_colors": (derived.get("BaseColors") or {}).get("value") or [],
        "accent_colors": (derived.get("AccentColors") or {}).get("value") or [],
        "avoid_colors": (derived.get("AvoidColors") or {}).get("value") or [],
        "contrast_level": _nested_value(derived, "ContrastLevel") or None,
        "frame_structure": _nested_value(derived, "FrameStructure") or None,
        "height_category": _nested_value(derived, "HeightCategory") or None,
        "body_shape": _nested_value(analysis, "BodyShape") or None,
        "primary_archetype": str(style_pref.get("primaryArchetype") or "") or None,
        "secondary_archetype": str(style_pref.get("secondaryArchetype") or "") or None,
        "risk_tolerance": str(style_pref.get("riskTolerance") or "") or None,
        "comfort_boundaries": list(style_pref.get("comfortBoundaries") or []),
        "wardrobe_items": wardrobe_summary,
    }


class OutfitCheckAgent:
    """Evaluates a user's described outfit against their profile."""

    def __init__(self, model: str = "gpt-5.4") -> None:
        self._client = OpenAI(api_key=get_api_key())
        self._model = model
        self._system_prompt = _load_prompt()

    def evaluate(
        self,
        *,
        user_context: Any,
        outfit_description: str,
        occasion_signal: Optional[str] = None,
        profile_confidence_pct: int = 0,
        image_path: str = "",
    ) -> OutfitCheckResult:
        payload = {
            "user_profile": _build_user_profile_payload(user_context),
            "outfit_description": outfit_description.strip(),
            "occasion_signal": occasion_signal,
            "profile_confidence_pct": profile_confidence_pct,
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
                _log.warning("Could not attach image to outfit check: %s", image_path, exc_info=True)

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
            text={"format": _CHECK_JSON_SCHEMA},
        )
        raw_text = getattr(response, "output_text", "") or "{}"
        raw = json.loads(raw_text)
        return OutfitCheckResult(raw)
