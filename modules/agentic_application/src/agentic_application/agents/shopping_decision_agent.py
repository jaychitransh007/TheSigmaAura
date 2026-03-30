from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from user_profiler.config import get_api_key

_log = logging.getLogger(__name__)
_URL_RE = re.compile(r"https?://\S+")


def _load_prompt() -> str:
    prompt_dir = Path(__file__).resolve()
    for base in [prompt_dir.parent] + list(prompt_dir.parents):
        candidate = base / "prompt" / "shopping_decision.md"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()
    raise FileNotFoundError("Could not locate prompt/shopping_decision.md")


_DECISION_JSON_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "shopping_decision_result",
        "strict": True,
        "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "verdict",
            "verdict_confidence",
            "verdict_note",
            "scores",
            "strengths",
            "concerns",
            "wardrobe_overlap",
            "pairing_suggestions",
            "if_you_buy",
            "instead_consider",
        ],
        "properties": {
            "verdict": {"type": "string", "enum": ["buy", "skip", "conditional"]},
            "verdict_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "verdict_note": {"type": "string"},
            "scores": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "color_suitability_pct",
                    "body_harmony_pct",
                    "style_fit_pct",
                    "wardrobe_versatility_pct",
                    "wardrobe_gap_pct",
                ],
                "properties": {
                    "color_suitability_pct": {"type": "integer"},
                    "body_harmony_pct": {"type": "integer"},
                    "style_fit_pct": {"type": "integer"},
                    "wardrobe_versatility_pct": {"type": "integer"},
                    "wardrobe_gap_pct": {"type": "integer"},
                },
            },
            "strengths": {"type": "array", "items": {"type": "string"}},
            "concerns": {"type": "array", "items": {"type": "string"}},
            "wardrobe_overlap": {
                "type": "object",
                "additionalProperties": False,
                "required": ["has_duplicate", "duplicate_detail", "overlap_level"],
                "properties": {
                    "has_duplicate": {"type": "boolean"},
                    "duplicate_detail": {"type": ["string", "null"]},
                    "overlap_level": {"type": "string", "enum": ["none", "moderate", "strong"]},
                },
            },
            "pairing_suggestions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["wardrobe_item", "pairing_note"],
                    "properties": {
                        "wardrobe_item": {"type": "string"},
                        "pairing_note": {"type": "string"},
                    },
                },
            },
            "if_you_buy": {"type": "string"},
            "instead_consider": {"type": ["string", "null"]},
        },
        },
    },
}


def _nested_value(payload: Dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, dict):
        return str(value.get("value") or "").strip()
    return str(value or "").strip()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _build_user_profile_payload(user_context: Any) -> Dict[str, Any]:
    derived = dict(getattr(user_context, "derived_interpretations", {}) or {})
    style_pref = dict(getattr(user_context, "style_preference", {}) or {})
    analysis = dict(getattr(user_context, "analysis_attributes", {}) or {})
    wardrobe_items = list(getattr(user_context, "wardrobe_items", []) or [])
    wardrobe_summary = [
        {
            "title": _clean_text(item.get("title")),
            "garment_category": _clean_text(item.get("garment_category")),
            "garment_subtype": _clean_text(item.get("garment_subtype")),
            "primary_color": _clean_text(item.get("primary_color")),
            "occasion_fit": _clean_text(item.get("occasion_fit")),
            "formality_level": _clean_text(item.get("formality_level")),
        }
        for item in wardrobe_items[:20]
    ]
    return {
        "gender": getattr(user_context, "gender", ""),
        "seasonal_color_group": _nested_value(derived, "SeasonalColorGroup") or None,
        "contrast_level": _nested_value(derived, "ContrastLevel") or None,
        "frame_structure": _nested_value(derived, "FrameStructure") or None,
        "height_category": _nested_value(derived, "HeightCategory") or None,
        "body_shape": _nested_value(analysis, "BodyShape") or None,
        "primary_archetype": _clean_text(style_pref.get("primaryArchetype")) or None,
        "secondary_archetype": _clean_text(style_pref.get("secondaryArchetype")) or None,
        "risk_tolerance": _clean_text(style_pref.get("riskTolerance")) or None,
        "comfort_boundaries": list(style_pref.get("comfortBoundaries") or []),
        "wardrobe_items": wardrobe_summary,
    }


class ShoppingDecisionResult:
    def __init__(self, raw: Dict[str, Any]) -> None:
        self.verdict = _clean_text(raw.get("verdict")) or "conditional"
        self.verdict_confidence = _clean_text(raw.get("verdict_confidence")) or "medium"
        self.verdict_note = _clean_text(raw.get("verdict_note"))
        scores = dict(raw.get("scores") or {})
        self.color_suitability_pct = max(0, min(100, int(scores.get("color_suitability_pct", 0))))
        self.body_harmony_pct = max(0, min(100, int(scores.get("body_harmony_pct", 0))))
        self.style_fit_pct = max(0, min(100, int(scores.get("style_fit_pct", 0))))
        self.wardrobe_versatility_pct = max(0, min(100, int(scores.get("wardrobe_versatility_pct", 0))))
        self.wardrobe_gap_pct = max(0, min(100, int(scores.get("wardrobe_gap_pct", 0))))
        self.strengths = [str(v).strip() for v in list(raw.get("strengths") or []) if str(v).strip()]
        self.concerns = [str(v).strip() for v in list(raw.get("concerns") or []) if str(v).strip()]
        overlap = dict(raw.get("wardrobe_overlap") or {})
        self.wardrobe_overlap = {
            "has_duplicate": bool(overlap.get("has_duplicate")),
            "duplicate_detail": _clean_text(overlap.get("duplicate_detail")) or None,
            "overlap_level": _clean_text(overlap.get("overlap_level")) or "none",
        }
        self.pairing_suggestions = [
            {
                "wardrobe_item": _clean_text(item.get("wardrobe_item")),
                "pairing_note": _clean_text(item.get("pairing_note")),
            }
            for item in list(raw.get("pairing_suggestions") or [])
            if _clean_text((item or {}).get("wardrobe_item"))
        ]
        self.if_you_buy = _clean_text(raw.get("if_you_buy"))
        self.instead_consider = _clean_text(raw.get("instead_consider")) or None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "verdict_confidence": self.verdict_confidence,
            "verdict_note": self.verdict_note,
            "scores": {
                "color_suitability_pct": self.color_suitability_pct,
                "body_harmony_pct": self.body_harmony_pct,
                "style_fit_pct": self.style_fit_pct,
                "wardrobe_versatility_pct": self.wardrobe_versatility_pct,
                "wardrobe_gap_pct": self.wardrobe_gap_pct,
            },
            "strengths": list(self.strengths),
            "concerns": list(self.concerns),
            "wardrobe_overlap": dict(self.wardrobe_overlap),
            "pairing_suggestions": list(self.pairing_suggestions),
            "if_you_buy": self.if_you_buy,
            "instead_consider": self.instead_consider,
        }


class ShoppingDecisionAgent:
    def __init__(self, model: str = "gpt-5.4") -> None:
        self._model = model
        self._system_prompt = _load_prompt()

    def evaluate(
        self,
        *,
        user_context: Any,
        product_description: str,
        product_urls: Optional[List[str]] = None,
        detected_garments: Optional[List[str]] = None,
        detected_colors: Optional[List[str]] = None,
        occasion_signal: Optional[str] = None,
        profile_confidence_pct: int = 0,
        wardrobe_overlap: Optional[Dict[str, Any]] = None,
        pairing_suggestions: Optional[List[Dict[str, str]]] = None,
    ) -> ShoppingDecisionResult:
        payload = {
            "user_profile": _build_user_profile_payload(user_context),
            "product_description": _clean_text(product_description),
            "product_urls": list(product_urls or []),
            "detected_garments": list(detected_garments or []),
            "detected_colors": list(detected_colors or []),
            "occasion_signal": occasion_signal,
            "profile_confidence_pct": int(profile_confidence_pct or 0),
            "precomputed_wardrobe_overlap": dict(wardrobe_overlap or {}),
            "precomputed_pairing_suggestions": list(pairing_suggestions or []),
        }

        client = OpenAI(api_key=get_api_key())
        response = client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": json.dumps(payload, default=str)},
            ],
            response_format=_DECISION_JSON_SCHEMA,
            temperature=0.2,
        )
        raw_text = response.choices[0].message.content or "{}"
        raw = json.loads(raw_text)
        return ShoppingDecisionResult(raw)


def extract_urls(message: str) -> List[str]:
    return [match.rstrip(").,!?") for match in _URL_RE.findall(str(message or ""))]
