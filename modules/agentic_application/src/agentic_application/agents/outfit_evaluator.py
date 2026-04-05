from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from openai import OpenAI

from user_profiler.config import get_api_key

from ..intent_registry import FollowUpIntent
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
                        "style_note", "occasion_note",
                        "body_harmony_pct", "color_suitability_pct",
                        "style_fit_pct", "risk_tolerance_pct",
                        "occasion_pct", "comfort_boundary_pct",
                        "specific_needs_pct", "pairing_coherence_pct",
                        "classic_pct", "dramatic_pct", "romantic_pct",
                        "natural_pct", "minimalist_pct", "creative_pct",
                        "sporty_pct", "edgy_pct",
                        "item_ids",
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
                        "body_harmony_pct": {"type": "integer"},
                        "color_suitability_pct": {"type": "integer"},
                        "style_fit_pct": {"type": "integer"},
                        "risk_tolerance_pct": {"type": "integer"},
                        "occasion_pct": {"type": "integer"},
                        "comfort_boundary_pct": {"type": "integer"},
                        "specific_needs_pct": {"type": "integer"},
                        "pairing_coherence_pct": {"type": "integer"},
                        "classic_pct": {"type": "integer"},
                        "dramatic_pct": {"type": "integer"},
                        "romantic_pct": {"type": "integer"},
                        "natural_pct": {"type": "integer"},
                        "minimalist_pct": {"type": "integer"},
                        "creative_pct": {"type": "integer"},
                        "sporty_pct": {"type": "integer"},
                        "edgy_pct": {"type": "integer"},
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
    formality_levels = _dedupe_strings(item.get("formality_level") for item in candidate.items)
    pattern_types = _dedupe_strings(item.get("pattern_type") for item in candidate.items)
    volume_profiles = _dedupe_strings(item.get("volume_profile") for item in candidate.items)
    fit_types = _dedupe_strings(item.get("fit_type") for item in candidate.items)
    silhouette_types = _dedupe_strings(item.get("silhouette_type") for item in candidate.items)
    return {
        "candidate_id": candidate.candidate_id,
        "candidate_type": candidate.candidate_type,
        "primary_colors": colors,
        "occasion_fits": occasions,
        "roles": roles,
        "garment_categories": categories,
        "formality_levels": formality_levels,
        "pattern_types": pattern_types,
        "volume_profiles": volume_profiles,
        "fit_types": fit_types,
        "silhouette_types": silhouette_types,
    }


def _candidate_delta(
    candidate: OutfitCandidate,
    combined_context: CombinedContext,
) -> Dict[str, Any]:
    previous = _latest_previous_recommendation(combined_context)
    previous_colors = _dedupe_strings(previous.get("primary_colors") or [])
    previous_occasions = _dedupe_strings(previous.get("occasion_fits") or [])
    previous_roles = _dedupe_strings(previous.get("roles") or [])
    previous_formalities = _dedupe_strings(previous.get("formality_levels") or [])
    previous_patterns = _dedupe_strings(previous.get("pattern_types") or [])
    previous_volumes = _dedupe_strings(previous.get("volume_profiles") or [])
    previous_fits = _dedupe_strings(previous.get("fit_types") or [])
    previous_silhouettes = _dedupe_strings(previous.get("silhouette_types") or [])
    candidate_sig = _candidate_signature(candidate)
    candidate_colors = candidate_sig["primary_colors"]
    candidate_occasions = candidate_sig["occasion_fits"]
    candidate_roles = candidate_sig["roles"]
    candidate_formalities = candidate_sig["formality_levels"]
    candidate_patterns = candidate_sig["pattern_types"]
    candidate_volumes = candidate_sig["volume_profiles"]
    candidate_fits = candidate_sig["fit_types"]
    candidate_silhouettes = candidate_sig["silhouette_types"]

    formality_shift = ""
    if previous_formalities and candidate_formalities and previous_formalities != candidate_formalities:
        formality_shift = f"{', '.join(previous_formalities)}\u2192{', '.join(candidate_formalities)}"

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
        "formality_shift": formality_shift,
        "shared_patterns": [p for p in candidate_patterns if p in previous_patterns],
        "new_patterns": [p for p in candidate_patterns if p not in previous_patterns],
        "shared_volumes": [v for v in candidate_volumes if v in previous_volumes],
        "new_volumes": [v for v in candidate_volumes if v not in previous_volumes],
        "shared_fits": [f for f in candidate_fits if f in previous_fits],
        "new_fits": [f for f in candidate_fits if f not in previous_fits],
        "shared_silhouettes": [s for s in candidate_silhouettes if s in previous_silhouettes],
        "new_silhouettes": [s for s in candidate_silhouettes if s not in previous_silhouettes],
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

    if intent == FollowUpIntent.CHANGE_COLOR:
        new_colors = list(delta.get("new_colors") or [])
        shared_colors = list(delta.get("shared_colors") or [])
        reasoning = "Compared against the previous recommendation to find a meaningful color shift."
        if new_colors:
            color_note = f"Shifts the palette toward {', '.join(new_colors)}."
        elif shared_colors:
            color_note = f"Keeps prior colors {', '.join(shared_colors)} because stronger alternatives were limited."

        # Build style_note for preserved non-color attributes
        style_parts: list[str] = []
        if delta.get("preserves_occasion"):
            style_parts.append("occasion fit")
        if delta.get("candidate_type_matches_previous"):
            style_parts.append("outfit structure")
        if not delta.get("formality_shift"):
            style_parts.append("formality")
        shared_silhouettes = list(delta.get("shared_silhouettes") or [])
        if shared_silhouettes:
            style_parts.append(f"silhouette ({', '.join(shared_silhouettes)})")
        shared_fits = list(delta.get("shared_fits") or [])
        if shared_fits:
            style_parts.append(f"fit ({', '.join(shared_fits)})")
        shared_volumes = list(delta.get("shared_volumes") or [])
        if shared_volumes:
            style_parts.append(f"volume ({', '.join(shared_volumes)})")
        if style_parts:
            style_note = f"Preserves {', '.join(style_parts)} while shifting colors."

    elif intent == FollowUpIntent.SIMILAR_TO_PREVIOUS:
        preserved = []
        if delta.get("candidate_type_matches_previous"):
            preserved.append("outfit structure")
        if delta.get("preserves_occasion"):
            preserved.append("occasion fit")
        if delta.get("preserves_roles"):
            preserved.append("pairing roles")
        shared_colors = list(delta.get("shared_colors") or [])
        if shared_colors:
            preserved.append(f"colors ({', '.join(shared_colors)})")
        shared_patterns = list(delta.get("shared_patterns") or [])
        if shared_patterns:
            preserved.append(f"patterns ({', '.join(shared_patterns)})")
        shared_volumes = list(delta.get("shared_volumes") or [])
        if shared_volumes:
            preserved.append(f"volume ({', '.join(shared_volumes)})")
        shared_fits = list(delta.get("shared_fits") or [])
        if shared_fits:
            preserved.append(f"fit ({', '.join(shared_fits)})")
        shared_silhouettes = list(delta.get("shared_silhouettes") or [])
        if shared_silhouettes:
            preserved.append(f"silhouette ({', '.join(shared_silhouettes)})")
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
    candidate_item_ids: Dict[str, set[str]] = {
        c.candidate_id: {str(item.get("product_id", "")) for item in c.items}
        for c in candidates
    }
    deltas = _delta_lookup(candidates, combined_context)
    normalized: List[EvaluatedRecommendation] = []
    seen: set[str] = set()

    for entry in sorted(evaluations, key=lambda row: row.rank or 9999):
        if entry.candidate_id not in candidate_ids or entry.candidate_id in seen:
            continue
        seen.add(entry.candidate_id)
        delta = deltas.get(entry.candidate_id, {})
        defaults = _followup_reasoning_defaults(delta)

        # Clamp match_score to valid range
        clamped_score = max(0.0, min(1.0, entry.match_score))

        # Validate item_ids against actual candidate items
        valid_ids = candidate_item_ids.get(entry.candidate_id, set())
        validated_item_ids = [iid for iid in entry.item_ids if iid in valid_ids]
        if not validated_item_ids:
            validated_item_ids = sorted(valid_ids)

        normalized.append(
            entry.model_copy(
                update={
                    "match_score": clamped_score,
                    "item_ids": validated_item_ids,
                    "reasoning": entry.reasoning or defaults["reasoning"],
                    "body_note": entry.body_note or "Considered body proportions.",
                    "color_note": entry.color_note or defaults["color_note"] or "Considered color harmony.",
                    "style_note": entry.style_note or defaults["style_note"] or "Considered style fit.",
                    "occasion_note": entry.occasion_note or defaults["occasion_note"] or "Considered occasion appropriateness.",
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

    # Surface additional seasonal groups for multi-group evaluation
    seasonal_raw = user.derived_interpretations.get("SeasonalColorGroup")
    if isinstance(seasonal_raw, dict) and seasonal_raw.get("additional_groups"):
        interps["SeasonalColorGroup_additional"] = [
            g["value"] for g in seasonal_raw["additional_groups"]
        ]

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
        "body_context_summary": {
            "height_category": interps.get("height_category", "") or interps.get("HeightCategory", ""),
            "frame_structure": interps.get("frame_structure", "") or interps.get("FrameStructure", ""),
            "body_shape": attrs.get("body_shape", "") or attrs.get("BodyShape", ""),
        },
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
        if combined_context.live.followup_intent == FollowUpIntent.CHANGE_COLOR:
            if delta["new_colors"]:
                color_note = f"Introduces a new color direction with {', '.join(delta['new_colors'])}."
            elif delta["shared_colors"]:
                color_note = (
                    "Keeps the prior color story because no stronger alternative survived retrieval."
                )
            reasoning = "Ranked by retrieval similarity with color-shift comparison to the previous look."
            # Explain preserved non-color attributes
            fb_style_parts: list[str] = []
            if delta["preserves_occasion"]:
                fb_style_parts.append("occasion fit")
            if delta["candidate_type_matches_previous"]:
                fb_style_parts.append("outfit structure")
            if not delta["formality_shift"]:
                fb_style_parts.append("formality")
            if delta["shared_silhouettes"]:
                fb_style_parts.append(f"silhouette ({', '.join(delta['shared_silhouettes'])})")
            if delta["shared_fits"]:
                fb_style_parts.append(f"fit ({', '.join(delta['shared_fits'])})")
            if delta["shared_volumes"]:
                fb_style_parts.append(f"volume ({', '.join(delta['shared_volumes'])})")
            if fb_style_parts:
                style_note = f"Preserves {', '.join(fb_style_parts)} while shifting colors."
        elif combined_context.live.followup_intent == FollowUpIntent.SIMILAR_TO_PREVIOUS:
            preserved = []
            if delta["candidate_type_matches_previous"]:
                preserved.append("same outfit structure")
            if delta["preserves_occasion"]:
                preserved.append("same occasion")
            if delta["preserves_roles"]:
                preserved.append("same pairing roles")
            if delta["shared_colors"]:
                preserved.append(f"colors ({', '.join(delta['shared_colors'])})")
            if delta["shared_patterns"]:
                preserved.append(f"patterns ({', '.join(delta['shared_patterns'])})")
            if delta["shared_volumes"]:
                preserved.append(f"volume ({', '.join(delta['shared_volumes'])})")
            if delta["shared_fits"]:
                preserved.append(f"fit ({', '.join(delta['shared_fits'])})")
            if delta["shared_silhouettes"]:
                preserved.append(f"silhouette ({', '.join(delta['shared_silhouettes'])})")
            if preserved:
                style_note = f"Preserves {' and '.join(preserved)} from the previous recommendation."
            reasoning = "Ranked by retrieval similarity with similarity-to-previous comparison."
            if delta["occasion_shift"]:
                occasion_note = f"Shifts occasion emphasis toward {', '.join(delta['occasion_shift'])}."
        fallback_pct = max(0, min(100, int(candidate.assembly_score * 100)))
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
                body_harmony_pct=fallback_pct,
                color_suitability_pct=fallback_pct,
                style_fit_pct=fallback_pct,
                risk_tolerance_pct=fallback_pct,
                occasion_pct=fallback_pct,
                comfort_boundary_pct=fallback_pct,
                specific_needs_pct=fallback_pct,
                pairing_coherence_pct=fallback_pct,
                item_ids=item_ids,
            )
        )
    return results


class OutfitEvaluator:
    def __init__(self, model: str = "gpt-5.4") -> None:
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
                    body_harmony_pct=max(0, min(100, int(entry.get("body_harmony_pct", 0)))),
                    color_suitability_pct=max(0, min(100, int(entry.get("color_suitability_pct", 0)))),
                    style_fit_pct=max(0, min(100, int(entry.get("style_fit_pct", 0)))),
                    risk_tolerance_pct=max(0, min(100, int(entry.get("risk_tolerance_pct", 0)))),
                    occasion_pct=max(0, min(100, int(entry.get("occasion_pct", 0)))),
                    comfort_boundary_pct=max(0, min(100, int(entry.get("comfort_boundary_pct", 0)))),
                    specific_needs_pct=max(0, min(100, int(entry.get("specific_needs_pct", 0)))),
                    pairing_coherence_pct=max(0, min(100, int(entry.get("pairing_coherence_pct", 0)))),
                    classic_pct=max(0, min(100, int(entry.get("classic_pct", 0)))),
                    dramatic_pct=max(0, min(100, int(entry.get("dramatic_pct", 0)))),
                    romantic_pct=max(0, min(100, int(entry.get("romantic_pct", 0)))),
                    natural_pct=max(0, min(100, int(entry.get("natural_pct", 0)))),
                    minimalist_pct=max(0, min(100, int(entry.get("minimalist_pct", 0)))),
                    creative_pct=max(0, min(100, int(entry.get("creative_pct", 0)))),
                    sporty_pct=max(0, min(100, int(entry.get("sporty_pct", 0)))),
                    edgy_pct=max(0, min(100, int(entry.get("edgy_pct", 0)))),
                    item_ids=list(entry.get("item_ids", [])),
                )
            )
        return _normalize_evaluations(results, candidates, combined_context)
