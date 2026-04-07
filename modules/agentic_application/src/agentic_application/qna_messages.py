"""Deterministic template engine for human-readable stage messages."""

from __future__ import annotations

from typing import Any, Dict, Optional

_PLAN_TYPE_DESCRIPTIONS = {
    "paired_only": "coordinated top + bottom",
    "complete_only": "complete one-piece outfits",
    "mixed": "a mix of complete and paired outfits",
}

_TEMPLATES: Dict[str, str] = {
    "validate_request_started": "Checking your request...",
    "onboarding_gate_started": "Checking whether your profile is ready for chat...",
    "onboarding_gate_blocked": "Complete your profile setup before chat can continue.",
    "onboarding_gate_completed": "Your profile is ready for chat.",
    "user_context_started": "Loading your style profile...",
    "user_context_completed": "Profile loaded — {richness} detail available.",
    "context_builder_started": "Reviewing conversation context...",
    "context_builder_completed": "Context loaded.",
    "copilot_planner_started": "Understanding what you need help with...",
    "copilot_planner_completed": "",  # dynamic
    "copilot_planner_error": "Sorry, I'm having trouble understanding that right now. Please try again.",
    "outfit_architect_started": "Planning outfit directions...",
    "outfit_architect_completed": "",  # dynamic
    "catalog_search_started": "Searching the catalog...",
    "catalog_search_completed": "",  # dynamic
    "catalog_search_blocked": "Catalog data isn't loaded in this environment — can't put together recommendations right now.",
    "outfit_assembly_started": "Assembling outfit combinations...",
    "outfit_assembly_completed": "Assembled {candidate_count} outfit candidates.",
    "outfit_evaluation_started": "",  # dynamic
    "outfit_evaluation_completed": "Top outfits selected.",
    "response_formatting_started": "Preparing your outfit recommendations...",
    "response_formatting_completed": "Your {outfit_count} outfit recommendations are ready.",
    "response_formatting_error": "Sorry, I wasn't able to put together recommendations this time. Please try again.",
    "virtual_tryon_started": "Generating virtual try-on previews...",
    "virtual_tryon_completed": "Try-on images ready.",
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
