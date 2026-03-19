from __future__ import annotations


def graceful_policy_message(reason_code: str, *, default: str = "") -> str:
    reason = str(reason_code or "").strip()
    if reason == "explicit_nudity":
        return "Explicit nude images are not allowed. Upload a clothed full-body, outfit, or product image instead."
    if reason == "unsafe_minor":
        return "Images of minors are not allowed. Upload an adult outfit, wardrobe, or product image instead."
    if reason == "unsafe_image":
        return "Unsafe or graphic images are not allowed. Send a normal outfit or product image instead."
    if reason == "restricted_category_upload":
        return "Items like lingerie or underwear are not supported here. Send outerwear, tops, bottoms, dresses, shoes, or accessories instead."
    if reason == "missing_person_image":
        return "I need your onboarding full-body photo before I can generate a try-on. Complete that step on web, then try again."
    if reason in {
        "quality_gate_failed",
        "low_resolution_output",
        "low_detail_output",
        "aspect_ratio_drift",
        "no_visible_tryon_change",
        "severe_generation_drift",
        "invalid_generated_image",
        "invalid_person_image",
        "missing_generated_image",
    }:
        return "I couldn't return a reliable try-on from that image. Send a cleaner product image or ask whether the item suits you instead."
    if reason == "tryon_request_failed":
        return "I couldn't generate a try-on right now. Try again with a cleaner product image or ask for a fit assessment instead."
    if reason == "unresolved_feedback_items":
        return "I couldn't attach that feedback to a specific outfit. Send the exact look again and I’ll link the feedback correctly."
    if reason == "item_outside_selected_outfit":
        return "That feedback item does not belong to the selected outfit. Pick one of the shown outfit items and try again."
    if reason == "turn_not_found":
        return "I couldn't find the recommendation you were trying to rate. Open the latest result and try again."
    if reason == "turn_conversation_mismatch":
        return "That feedback target doesn't belong to this conversation. Rate the outfit from the same chat thread."
    if reason == "onboarding_required":
        return "Complete the required onboarding steps first, then come back to chat."
    return default or "I couldn't complete that request safely. Try a cleaner input or a simpler styling question."
