"""Stage A of the split architect (May 3, 2026 — Lever 3 of the perf plan).

Produces direction skeletons (`direction_id`, `direction_type`, `roles[]`,
`hard_filters`, color/formality targets, concept_notes) but NOT the
full `query_document` strings — Stage B (`OutfitArchitectQueryBuilder`)
fills those in per-direction in parallel. The split lets us:

- run Stage A on a much smaller input (3–4K tokens vs 15K) for a faster
  structured-reasoning pass
- run Stage B per-direction in parallel so the wallclock = max(t1,t2,t3)
  instead of t1+t2+t3
- keep the smarter model (gpt-5.5) on the structured-reasoning task and
  drop to gpt-5-mini for the query-writing transformation

The split mode is gated by `OUTFIT_ARCHITECT_MODE=split` (env var).
Default `monolithic` preserves the legacy single-call architect.
"""

from __future__ import annotations

import json
import logging
from functools import cached_property
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from user_profiler.config import get_api_key

from ..schemas import CombinedContext

_log = logging.getLogger(__name__)


def _load_plan_prompt() -> str:
    here = Path(__file__).resolve()
    for base in [here.parent] + list(here.parents):
        candidate = base / "prompt" / "outfit_architect_plan.md"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()
    raise FileNotFoundError("prompt/outfit_architect_plan.md not found")


_PLAN_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "name": "architect_plan",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["resolved_context", "retrieval_count", "direction_plans"],
        "properties": {
            "resolved_context": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "occasion_signal", "formality_hint", "time_hint",
                    "specific_needs", "is_followup", "followup_intent", "ranking_bias",
                ],
                "properties": {
                    "occasion_signal": {"type": ["string", "null"]},
                    "formality_hint": {"type": ["string", "null"]},
                    "time_hint": {"type": ["string", "null"]},
                    "specific_needs": {"type": "array", "items": {"type": "string"}},
                    "is_followup": {"type": "boolean"},
                    "followup_intent": {"type": ["string", "null"]},
                    "ranking_bias": {"type": "string"},
                },
            },
            "retrieval_count": {"type": "integer"},
            "direction_plans": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["direction_id", "direction_type", "label", "rationale", "query_seeds"],
                    "properties": {
                        "direction_id": {"type": "string"},
                        "direction_type": {"type": "string"},
                        "label": {"type": "string"},
                        "rationale": {"type": "string"},
                        "query_seeds": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "query_id", "role", "hard_filters",
                                    "target_color_role", "target_formality",
                                    "target_garment_subtypes", "concept_notes",
                                ],
                                "properties": {
                                    "query_id": {"type": "string"},
                                    "role": {"type": "string"},
                                    "hard_filters": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["gender_expression", "garment_subtype"],
                                        "properties": {
                                            "gender_expression": {"type": ["string", "null"]},
                                            "garment_subtype": {
                                                "anyOf": [
                                                    {"type": "string"},
                                                    {"type": "array", "items": {"type": "string"}},
                                                    {"type": "null"},
                                                ],
                                            },
                                        },
                                    },
                                    "target_color_role": {"type": "string"},
                                    "target_formality": {"type": "string"},
                                    "target_garment_subtypes": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "concept_notes": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}


def _compact_anchor(anchor: Dict[str, Any] | None) -> Optional[Dict[str, Any]]:
    if not anchor:
        return None
    keep = ("title", "garment_category", "garment_subtype", "primary_color",
            "secondary_color", "pattern_type", "formality_level", "occasion_fit")
    return {k: anchor.get(k) for k in keep if anchor.get(k)}


def _summarize_inventory(inventory: List[Dict[str, Any]] | None) -> Dict[str, int]:
    """Reduce the full per-row catalog inventory to a `{subtype: count}` dict.

    Saves ~1.5K tokens vs sending each `{gender, category, subtype,
    completeness, count}` row as a JSON object.
    """
    if not inventory:
        return {}
    out: Dict[str, int] = {}
    for row in inventory:
        sub = str(row.get("garment_subtype") or "").strip()
        if not sub:
            continue
        out[sub] = int(out.get(sub, 0)) + int(row.get("count") or 0)
    return out


def _summarize_previous_recs(prev: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    if not prev:
        return []
    keep = ("title", "garment_subtypes", "primary_colors", "occasion_fits", "formality_levels")
    return [{k: r.get(k) for k in keep if r.get(k) is not None} for r in prev]


def _build_planner_payload(ctx: CombinedContext) -> str:
    """Compact input for Stage A. Drops heavy fields (full conversation
    history, full attribute dump, full catalog rows) that Stage A doesn't
    need to make structure decisions — Stage B sees the full slice for
    its direction."""
    user = ctx.user
    profile_summary = {
        "gender": user.gender,
        "body_shape": _val(user.analysis_attributes.get("BodyShape")),
        "frame_structure": _val(user.derived_interpretations.get("FrameStructure")),
        "height_category": _val(user.derived_interpretations.get("HeightCategory")),
        "primary_archetype": (user.style_preference or {}).get("primaryArchetype"),
        "secondary_archetype": (user.style_preference or {}).get("secondaryArchetype"),
        "risk_tolerance": (user.style_preference or {}).get("riskTolerance"),
        "formality_lean": (user.style_preference or {}).get("formalityLean"),
        "seasonal_color_group": _val(user.derived_interpretations.get("SeasonalColorGroup")),
    }
    payload = {
        "user_message": ctx.live.user_need,
        "live_context": {
            "weather_context": ctx.live.weather_context or None,
            "time_of_day": ctx.live.time_of_day or None,
            "target_product_type": ctx.live.target_product_type or None,
            "is_followup": ctx.live.is_followup,
        },
        "conversation_memory": (
            ctx.conversation_memory.model_dump() if ctx.conversation_memory else None
        ),
        "profile_summary": profile_summary,
        "anchor_garment": _compact_anchor(getattr(ctx.live, "anchor_garment", None)),
        "catalog_inventory_summary": _summarize_inventory(ctx.catalog_inventory),
        "previous_recommendations_summary": _summarize_previous_recs(ctx.previous_recommendations),
        "hard_filters_seed": ctx.hard_filters,
    }
    return json.dumps(payload, indent=2, default=str)


def _val(field: Any) -> str:
    if isinstance(field, dict):
        return str(field.get("value") or "").strip()
    return str(field or "").strip()


class OutfitArchitectPlanner:
    """Stage A — structured reasoning over a small input.

    Returns the raw dict result (resolved_context + direction_plans);
    the dispatcher in `OutfitArchitect.plan` hands it to Stage B.
    """

    def __init__(self, model: str = "gpt-5.5") -> None:
        self._model = model
        self._system_prompt = _load_plan_prompt()
        self.last_usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    @cached_property
    def _client(self) -> OpenAI:
        return OpenAI(api_key=get_api_key())

    def plan(self, combined_context: CombinedContext) -> Dict[str, Any]:
        from platform_core.cost_estimator import extract_token_usage
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        response = self._client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": self._system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": _build_planner_payload(combined_context)}]},
            ],
            text={"format": _PLAN_SCHEMA},
        )
        self.last_usage = extract_token_usage(response)
        raw = json.loads(getattr(response, "output_text", "") or "{}")
        if not raw.get("direction_plans"):
            raise RuntimeError("Architect Planner returned no direction_plans")
        return raw
