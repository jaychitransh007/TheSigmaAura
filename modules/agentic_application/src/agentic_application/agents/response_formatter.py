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

import re

MAX_FORMATTED_OUTFITS = 3

_ARCHETYPE_RE = re.compile(r"style_archetype_primary:\s*(.+)", re.IGNORECASE)


def _extract_plan_archetype(plan: RecommendationPlan | None) -> str:
    """Extract the style archetype actually used in the plan's query documents."""
    if not plan:
        return ""
    for direction in plan.directions:
        for query in direction.queries:
            match = _ARCHETYPE_RE.search(query.query_document)
            if match:
                value = match.group(1).strip()
                if value and value.lower() not in {"unknown", "null", "none", ""}:
                    return value
    return ""


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
        "formality_level": str(item.get("formality_level", "")),
        "occasion_fit": str(item.get("occasion_fit", "")),
        "pattern_type": str(item.get("pattern_type", "")),
        "volume_profile": str(item.get("volume_profile", "")),
        "fit_type": str(item.get("fit_type", "")),
        "silhouette_type": str(item.get("silhouette_type", "")),
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
                    classic_pct=rec.classic_pct,
                    dramatic_pct=rec.dramatic_pct,
                    romantic_pct=rec.romantic_pct,
                    natural_pct=rec.natural_pct,
                    minimalist_pct=rec.minimalist_pct,
                    creative_pct=rec.creative_pct,
                    sporty_pct=rec.sporty_pct,
                    edgy_pct=rec.edgy_pct,
                    items=[_build_item_card(item) for item in items],
                )
            )

        message = self._build_message(combined_context, outfits, plan)
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
        self,
        ctx: CombinedContext,
        outfits: List[OutfitCard],
        plan: RecommendationPlan | None = None,
    ) -> str:
        intent = (ctx.live.followup_intent or "").strip()
        if intent == "change_color":
            opening = f"Here are {len(outfits)} outfit recommendations with a fresh color direction"
        elif intent == "similar_to_previous":
            opening = f"Here are {len(outfits)} outfit recommendations in a similar style"
        else:
            opening = f"Here are {len(outfits)} outfit recommendations"
        parts: List[str] = [opening]

        occasion = ctx.live.occasion_signal
        if occasion:
            parts.append(f"for your {occasion.replace('_', ' ')}")

        primary = _extract_plan_archetype(plan) if plan else ""
        if not primary:
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
        intent = (ctx.live.followup_intent or "").strip()

        # Intent-specific chips take priority
        if intent == "change_color":
            return [
                "Show me something similar to these",
                "Try a completely different style",
                "Show me bolder options",
                "Show me more options",
                "Something completely different",
            ][:5]
        if intent == "similar_to_previous":
            return [
                "Show me a different color direction",
                "Show me something bolder",
                "Show me more options",
                "Something completely different",
                "Show me top and bottom pairings instead" if plan.plan_type != "paired_only" else "Show me complete outfit alternatives",
            ][:5]

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
