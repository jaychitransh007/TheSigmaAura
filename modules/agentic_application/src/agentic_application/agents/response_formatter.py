from __future__ import annotations

from typing import Any, Dict, List

from ..intent_registry import FollowUpIntent
from ..schemas import (
    CombinedContext,
    EvaluatedRecommendation,
    OutfitCandidate,
    OutfitCard,
    RecommendationPlan,
    RecommendationResponse,
)

import re
from platform_core.restricted_categories import detect_restricted_record

MAX_FORMATTED_OUTFITS = 3


def _direction_types(plan: RecommendationPlan) -> set[str]:
    """Return the set of direction_type values in the plan."""
    return {d.direction_type for d in plan.directions}

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


def _browser_safe_image_url(raw: str) -> str:
    """Rewrite local data/ paths to the FastAPI serving route.

    Catalog items carry HTTP(S) URLs which pass through unchanged.
    Wardrobe items carry relative paths like
    ``data/onboarding/images/wardrobe/abc.jpg`` which the browser can't
    fetch directly. This helper rewrites them to
    ``/v1/onboarding/images/local?path=...`` which the FastAPI route
    serves. Duplicated from ``AgenticOrchestrator._browser_safe_image_url``
    so the response formatter can apply it without importing the
    orchestrator.
    """
    from urllib.parse import quote
    raw = str(raw or "").strip()
    if not raw:
        return ""
    normalized = raw.lower()
    if normalized.startswith(("http://", "https://", "data:", "/v1/")):
        return raw
    if raw.startswith("data/") or "/data/onboarding/images/" in raw or "onboarding/images/" in raw:
        return "/v1/onboarding/images/local?path=" + quote(raw, safe="/._-")
    return raw


def _build_item_card(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "product_id": str(item.get("product_id", "")),
        "similarity": float(item.get("similarity", 0.0) or 0.0),
        "title": str(item.get("title", "")),
        "image_url": _browser_safe_image_url(item.get("image_url") or item.get("image_path") or ""),
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
        "source": str(item.get("source", "catalog") or "catalog"),
    }


def _filter_allowed_items(items: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[str]]:
    allowed: List[Dict[str, Any]] = []
    blocked_terms: List[str] = []
    for item in items:
        blocked_term = detect_restricted_record(item)
        if blocked_term:
            blocked_terms.append(blocked_term)
            continue
        allowed.append(item)
    return allowed, blocked_terms


def _summarize_answer_components(outfits: List[OutfitCard]) -> Dict[str, Any]:
    breakdown: List[Dict[str, Any]] = []
    wardrobe_item_count = 0
    catalog_item_count = 0
    for outfit in outfits:
        item_sources = [str(item.get("source", "catalog") or "catalog") for item in outfit.items]
        wardrobe_count = sum(1 for source in item_sources if source == "wardrobe")
        catalog_count = sum(1 for source in item_sources if source == "catalog")
        wardrobe_item_count += wardrobe_count
        catalog_item_count += catalog_count
        source_mix = "mixed" if wardrobe_count and catalog_count else ("wardrobe" if wardrobe_count else "catalog")
        breakdown.append(
            {
                "rank": outfit.rank,
                "source_mix": source_mix,
                "wardrobe_item_count": wardrobe_count,
                "catalog_item_count": catalog_count,
            }
        )

    primary_source = "mixed"
    if wardrobe_item_count and not catalog_item_count:
        primary_source = "wardrobe"
    elif catalog_item_count and not wardrobe_item_count:
        primary_source = "catalog"

    return {
        "primary_source": primary_source,
        "wardrobe_item_count": wardrobe_item_count,
        "catalog_item_count": catalog_item_count,
        "outfit_breakdown": breakdown,
    }


def _candidate_items_by_id(
    candidates: List[OutfitCandidate],
) -> Dict[str, List[Dict[str, Any]]]:
    return {c.candidate_id: c.items for c in candidates}


def _build_zero_result_fallback(ctx: CombinedContext) -> tuple[str, List[str]]:
    """Build a profile-grounded fallback message when retrieval returns no candidates."""
    derived = dict(ctx.user.derived_interpretations or {})
    style_pref = dict(ctx.user.style_preference or {})

    seasonal = ""
    sg = derived.get("SeasonalColorGroup")
    if isinstance(sg, dict):
        seasonal = str(sg.get("value") or "").strip()
    elif isinstance(sg, str):
        seasonal = sg.strip()

    contrast = ""
    cl = derived.get("ContrastLevel")
    if isinstance(cl, dict):
        contrast = str(cl.get("value") or "").strip()
    elif isinstance(cl, str):
        contrast = cl.strip()

    frame = ""
    fs = derived.get("FrameStructure")
    if isinstance(fs, dict):
        frame = str(fs.get("value") or "").strip()
    elif isinstance(fs, str):
        frame = fs.strip()

    primary = str(style_pref.get("primaryArchetype") or "").strip()
    secondary = str(style_pref.get("secondaryArchetype") or "").strip()

    has_profile = any([seasonal, contrast, frame, primary])

    if not has_profile:
        return (
            "I couldn't find matching outfits for your request. Try broadening your requirements.",
            ["Try a different occasion", "Show me something casual"],
        )

    parts: List[str] = [
        "I couldn't find exact catalog matches for this request, but here's what I'd recommend based on your profile."
    ]

    if seasonal:
        if seasonal in ("Spring", "Autumn"):
            parts.append(f"As a {seasonal} season, lean toward warm-toned pieces — earthy neutrals, rich warm shades, and gold accents.")
        else:
            parts.append(f"As a {seasonal} season, lean toward cool-toned pieces — icy neutrals, crisp cool shades, and silver accents.")

    if contrast:
        contrast_lower = contrast.lower()
        if "high" in contrast_lower:
            parts.append("With your high contrast, look for pieces with strong light-dark pairings or bold prints.")
        elif "low" in contrast_lower:
            parts.append("With your low contrast, tonal and blended palettes will look most polished.")

    if frame:
        frame_lower = frame.lower()
        if "broad" in frame_lower:
            parts.append("For your frame, prioritise waist-defining cuts and structured shoulders.")
        elif "narrow" in frame_lower:
            parts.append("For your frame, streamlined and fitted pieces will create the cleanest lines.")

    if primary:
        style_desc = primary
        if secondary:
            style_desc += f" + {secondary}"
        parts.append(f"Stay within your {style_desc} style direction when shopping.")

    parts.append("Try adjusting the occasion or style direction and I'll search again with sharper criteria.")

    suggestions = [
        "Try a different occasion",
        "Show me something casual",
        "What colors suit me best?",
        "Surprise me",
    ]
    return " ".join(parts), suggestions


class ResponseFormatter:
    """Converts evaluated recommendations into user-facing response."""

    def format(
        self,
        evaluated: List[EvaluatedRecommendation],
        combined_context: CombinedContext,
        plan: RecommendationPlan,
        candidates: List[OutfitCandidate],
        *,
        planner_message: str | None = None,
        planner_suggestions: list[str] | None = None,
    ) -> RecommendationResponse:
        if not evaluated:
            fallback_message, fallback_suggestions = _build_zero_result_fallback(combined_context)
            return RecommendationResponse(
                success=True,
                message=fallback_message,
                outfits=[],
                follow_up_suggestions=fallback_suggestions,
                metadata={
                    "direction_types": sorted(_direction_types(plan)),
                    "plan_source": plan.plan_source,
                    "direction_count": len(plan.directions),
                    "zero_result_fallback": True,
                },
            )

        items_lookup = _candidate_items_by_id(candidates)
        outfits: List[OutfitCard] = []
        blocked_item_count = 0

        for rec in sorted(evaluated, key=lambda r: r.rank)[:MAX_FORMATTED_OUTFITS]:
            raw_items = items_lookup.get(rec.candidate_id, [])
            items, blocked_terms = _filter_allowed_items(raw_items)
            blocked_item_count += len(blocked_terms)
            if not items:
                continue
            outfits.append(
                OutfitCard(
                    rank=len(outfits) + 1,
                    title=rec.title,
                    reasoning=rec.reasoning,
                    body_note=rec.body_note,
                    color_note=rec.color_note,
                    style_note=rec.style_note,
                    occasion_note=rec.occasion_note,
                    # 5 always-evaluated dimensions
                    body_harmony_pct=rec.body_harmony_pct,
                    color_suitability_pct=rec.color_suitability_pct,
                    style_fit_pct=rec.style_fit_pct,
                    risk_tolerance_pct=rec.risk_tolerance_pct,
                    comfort_boundary_pct=rec.comfort_boundary_pct,
                    # 4 context-gated dimensions — pass None straight through;
                    # the OutfitCard schema accepts Optional[int] and the
                    # frontend drops null radar slices. pairing_coherence_pct
                    # arrives as None for garment_evaluation / style_discovery /
                    # explanation_request (intent-gated), as a real int for
                    # the pairing-capable intents.
                    pairing_coherence_pct=rec.pairing_coherence_pct,
                    occasion_pct=rec.occasion_pct,
                    specific_needs_pct=rec.specific_needs_pct,
                    weather_time_pct=rec.weather_time_pct,
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

        if not outfits:
            return RecommendationResponse(
                success=True,
                message="I couldn't return safe outfit recommendations for this request. Try a different occasion or style direction.",
                outfits=[],
                follow_up_suggestions=["Try a different occasion", "Show me something casual"],
                metadata={
                    "direction_types": sorted(_direction_types(plan)),
                    "plan_source": plan.plan_source,
                    "direction_count": len(plan.directions),
                    "restricted_item_exclusion_count": blocked_item_count,
                },
            )

        message = planner_message if planner_message else self._build_message(combined_context, outfits, plan)
        if planner_suggestions:
            suggestions = planner_suggestions
            follow_up_groups: List[Dict[str, Any]] = []
        else:
            follow_up_groups = self._build_follow_up_groups(combined_context, plan)
            suggestions = self._flatten_follow_up_groups(follow_up_groups)

        return RecommendationResponse(
            success=True,
            message=message,
            outfits=outfits,
            follow_up_suggestions=suggestions,
            metadata={
                "direction_types": sorted(_direction_types(plan)),
                "plan_source": plan.plan_source,
                "direction_count": len(plan.directions),
                "outfit_count": len(outfits),
                "restricted_item_exclusion_count": blocked_item_count,
                "answer_components": _summarize_answer_components(outfits),
                "follow_up_groups": follow_up_groups,
            },
        )

    @staticmethod
    def _flatten_follow_up_groups(groups: List[Dict[str, Any]]) -> List[str]:
        """Stable, deduped flatten of grouped suggestions, capped at 5."""
        out: List[str] = []
        for group in groups:
            for s in group.get("suggestions") or []:
                if s and s not in out:
                    out.append(s)
                if len(out) >= 5:
                    return out
        return out[:5]

    def _build_message(
        self,
        ctx: CombinedContext,
        outfits: List[OutfitCard],
        plan: RecommendationPlan | None = None,
    ) -> str:
        intent = (ctx.live.followup_intent or "").strip()
        if intent == FollowUpIntent.CHANGE_COLOR:
            opening = f"Here are {len(outfits)} outfit recommendations with a fresh color direction"
        elif intent == FollowUpIntent.SIMILAR_TO_PREVIOUS:
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

    # Stable bucket labels — UI groups quick-replies under these. Keep in sync
    # with the renderer in modules/platform_core/.../ui.py.
    _BUCKET_IMPROVE = "Improve It"
    _BUCKET_ALTERNATIVES = "Show Alternatives"
    _BUCKET_EXPLAIN = "Explain Why"
    _BUCKET_SHOP_GAP = "Shop The Gap"
    _BUCKET_SAVE = "Save For Later"

    def _build_follow_up_suggestions(
        self, ctx: CombinedContext, plan: RecommendationPlan
    ) -> List[str]:
        groups = self._build_follow_up_groups(ctx, plan)
        flat: List[str] = []
        for group in groups:
            for s in group["suggestions"]:
                if s not in flat:
                    flat.append(s)
                if len(flat) >= 5:
                    return flat
        return flat[:5]

    def _build_follow_up_groups(
        self, ctx: CombinedContext, plan: RecommendationPlan
    ) -> List[Dict[str, Any]]:
        """Return follow-up suggestions grouped by intent bucket.

        Each entry is `{"label": str, "bucket": str, "suggestions": [str]}`.
        Consumers (UI, response formatter, tests) read structured buckets
        instead of substring-matching the raw suggestion text.
        """
        intent = (ctx.live.followup_intent or "").strip()
        dtypes = _direction_types(plan)
        improve: List[str] = []
        alternatives: List[str] = []
        shop_gap: List[str] = []

        if intent == FollowUpIntent.CHANGE_COLOR:
            improve.extend(["Show me bolder options"])
            alternatives.extend([
                "Show me something similar to these",
                "Try a completely different style",
                "Show me more options",
                "Something completely different",
            ])
        elif intent == FollowUpIntent.SIMILAR_TO_PREVIOUS:
            improve.extend(["Show me something bolder"])
            alternatives.extend([
                "Show me a different color direction",
                "Show me more options",
                "Something completely different",
                (
                    "Show me complete outfit alternatives"
                    if "paired" in dtypes or "three_piece" in dtypes
                    else "Show me top and bottom pairings instead"
                ),
            ])
        else:
            if ctx.live.formality_hint in {"formal", "semi_formal", "ultra_formal"}:
                improve.append("Show me something less formal")
            elif ctx.live.formality_hint in {"casual", "smart_casual"}:
                improve.append("Show me something more formal")
            improve.append("Show me bolder options")

            if "paired" not in dtypes and "three_piece" not in dtypes:
                alternatives.append("Show me top and bottom pairings instead")
            elif "complete" not in dtypes:
                alternatives.append("Show me complete outfit alternatives")
            alternatives.append("Show me more options")
            alternatives.append("Something completely different")

        # Catalog upsell only when wardrobe-first or hybrid is dominant
        components = _summarize_answer_components([])  # placeholder; outfits passed elsewhere
        if "wardrobe" in str(components.get("primary_source") or ""):
            shop_gap.append("Show me catalog options to fill the gap")

        groups: List[Dict[str, Any]] = []
        if improve:
            groups.append({"bucket": "improve", "label": self._BUCKET_IMPROVE, "suggestions": improve})
        if alternatives:
            groups.append({"bucket": "alternatives", "label": self._BUCKET_ALTERNATIVES, "suggestions": alternatives})
        if shop_gap:
            groups.append({"bucket": "shop_gap", "label": self._BUCKET_SHOP_GAP, "suggestions": shop_gap})
        return groups
