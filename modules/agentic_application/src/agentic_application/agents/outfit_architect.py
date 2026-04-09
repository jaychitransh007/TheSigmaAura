from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI

from user_profiler.config import get_api_key

from ..schemas import CombinedContext, DirectionSpec, QuerySpec, RecommendationPlan, ResolvedContextBlock

_log = logging.getLogger(__name__)


def _load_prompt() -> str:
    prompt_dir = Path(__file__).resolve()
    for base in [prompt_dir.parent] + list(prompt_dir.parents):
        candidate = base / "prompt" / "outfit_architect.md"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()
    raise FileNotFoundError("Could not locate prompt/outfit_architect.md")


_PLAN_JSON_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "name": "recommendation_plan",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["resolved_context", "plan_type", "retrieval_count", "directions"],
        "properties": {
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
                },
            },
            "plan_type": {
                "type": "string",
                "enum": ["complete_only", "paired_only", "mixed"],
            },
            "retrieval_count": {"type": "integer"},
            "directions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["direction_id", "direction_type", "label", "queries"],
                    "properties": {
                        "direction_id": {"type": "string"},
                        "direction_type": {
                            "type": "string",
                            "enum": ["complete", "paired"],
                        },
                        "label": {"type": "string"},
                        "queries": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["query_id", "role", "hard_filters", "query_document"],
                                "properties": {
                                    "query_id": {"type": "string"},
                                    "role": {
                                        "type": "string",
                                        "enum": ["complete", "top", "bottom"],
                                    },
                                    "hard_filters": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": [
                                            "garment_subtype",
                                            "gender_expression",
                                        ],
                                        "properties": {
                                            "garment_subtype": {
                                                "anyOf": [
                                                    {"type": "string"},
                                                    {"type": "array", "items": {"type": "string"}},
                                                    {"type": "null"},
                                                ],
                                            },
                                            "gender_expression": {
                                                "type": ["string", "null"],
                                                "enum": ["masculine", "feminine", "unisex", None],
                                            },
                                        },
                                    },
                                    "query_document": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}


def _extract_value(payload: Dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, dict):
        return str(value.get("value") or "").strip()
    return str(value or "").strip()


def _build_user_payload(ctx: CombinedContext) -> str:
    user = ctx.user
    profile_block = {
        "gender": user.gender,
        "height_cm": user.height_cm,
        "waist_cm": user.waist_cm,
        "profession": user.profession,
        "profile_richness": user.profile_richness,
    }
    attrs = {key: _extract_value(user.analysis_attributes, key) for key in user.analysis_attributes}
    interps = {}
    for key in user.derived_interpretations:
        raw = user.derived_interpretations[key]
        if isinstance(raw, dict):
            val = raw.get("value", "")
            interps[key] = ", ".join(val) if isinstance(val, list) else str(val or "").strip()
        else:
            interps[key] = str(raw or "").strip()

    # Surface additional seasonal groups for multi-group color guidance
    seasonal_raw = user.derived_interpretations.get("SeasonalColorGroup")
    if isinstance(seasonal_raw, dict) and seasonal_raw.get("additional_groups"):
        interps["SeasonalColorGroup_additional"] = [
            g["value"] for g in seasonal_raw["additional_groups"]
        ]

    payload = {
        "profile": profile_block,
        "analysis_attributes": attrs,
        "derived_interpretations": interps,
        "style_preference": user.style_preference,
        "user_message": ctx.live.user_need,
        "conversation_history": ctx.conversation_history or [],
        "hard_filters": ctx.hard_filters,
        "previous_recommendations": ctx.previous_recommendations,
        "conversation_memory": (
            ctx.conversation_memory.model_dump() if ctx.conversation_memory else None
        ),
        "catalog_inventory": ctx.catalog_inventory,
    }
    if ctx.live.anchor_garment:
        payload["anchor_garment"] = ctx.live.anchor_garment
    return json.dumps(payload, indent=2, default=str)


class OutfitArchitect:
    def __init__(self, model: str = "gpt-5.4") -> None:
        self._client = OpenAI(api_key=get_api_key())
        self._model = model
        self._system_prompt = _load_prompt()

    def plan(self, combined_context: CombinedContext) -> RecommendationPlan:
        """Generate a RecommendationPlan via LLM. Raises on failure."""
        response = self._client.responses.create(
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": self._system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": _build_user_payload(combined_context)}],
                },
            ],
            text={"format": _PLAN_JSON_SCHEMA},
        )

        raw = json.loads(getattr(response, "output_text", "") or "{}")
        plan = self._parse_plan(raw)

        if not plan.directions:
            raise RuntimeError("Outfit architect returned a plan with no directions")

        return plan

    def _parse_plan(self, raw: Dict[str, Any]) -> RecommendationPlan:
        directions: List[DirectionSpec] = []
        for direction in raw.get("directions", []):
            queries = [
                QuerySpec(
                    query_id=query["query_id"],
                    role=query["role"],
                    hard_filters={
                        k: v for k, v in (query.get("hard_filters") or {}).items()
                        if v is not None and str(v).strip().lower() not in ("null", "")
                    },
                    query_document=query["query_document"],
                )
                for query in direction.get("queries", [])
            ]
            if not queries:
                continue
            directions.append(
                DirectionSpec(
                    direction_id=direction["direction_id"],
                    direction_type=direction["direction_type"],
                    label=direction["label"],
                    queries=queries,
                )
            )
        resolved_ctx = None
        raw_resolved = raw.get("resolved_context")
        if isinstance(raw_resolved, dict):
            resolved_ctx = ResolvedContextBlock(
                occasion_signal=raw_resolved.get("occasion_signal"),
                formality_hint=raw_resolved.get("formality_hint"),
                time_hint=raw_resolved.get("time_hint"),
                specific_needs=raw_resolved.get("specific_needs") or [],
                is_followup=bool(raw_resolved.get("is_followup")),
                followup_intent=raw_resolved.get("followup_intent"),
            )
        return RecommendationPlan(
            plan_type=raw.get("plan_type", "complete_only"),
            retrieval_count=int(raw.get("retrieval_count", 12)),
            directions=directions,
            plan_source="llm",
            resolved_context=resolved_ctx,
        )
