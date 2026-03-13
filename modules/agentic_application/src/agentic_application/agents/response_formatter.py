from __future__ import annotations

from typing import Any, Dict, List

from ..schemas import (
    CombinedContext,
    EvaluatedRecommendation,
    OutfitCandidate,
    OutfitCard,
    RecommendationPlan,
    RecommendationResponse,
)

MAX_FORMATTED_OUTFITS = 3


def _build_item_card(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "product_id": str(item.get("product_id", "")),
        "similarity": float(item.get("similarity", 0.0) or 0.0),
        "title": str(item.get("title", "")),
        "image_url": str(item.get("image_url", "")),
        "price": str(item.get("price", "")),
        "product_url": str(item.get("product_url", "")),
        "garment_category": str(item.get("garment_category", "")),
        "garment_subtype": str(item.get("garment_subtype", "")),
        "primary_color": str(item.get("primary_color", "")),
        "role": str(item.get("role", "")),
    }


def _candidate_items_by_id(
    candidates: List[OutfitCandidate],
) -> Dict[str, List[Dict[str, Any]]]:
    return {c.candidate_id: c.items for c in candidates}


class ResponseFormatter:
    """Converts evaluated recommendations into user-facing response."""

    def format(
        self,
        evaluated: List[EvaluatedRecommendation],
        combined_context: CombinedContext,
        plan: RecommendationPlan,
        candidates: List[OutfitCandidate],
    ) -> RecommendationResponse:
        if not evaluated:
            return RecommendationResponse(
                success=True,
                message="I couldn't find matching outfits for your request. Try broadening your requirements.",
                outfits=[],
                follow_up_suggestions=["Try a different occasion", "Show me something casual"],
                metadata={
                    "plan_type": plan.plan_type,
                    "plan_source": plan.plan_source,
                    "direction_count": len(plan.directions),
                },
            )

        items_lookup = _candidate_items_by_id(candidates)
        outfits: List[OutfitCard] = []

        for rec in sorted(evaluated, key=lambda r: r.rank)[:MAX_FORMATTED_OUTFITS]:
            items = items_lookup.get(rec.candidate_id, [])
            outfits.append(
                OutfitCard(
                    rank=rec.rank,
                    title=rec.title,
                    reasoning=rec.reasoning,
                    body_note=rec.body_note,
                    color_note=rec.color_note,
                    style_note=rec.style_note,
                    occasion_note=rec.occasion_note,
                    items=[_build_item_card(item) for item in items],
                )
            )

        message = self._build_message(combined_context, outfits)
        suggestions = self._build_follow_up_suggestions(combined_context, plan)

        return RecommendationResponse(
            success=True,
            message=message,
            outfits=outfits,
            follow_up_suggestions=suggestions,
            metadata={
                "plan_type": plan.plan_type,
                "plan_source": plan.plan_source,
                "direction_count": len(plan.directions),
                "outfit_count": len(outfits),
            },
        )

    def _build_message(
        self, ctx: CombinedContext, outfits: List[OutfitCard]
    ) -> str:
        parts: List[str] = [f"Here are {len(outfits)} outfit recommendations"]

        occasion = ctx.live.occasion_signal
        if occasion:
            parts.append(f"for your {occasion.replace('_', ' ')}")

        primary = str(ctx.user.style_preference.get("primaryArchetype") or "").strip()
        seasonal = ""
        sg = ctx.user.derived_interpretations.get("SeasonalColorGroup")
        if isinstance(sg, dict):
            seasonal = str(sg.get("value") or "").strip()
        elif isinstance(sg, str):
            seasonal = sg.strip()

        qualifiers: List[str] = []
        if primary:
            qualifiers.append(f"{primary} style")
        if seasonal:
            qualifiers.append(f"{seasonal} palette")
        if qualifiers:
            parts.append(f"considering your {' and '.join(qualifiers)}")

        return ", ".join(parts) + "."

    def _build_follow_up_suggestions(
        self, ctx: CombinedContext, plan: RecommendationPlan
    ) -> List[str]:
        suggestions: List[str] = []

        if ctx.live.formality_hint in {"formal", "semi_formal", "ultra_formal"}:
            suggestions.append("Show me something less formal")
        elif ctx.live.formality_hint in {"casual", "smart_casual"}:
            suggestions.append("Show me something more formal")

        if plan.plan_type == "complete_only":
            suggestions.append("Show me top and bottom pairings instead")
        elif plan.plan_type == "paired_only":
            suggestions.append("Show me complete outfit alternatives")

        suggestions.append("Show me bolder options")
        suggestions.append("Show me more options")
        suggestions.append("Something completely different")

        return suggestions[:5]
