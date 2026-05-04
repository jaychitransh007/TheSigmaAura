"""Deterministic template engine for human-readable stage messages."""

from __future__ import annotations

from typing import Any, Dict, Optional

_DIRECTION_TYPE_LABELS = {
    "complete": "complete sets",
    "paired": "two-piece pairings",
    "three_piece": "three-piece layered looks",
}

_TEMPLATES: Dict[str, str] = {
    # Stylist-voice stage messages (Confident Luxe § Voice & Microcopy).
    # No ellipsis, no exclamation marks, short, end with a period.
    "validate_request_started": "Reading what you need.",
    "onboarding_gate_started": "Opening your studio.",
    "onboarding_gate_blocked": "Finish your profile and we'll pick this back up.",
    "onboarding_gate_completed": "",  # silent — don't interrupt the flow
    "user_context_started": "Opening your dossier.",
    "user_context_completed": "",  # silent — "Profile loaded" is noise
    "context_builder_started": "Thinking this through.",
    "context_builder_completed": "",  # silent
    "copilot_planner_started": "Thinking this through.",
    "copilot_planner_completed": "",  # dynamic
    "copilot_planner_error": "I lost the thread on that one. Try me again.",
    "outfit_architect_started": "Laying pieces on the table.",
    "outfit_architect_completed": "",  # dynamic
    "catalog_search_started": "Looking through the catalog.",
    "catalog_search_completed": "",  # dynamic
    "catalog_search_blocked": "The catalog isn't loaded in this environment — I can't put together recommendations right now.",
    # May 3, 2026: outfit_assembly + outfit_evaluation stages were retired
    # when the LLM ranker (Composer + Rater) replaced the deterministic
    # assembler + reranker + legacy text evaluator. The orchestrator now
    # emits outfit_composer → outfit_rater → visual_evaluation.
    "outfit_composer_started": "Pairing this back for you.",
    "outfit_composer_completed": "",  # silent — raw outfit count is noise
    "outfit_rater_started": "",  # dynamic
    "outfit_rater_completed": "",  # silent — the visual evaluator follows
    "visual_evaluation_started": "",  # dynamic
    "visual_evaluation_completed": "Finding something that fits.",
    "visual_evaluation_error": "",  # silent — fallback path takes over
    "response_formatting_started": "Writing it up.",
    "response_formatting_completed": "",  # silent — the answer is about to appear
    "response_formatting_error": "I couldn't pull that together this time. Try me again.",
    # tryon_render fires when Gemini actually renders the candidates (inside the
    # visual_evaluation block, before the gpt-5-mini eval); attach_tryon_images
    # fires at the end of the pipeline as a cache lookup that wires the rendered
    # image URLs onto each shipped OutfitCard. Both produce the same UX moment
    # ("trying on") so we surface only the first; the second stays silent.
    "tryon_render_started": "Trying these on you.",
    "tryon_render_completed": "",  # silent — the eval/images follow inline
    "attach_tryon_images_started": "",  # silent — renders already happened
    "attach_tryon_images_completed": "",  # silent — the images appear inline
    "outfit_architect_error": "Something got in the way. Try me again.",
}


def _outfit_architect_completed(ctx: Dict[str, Any]) -> str:
    dtypes = ctx.get("direction_types") or []
    labels = [_DIRECTION_TYPE_LABELS.get(dt, dt) for dt in dtypes if dt]
    desc = ", ".join(labels) if labels else "outfits"
    n = ctx.get("direction_count")
    if n is not None:
        return f"I see {desc} across {n} directions."
    return f"I see {desc}."


def _catalog_search_completed(ctx: Dict[str, Any]) -> str:
    product_count = ctx.get("product_count", 0)
    set_count = ctx.get("set_count", 0)
    msg = f"Pulled {product_count} pieces across {set_count} searches."
    if ctx.get("relaxed"):
        msg += " I broadened the net for variety."
    return msg


def _visual_evaluation_started(ctx: Dict[str, Any]) -> str:
    factors = []
    if ctx.get("has_body_data"):
        factors.append("body type")
    if ctx.get("has_color_season"):
        factors.append("color season")
    if ctx.get("has_style_pref"):
        factors.append("style preferences")
    target_count = ctx.get("target_count")
    if factors:
        label = ", ".join(factors[:-1]) + " and " + factors[-1] if len(factors) > 1 else factors[0]
        if target_count:
            return f"Evaluating {target_count} looks for your {label}..."
        return f"Evaluating outfits for your {label}..."
    return "Evaluating outfits for overall fit and style..."


def _outfit_rater_started(ctx: Dict[str, Any]) -> str:
    n = ctx.get("composed_count") or ctx.get("input_summary")
    if n:
        return f"Rating {n} candidates..."
    return "Rating candidates..."


def _copilot_planner_completed(ctx: Dict[str, Any]) -> str:
    primary = str(ctx.get("primary_intent") or "").replace("_", " ").strip()
    if primary:
        return f"Intent understood — routing this as {primary}."
    return "Intent understood."


_DYNAMIC_HANDLERS = {
    "copilot_planner_completed": _copilot_planner_completed,
    "outfit_architect_completed": _outfit_architect_completed,
    "catalog_search_completed": _catalog_search_completed,
    "outfit_rater_started": _outfit_rater_started,
    "visual_evaluation_started": _visual_evaluation_started,
}


def generate_stage_message(
    stage: str,
    detail: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> str:
    key = f"{stage}_{detail}" if detail else stage
    ctx = context or {}

    handler = _DYNAMIC_HANDLERS.get(key)
    if handler is not None:
        return handler(ctx)

    template = _TEMPLATES.get(key)
    if template is None:
        return ""

    try:
        return template.format(**ctx) if ctx else template
    except KeyError:
        return template.split("{")[0].rstrip() if "{" in template else template
