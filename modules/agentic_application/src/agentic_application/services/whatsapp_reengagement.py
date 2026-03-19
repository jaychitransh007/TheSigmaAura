from __future__ import annotations

from typing import Any, Dict, List


def build_whatsapp_reengagement_message(
    *,
    previous_context: Dict[str, Any] | None,
    reminder_type: str = "",
) -> Dict[str, Any]:
    previous_context = dict(previous_context or {})
    memory = dict(previous_context.get("memory") or {})
    requested_type = str(reminder_type or "").strip()
    last_intent = str(previous_context.get("last_intent") or "").strip()
    last_occasion = str(previous_context.get("last_occasion") or "").replace("_", " ").strip()
    wardrobe_item_count = int(memory.get("wardrobe_item_count") or 0)

    if requested_type == "reactivation":
        message = "Need help deciding what to wear or buy this week? Send me a product link, outfit photo, or occasion."
        suggestions = [
            "Should I buy this?",
            "Outfit check this",
            "What should I wear this week?",
        ]
        resolved_type = "reactivation"
    elif requested_type == "shopping" or last_intent == "shopping_decision":
        message = "Thinking about buying something? Send me the product link and I’ll give you a quick buy / skip verdict."
        suggestions = [
            "Should I buy this?",
            "What goes with this piece?",
            "Show me better options from the catalog",
        ]
        resolved_type = "shopping"
    elif requested_type == "wardrobe" or last_intent == "pairing_request":
        message = "Need another pairing? Send the piece and I’ll pair it from your wardrobe first."
        suggestions = [
            "Use my wardrobe first",
            "What goes with this piece?",
            "Plan outfits from my wardrobe",
        ]
        resolved_type = "wardrobe"
    elif last_intent == "capsule_or_trip_planning":
        message = "Planning another trip or workweek? I can turn your wardrobe into a quick capsule again."
        suggestions = [
            "Plan a workweek capsule",
            "Plan outfits for a trip",
            "Show me better options from the catalog",
        ]
        resolved_type = "followup"
    elif requested_type == "occasion" or last_intent == "occasion_recommendation":
        if last_occasion:
            message = f"Need another look for {last_occasion}? I can start with your wardrobe and then show better catalog options if needed."
        else:
            message = "Need another outfit for an occasion? I can start with your wardrobe and then show better catalog options if needed."
        suggestions = [
            "What should I wear tomorrow?",
            "Use my wardrobe first",
            "Show me catalog alternatives",
        ]
        resolved_type = "occasion"
    else:
        if wardrobe_item_count > 0:
            message = "Need help getting dressed this week? I can use your wardrobe first or help you decide what to buy."
            suggestions = [
                "Use my wardrobe first",
                "Should I buy this?",
                "What should I wear tomorrow?",
            ]
        else:
            message = "Need help deciding what to wear or buy this week? Send me a product link, outfit photo, or occasion."
            suggestions = [
                "Should I buy this?",
                "Outfit check this",
                "What should I wear tomorrow?",
            ]
        resolved_type = requested_type or "followup"

    return {
        "reminder_type": resolved_type,
        "assistant_message": message,
        "follow_up_suggestions": suggestions[:3],
        "metadata": {
            "last_intent": last_intent,
            "last_occasion": last_occasion,
            "wardrobe_item_count": wardrobe_item_count,
            "requested_reminder_type": requested_type,
        },
    }
