"""
Sigma Aura — Intent Registry

Single source of truth for all intent, action, and follow-up intent
identifiers used across the copilot planner, orchestrator, agents,
and services.

Usage:
    from agentic_application.intent_registry import Intent, Action, FollowUpIntent

    if plan_result.intent == Intent.OUTFIT_CHECK:
        ...
    if plan_result.action == Action.RUN_RECOMMENDATION_PIPELINE:
        ...

All members are StrEnum values — they compare equal to their plain
string equivalents, serialize as strings in JSON/Pydantic, and work
as dict keys without any special handling.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import List


# ── Primary Intents (12) ─────────────────────────────────────────────

class Intent(StrEnum):
    OCCASION_RECOMMENDATION = "occasion_recommendation"
    PRODUCT_BROWSE = "product_browse"
    STYLE_DISCOVERY = "style_discovery"
    EXPLANATION_REQUEST = "explanation_request"
    SHOPPING_DECISION = "shopping_decision"
    PAIRING_REQUEST = "pairing_request"
    OUTFIT_CHECK = "outfit_check"
    GARMENT_ON_ME_REQUEST = "garment_on_me_request"
    CAPSULE_OR_TRIP_PLANNING = "capsule_or_trip_planning"
    WARDROBE_INGESTION = "wardrobe_ingestion"
    FEEDBACK_SUBMISSION = "feedback_submission"
    VIRTUAL_TRYON_REQUEST = "virtual_tryon_request"


# ── Actions (9) ──────────────────────────────────────────────────────

class Action(StrEnum):
    RUN_RECOMMENDATION_PIPELINE = "run_recommendation_pipeline"
    RUN_PRODUCT_BROWSE = "run_product_browse"
    RUN_OUTFIT_CHECK = "run_outfit_check"
    RUN_SHOPPING_DECISION = "run_shopping_decision"
    RESPOND_DIRECTLY = "respond_directly"
    ASK_CLARIFICATION = "ask_clarification"
    RUN_VIRTUAL_TRYON = "run_virtual_tryon"
    SAVE_WARDROBE_ITEM = "save_wardrobe_item"
    SAVE_FEEDBACK = "save_feedback"


# ── Follow-Up Intents (7) ────────────────────────────────────────────

class FollowUpIntent(StrEnum):
    INCREASE_BOLDNESS = "increase_boldness"
    DECREASE_FORMALITY = "decrease_formality"
    INCREASE_FORMALITY = "increase_formality"
    CHANGE_COLOR = "change_color"
    FULL_ALTERNATIVE = "full_alternative"
    MORE_OPTIONS = "more_options"
    SIMILAR_TO_PREVIOUS = "similar_to_previous"


# ── Metadata ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class IntentMeta:
    name: Intent
    label: str
    description: str
    default_action: Action
    handler: str


@dataclass(frozen=True)
class ActionMeta:
    name: Action
    label: str
    description: str


INTENT_REGISTRY: dict[Intent, IntentMeta] = {
    Intent.OCCASION_RECOMMENDATION: IntentMeta(
        name=Intent.OCCASION_RECOMMENDATION,
        label="Outfit Picks",
        description="User wants outfit suggestions or product recommendations for an occasion",
        default_action=Action.RUN_RECOMMENDATION_PIPELINE,
        handler="occasion_recommendation",
    ),
    Intent.PRODUCT_BROWSE: IntentMeta(
        name=Intent.PRODUCT_BROWSE,
        label="Browse Products",
        description="User wants to browse or search catalog items by category, color, or attribute without an occasion",
        default_action=Action.RUN_PRODUCT_BROWSE,
        handler="product_browse",
    ),
    Intent.STYLE_DISCOVERY: IntentMeta(
        name=Intent.STYLE_DISCOVERY,
        label="Style Advice",
        description="User asks theory/knowledge questions about what suits them",
        default_action=Action.RESPOND_DIRECTLY,
        handler="style_discovery",
    ),
    Intent.EXPLANATION_REQUEST: IntentMeta(
        name=Intent.EXPLANATION_REQUEST,
        label="Explain Why",
        description="User asks why something was recommended or how an outfit works",
        default_action=Action.RESPOND_DIRECTLY,
        handler="explanation_request",
    ),
    Intent.SHOPPING_DECISION: IntentMeta(
        name=Intent.SHOPPING_DECISION,
        label="Should I Buy?",
        description="User asks whether to buy a specific item",
        default_action=Action.RUN_SHOPPING_DECISION,
        handler="shopping_decision",
    ),
    Intent.PAIRING_REQUEST: IntentMeta(
        name=Intent.PAIRING_REQUEST,
        label="Style This",
        description="User asks what goes with a specific piece",
        default_action=Action.RUN_RECOMMENDATION_PIPELINE,
        handler="pairing_request",
    ),
    Intent.OUTFIT_CHECK: IntentMeta(
        name=Intent.OUTFIT_CHECK,
        label="Check My Outfit",
        description="User wants feedback on an outfit they describe or show",
        default_action=Action.RUN_OUTFIT_CHECK,
        handler="outfit_check",
    ),
    Intent.GARMENT_ON_ME_REQUEST: IntentMeta(
        name=Intent.GARMENT_ON_ME_REQUEST,
        label="Try It On Me",
        description="User asks if a specific garment would suit them",
        default_action=Action.RESPOND_DIRECTLY,
        handler="garment_on_me_request",
    ),
    Intent.CAPSULE_OR_TRIP_PLANNING: IntentMeta(
        name=Intent.CAPSULE_OR_TRIP_PLANNING,
        label="Plan a Trip",
        description="User wants a capsule wardrobe or packing list",
        default_action=Action.RESPOND_DIRECTLY,
        handler="capsule_or_trip_planning",
    ),
    Intent.WARDROBE_INGESTION: IntentMeta(
        name=Intent.WARDROBE_INGESTION,
        label="Save to Wardrobe",
        description="User wants to save items to their wardrobe",
        default_action=Action.SAVE_WARDROBE_ITEM,
        handler="wardrobe_ingestion",
    ),
    Intent.FEEDBACK_SUBMISSION: IntentMeta(
        name=Intent.FEEDBACK_SUBMISSION,
        label="Give Feedback",
        description="User expresses like/dislike of recommendations",
        default_action=Action.SAVE_FEEDBACK,
        handler="feedback_submission",
    ),
    Intent.VIRTUAL_TRYON_REQUEST: IntentMeta(
        name=Intent.VIRTUAL_TRYON_REQUEST,
        label="Virtual Try-On",
        description="User wants to virtually try on a garment",
        default_action=Action.RUN_VIRTUAL_TRYON,
        handler="virtual_tryon_request",
    ),
}

ACTION_REGISTRY: dict[Action, ActionMeta] = {
    Action.RUN_RECOMMENDATION_PIPELINE: ActionMeta(
        name=Action.RUN_RECOMMENDATION_PIPELINE,
        label="Show Outfits",
        description="Full recommendation pipeline: architect → search → assemble → evaluate → format",
    ),
    Action.RUN_PRODUCT_BROWSE: ActionMeta(
        name=Action.RUN_PRODUCT_BROWSE,
        label="Browse Catalog",
        description="Direct catalog search by category/color/attribute constraints, returning individual product cards",
    ),
    Action.RUN_OUTFIT_CHECK: ActionMeta(
        name=Action.RUN_OUTFIT_CHECK,
        label="Check Outfit",
        description="Evaluate outfit with structured scoring, critique, and improvement suggestions",
    ),
    Action.RUN_SHOPPING_DECISION: ActionMeta(
        name=Action.RUN_SHOPPING_DECISION,
        label="Buy or Skip",
        description="Buy/skip verdict with wardrobe context and pairing suggestions",
    ),
    Action.RESPOND_DIRECTLY: ActionMeta(
        name=Action.RESPOND_DIRECTLY,
        label="Direct Answer",
        description="Pure knowledge/advice response without showing products",
    ),
    Action.ASK_CLARIFICATION: ActionMeta(
        name=Action.ASK_CLARIFICATION,
        label="Clarify",
        description="Ask user for more information when request is too vague",
    ),
    Action.RUN_VIRTUAL_TRYON: ActionMeta(
        name=Action.RUN_VIRTUAL_TRYON,
        label="Try On",
        description="Generate virtual try-on image via Gemini",
    ),
    Action.SAVE_WARDROBE_ITEM: ActionMeta(
        name=Action.SAVE_WARDROBE_ITEM,
        label="Save Item",
        description="Save item to user's wardrobe with enrichment",
    ),
    Action.SAVE_FEEDBACK: ActionMeta(
        name=Action.SAVE_FEEDBACK,
        label="Save Feedback",
        description="Record like/dislike feedback on recommendations",
    ),
}


# ── Helpers ───────────────────────────────────────────────────────────

def intent_enum_values() -> List[str]:
    """Return intent string values for JSON schema generation."""
    return [i.value for i in Intent]


def action_enum_values() -> List[str]:
    """Return action string values for JSON schema generation."""
    return [a.value for a in Action]
