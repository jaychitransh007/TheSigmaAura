from __future__ import annotations

import re
from typing import Any, Dict, List

from platform_core.fallback_messages import graceful_policy_message

from .schemas import ProfileConfidence, UserContext

_URL_RE = re.compile(r"https?://\S+")
_COLOR_WORDS = (
    "black", "white", "cream", "beige", "brown", "tan", "navy", "blue", "red",
    "burgundy", "green", "olive", "pink", "purple", "grey", "gray", "gold", "silver",
)
_GARMENT_WORDS = (
    "dress", "blazer", "jacket", "coat", "jeans", "trousers", "pants", "shirt",
    "top", "skirt", "heels", "sneakers", "bag", "blouse", "suit", "cardigan",
)


def _build_catalog_upsell(*, rationale: str) -> Dict[str, Any]:
    return {
        "available": True,
        "cta": "Show me better options from the catalog",
        "rationale": rationale,
    }


def build_style_discovery_response(
    *,
    user_context: UserContext,
    profile_confidence: ProfileConfidence,
) -> tuple[str, List[str]]:
    style_pref = dict(user_context.style_preference or {})
    primary = str(style_pref.get("primaryArchetype") or "").strip()
    secondary = str(style_pref.get("secondaryArchetype") or "").strip()

    derived = dict(user_context.derived_interpretations or {})
    seasonal = _nested_value(derived, "SeasonalColorGroup")
    contrast = _nested_value(derived, "ContrastLevel")
    frame = _nested_value(derived, "FrameStructure")
    height = _nested_value(derived, "HeightCategory")

    parts: List[str] = ["Based on your saved profile,"]

    if primary and secondary:
        parts.append(f"your strongest style direction is {primary} blended with {secondary}.")
    elif primary:
        parts.append(f"your strongest style direction is {primary}.")
    else:
        parts.append("your strongest style direction is still developing.")

    descriptors: List[str] = []
    if seasonal:
        descriptors.append(f"{seasonal} color guidance")
    if contrast:
        descriptors.append(f"{contrast} contrast handling")
    if frame:
        descriptors.append(f"{frame} frame balance")
    if height:
        descriptors.append(f"{height.lower()} proportion awareness")
    if descriptors:
        parts.append("I would lean on " + ", ".join(descriptors[:-1]) + (" and " + descriptors[-1] if len(descriptors) > 1 else descriptors[0]) + ".")

    if profile_confidence.score_pct < 85 and profile_confidence.improvement_actions:
        parts.append(
            "Your profile confidence is "
            f"{profile_confidence.score_pct}%. "
            f"To improve it, {profile_confidence.improvement_actions[0].rstrip('.').lower()}."
        )

    suggestions = [
        "Show me outfits for work",
        "Explain why this style suits me",
        "Show me something I should avoid",
        "What colors should I prioritise?",
    ]
    return " ".join(parts), suggestions


def build_explanation_response(
    *,
    user_context: UserContext,
    previous_context: Dict[str, Any],
    profile_confidence: ProfileConfidence,
) -> tuple[str, List[str]]:
    recommendations = list(previous_context.get("last_recommendations") or [])
    if not recommendations:
        return (
            "I can explain recommendations after I have suggested something. Ask for an outfit, pairing, or shopping decision first.",
            ["Show me an outfit for work", "Should I buy this?", "What goes with this piece?"],
        )

    top = recommendations[0]
    colors = ", ".join(top.get("primary_colors") or [])
    categories = ", ".join(top.get("garment_categories") or [])
    occasion = str(previous_context.get("last_occasion") or "").replace("_", " ").strip()
    primary = str((user_context.style_preference or {}).get("primaryArchetype") or "").strip()
    seasonal = _nested_value(dict(user_context.derived_interpretations or {}), "SeasonalColorGroup")
    recommendation_confidence = dict((previous_context.get("last_response_metadata") or {}).get("recommendation_confidence") or {})
    answer_source = str((previous_context.get("last_response_metadata") or {}).get("answer_source") or "").strip()
    answer_components = dict((previous_context.get("last_response_metadata") or {}).get("answer_components") or {})
    catalog_upsell = dict((previous_context.get("last_response_metadata") or {}).get("catalog_upsell") or {})
    feedback_summary = dict(previous_context.get("last_feedback_summary") or {})
    memory = dict(previous_context.get("memory") or {})

    parts: List[str] = ["I weighted your last recommendation using your saved profile and the request context."]
    if occasion:
        parts.append(f"The last request was anchored to {occasion}.")
    if primary:
        parts.append(f"Your saved style preference points toward {primary}.")
    if seasonal:
        parts.append(f"I also used your {seasonal} color guidance.")
    if colors:
        parts.append(f"The top option leaned on colors like {colors}.")
    if categories:
        parts.append(f"It also matched garment directions such as {categories}.")
    wardrobe_item_count = int(memory.get("wardrobe_item_count") or 0)
    if answer_source == "wardrobe_first":
        parts.append("I started from your saved wardrobe before considering outside options.")
    elif answer_components:
        wardrobe_count = int(answer_components.get("wardrobe_item_count") or 0)
        catalog_count = int(answer_components.get("catalog_item_count") or 0)
        if wardrobe_count and catalog_count:
            parts.append(f"I used a mixed answer: {wardrobe_count} wardrobe item(s) and {catalog_count} catalog item(s).")
        elif catalog_count:
            parts.append(f"I grounded the answer in catalog retrieval across {catalog_count} surfaced item(s).")
        elif wardrobe_count:
            parts.append(f"I relied on {wardrobe_count} item(s) from your saved wardrobe.")
    if wardrobe_item_count and not answer_source:
        parts.append(f"You currently have {wardrobe_item_count} wardrobe item(s) saved, which affects whether I can anchor answers in what you already own.")
    if catalog_upsell.get("available"):
        parts.append("I also kept a catalog fallback available in case you want stronger alternatives than the first pass.")
    parts.append(
        f"Your current profile confidence is {profile_confidence.score_pct}%, which affects how strongly I can personalize the result."
    )
    if recommendation_confidence:
        band = str(recommendation_confidence.get("confidence_band") or "").strip()
        score_pct = int(recommendation_confidence.get("score_pct") or 0)
        summary = str(recommendation_confidence.get("summary") or "").strip()
        if band:
            parts.append(f"The last recommendation confidence was {score_pct}% ({band}).")
        if summary:
            parts.append(summary)
        explanation = list(recommendation_confidence.get("explanation") or [])
        if explanation:
            parts.append(explanation[0])
    if feedback_summary:
        feedback_event = str(feedback_summary.get("event_type") or "").strip()
        feedback_count = int(feedback_summary.get("item_count") or len(list(feedback_summary.get("item_ids") or [])))
        if feedback_event == "like":
            parts.append(f"I’m also carrying forward your positive feedback on {feedback_count} item(s) from the recent recommendation.")
        elif feedback_event:
            parts.append(f"I’m also carrying forward your negative feedback on {feedback_count} item(s) so I can avoid repeating them.")

    suggestions = [
        "Show me something bolder",
        "Show me a different color direction",
        "What goes with this piece?",
        "What style suits me?",
    ]
    return " ".join(parts), suggestions


def build_shopping_decision_response(
    *,
    message: str,
    user_context: UserContext,
    previous_context: Dict[str, Any],
    profile_confidence: ProfileConfidence,
) -> tuple[str, List[str], Dict[str, Any]]:
    lowered = str(message or "").strip().lower()
    urls = _URL_RE.findall(lowered)
    detected_colors = [color for color in _COLOR_WORDS if color in lowered]
    detected_garments = [garment for garment in _GARMENT_WORDS if garment in lowered]

    style_pref = dict(user_context.style_preference or {})
    primary = str(style_pref.get("primaryArchetype") or "").strip()
    secondary = str(style_pref.get("secondaryArchetype") or "").strip()
    derived = dict(user_context.derived_interpretations or {})
    seasonal = _nested_value(derived, "SeasonalColorGroup")
    frame = _nested_value(derived, "FrameStructure")
    occasion = str(previous_context.get("last_occasion") or "").replace("_", " ").strip()

    evidence_score = 0
    evidence_reasons: List[str] = []
    if urls:
        evidence_score += 2
        evidence_reasons.append("you shared a product link")
    if detected_garments:
        evidence_score += 1
        evidence_reasons.append(f"you identified the item as {detected_garments[0]}")
    if detected_colors:
        evidence_score += 1
        evidence_reasons.append(f"you mentioned color cues like {detected_colors[0]}")
    if profile_confidence.score_pct >= 75:
        evidence_score += 1
        evidence_reasons.append("your profile confidence is strong enough for a sharper verdict")
    if primary:
        evidence_score += 1
        evidence_reasons.append(f"your saved style direction points toward {primary}")

    verdict = "buy" if evidence_score >= 4 else "skip"

    parts: List[str] = [
        f"My current {verdict} / skip verdict is: {verdict.upper()}."
        if verdict == "buy"
        else "My current buy / skip verdict is: SKIP FOR NOW."
    ]
    if evidence_reasons:
        parts.append("I’m basing that on " + ", ".join(evidence_reasons[:-1]) + (" and " + evidence_reasons[-1] if len(evidence_reasons) > 1 else evidence_reasons[0]) + ".")
    if seasonal:
        parts.append(f"I would still check whether the product sits inside your {seasonal} color direction.")
    if frame:
        parts.append(f"I’d also pressure-test the silhouette against your {frame.lower()} frame balance.")
    if occasion:
        parts.append(f"Your last saved occasion context was {occasion}, so I’m implicitly filtering for that level of polish.")
    if secondary:
        parts.append(f"If the piece feels too far from your {primary} + {secondary} blend, I would be more cautious.")
    elif primary:
        parts.append(f"If the piece feels too far from your {primary} direction, I would be more cautious.")
    if verdict != "buy":
        parts.append("To upgrade this from a provisional skip, send a screenshot or include the exact color, shape, and occasion you want it for.")

    suggestions = [
        "Paste the product link again with the occasion",
        "Upload a screenshot for a sharper verdict",
        "What would pair with this if I buy it?",
        "Show me a safer alternative",
    ]
    payload = {
        "verdict": verdict,
        "product_urls": urls,
        "detected_colors": detected_colors,
        "detected_garments": detected_garments,
        "evidence_score": evidence_score,
        "memory_sources_read": [
            "user_profile",
            "style_preference",
            "derived_interpretations",
            "conversation_memory",
        ],
        "memory_sources_written": [
            "conversation_memory",
            "sentiment_history",
            "confidence_history",
        ],
    }
    return " ".join(parts), suggestions, payload


def build_pairing_request_response(
    *,
    message: str,
    user_context: UserContext,
    previous_context: Dict[str, Any],
    profile_confidence: ProfileConfidence,
) -> tuple[str, List[str], Dict[str, Any]]:
    lowered = str(message or "").strip().lower()
    urls = _URL_RE.findall(lowered)
    detected_colors = [color for color in _COLOR_WORDS if color in lowered]
    detected_garments = [garment for garment in _GARMENT_WORDS if garment in lowered]
    wardrobe_items = list(user_context.wardrobe_items or [])
    style_pref = dict(user_context.style_preference or {})
    primary = str(style_pref.get("primaryArchetype") or "").strip()
    derived = dict(user_context.derived_interpretations or {})
    seasonal = _nested_value(derived, "SeasonalColorGroup")
    occasion = str(previous_context.get("last_occasion") or "").replace("_", " ").strip()

    target_piece = detected_garments[0] if detected_garments else "piece"
    target_role = _infer_pairing_role(target_piece)
    wardrobe_matches = _select_wardrobe_pairings(
        wardrobe_items=wardrobe_items,
        target_piece=target_piece,
        target_role=target_role,
        detected_colors=detected_colors,
        occasion=occasion,
    )[:3]

    parts: List[str] = [f"Here’s how I would start pairing that {target_piece}."]
    if wardrobe_matches:
        names = [str(item.get("title") or "saved wardrobe item").strip() for item in wardrobe_matches]
        parts.append(
            "From your wardrobe first, I would test it with "
            + ", ".join(names[:-1]) + (" and " + names[-1] if len(names) > 1 else names[0])
            + "."
        )
    else:
        parts.append("I do not have enough saved wardrobe coverage yet, so I would start with catalog-safe pairings.")

    if detected_colors:
        parts.append(f"Because you called out {detected_colors[0]}, I would keep the pairing palette controlled around that color story.")
    if seasonal:
        parts.append(f"I would keep the pairing inside your {seasonal} color direction.")
    if primary:
        parts.append(f"I would bias the combination toward your {primary} style direction.")
    if occasion:
        parts.append(f"I’m also keeping your last occasion context, {occasion}, in mind.")
    if profile_confidence.score_pct < 75:
        parts.append("Your profile is good enough to guide pairings, but sharper image/profile inputs would make the pairings more reliable.")
    if urls:
        parts.append("Because you shared a product link, I can tighten this further once you ask for wardrobe-first or catalog-first pairings explicitly.")
    parts.append("If you want, I can also suggest better catalog options that play the same role more cleanly.")

    suggestions = [
        "Use my wardrobe first",
        "Show me better options from the catalog",
        "Show me catalog pairings",
        "Should I buy this piece first?",
        "Give me a full outfit around it",
    ]
    payload = {
        "target_piece": target_piece,
        "target_role": target_role,
        "product_urls": urls,
        "detected_colors": detected_colors,
        "detected_garments": detected_garments,
        "wardrobe_pairing_candidates": [
            {
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or ""),
                "source": "wardrobe",
                "compatibility_score": int(item.get("_compatibility_score") or 0),
                "compatibility_reasons": list(item.get("_compatibility_reasons") or []),
            }
            for item in wardrobe_matches
        ],
        "catalog_pairing_available": True,
        "pairing_mode": "wardrobe_first",
        "catalog_upsell": _build_catalog_upsell(
            rationale="Use catalog options if you want a stronger or more polished complement than what is currently saved in your wardrobe.",
        ),
        "memory_sources_read": [
            "user_profile",
            "style_preference",
            "derived_interpretations",
            "wardrobe_memory",
            "conversation_memory",
        ],
        "memory_sources_written": [
            "conversation_memory",
            "sentiment_history",
            "confidence_history",
        ],
    }
    return " ".join(parts), suggestions, payload


def build_outfit_check_response(
    *,
    message: str,
    user_context: UserContext,
    previous_context: Dict[str, Any],
    profile_confidence: ProfileConfidence,
) -> tuple[str, List[str], Dict[str, Any]]:
    lowered = str(message or "").strip().lower()
    detected_colors = [color for color in _COLOR_WORDS if color in lowered]
    detected_garments = [garment for garment in _GARMENT_WORDS if garment in lowered]

    style_pref = dict(user_context.style_preference or {})
    primary = str(style_pref.get("primaryArchetype") or "").strip()
    secondary = str(style_pref.get("secondaryArchetype") or "").strip()
    derived = dict(user_context.derived_interpretations or {})
    seasonal = _nested_value(derived, "SeasonalColorGroup")
    frame = _nested_value(derived, "FrameStructure")
    contrast = _nested_value(derived, "ContrastLevel")
    occasion = str(previous_context.get("last_occasion") or "").replace("_", " ").strip()

    assessment_score = 0
    if detected_garments:
        assessment_score += 1
    if detected_colors:
        assessment_score += 1
    if primary:
        assessment_score += 1
    if profile_confidence.score_pct >= 75:
        assessment_score += 1

    assessment = "strong" if assessment_score >= 3 else "mixed"
    parts: List[str] = [
        "My current outfit-check read is "
        + ("strong." if assessment == "strong" else "mixed, with a few things I would tighten.")
    ]
    if detected_garments:
        parts.append(f"You’re signaling pieces like {', '.join(detected_garments[:2])}, which gives me enough structure to assess the look.")
    else:
        parts.append("I can give a directional read from text, but an image would make the assessment much more reliable.")
    if detected_colors and seasonal:
        parts.append(f"The color story sounds closest to {', '.join(detected_colors[:2])}, so I’d check whether that stays inside your {seasonal} guidance.")
    elif seasonal:
        parts.append(f"I’d measure the color balance against your {seasonal} direction.")
    if frame:
        parts.append(f"I’d also check whether the shape balance supports your {frame.lower()} frame.")
    if contrast:
        parts.append(f"Your {contrast.lower()} contrast handling also matters for whether the look feels sharp or washed out.")
    if primary and secondary:
        parts.append(f"Stylistically, I’d want the outfit to stay coherent with your {primary} + {secondary} blend.")
    elif primary:
        parts.append(f"Stylistically, I’d want the outfit to stay coherent with your {primary} direction.")
    if occasion:
        parts.append(f"I’m reading it against your recent {occasion} context.")
    if assessment != "strong":
        parts.append("If you want a sharper read, send a photo or tell me the exact top, bottom, shoes, and color mix.")

    suggestions = [
        "Upload a photo for a sharper outfit check",
        "Tell me what part feels off",
        "What would improve this look?",
        "Give me a cleaner alternative",
    ]
    payload = {
        "assessment": assessment,
        "detected_colors": detected_colors,
        "detected_garments": detected_garments,
        "image_required_for_high_confidence": True,
        "memory_sources_read": [
            "user_profile",
            "style_preference",
            "derived_interpretations",
            "conversation_memory",
            "feedback_history",
        ],
        "memory_sources_written": [
            "conversation_memory",
            "sentiment_history",
            "confidence_history",
        ],
    }
    return " ".join(parts), suggestions, payload


def build_garment_on_me_response(
    *,
    message: str,
    user_context: UserContext,
    previous_context: Dict[str, Any],
    profile_confidence: ProfileConfidence,
) -> tuple[str, List[str], Dict[str, Any]]:
    lowered = str(message or "").strip().lower()
    urls = _URL_RE.findall(lowered)
    detected_colors = [color for color in _COLOR_WORDS if color in lowered]
    detected_garments = [garment for garment in _GARMENT_WORDS if garment in lowered]

    style_pref = dict(user_context.style_preference or {})
    primary = str(style_pref.get("primaryArchetype") or "").strip()
    secondary = str(style_pref.get("secondaryArchetype") or "").strip()
    derived = dict(user_context.derived_interpretations or {})
    seasonal = _nested_value(derived, "SeasonalColorGroup")
    frame = _nested_value(derived, "FrameStructure")
    height = _nested_value(derived, "HeightCategory")
    body_shape = _nested_value(dict(user_context.analysis_attributes or {}), "BodyShape")
    occasion = str(previous_context.get("last_occasion") or "").replace("_", " ").strip()

    target_piece = detected_garments[0] if detected_garments else "piece"
    fit_confidence = 0
    if target_piece != "piece":
        fit_confidence += 1
    if seasonal:
        fit_confidence += 1
    if frame or body_shape or height:
        fit_confidence += 1
    if profile_confidence.score_pct >= 75:
        fit_confidence += 1

    qualitative_fit = "promising" if fit_confidence >= 3 else "uncertain"
    parts: List[str] = [
        f"My current read is that this {target_piece} looks {qualitative_fit} for you."
        if target_piece != "piece"
        else "My current read is directionally useful, but still limited because I do not know the exact garment type."
    ]
    if seasonal:
        if detected_colors:
            parts.append(f"The color story sounds closest to {', '.join(detected_colors[:2])}, so I’d check that against your {seasonal} guidance.")
        else:
            parts.append(f"I would first check whether the color sits inside your {seasonal} direction.")
    if frame:
        parts.append(f"I’d pressure-test the silhouette against your {frame.lower()} frame balance.")
    if body_shape:
        parts.append(f"Your saved body-shape read, {body_shape.lower()}, also affects whether the cut will feel balanced on you.")
    if height:
        parts.append(f"Your {height.lower()} proportion profile matters for hem, break, and visual length.")
    if primary and secondary:
        parts.append(f"I’d also want the garment mood to stay inside your {primary} + {secondary} style blend.")
    elif primary:
        parts.append(f"I’d also want the garment mood to stay inside your {primary} style direction.")
    if occasion:
        parts.append(f"I’m loosely reading it against your recent {occasion} context.")
    if urls:
        parts.append("Because you shared a product link, I can use this as the basis for a later try-on or sharper shopping verdict.")
    if qualitative_fit != "promising":
        parts.append("To make this much more reliable, send a product image or link plus the occasion you want it for.")

    suggestions = [
        "Try this on me if safe",
        "Should I buy it?",
        "What would pair with it?",
        "Show me a safer alternative",
    ]
    payload = {
        "target_piece": target_piece,
        "qualitative_fit": qualitative_fit,
        "product_urls": urls,
        "detected_colors": detected_colors,
        "detected_garments": detected_garments,
        "tryon_eligible": bool(urls or target_piece != "piece"),
        "memory_sources_read": [
            "user_profile",
            "analysis_attributes",
            "derived_interpretations",
            "style_preference",
            "conversation_memory",
        ],
        "memory_sources_written": [
            "conversation_memory",
            "sentiment_history",
            "confidence_history",
        ],
    }
    return " ".join(parts), suggestions, payload


def build_capsule_or_trip_planning_response(
    *,
    message: str,
    user_context: UserContext,
    previous_context: Dict[str, Any],
    profile_confidence: ProfileConfidence,
) -> tuple[str, List[str], Dict[str, Any]]:
    lowered = str(message or "").strip().lower()
    wardrobe_items = list(user_context.wardrobe_items or [])
    style_pref = dict(user_context.style_preference or {})
    primary = str(style_pref.get("primaryArchetype") or "").strip()
    secondary = str(style_pref.get("secondaryArchetype") or "").strip()
    derived = dict(user_context.derived_interpretations or {})
    seasonal = _nested_value(derived, "SeasonalColorGroup")
    occasion = str(previous_context.get("last_occasion") or "").replace("_", " ").strip()

    planning_type = "trip" if any(token in lowered for token in ("trip", "travel", "pack", "vacation")) else "capsule"
    horizon = "5 looks" if "workweek" in lowered else "3-5 looks"
    wardrobe_count = len(wardrobe_items)
    has_wardrobe = wardrobe_count > 0

    anchors: List[str] = []
    if has_wardrobe:
        anchors = [str(item.get("title") or "").strip() for item in wardrobe_items[:3] if str(item.get("title") or "").strip()]

    parts: List[str] = [
        f"I would plan this as a bounded {planning_type} set, not as a full wardrobe rebuild."
    ]
    parts.append(f"My starting shape would be {horizon} built around a small number of repeating anchors.")
    if anchors:
        parts.append(
            "From your saved wardrobe, I would start with "
            + ", ".join(anchors[:-1]) + (" and " + anchors[-1] if len(anchors) > 1 else anchors[0])
            + "."
        )
    else:
        parts.append("You have limited wardrobe memory saved right now, so I would need either wardrobe seeding or allow catalog gaps to fill the plan.")
    if seasonal:
        parts.append(f"I would keep the palette controlled inside your {seasonal} direction so the set stays mixable.")
    if primary and secondary:
        parts.append(f"I would keep the capsule mood consistent with your {primary} + {secondary} blend.")
    elif primary:
        parts.append(f"I would keep the capsule mood consistent with your {primary} direction.")
    if occasion:
        parts.append(f"I’m also using your recent {occasion} context as a planning constraint.")
    if profile_confidence.score_pct < 75:
        parts.append("Your profile is usable, but better image/style data would make the plan more precise.")

    suggestions = [
        "Use my wardrobe first",
        "Fill the gaps from catalog",
        "Plan a workweek version",
        "Plan a travel packing list",
    ]
    payload = {
        "planning_type": planning_type,
        "target_horizon": horizon,
        "wardrobe_anchor_count": len(anchors),
        "wardrobe_anchors": anchors,
        "catalog_gap_fill_needed": not has_wardrobe,
        "memory_sources_read": [
            "user_profile",
            "style_preference",
            "derived_interpretations",
            "wardrobe_memory",
            "conversation_memory",
        ],
        "memory_sources_written": [
            "conversation_memory",
            "sentiment_history",
            "confidence_history",
        ],
    }
    return " ".join(parts), suggestions, payload


def build_wardrobe_ingestion_response(
    *,
    message: str,
    user_context: UserContext,
    profile_confidence: ProfileConfidence,
    saved_item: Dict[str, Any] | None = None,
) -> tuple[str, List[str], Dict[str, Any]]:
    lowered = str(message or "").strip().lower()
    urls = _URL_RE.findall(lowered)
    detected_colors = [color for color in _COLOR_WORDS if color in lowered]
    detected_garments = [garment for garment in _GARMENT_WORDS if garment in lowered]
    style_pref = dict(user_context.style_preference or {})
    primary = str(style_pref.get("primaryArchetype") or "").strip()
    target_piece = detected_garments[0] if detected_garments else "piece"

    title_parts = []
    if detected_colors:
        title_parts.append(detected_colors[0].title())
    if detected_garments:
        title_parts.append(detected_garments[0].title())
    title = " ".join(title_parts).strip() or "Saved Wardrobe Item"

    saved = bool(saved_item)
    parts: List[str] = [
        f"I {'saved' if saved else 'can save'} this {target_piece} into your wardrobe memory."
        if target_piece != "piece"
        else f"I {'saved' if saved else 'can save'} this item into your wardrobe memory."
    ]
    if detected_colors:
        parts.append(f"I captured the color signal as {detected_colors[0]}.")
    if primary:
        parts.append(f"This will help me make future answers more consistent with your {primary} direction.")
    if not saved:
        parts.append("I still need at least the garment type or a product link to save it cleanly.")
    elif profile_confidence.score_pct < 75:
        parts.append("Your wardrobe memory is growing, but sharper profile data will make future wardrobe-first answers stronger.")

    suggestions = [
        "Save another wardrobe item",
        "What goes with this piece?",
        "Build outfits from my wardrobe",
        "Plan a capsule with my wardrobe",
    ]
    payload = {
        "saved": saved,
        "title": title,
        "product_urls": urls,
        "detected_colors": detected_colors,
        "detected_garments": detected_garments,
        "saved_item_id": str((saved_item or {}).get("id") or ""),
        "memory_sources_read": [
            "user_profile",
            "style_preference",
            "wardrobe_memory",
        ],
        "memory_sources_written": [
            "wardrobe_memory",
            "conversation_memory",
            "sentiment_history",
            "confidence_history",
        ],
    }
    return " ".join(parts), suggestions, payload


def build_feedback_submission_response(
    *,
    message: str,
    previous_context: Dict[str, Any],
) -> tuple[str, List[str], Dict[str, Any]]:
    lowered = str(message or "").strip().lower()
    recommendations = list(previous_context.get("last_recommendations") or [])
    top = recommendations[0] if recommendations else {}
    negative_tokens = ("i dislike", "i don't like", "i dont like", "hate this", "not for me")
    positive_tokens = ("i like", "i love", "love this", "like this")
    if any(token in lowered for token in negative_tokens):
        event_type = "dislike"
    elif any(token in lowered for token in positive_tokens):
        event_type = "like"
    else:
        event_type = "dislike"
    item_ids = [str(value) for value in (top.get("item_ids") or []) if str(value).strip()]
    outfit_rank = int(top.get("rank") or 1) if str(top.get("rank") or "").strip() else 1

    if not recommendations:
        return (
            "I can store feedback once I have something to attach it to. Ask for an outfit, pairing, or shopping suggestion first.",
            ["Show me an outfit", "Should I buy this?", "What goes with this piece?"],
            {
                "event_type": event_type,
                "resolved": False,
                "item_ids": [],
                "memory_sources_read": ["conversation_memory"],
                "memory_sources_written": [],
            },
        )

    parts: List[str] = [
        "I’ve attached that feedback to your most recent recommendation."
        if item_ids
        else "I understood the feedback, but I could not resolve item-level links from the last recommendation."
    ]
    parts.append(
        "I’ll use it to "
        + ("lean further into similar directions." if event_type == "like" else "avoid repeating the same direction.")
    )

    suggestions = [
        "Show me another option",
        "Explain why you recommended it",
        "Show me something more like this" if event_type == "like" else "Show me something different",
        "What should I try next?",
    ]
    payload = {
        "event_type": event_type,
        "resolved": bool(item_ids),
        "item_ids": item_ids,
        "outfit_rank": outfit_rank,
        "target_turn_id": str((previous_context.get("last_response_metadata") or {}).get("turn_id") or ""),
        "memory_sources_read": [
            "recommendation_history",
            "conversation_memory",
        ],
        "memory_sources_written": [
            "feedback_history",
            "catalog_interaction_history",
            "conversation_memory",
        ],
    }
    return " ".join(parts), suggestions, payload


def build_virtual_tryon_response(
    *,
    message: str,
    success: bool,
    product_url: str = "",
    error_message: str = "",
) -> tuple[str, List[str], Dict[str, Any]]:
    if success:
        message_text = "I generated a virtual try-on preview for that piece and it passed the quality checks."
        suggestions = [
            "Should I buy this too?",
            "What would pair with it?",
            "Show me a safer alternative",
            "Explain whether it suits me",
        ]
    else:
        lowered_error = str(error_message or "").lower()
        if "full-body" in lowered_error:
            message_text = graceful_policy_message("missing_person_image")
        elif error_message:
            message_text = error_message
        else:
            message_text = (
                "I couldn’t generate a reliable try-on from this request yet. "
                "You can still ask whether the garment suits you, or send a cleaner product image/link."
            )
        suggestions = [
            "How will this look on me?",
            "Should I buy this?",
            "Send a cleaner product image",
            "What goes with this piece?",
        ]

    payload = {
        "success": success,
        "product_url": product_url,
        "error_message": error_message,
        "memory_sources_read": [
            "user_profile",
            "conversation_memory",
        ],
        "memory_sources_written": [
            "conversation_memory",
            "policy_event_log",
        ],
    }
    return message_text, suggestions, payload


def _nested_value(payload: Dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, dict):
        return str(value.get("value") or "").strip()
    return str(value or "").strip()


def _infer_pairing_role(target_piece: str) -> str:
    piece = str(target_piece or "").strip().lower()
    top_like = {"blazer", "jacket", "coat", "shirt", "top", "blouse", "cardigan"}
    bottom_like = {"jeans", "trousers", "pants", "skirt"}
    if piece in top_like:
        return "top"
    if piece in bottom_like:
        return "bottom"
    return "unknown"


def _select_wardrobe_pairings(
    *,
    wardrobe_items: List[Dict[str, Any]],
    target_piece: str,
    target_role: str,
    detected_colors: List[str],
    occasion: str,
) -> List[Dict[str, Any]]:
    scored: List[Dict[str, Any]] = []
    target_piece = str(target_piece or "").strip().lower()
    target_colors = {str(color or "").strip().lower() for color in detected_colors if str(color or "").strip()}
    complementary_categories = {
        "top": {"bottom", "trousers", "pants", "skirt", "jeans"},
        "bottom": {"top", "shirt", "blouse", "outerwear", "jacket", "blazer"},
    }
    desired = complementary_categories.get(target_role, set())

    for item in list(wardrobe_items or []):
        category = str(item.get("garment_category") or "").strip().lower()
        subtype = str(item.get("garment_subtype") or "").strip().lower()
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        if target_piece and target_piece in {category, subtype}:
            continue
        if desired and not (category in desired or subtype in desired):
            continue

        score = 0
        reasons: List[str] = []
        if desired and (category in desired or subtype in desired):
            score += 3
            reasons.append("complementary role")
        elif target_role == "unknown" and category:
            score += 1
            reasons.append("available saved piece")

        item_color = str(item.get("primary_color") or "").strip().lower()
        if target_colors and item_color in target_colors:
            score += 1
            reasons.append("shared color story")
        elif target_colors and item_color in {"cream", "white", "black", "navy", "beige", "brown", "tan"}:
            score += 1
            reasons.append("neutral color bridge")

        item_occasion = str(item.get("occasion_fit") or "").strip().lower().replace(" ", "_")
        if occasion and item_occasion and item_occasion == occasion.replace(" ", "_"):
            score += 1
            reasons.append("occasion aligned")

        if score <= 0:
            continue
        enriched = dict(item)
        enriched["_compatibility_score"] = score
        enriched["_compatibility_reasons"] = reasons
        scored.append(enriched)

    scored.sort(
        key=lambda item: (
            -int(item.get("_compatibility_score") or 0),
            str(item.get("title") or "").lower(),
        )
    )
    return scored
