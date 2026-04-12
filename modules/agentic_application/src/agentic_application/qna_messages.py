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
    "outfit_assembly_started": "Pairing this back for you.",
    "outfit_assembly_completed": "",  # silent — raw candidate count is noise
    "outfit_evaluation_started": "",  # dynamic
    "outfit_evaluation_completed": "Finding something that fits.",
    "response_formatting_started": "Writing it up.",
    "response_formatting_completed": "",  # silent — the answer is about to appear
    "response_formatting_error": "I couldn't pull that together this time. Try me again.",
    "virtual_tryon_started": "Trying these on you.",
    "virtual_tryon_completed": "",  # silent — the images appear inline
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


def _outfit_evaluation_started(ctx: Dict[str, Any]) -> str:
    factors = []
    if ctx.get("has_body_data"):
        factors.append("body type")
    if ctx.get("has_color_season"):
        factors.append("color season")
    if ctx.get("has_style_pref"):
        factors.append("style preferences")
    if factors:
        label = ", ".join(factors[:-1]) + " and " + factors[-1] if len(factors) > 1 else factors[0]
        return f"Evaluating outfits for your {label}..."
    return "Evaluating outfits for overall fit and style..."


def _copilot_planner_completed(ctx: Dict[str, Any]) -> str:
    primary = str(ctx.get("primary_intent") or "").replace("_", " ").strip()
    if primary:
        return f"Intent understood — routing this as {primary}."
    return "Intent understood."


_DYNAMIC_HANDLERS = {
    "copilot_planner_completed": _copilot_planner_completed,
    "outfit_architect_completed": _outfit_architect_completed,
    "catalog_search_completed": _catalog_search_completed,
    "outfit_evaluation_started": _outfit_evaluation_started,
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
