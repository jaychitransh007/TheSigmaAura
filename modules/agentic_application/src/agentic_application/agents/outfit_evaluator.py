from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI

from user_profiler.config import get_api_key

from ..schemas import (
    CombinedContext,
    EvaluatedRecommendation,
    OutfitCandidate,
    RecommendationPlan,
)


def _load_prompt() -> str:
    prompt_dir = Path(__file__).resolve()
    for base in [prompt_dir.parent] + list(prompt_dir.parents):
        candidate = base / "prompt" / "outfit_evaluator.md"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()
    raise FileNotFoundError("Could not locate prompt/outfit_evaluator.md")


_EVAL_JSON_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "name": "outfit_evaluations",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["evaluations"],
        "properties": {
            "evaluations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "candidate_id", "rank", "match_score", "title",
                        "reasoning", "body_note", "color_note",
                        "style_note", "occasion_note", "item_ids",
                    ],
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "rank": {"type": "integer"},
                        "match_score": {"type": "number"},
                        "title": {"type": "string"},
                        "reasoning": {"type": "string"},
                        "body_note": {"type": "string"},
                        "color_note": {"type": "string"},
                        "style_note": {"type": "string"},
                        "occasion_note": {"type": "string"},
                        "item_ids": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
    },
}


def _build_eval_payload(
    candidates: List[OutfitCandidate],
    combined_context: CombinedContext,
    plan: RecommendationPlan,
) -> str:
    user = combined_context.user
    attrs = {}
    for k, v in user.analysis_attributes.items():
        attrs[k] = v.get("value", "") if isinstance(v, dict) else v
    interps = {}
    for k, v in user.derived_interpretations.items():
        interps[k] = v.get("value", "") if isinstance(v, dict) else v

    payload = {
        "user_profile": {
            "gender": user.gender,
            "height_cm": user.height_cm,
            "waist_cm": user.waist_cm,
            "analysis_attributes": attrs,
            "derived_interpretations": interps,
            "style_preference": user.style_preference,
        },
        "live_context": combined_context.live.model_dump(),
        "plan_type": plan.plan_type,
        "candidates": [c.model_dump() for c in candidates],
    }
    return json.dumps(payload, indent=2, default=str)


def _fallback_evaluations(
    candidates: List[OutfitCandidate],
) -> List[EvaluatedRecommendation]:
    """Graceful degradation: return candidates sorted by assembly_score."""
    sorted_candidates = sorted(candidates, key=lambda c: c.assembly_score, reverse=True)
    results: List[EvaluatedRecommendation] = []
    for rank, candidate in enumerate(sorted_candidates[:5], start=1):
        item_ids = [str(item.get("product_id", "")) for item in candidate.items]
        title = " + ".join(
            str(item.get("title", "")) for item in candidate.items if item.get("title")
        ) or f"Outfit {rank}"
        results.append(
            EvaluatedRecommendation(
                candidate_id=candidate.candidate_id,
                rank=rank,
                match_score=candidate.assembly_score,
                title=title,
                reasoning="Ranked by retrieval similarity.",
                body_note="",
                color_note="",
                style_note="",
                occasion_note="",
                item_ids=item_ids,
            )
        )
    return results


class OutfitEvaluator:
    def __init__(self, model: str = "gpt-5-mini") -> None:
        self._client = OpenAI(api_key=get_api_key())
        self._model = model
        self._system_prompt = _load_prompt()

    def evaluate(
        self,
        candidates: List[OutfitCandidate],
        combined_context: CombinedContext,
        plan: RecommendationPlan,
    ) -> List[EvaluatedRecommendation]:
        """Evaluate and rank outfit candidates. Falls back on LLM failure."""
        if not candidates:
            return []

        try:
            return self._llm_evaluate(candidates, combined_context, plan)
        except Exception:
            return _fallback_evaluations(candidates)

    def _llm_evaluate(
        self,
        candidates: List[OutfitCandidate],
        combined_context: CombinedContext,
        plan: RecommendationPlan,
    ) -> List[EvaluatedRecommendation]:
        user_payload = _build_eval_payload(candidates, combined_context, plan)

        response = self._client.responses.create(
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": self._system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_payload}],
                },
            ],
            text={"format": _EVAL_JSON_SCHEMA},
        )

        raw = json.loads(getattr(response, "output_text", "") or "{}")
        evaluations = raw.get("evaluations", [])

        results: List[EvaluatedRecommendation] = []
        for entry in evaluations:
            results.append(
                EvaluatedRecommendation(
                    candidate_id=str(entry.get("candidate_id", "")),
                    rank=int(entry.get("rank", 0)),
                    match_score=float(entry.get("match_score", 0.0)),
                    title=str(entry.get("title", "")),
                    reasoning=str(entry.get("reasoning", "")),
                    body_note=str(entry.get("body_note", "")),
                    color_note=str(entry.get("color_note", "")),
                    style_note=str(entry.get("style_note", "")),
                    occasion_note=str(entry.get("occasion_note", "")),
                    item_ids=list(entry.get("item_ids", [])),
                )
            )
        return results
