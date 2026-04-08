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


# ── Primary Intents (7 advisory + feedback + silent wardrobe_ingestion) ────
#
# Phase 12A consolidated the taxonomy from 12 → 7 advisory + feedback +
# silent wardrobe_ingestion. Removed intents and what replaced them:
#   - product_browse           → folded into OCCASION_RECOMMENDATION via
#                                CopilotResolvedContext.target_product_type
#   - shopping_decision        → absorbed into GARMENT_EVALUATION
#   - garment_on_me_request    → absorbed into GARMENT_EVALUATION
#   - virtual_tryon_request    → absorbed into GARMENT_EVALUATION
#   - capsule_or_trip_planning → deferred (will return in a later phase)
#
# WARDROBE_INGESTION is intentionally retained as a silent-save variant for
# programmatic / bulk upload paths. The planner prompt does NOT classify
# user messages as wardrobe_ingestion.

class Intent(StrEnum):
    OCCASION_RECOMMENDATION = "occasion_recommendation"
    PAIRING_REQUEST = "pairing_request"
    GARMENT_EVALUATION = "garment_evaluation"
    OUTFIT_CHECK = "outfit_check"
    STYLE_DISCOVERY = "style_discovery"
    EXPLANATION_REQUEST = "explanation_request"
    FEEDBACK_SUBMISSION = "feedback_submission"
    WARDROBE_INGESTION = "wardrobe_ingestion"  # silent-save variant only


# ── Actions (7) ──────────────────────────────────────────────────────
#
# Phase 12A removed RUN_SHOPPING_DECISION, RUN_VIRTUAL_TRYON, and
# RUN_PRODUCT_BROWSE. RUN_GARMENT_EVALUATION owns the merged intent.

class Action(StrEnum):
    RUN_RECOMMENDATION_PIPELINE = "run_recommendation_pipeline"
    RUN_OUTFIT_CHECK = "run_outfit_check"
    RUN_GARMENT_EVALUATION = "run_garment_evaluation"
    RESPOND_DIRECTLY = "respond_directly"
    ASK_CLARIFICATION = "ask_clarification"
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
        description=(
            "User wants outfit suggestions for an occasion or wants to see "
            "specific catalog products (when target_product_type is set)."
        ),
        default_action=Action.RUN_RECOMMENDATION_PIPELINE,
        handler="occasion_recommendation",
    ),
    Intent.PAIRING_REQUEST: IntentMeta(
        name=Intent.PAIRING_REQUEST,
        label="Style This",
        description="User asks what goes with a specific anchor garment",
        default_action=Action.RUN_RECOMMENDATION_PIPELINE,
        handler="pairing_request",
    ),
    Intent.GARMENT_EVALUATION: IntentMeta(
        name=Intent.GARMENT_EVALUATION,
        label="Evaluate This Piece",
        description=(
            "User uploads a garment photo and asks whether it suits them, "
            "whether to buy it, or to try it on. Phase 12B will run a "
            "tryon → visual evaluator → format pipeline; the Phase 12A shim "
            "delegates to the existing OutfitCheckAgent path."
        ),
        default_action=Action.RUN_GARMENT_EVALUATION,
        handler="garment_evaluation",
    ),
    Intent.OUTFIT_CHECK: IntentMeta(
        name=Intent.OUTFIT_CHECK,
        label="Check My Outfit",
        description="User wants feedback on an outfit they're wearing or considering",
        default_action=Action.RUN_OUTFIT_CHECK,
        handler="outfit_check",
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
    Intent.FEEDBACK_SUBMISSION: IntentMeta(
        name=Intent.FEEDBACK_SUBMISSION,
        label="Give Feedback",
        description="User expresses like/dislike of recommendations",
        default_action=Action.SAVE_FEEDBACK,
        handler="feedback_submission",
    ),
    Intent.WARDROBE_INGESTION: IntentMeta(
        name=Intent.WARDROBE_INGESTION,
        label="Save to Wardrobe",
        description=(
            "Silent-save variant — programmatic / bulk upload path. The "
            "planner does NOT classify user messages as wardrobe_ingestion."
        ),
        default_action=Action.SAVE_WARDROBE_ITEM,
        handler="wardrobe_ingestion",
    ),
}

ACTION_REGISTRY: dict[Action, ActionMeta] = {
    Action.RUN_RECOMMENDATION_PIPELINE: ActionMeta(
        name=Action.RUN_RECOMMENDATION_PIPELINE,
        label="Show Outfits",
        description="Full recommendation pipeline: architect → search → assemble → evaluate → format",
    ),
    Action.RUN_OUTFIT_CHECK: ActionMeta(
        name=Action.RUN_OUTFIT_CHECK,
        label="Check Outfit",
        description="Evaluate outfit with structured scoring, critique, and improvement suggestions",
    ),
    Action.RUN_GARMENT_EVALUATION: ActionMeta(
        name=Action.RUN_GARMENT_EVALUATION,
        label="Evaluate Garment",
        description=(
            "Single-garment evaluation pipeline. Phase 12A: shim that "
            "reuses the OutfitCheckAgent path. Phase 12B: tryon → visual "
            "evaluator → response formatter with optional buy/skip verdict."
        ),
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
