from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from user_profiler.config import get_api_key

from ..schemas import CombinedContext, DirectionSpec, QuerySpec, RecommendationPlan


_COLOR_TERMS = [
    "black",
    "white",
    "navy",
    "blue",
    "green",
    "olive",
    "red",
    "burgundy",
    "pink",
    "brown",
    "beige",
    "cream",
    "tan",
    "grey",
    "gray",
    "yellow",
    "mustard",
    "orange",
    "purple",
]


# ---------------------------------------------------------------------------
# Seasonal palette data: anchor (bottom) + accent (top) color pairs.
# Each seasonal group maps to a list of (top_color, bottom_color) pairings
# ordered by versatility.  The first pair is the safest default.
# ---------------------------------------------------------------------------

_SEASONAL_PALETTES: Dict[str, List[Tuple[str, str]]] = {
    # --- Warm families ---
    "warm spring": [("coral", "navy"), ("peach", "camel"), ("ivory", "olive"), ("turquoise", "beige")],
    "light spring": [("blush", "light grey"), ("cream", "soft navy"), ("peach", "khaki"), ("mint", "stone")],
    "clear spring": [("bright coral", "navy"), ("ivory", "black"), ("turquoise", "charcoal"), ("hot pink", "white")],
    "warm autumn": [("cream", "olive"), ("rust", "dark brown"), ("mustard", "navy"), ("terracotta", "khaki")],
    "soft autumn": [("dusty rose", "olive"), ("cream", "brown"), ("sage", "chocolate"), ("soft teal", "camel")],
    "deep autumn": [("burnt orange", "black"), ("olive", "dark brown"), ("cream", "charcoal"), ("rust", "navy")],
    # --- Cool families ---
    "cool winter": [("white", "black"), ("icy blue", "charcoal"), ("fuchsia", "navy"), ("silver grey", "black")],
    "deep winter": [("white", "black"), ("icy pink", "navy"), ("burgundy", "charcoal"), ("emerald", "black")],
    "clear winter": [("hot pink", "black"), ("white", "navy"), ("cobalt", "charcoal"), ("icy violet", "black")],
    "cool summer": [("dusty rose", "slate"), ("lavender", "navy"), ("soft white", "charcoal"), ("powder blue", "grey")],
    "light summer": [("powder blue", "light grey"), ("soft pink", "dove grey"), ("lavender", "slate"), ("mint", "stone")],
    "soft summer": [("mauve", "grey"), ("dusty blue", "charcoal"), ("rose", "slate"), ("sage", "soft navy")],
}

# Fallback when seasonal group is unknown or missing
_DEFAULT_PALETTE: List[Tuple[str, str]] = [
    ("white", "navy"), ("cream", "charcoal"), ("light blue", "black"), ("grey", "black"),
]


# ---------------------------------------------------------------------------
# Volume balance rules: body shape → recommended (top_volume, bottom_volume).
# Uses FrameStructure from derived interpretations.
# ---------------------------------------------------------------------------

_VOLUME_BALANCE: Dict[str, Tuple[str, str]] = {
    "light and narrow": ("relaxed", "slim"),          # add volume on top to balance narrow frame
    "light and broad": ("fitted", "straight"),         # follow broad frame without adding bulk
    "medium and balanced": ("balanced", "balanced"),
    "solid and narrow": ("fitted", "straight"),        # fitted top, clean bottom
    "solid and broad": ("structured", "straight"),     # structured top, straight bottom
}

_DEFAULT_VOLUME: Tuple[str, str] = ("balanced", "balanced")


# ---------------------------------------------------------------------------
# Pattern distribution: one piece carries the pattern, the other stays solid.
# ---------------------------------------------------------------------------

def _distribute_pattern(pattern_type: str, *, boldness: bool) -> Tuple[str, str]:
    """Return (top_pattern, bottom_pattern). Pattern goes on top by default."""
    if boldness:
        return pattern_type if pattern_type != "solid" else "statement", "solid"
    if pattern_type in {"solid", "unknown", ""}:
        return "solid", "solid"
    # Pattern on top, solid on bottom
    return pattern_type, "solid"


# ---------------------------------------------------------------------------
# Outfit concept: holistic vision for a paired outfit before query decomposition.
# ---------------------------------------------------------------------------

@dataclass
class _OutfitConcept:
    """Holistic outfit vision derived from user context for a paired direction."""
    top_color: str
    bottom_color: str
    top_volume: str
    bottom_volume: str
    top_pattern: str
    bottom_pattern: str
    top_fabric_drape: str
    bottom_fabric_drape: str
    color_temperature: str


def _build_outfit_concept(ctx: CombinedContext) -> _OutfitConcept:
    """Derive a coordinated outfit concept from user context."""
    derived = ctx.user.derived_interpretations
    style_pref = ctx.user.style_preference
    seasonal_group = _extract_value(derived, "SeasonalColorGroup").lower()
    frame_structure = _extract_value(derived, "FrameStructure").lower()
    formality = _resolve_formality(ctx)
    boldness = ctx.live.followup_intent == "increase_boldness"
    streamlined = any(need in {"elongation", "slimming"} for need in ctx.live.specific_needs)

    # --- Color assignment ---
    explicit_color = _extract_color_hint(ctx.live.user_need)
    palette = _SEASONAL_PALETTES.get(seasonal_group, _DEFAULT_PALETTE)

    if explicit_color != "unknown":
        # User asked for a specific color — use it as primary, pick complementary anchor
        top_color = explicit_color
        bottom_color = palette[0][1]  # anchor from palette
    elif ctx.live.followup_intent == "change_color":
        # Rotate to second palette pair to change direction
        pair = palette[1] if len(palette) > 1 else palette[0]
        top_color, bottom_color = pair
    elif ctx.live.followup_intent == "similar_to_previous":
        prev_color = _previous_primary_color(ctx)
        if prev_color:
            top_color = prev_color
            bottom_color = palette[0][1]
        else:
            top_color, bottom_color = palette[0]
    else:
        top_color, bottom_color = palette[0]

    # --- Volume balance ---
    if streamlined:
        top_volume, bottom_volume = "streamlined", "slim"
    elif ctx.live.followup_intent == "similar_to_previous":
        prev_vol = _previous_list_value(ctx, "volume_profiles")
        if prev_vol:
            # Preserve previous volume on top, complement on bottom
            top_volume = prev_vol
            bottom_volume = "slim" if prev_vol in {"oversized", "relaxed"} else "balanced"
        else:
            top_volume, bottom_volume = _VOLUME_BALANCE.get(frame_structure, _DEFAULT_VOLUME)
    else:
        top_volume, bottom_volume = _VOLUME_BALANCE.get(frame_structure, _DEFAULT_VOLUME)

    # --- Pattern distribution ---
    raw_pattern = _safe_value(style_pref.get("patternType"))
    if ctx.live.followup_intent == "similar_to_previous":
        prev_pat = _previous_list_value(ctx, "pattern_types")
        if prev_pat:
            raw_pattern = prev_pat
    top_pattern, bottom_pattern = _distribute_pattern(raw_pattern, boldness=boldness)

    # --- Fabric drape ---
    if formality in {"formal", "semi_formal"}:
        top_drape, bottom_drape = "structured", "structured"
    elif formality in {"business_casual"}:
        top_drape, bottom_drape = "balanced", "structured"
    else:
        top_drape, bottom_drape = "relaxed", "balanced"

    return _OutfitConcept(
        top_color=top_color,
        bottom_color=bottom_color,
        top_volume=top_volume,
        bottom_volume=bottom_volume,
        top_pattern=top_pattern,
        bottom_pattern=bottom_pattern,
        top_fabric_drape=top_drape,
        bottom_fabric_drape=bottom_drape,
        color_temperature=_seasonal_temperature(seasonal_group),
    )


def _load_prompt() -> str:
    prompt_dir = Path(__file__).resolve()
    for base in [prompt_dir.parent] + list(prompt_dir.parents):
        candidate = base / "prompt" / "outfit_architect.md"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()
    raise FileNotFoundError("Could not locate prompt/outfit_architect.md")


_PLAN_JSON_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "name": "recommendation_plan",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["plan_type", "retrieval_count", "directions"],
        "properties": {
            "plan_type": {
                "type": "string",
                "enum": ["complete_only", "paired_only", "mixed"],
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
                            "enum": ["complete", "paired"],
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
                                        "enum": ["complete", "top", "bottom"],
                                    },
                                    "hard_filters": {
                                        "type": "object",
                                        "additionalProperties": {"type": "string"},
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


def _safe_value(value: Any, *, default: str = "unknown") -> str:
    text = str(value or "").strip()
    return text or default


def _extract_color_hint(text: str) -> str:
    lowered = text.lower()
    for color in _COLOR_TERMS:
        if f" {color} " in f" {lowered} ":
            return color
    return "unknown"


def _latest_previous_recommendation(ctx: CombinedContext) -> Dict[str, Any]:
    recommendations = ctx.previous_recommendations or []
    if recommendations and isinstance(recommendations[0], dict):
        return recommendations[0]
    return {}


def _previous_primary_color(ctx: CombinedContext) -> str:
    previous = _latest_previous_recommendation(ctx)
    colors = previous.get("primary_colors")
    if isinstance(colors, list):
        for color in colors:
            normalized = str(color or "").strip().lower()
            if normalized:
                return normalized
    return ""


def _previous_occasion(ctx: CombinedContext) -> str:
    previous = _latest_previous_recommendation(ctx)
    occasions = previous.get("occasion_fits")
    if isinstance(occasions, list):
        for occasion in occasions:
            normalized = str(occasion or "").strip().lower()
            if normalized:
                return normalized
    return ""


def _previous_candidate_type(ctx: CombinedContext) -> str:
    previous = _latest_previous_recommendation(ctx)
    candidate_type = str(previous.get("candidate_type") or "").strip().lower()
    return candidate_type


def _previous_list_value(ctx: CombinedContext, key: str) -> str:
    previous = _latest_previous_recommendation(ctx)
    values = previous.get(key)
    if isinstance(values, list):
        for value in values:
            normalized = str(value or "").strip().lower()
            if normalized:
                return normalized
    return ""


def _resolved_primary_color(ctx: CombinedContext) -> str:
    explicit_color = _extract_color_hint(ctx.live.user_need)
    if explicit_color != "unknown":
        return explicit_color
    if ctx.live.followup_intent == "similar_to_previous":
        previous_color = _previous_primary_color(ctx)
        if previous_color:
            return previous_color
    return "unknown"


def _preserved_pattern_type(ctx: CombinedContext, style_pref: Dict[str, Any], *, boldness: bool) -> str:
    if boldness:
        return "statement"
    if ctx.live.followup_intent == "similar_to_previous":
        previous_pattern = _previous_list_value(ctx, "pattern_types")
        if previous_pattern:
            return previous_pattern
    return _safe_value(style_pref.get("patternType"))


def _preserved_volume_profile(ctx: CombinedContext, *, streamlined: bool) -> str:
    if streamlined:
        return "streamlined"
    if ctx.live.followup_intent == "similar_to_previous":
        previous_volume = _previous_list_value(ctx, "volume_profiles")
        if previous_volume:
            return previous_volume
    return "balanced"


def _preserved_fit_type(ctx: CombinedContext, formality: str) -> str:
    if ctx.live.followup_intent == "similar_to_previous":
        previous_fit = _previous_list_value(ctx, "fit_types")
        if previous_fit:
            return previous_fit
    return "tailored" if formality in {"formal", "semi_formal", "business_casual"} else "relaxed"


def _preserved_silhouette_type(ctx: CombinedContext) -> str:
    if "elongation" in ctx.live.specific_needs:
        return "elongated"
    if ctx.live.followup_intent == "similar_to_previous":
        previous_silhouette = _previous_list_value(ctx, "silhouette_types")
        if previous_silhouette:
            return previous_silhouette
    return "balanced"


def _seasonal_temperature(seasonal_group: str) -> str:
    lowered = seasonal_group.lower()
    if "spring" in lowered or "autumn" in lowered or "fall" in lowered:
        return "warm"
    if "summer" in lowered or "winter" in lowered:
        return "cool"
    return "neutral"


def _resolve_formality(ctx: CombinedContext) -> str:
    candidates = [
        ctx.live.formality_hint,
        getattr(ctx.conversation_memory, "formality_hint", None),
        ctx.user.style_preference.get("formalityLean"),
    ]
    for value in candidates:
        normalized = str(value or "").strip().lower().replace(" ", "_")
        if normalized:
            return normalized
    return "smart_casual"


def _resolve_style_goal(ctx: CombinedContext) -> str:
    if ctx.live.followup_intent == "similar_to_previous" and ctx.previous_recommendations:
        return "similar to previous recommendation"
    if ctx.live.followup_intent == "change_color":
        previous_color = _previous_primary_color(ctx)
        if previous_color:
            return f"change color direction away from {previous_color}"
        return "change color direction"
    if ctx.live.specific_needs:
        return ", ".join(ctx.live.specific_needs)
    if ctx.live.occasion_signal:
        return ctx.live.occasion_signal.replace("_", " ")
    return "profile aware outfit"


def _determine_plan_type(ctx: CombinedContext) -> str:
    lowered = ctx.live.user_need.lower()
    if any(token in lowered for token in ("pairing", "pairings", "top and bottom", "separates")):
        return "paired_only"
    if any(
        token in lowered
        for token in ("complete outfit", "full outfit", "one piece", "dress", "jumpsuit")
    ):
        return "complete_only"
    previous_candidate_type = _previous_candidate_type(ctx)
    if ctx.live.followup_intent == "similar_to_previous":
        if previous_candidate_type == "paired":
            return "paired_only"
        if previous_candidate_type == "complete":
            return "complete_only"
    if ctx.live.is_followup and ctx.conversation_memory and ctx.conversation_memory.plan_type:
        return ctx.conversation_memory.plan_type
    return "mixed"


def _direction_queries(plan_type: str) -> List[Tuple[str, str]]:
    if plan_type == "complete_only":
        return [("A", "complete")]
    if plan_type == "paired_only":
        return [("B", "paired")]
    return [("A", "complete"), ("B", "paired")]


def _top_subtype(formality: str, gender: str) -> str:
    if formality in {"formal", "semi_formal", "business_casual"}:
        return "shirt" if gender == "male" else "blouse"
    if formality == "casual":
        return "t_shirt"
    return "top"


def _bottom_subtype(formality: str) -> str:
    if formality in {"formal", "semi_formal", "business_casual"}:
        return "trousers"
    if formality == "casual":
        return "jeans"
    return "pants"


def _query_sections(
    ctx: CombinedContext,
    *,
    role: str,
    styling_completeness: str,
    concept: Optional[_OutfitConcept] = None,
) -> Dict[str, Dict[str, str]]:
    derived = ctx.user.derived_interpretations
    style_pref = ctx.user.style_preference
    gender = str(ctx.user.gender or "").strip().lower()
    formality = _resolve_formality(ctx)
    seasonal_group = _extract_value(derived, "SeasonalColorGroup")
    contrast_level = _extract_value(derived, "ContrastLevel")
    frame_structure = _extract_value(derived, "FrameStructure")
    height_category = _extract_value(derived, "HeightCategory")
    waist_size_band = _extract_value(derived, "WaistSizeBand")
    resolved_occasion = (
        _previous_occasion(ctx)
        if ctx.live.followup_intent == "similar_to_previous" and not ctx.live.occasion_signal
        else str(ctx.live.occasion_signal or "").strip().lower()
    )
    boldness = ctx.live.followup_intent == "increase_boldness"
    streamlined = any(need in {"elongation", "slimming"} for need in ctx.live.specific_needs)
    silhouette_type = _preserved_silhouette_type(ctx)

    if role == "top":
        garment_category = "top"
        garment_subtype = _top_subtype(formality, gender)
    elif role == "bottom":
        garment_category = "bottom"
        garment_subtype = _bottom_subtype(formality)
    else:
        garment_category = "unknown"
        garment_subtype = "unknown"

    # --- Derive role-specific values from concept (paired) or fallback (complete) ---
    if concept and role in ("top", "bottom"):
        if role == "top":
            primary_color = concept.top_color
            volume_profile = concept.top_volume
            pattern_type = concept.top_pattern
            fabric_drape = concept.top_fabric_drape
        else:
            primary_color = concept.bottom_color
            volume_profile = concept.bottom_volume
            pattern_type = concept.bottom_pattern
            fabric_drape = concept.bottom_fabric_drape
        color_temperature = concept.color_temperature
        fit_type = _preserved_fit_type(ctx, formality)
    else:
        # Complete outfit or no concept — use uniform values (original behavior)
        primary_color = _resolved_primary_color(ctx)
        volume_profile = _preserved_volume_profile(ctx, streamlined=streamlined)
        pattern_type = _preserved_pattern_type(ctx, style_pref, boldness=boldness)
        fabric_drape = "structured" if formality in {"formal", "semi_formal"} else "balanced"
        color_temperature = _seasonal_temperature(seasonal_group)
        fit_type = _preserved_fit_type(ctx, formality)

    return {
        "USER_NEED": {
            "request_summary": _safe_value(ctx.live.user_need),
            "styling_goal": _resolve_style_goal(ctx),
        },
        "PROFILE_AND_STYLE": {
            "gender_expression_target": _safe_value(ctx.hard_filters.get("gender_expression")),
            "style_archetype_primary": _safe_value(style_pref.get("primaryArchetype")),
            "style_archetype_secondary": _safe_value(style_pref.get("secondaryArchetype")),
            "seasonal_color_group": _safe_value(seasonal_group),
            "contrast_level": _safe_value(contrast_level),
            "frame_structure": _safe_value(frame_structure),
            "height_category": _safe_value(height_category),
            "waist_size_band": _safe_value(waist_size_band),
        },
        "GARMENT_REQUIREMENTS": {
            "GarmentCategory": garment_category,
            "GarmentSubtype": garment_subtype,
            "StylingCompleteness": styling_completeness,
            "SilhouetteContour": "streamlined" if volume_profile in {"streamlined", "slim"} else "balanced",
            "SilhouetteType": silhouette_type,
            "VolumeProfile": volume_profile,
            "FitEase": "comfortable" if "comfort_priority" in ctx.live.specific_needs else "balanced",
            "FitType": fit_type,
            "GarmentLength": "long_line" if "elongation" in ctx.live.specific_needs else "balanced",
            "ShoulderStructure": "soft" if gender == "female" else "structured",
            "WaistDefinition": "defined" if "slimming" in ctx.live.specific_needs else "balanced",
            "HipDefinition": "balanced",
            "NecklineType": "v_neck" if "elongation" in ctx.live.specific_needs else "unknown",
            "NecklineDepth": "balanced",
            "SleeveLength": "balanced",
            "SkinExposureLevel": "low" if "authority" in ctx.live.specific_needs else "balanced",
        },
        "FABRIC_AND_BUILD": {
            "FabricDrape": fabric_drape,
            "FabricWeight": "medium",
            "FabricTexture": "smooth" if streamlined else "balanced",
            "StretchLevel": "moderate" if "comfort_priority" in ctx.live.specific_needs else "low",
            "EdgeSharpness": "refined" if formality in {"formal", "semi_formal", "business_casual"} else "soft",
            "ConstructionDetail": "clean_finish",
        },
        "PATTERN_AND_COLOR": {
            "PatternType": pattern_type,
            "PatternScale": "medium",
            "PatternOrientation": "vertical" if "elongation" in ctx.live.specific_needs else "balanced",
            "ContrastLevel": _safe_value(contrast_level),
            "ColorTemperature": color_temperature,
            "ColorSaturation": "high" if boldness else "balanced",
            "ColorValue": "medium_deep" if "slimming" in ctx.live.specific_needs else "balanced",
            "ColorCount": "2",
            "PrimaryColor": primary_color,
            "SecondaryColor": "neutral",
        },
        "OCCASION_AND_SIGNAL": {
            "FormalitySignalStrength": "high" if formality in {"formal", "semi_formal"} else "medium",
            "FormalityLevel": formality,
            "OccasionFit": _safe_value(resolved_occasion),
            "OccasionSignal": _safe_value(resolved_occasion),
            "TimeOfDay": _safe_value(ctx.live.time_hint),
        },
    }


def _format_query_document(sections: Dict[str, Dict[str, str]]) -> str:
    lines: List[str] = []
    for section, fields in sections.items():
        lines.append(f"{section}:")
        for label, value in fields.items():
            lines.append(f"- {label}: {_safe_value(value)}")
        lines.append("")
    return "\n".join(lines).strip()


def _query_specs(ctx: CombinedContext, *, direction_id: str, direction_type: str) -> List[QuerySpec]:
    if direction_type == "complete":
        return [
            QuerySpec(
                query_id=f"{direction_id}1",
                role="complete",
                hard_filters={"styling_completeness": "complete"},
                query_document=_format_query_document(
                    _query_sections(ctx, role="complete", styling_completeness="complete")
                ),
            )
        ]
    # Build concept for coordinated paired queries
    concept = _build_outfit_concept(ctx)
    return [
        QuerySpec(
            query_id=f"{direction_id}1",
            role="top",
            hard_filters={"styling_completeness": "needs_pairing"},
            query_document=_format_query_document(
                _query_sections(ctx, role="top", styling_completeness="needs_pairing", concept=concept)
            ),
        ),
        QuerySpec(
            query_id=f"{direction_id}2",
            role="bottom",
            hard_filters={"styling_completeness": "needs_pairing"},
            query_document=_format_query_document(
                _query_sections(ctx, role="bottom", styling_completeness="needs_pairing", concept=concept)
            ),
        ),
    ]


def _fallback_directions(ctx: CombinedContext, plan_type: str) -> List[DirectionSpec]:
    directions: List[DirectionSpec] = []
    for direction_id, direction_type in _direction_queries(plan_type):
        directions.append(
            DirectionSpec(
                direction_id=direction_id,
                direction_type=direction_type,
                label="Complete outfit" if direction_type == "complete" else "Top and bottom pairing",
                queries=_query_specs(ctx, direction_id=direction_id, direction_type=direction_type),
            )
        )
    return directions


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
    interps = {
        key: _extract_value(user.derived_interpretations, key)
        for key in user.derived_interpretations
    }

    payload = {
        "profile": profile_block,
        "analysis_attributes": attrs,
        "derived_interpretations": interps,
        "style_preference": user.style_preference,
        "live_context": ctx.live.model_dump(),
        "hard_filters": ctx.hard_filters,
        "previous_recommendations": ctx.previous_recommendations,
        "conversation_memory": (
            ctx.conversation_memory.model_dump() if ctx.conversation_memory else None
        ),
    }
    return json.dumps(payload, indent=2, default=str)


class OutfitArchitect:
    def __init__(self, model: str = "gpt-5.4") -> None:
        self._client = OpenAI(api_key=get_api_key())
        self._model = model
        self._system_prompt = _load_prompt()

    def plan(self, combined_context: CombinedContext) -> RecommendationPlan:
        """Generate a RecommendationPlan, falling back to deterministic planning when needed."""
        try:
            plan = self._llm_plan(combined_context)
            if plan.directions:
                return plan
        except Exception:
            pass
        return self._fallback_plan(combined_context)

    def _llm_plan(self, combined_context: CombinedContext) -> RecommendationPlan:
        response = self._client.responses.create(
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": self._system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": _build_user_payload(combined_context)}],
                },
            ],
            text={"format": _PLAN_JSON_SCHEMA},
        )

        raw = json.loads(getattr(response, "output_text", "") or "{}")
        return self._parse_plan(raw)

    def _parse_plan(self, raw: Dict[str, Any]) -> RecommendationPlan:
        directions: List[DirectionSpec] = []
        for direction in raw.get("directions", []):
            queries = [
                QuerySpec(
                    query_id=query["query_id"],
                    role=query["role"],
                    hard_filters=query.get("hard_filters") or {},
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
        return RecommendationPlan(
            plan_type=raw.get("plan_type", "complete_only"),
            retrieval_count=int(raw.get("retrieval_count", 12)),
            directions=directions,
            plan_source="llm",
        )

    def _fallback_plan(self, combined_context: CombinedContext) -> RecommendationPlan:
        plan_type = _determine_plan_type(combined_context)
        retrieval_count = 12 if combined_context.user.profile_richness == "full" else 10
        return RecommendationPlan(
            plan_type=plan_type,
            retrieval_count=retrieval_count,
            directions=_fallback_directions(combined_context, plan_type),
            plan_source="fallback",
        )
