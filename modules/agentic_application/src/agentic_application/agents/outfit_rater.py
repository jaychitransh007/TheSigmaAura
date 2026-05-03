"""Outfit Rater — May 3 2026.

Second LLM stage in the new ranker pipeline. Takes the Composer's
output (up to 10 constructed outfits) plus the user request + context
and emits a four-dimension rubric score per outfit, a derived
fashion_score, a rank ordering, and an `unsuitable` veto flag.

Replaces the deterministic Reranker. The fashion_score is a weighted
blend of `occasion_fit`, `body_harmony`, `color_harmony`,
`archetype_match` — all 0–100 integers. The blend weights have a
default and intent-driven overrides; both live in the prompt so the
model can shift them turn by turn.

Audit:
- model_call_logs gets the full raw request + response.
- tool_traces gets a distilled `rater_decision` row with
  per-outfit scores + rationales preserved.
"""

from __future__ import annotations

import json
import logging
from functools import cached_property
from pathlib import Path
from typing import Any, Dict, List, Sequence

from openai import OpenAI

from platform_core.cost_estimator import extract_token_usage
from user_profiler.config import get_api_key

from ..schemas import (
    CombinedContext,
    ComposedOutfit,
    RatedOutfit,
    RaterResult,
    RetrievedProduct,
    RetrievedSet,
)
from .outfit_composer import _ITEM_ATTRS, _item_summary, _user_context_block

_log = logging.getLogger(__name__)


def _find_prompt_dir() -> Path:
    here = Path(__file__).resolve()
    for base in [here.parent] + list(here.parents):
        candidate = base / "prompt"
        if candidate.is_dir() and (candidate / "outfit_rater.md").exists():
            return candidate
    raise FileNotFoundError("Could not locate prompt/ directory containing outfit_rater.md")


def _load_prompt() -> str:
    return (_find_prompt_dir() / "outfit_rater.md").read_text(encoding="utf-8").strip()


_RATER_JSON_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "name": "outfit_rater_result",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["ranked_outfits", "overall_assessment"],
        "properties": {
            "ranked_outfits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "composer_id",
                        "rank",
                        "fashion_score",
                        "occasion_fit",
                        "body_harmony",
                        "color_harmony",
                        "archetype_match",
                        "rationale",
                        "unsuitable",
                    ],
                    "properties": {
                        "composer_id": {"type": "string"},
                        "rank": {"type": "integer"},
                        "fashion_score": {"type": "integer"},
                        "occasion_fit": {"type": "integer"},
                        "body_harmony": {"type": "integer"},
                        "color_harmony": {"type": "integer"},
                        "archetype_match": {"type": "integer"},
                        "rationale": {"type": "string"},
                        "unsuitable": {"type": "boolean"},
                    },
                },
            },
            "overall_assessment": {
                "type": "string",
                "enum": ["strong", "moderate", "weak"],
            },
        },
    },
}


def _build_outfit_payload(
    composed: Sequence[ComposedOutfit],
    items_by_id: Dict[str, RetrievedProduct],
) -> List[Dict[str, Any]]:
    """For each composed outfit, expand its item_ids into the full attr
    dict the Rater will see. Anything the Rater needs to reason about
    style coherence belongs here."""
    payload: List[Dict[str, Any]] = []
    for outfit in composed:
        item_details = []
        for iid in outfit.item_ids:
            product = items_by_id.get(iid)
            if product is None:
                # Composer validation passed but we lost the product —
                # shouldn't happen. Surface a stub so the Rater can
                # still reason about what's there.
                # Pad with empty strings for every attr the Rater
                # prompt promises so the schema stays consistent.
                item_details.append({
                    "item_id": iid,
                    "title": "(missing)",
                    **{k: "" for k in _ITEM_ATTRS},
                })
                continue
            item_details.append(_item_summary(iid, product))
        payload.append(
            {
                "composer_id": outfit.composer_id,
                "direction_id": outfit.direction_id,
                "direction_type": outfit.direction_type,
                "composer_rationale": outfit.rationale,
                "item_details": item_details,
            }
        )
    return payload


class OutfitRater:
    """LLM-driven outfit scorer. One gpt-5-mini call per turn.

    Inputs: the Composer's outfits + user message + user context.
    Output: ranked outfits with per-dimension scores, blended
    fashion_score, and unsuitable veto.
    """

    def __init__(self, model: str = "gpt-5-mini") -> None:
        self._model = model
        self._system_prompt = _load_prompt()
        self.last_usage: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    @cached_property
    def _client(self) -> OpenAI:
        return OpenAI(api_key=get_api_key())

    def rate(
        self,
        combined_context: CombinedContext,
        composed_outfits: Sequence[ComposedOutfit],
        retrieved_sets: Sequence[RetrievedSet],
    ) -> RaterResult:
        """Score and rank the composed outfits. One LLM call.

        ``retrieved_sets`` is the same pool the Composer saw — we use it
        only to look up each item's full attributes for the Rater's
        prompt.
        """
        if not composed_outfits:
            return RaterResult(ranked_outfits=[], overall_assessment="weak")

        items_by_id: Dict[str, RetrievedProduct] = {}
        for rs in retrieved_sets:
            for p in rs.products:
                items_by_id[p.product_id] = p

        user_payload = json.dumps(
            {
                "user": _user_context_block(combined_context),
                "outfits": _build_outfit_payload(composed_outfits, items_by_id),
            },
            indent=2,
            default=str,
        )

        response = self._client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": self._system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_payload}]},
            ],
            text={"format": _RATER_JSON_SCHEMA},
        )
        self.last_usage = extract_token_usage(response)
        raw_text = getattr(response, "output_text", "") or "{}"
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            _log.warning("OutfitRater: JSON parse failed (%s); returning empty result", exc)
            return RaterResult(ranked_outfits=[], overall_assessment="weak", raw_response=raw_text)

        valid_ids = {o.composer_id for o in composed_outfits}
        ranked: List[RatedOutfit] = []
        for raw_o in raw.get("ranked_outfits", []):
            cid = str(raw_o.get("composer_id", ""))
            if cid not in valid_ids:
                _log.warning("OutfitRater: dropping unknown composer_id %s", cid)
                continue
            ranked.append(
                RatedOutfit(
                    composer_id=cid,
                    rank=int(raw_o.get("rank", 0) or 0),
                    fashion_score=_clamp01(int(raw_o.get("fashion_score", 0) or 0)),
                    occasion_fit=_clamp01(int(raw_o.get("occasion_fit", 0) or 0)),
                    body_harmony=_clamp01(int(raw_o.get("body_harmony", 0) or 0)),
                    color_harmony=_clamp01(int(raw_o.get("color_harmony", 0) or 0)),
                    archetype_match=_clamp01(int(raw_o.get("archetype_match", 0) or 0)),
                    rationale=str(raw_o.get("rationale", "")),
                    unsuitable=bool(raw_o.get("unsuitable", False)),
                )
            )

        # Renumber ranks defensively in fashion_score-desc order. The
        # Rater is supposed to do this in the prompt but if it sends a
        # bad ordering we don't want it to leak downstream.
        ranked.sort(key=lambda r: (-r.fashion_score, r.composer_id))
        for i, r in enumerate(ranked, start=1):
            r.rank = i

        return RaterResult(
            ranked_outfits=ranked,
            overall_assessment=str(raw.get("overall_assessment") or "moderate"),
            raw_response=raw_text,
        )


def _clamp01(value: int) -> int:
    """Clamp an int to 0..100. Defensive — the prompt asks for 0–100 but
    the model occasionally emits 0–10 or 0–1 scores during early-stage
    drift. Clamp first, calibrate later."""
    return max(0, min(100, int(value)))
