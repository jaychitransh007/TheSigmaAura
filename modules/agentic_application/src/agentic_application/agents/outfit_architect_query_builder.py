"""Stage B of the split architect (May 3, 2026 — Lever 3 of the perf plan).

Takes one direction plan (from Stage A) + the per-direction-relevant
slice of user context, and emits the populated `QuerySpec[]` with full
`query_document` strings. One call per direction; the dispatcher runs
multiple Stage B calls in parallel via `ThreadPoolExecutor`.

Runs on gpt-5-mini by default — query writing is a tractable
transformation that doesn't need the bigger reasoning model.
"""

from __future__ import annotations

import json
import logging
from functools import cached_property
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI

from user_profiler.config import get_api_key

from ..schemas import CombinedContext, QuerySpec

_log = logging.getLogger(__name__)


def _load_query_prompt() -> str:
    here = Path(__file__).resolve()
    for base in [here.parent] + list(here.parents):
        candidate = base / "prompt" / "outfit_architect_query.md"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()
    raise FileNotFoundError("prompt/outfit_architect_query.md not found")


_QUERY_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "name": "architect_query_builder",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["direction_id", "queries"],
        "properties": {
            "direction_id": {"type": "string"},
            "queries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["query_id", "role", "hard_filters", "query_document"],
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
                        "query_document": {"type": "string"},
                    },
                },
            },
        },
    },
}


def _val(field: Any) -> str:
    if isinstance(field, dict):
        return str(field.get("value") or "").strip()
    return str(field or "").strip()


def _build_query_payload(
    *, direction_plan: Dict[str, Any], ctx: CombinedContext, resolved_context: Dict[str, Any],
) -> str:
    """Per-direction input to Stage B. We send the full color/style
    palette + body attribute slice (all needed to write a complete query
    document) but skip the conversation history and previous recs that
    Stage A already used to make structure decisions."""
    user = ctx.user
    interps: Dict[str, Any] = {}
    for key in user.derived_interpretations:
        raw = user.derived_interpretations[key]
        if isinstance(raw, dict):
            v = raw.get("value", "")
            interps[key] = ", ".join(v) if isinstance(v, list) else str(v or "").strip()
        else:
            interps[key] = str(raw or "").strip()
    base_colors = _list_field(user.derived_interpretations.get("BaseColors"))
    accent_colors = _list_field(user.derived_interpretations.get("AccentColors"))
    avoid_colors = _list_field(user.derived_interpretations.get("AvoidColors"))
    seasonal_additional: List[str] = []
    seasonal_raw = user.derived_interpretations.get("SeasonalColorGroup")
    if isinstance(seasonal_raw, dict) and seasonal_raw.get("additional_groups"):
        seasonal_additional = [g["value"] for g in seasonal_raw["additional_groups"] if g.get("value")]

    profile = {
        "gender": user.gender,
        "body_shape": _val(user.analysis_attributes.get("BodyShape")),
        "frame_structure": interps.get("FrameStructure"),
        "height_category": interps.get("HeightCategory"),
        "waist_size_band": interps.get("WaistSizeBand"),
        "sub_season": interps.get("SubSeason"),
        "skin_hair_contrast": interps.get("SkinHairContrast"),
        "color_dimension_profile": interps.get("ColorDimensionProfile"),
        "contrast_level": interps.get("ContrastLevel"),
    }
    payload = {
        "direction": direction_plan,
        "resolved_context": resolved_context,
        "live_context": {
            "weather_context": ctx.live.weather_context or None,
            "time_of_day": ctx.live.time_of_day or None,
        },
        "user_message": ctx.live.user_need,
        "profile": profile,
        "style_preference": user.style_preference,
        "base_colors": base_colors,
        "accent_colors": accent_colors,
        "avoid_colors": avoid_colors,
        "seasonal_color_group_additional": seasonal_additional,
    }
    if getattr(ctx.live, "anchor_garment", None):
        payload["anchor_garment"] = ctx.live.anchor_garment
    return json.dumps(payload, indent=2, default=str)


def _list_field(field: Any) -> List[str]:
    if isinstance(field, dict):
        v = field.get("value")
        if isinstance(v, list):
            return [str(x) for x in v if x]
        if isinstance(v, str) and v:
            return [v]
    return []


class OutfitArchitectQueryBuilder:
    """Stage B — per-direction query writer.

    `build(direction_plan, ctx, resolved_context)` returns a list of
    `QuerySpec` for the direction. The dispatcher in
    `OutfitArchitect.plan` calls this once per direction in parallel.
    """

    def __init__(self, model: str = "gpt-5-mini") -> None:
        self._model = model
        self._system_prompt = _load_query_prompt()
        self.last_usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    @cached_property
    def _client(self) -> OpenAI:
        return OpenAI(api_key=get_api_key())

    def build(
        self,
        *,
        direction_plan: Dict[str, Any],
        combined_context: CombinedContext,
        resolved_context: Dict[str, Any],
    ) -> tuple[List[QuerySpec], Dict[str, int]]:
        """Return ``(queries, usage)`` so a parallel caller can tally
        per-call token counts without racing on instance state."""
        from platform_core.cost_estimator import extract_token_usage
        local_usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        # max_output_tokens is the latency lever — empirical (May 3, 2026):
        # without a cap, Stage B emits 3.5K+ tokens per call and split
        # mode loses to monolithic. The first try at 1,500 was too
        # tight: a paired direction emits 2 query_documents × ~400
        # tokens + JSON envelope including \n escaping easily exceeds
        # 1,500 and truncates mid-JSON. 3,000 leaves room for the
        # full response while keeping each parallel call meaningfully
        # bounded — at gpt-5-mini's ~100 tok/s, 3K tokens = ~30s
        # wallclock per parallel call; with prompt-level output budget
        # (≤ 1,200 tokens / response, ≤ 350 / query_document) the
        # typical call lands well under the cap.
        response = self._client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": self._system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": _build_query_payload(
                    direction_plan=direction_plan, ctx=combined_context, resolved_context=resolved_context,
                )}]},
            ],
            text={"format": _QUERY_SCHEMA},
            max_output_tokens=3000,
        )
        local_usage = extract_token_usage(response) or local_usage
        # Best-effort instance attr for tests that look at last_usage.
        # Threaded callers should rely on the returned tuple, not this.
        self.last_usage = dict(local_usage)
        # Detect truncation by max_output_tokens — surface a clear
        # error rather than the cryptic "no queries" the empty-array
        # case used to produce.
        incomplete = getattr(response, "incomplete_details", None)
        if incomplete is not None:
            reason = getattr(incomplete, "reason", None) or (
                incomplete.get("reason") if isinstance(incomplete, dict) else None
            )
            if reason:
                raise RuntimeError(
                    f"Architect Query Builder response was incomplete (reason={reason}); "
                    "try widening max_output_tokens or tightening the output budget in "
                    "prompt/outfit_architect_query.md."
                )
        output_text = getattr(response, "output_text", "") or ""
        try:
            raw = json.loads(output_text) if output_text else {}
        except json.JSONDecodeError as exc:
            _log.warning(
                "Architect Query Builder returned invalid JSON (likely truncated): %s",
                str(exc)[:200],
            )
            raise RuntimeError(
                "Architect Query Builder returned invalid JSON — likely truncated. "
                f"Output length: {len(output_text)} chars."
            ) from exc
        queries_raw = raw.get("queries") or []
        queries = [
            QuerySpec(
                query_id=str(q.get("query_id") or ""),
                role=str(q.get("role") or ""),
                hard_filters=dict(q.get("hard_filters") or {}),
                query_document=str(q.get("query_document") or ""),
            )
            for q in queries_raw
        ]
        return queries, dict(local_usage)
