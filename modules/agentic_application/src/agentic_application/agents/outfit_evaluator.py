from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

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


def _dedupe_strings(values: Iterable[Any]) -> List[str]:
    ordered: List[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _latest_previous_recommendation(combined_context: CombinedContext) -> Dict[str, Any]:
    previous = combined_context.previous_recommendations or []
    if previous and isinstance(previous[0], dict):
        return previous[0]
    return {}


def _candidate_signature(candidate: OutfitCandidate) -> Dict[str, Any]:
    colors = _dedupe_strings(item.get("primary_color") for item in candidate.items)
    occasions = _dedupe_strings(item.get("occasion_fit") for item in candidate.items)
    roles = _dedupe_strings(item.get("role") for item in candidate.items)
    categories = _dedupe_strings(item.get("garment_category") for item in candidate.items)
    return {
        "candidate_id": candidate.candidate_id,
        "candidate_type": candidate.candidate_type,
        "primary_colors": colors,
        "occasion_fits": occasions,
        "roles": roles,
        "garment_categories": categories,
    }


def _candidate_delta(
    candidate: OutfitCandidate,
    combined_context: CombinedContext,
) -> Dict[str, Any]:
    previous = _latest_previous_recommendation(combined_context)
    previous_colors = _dedupe_strings(previous.get("primary_colors") or [])
    previous_occasions = _dedupe_strings(previous.get("occasion_fits") or [])
    previous_roles = _dedupe_strings(previous.get("roles") or [])
    candidate_sig = _candidate_signature(candidate)
    candidate_colors = candidate_sig["primary_colors"]
    candidate_occasions = candidate_sig["occasion_fits"]
    candidate_roles = candidate_sig["roles"]

    return {
        "candidate_id": candidate.candidate_id,
        "followup_intent": combined_context.live.followup_intent,
        "candidate_type_matches_previous": (
            bool(previous)
            and str(previous.get("candidate_type") or "").strip().lower() == candidate.candidate_type
        ),
        "shared_colors": [color for color in candidate_colors if color in previous_colors],
        "new_colors": [color for color in candidate_colors if color not in previous_colors],
        "preserves_occasion": any(occasion in previous_occasions for occasion in candidate_occasions),
        "occasion_shift": [occasion for occasion in candidate_occasions if occasion not in previous_occasions],
        "preserves_roles": bool(candidate_roles) and candidate_roles == previous_roles,
    }


def _delta_lookup(
    candidates: List[OutfitCandidate],
    combined_context: CombinedContext,
) -> Dict[str, Dict[str, Any]]:
    return {
        candidate.candidate_id: _candidate_delta(candidate, combined_context)
        for candidate in candidates
    }


def _followup_reasoning_defaults(
    delta: Dict[str, Any],
) -> Dict[str, str]:
    intent = str(delta.get("followup_intent") or "").strip()
    reasoning = ""
    color_note = ""
    style_note = ""
    occasion_note = ""

    if intent == "change_color":
        new_colors = list(delta.get("new_colors") or [])
        shared_colors = list(delta.get("shared_colors") or [])
        reasoning = "Compared against the previous recommendation to find a meaningful color shift."
        if new_colors:
            color_note = f"Shifts the palette toward {', '.join(new_colors)}."
        elif shared_colors:
            color_note = f"Keeps prior colors {', '.join(shared_colors)} because stronger alternatives were limited."
    elif intent == "similar_to_previous":
        preserved = []
        if delta.get("candidate_type_matches_previous"):
            preserved.append("outfit structure")
        if delta.get("preserves_occasion"):
            preserved.append("occasion fit")
        if delta.get("preserves_roles"):
            preserved.append("pairing roles")
        reasoning = "Compared against the previous recommendation to preserve its strongest qualities."
        if preserved:
            style_note = f"Preserves {', '.join(preserved)} from the previous recommendation."
        shifts = list(delta.get("occasion_shift") or [])
        if shifts:
            occasion_note = f"Adjusts occasion emphasis toward {', '.join(shifts)}."

    return {
        "reasoning": reasoning,
        "color_note": color_note,
        "style_note": style_note,
        "occasion_note": occasion_note,
    }


def _normalize_evaluations(
    evaluations: List[EvaluatedRecommendation],
    candidates: List[OutfitCandidate],
    combined_context: CombinedContext,
) -> List[EvaluatedRecommendation]:
    candidate_ids = {candidate.candidate_id for candidate in candidates}
    deltas = _delta_lookup(candidates, combined_context)
    normalized: List[EvaluatedRecommendation] = []
    seen: set[str] = set()

    for entry in sorted(evaluations, key=lambda row: row.rank or 9999):
        if entry.candidate_id not in candidate_ids or entry.candidate_id in seen:
            continue
        seen.add(entry.candidate_id)
        delta = deltas.get(entry.candidate_id, {})
        defaults = _followup_reasoning_defaults(delta)
        normalized.append(
            entry.model_copy(
                update={
                    "reasoning": entry.reasoning or defaults["reasoning"],
                    "color_note": entry.color_note or defaults["color_note"],
                    "style_note": entry.style_note or defaults["style_note"],
                    "occasion_note": entry.occasion_note or defaults["occasion_note"],
                }
            )
        )

    for rank, entry in enumerate(normalized, start=1):
        normalized[rank - 1] = entry.model_copy(update={"rank": rank})

    return normalized[:5]


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
        "conversation_memory": (
            combined_context.conversation_memory.model_dump()
            if combined_context.conversation_memory
            else None
        ),
        "previous_recommendations": combined_context.previous_recommendations,
        "previous_recommendation_focus": _latest_previous_recommendation(combined_context) or None,
        "plan_type": plan.plan_type,
        "candidates": [c.model_dump() for c in candidates],
        "candidate_deltas": [_candidate_delta(candidate, combined_context) for candidate in candidates],
    }
    return json.dumps(payload, indent=2, default=str)


def _fallback_evaluations(
    candidates: List[OutfitCandidate],
    combined_context: CombinedContext,
) -> List[EvaluatedRecommendation]:
    """Graceful degradation: return candidates sorted by assembly_score."""
    sorted_candidates = sorted(candidates, key=lambda c: c.assembly_score, reverse=True)
    results: List[EvaluatedRecommendation] = []
    for rank, candidate in enumerate(sorted_candidates[:5], start=1):
        item_ids = [str(item.get("product_id", "")) for item in candidate.items]
        title = " + ".join(
            str(item.get("title", "")) for item in candidate.items if item.get("title")
        ) or f"Outfit {rank}"
        delta = _candidate_delta(candidate, combined_context)
        reasoning = "Ranked by retrieval similarity."
        color_note = ""
        style_note = ""
        occasion_note = ""
        if combined_context.live.followup_intent == "change_color":
            if delta["new_colors"]:
                color_note = f"Introduces a new color direction with {', '.join(delta['new_colors'])}."
            elif delta["shared_colors"]:
                color_note = (
                    "Keeps the prior color story because no stronger alternative survived retrieval."
                )
            reasoning = "Ranked by retrieval similarity with color-shift comparison to the previous look."
        elif combined_context.live.followup_intent == "similar_to_previous":
            preserved = []
            if delta["candidate_type_matches_previous"]:
                preserved.append("same outfit structure")
            if delta["preserves_occasion"]:
                preserved.append("same occasion")
            if delta["preserves_roles"]:
                preserved.append("same pairing roles")
            if preserved:
                style_note = f"Preserves {' and '.join(preserved)} from the previous recommendation."
            reasoning = "Ranked by retrieval similarity with similarity-to-previous comparison."
            if delta["occasion_shift"]:
                occasion_note = f"Shifts occasion emphasis toward {', '.join(delta['occasion_shift'])}."
        results.append(
            EvaluatedRecommendation(
                candidate_id=candidate.candidate_id,
                rank=rank,
                match_score=candidate.assembly_score,
                title=title,
                reasoning=reasoning,
                body_note="",
                color_note=color_note,
                style_note=style_note,
                occasion_note=occasion_note,
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
            return _fallback_evaluations(candidates, combined_context)

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
        return _normalize_evaluations(results, candidates, combined_context)
