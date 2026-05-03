from __future__ import annotations

import json
import logging
from functools import cached_property
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI

from user_profiler.config import get_api_key

from ..schemas import CombinedContext, DirectionSpec, QuerySpec, RecommendationPlan, ResolvedContextBlock

_log = logging.getLogger(__name__)


def _find_prompt_dir() -> Path:
    """Locate the `prompt/` directory by walking up from this file."""
    here = Path(__file__).resolve()
    for base in [here.parent] + list(here.parents):
        candidate = base / "prompt"
        if candidate.is_dir() and (candidate / "outfit_architect.md").exists():
            return candidate
    raise FileNotFoundError("Could not locate prompt/ directory containing outfit_architect.md")


def _load_prompt() -> str:
    """Load the base architect system prompt (~4.8K tokens after the
    May-3 trim). The anchor + follow-up modules are appended at request
    time by `_assemble_system_prompt`."""
    return (_find_prompt_dir() / "outfit_architect.md").read_text(encoding="utf-8").strip()


def _load_module(name: str) -> str:
    """Load a conditional prompt module from prompt/outfit_architect_<name>.md.

    Returns the trimmed file contents on success; on missing-file or read
    error, logs a warning and returns an empty string so the base prompt
    still ships (degraded but functional).
    """
    try:
        path = _find_prompt_dir() / f"outfit_architect_{name}.md"
        if not path.exists():
            _log.warning("Architect prompt module missing: %s", path)
            return ""
        return path.read_text(encoding="utf-8").strip()
    except (OSError, FileNotFoundError) as exc:  # noqa: BLE001
        _log.warning("Failed to load architect prompt module %s: %s", name, exc)
        return ""


def _assemble_system_prompt(
    base: str,
    *,
    has_anchor: bool,
    is_followup: bool,
    anchor_module: str = "",
    followup_module: str = "",
) -> str:
    """Conditionally append modules to the base prompt at request time.

    Lever 2 of the May 3, 2026 perf plan: the anchor + follow-up rule
    sections used to live in the always-loaded base prompt at ~1,100
    tokens of dead weight on every non-anchor / non-followup turn. We
    now load them only when the request actually needs them.
    """
    parts: List[str] = [base]
    if has_anchor and anchor_module:
        parts.append(anchor_module)
    if is_followup and followup_module:
        parts.append(followup_module)
    return "\n\n".join(parts)


_PLAN_JSON_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "name": "recommendation_plan",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["resolved_context", "retrieval_count", "directions"],
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
                    "ranking_bias",
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
                    "ranking_bias": {
                        "type": "string",
                        "enum": [
                            "conservative",
                            "balanced",
                            "expressive",
                            "formal_first",
                            "comfort_first",
                        ],
                    },
                },
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
                            "enum": ["complete", "paired", "three_piece"],
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
                                        "enum": ["complete", "top", "bottom", "outerwear"],
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

    live_context_block: Dict[str, Any] = {
        "weather_context": ctx.live.weather_context or None,
        "time_of_day": ctx.live.time_of_day or None,
        "target_product_type": ctx.live.target_product_type or None,
    }

    payload = {
        "profile": profile_block,
        "analysis_attributes": attrs,
        "derived_interpretations": interps,
        "style_preference": user.style_preference,
        "user_message": ctx.live.user_need,
        "live_context": live_context_block,
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
    def __init__(self, model: str = "gpt-5.5") -> None:
        # May 1, 2026: upgraded from gpt-5.4 to gpt-5.5. Architect quality
        # drives retrieval quality across the entire pipeline (directions,
        # hard filters, query documents) so we pay the bigger model on
        # a single call to lift the output of every downstream stage.
        #
        # Lazy OpenAI client (see CopilotPlanner for the pattern).
        self._model = model
        self._system_prompt_base = _load_prompt()
        self._anchor_module = _load_module("anchor")
        self._followup_module = _load_module("followup")
        # Item 4 (May 1, 2026): orchestrator picks this up post-call.
        self.last_usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    @cached_property
    def _client(self) -> OpenAI:
        return OpenAI(api_key=get_api_key())

    def _build_system_prompt(self, combined_context: CombinedContext) -> str:
        """Assemble the system prompt at request time, including only the
        modules relevant to this turn. See `_assemble_system_prompt`."""
        has_anchor = bool(getattr(combined_context.live, "anchor_garment", None))
        history = combined_context.conversation_history or []
        is_followup = bool(history) or bool(combined_context.previous_recommendations)
        return _assemble_system_prompt(
            self._system_prompt_base,
            has_anchor=has_anchor,
            is_followup=is_followup,
            anchor_module=self._anchor_module,
            followup_module=self._followup_module,
        )

    def plan(self, combined_context: CombinedContext) -> RecommendationPlan:
        """Generate a RecommendationPlan via LLM. Raises on failure."""
        from platform_core.cost_estimator import extract_token_usage
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        system_prompt = self._build_system_prompt(combined_context)
        response = self._client.responses.create(
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": _build_user_payload(combined_context)}],
                },
            ],
            text={"format": _PLAN_JSON_SCHEMA},
        )
        self.last_usage = extract_token_usage(response)

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
                ranking_bias=str(raw_resolved.get("ranking_bias") or "balanced"),
            )
        return RecommendationPlan(
            retrieval_count=int(raw.get("retrieval_count", 5)),
            directions=directions,
            plan_source="llm",
            resolved_context=resolved_ctx,
        )
