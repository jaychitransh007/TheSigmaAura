"""Deterministic template engine for human-readable stage messages."""

from __future__ import annotations

from typing import Any, Dict, Optional

_PLAN_TYPE_DESCRIPTIONS = {
    "paired_only": "a coordinated top + bottom look",
    "complete_only": "complete one-piece looks",
    "mixed": "a mix of complete and paired looks",
}

_TEMPLATES: Dict[str, str] = {
    "validate_request_started": "Reading your request…",
    "onboarding_gate_started": "Getting your profile ready…",
    "onboarding_gate_blocked": "Complete your profile setup before chat can continue.",
    "onboarding_gate_completed": "",  # silent — don't interrupt the flow
    "user_context_started": "Pulling up your style profile…",
    "user_context_completed": "",  # silent — "Profile loaded" is noise
    "context_builder_started": "Thinking about what you asked…",
    "context_builder_completed": "",  # silent
    "copilot_planner_started": "Thinking about what you asked…",
    "copilot_planner_completed": "",  # dynamic
    "copilot_planner_error": "Sorry, I'm having trouble understanding that right now. Please try again.",
    "outfit_architect_started": "Sketching outfit directions…",
    "outfit_architect_completed": "",  # dynamic
    "catalog_search_started": "Pulling matching pieces from the catalog…",
    "catalog_search_completed": "",  # dynamic
    "catalog_search_blocked": "The catalog isn't loaded in this environment — I can't put together recommendations right now.",
    "outfit_assembly_started": "Building outfit combinations…",
    "outfit_assembly_completed": "",  # silent — raw candidate count is noise
    "outfit_evaluation_started": "",  # dynamic
    "outfit_evaluation_completed": "Picking the best looks…",
    "response_formatting_started": "Putting your recommendations together…",
    "response_formatting_completed": "",  # silent — the answer is about to appear
    "response_formatting_error": "Sorry, I wasn't able to put together recommendations this time. Please try again.",
    "virtual_tryon_started": "Generating try-on previews…",
    "virtual_tryon_completed": "",  # silent — the images appear inline
    "outfit_architect_error": "Sorry, I couldn't process your request right now. Please try again.",
}


def _outfit_architect_completed(ctx: Dict[str, Any]) -> str:
    plan_type = ctx.get("plan_type") or ""
    desc = _PLAN_TYPE_DESCRIPTIONS.get(plan_type, plan_type or "outfits")
    n = ctx.get("direction_count")
    if n is not None:
        return f"Plan ready — {desc} across {n} style directions."
    return f"Plan ready — {desc}."


def _catalog_search_completed(ctx: Dict[str, Any]) -> str:
    product_count = ctx.get("product_count", 0)
    set_count = ctx.get("set_count", 0)
    msg = f"Found {product_count} matching products across {set_count} searches."
    if ctx.get("relaxed"):
        msg += " (broadened search for better variety)"
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
