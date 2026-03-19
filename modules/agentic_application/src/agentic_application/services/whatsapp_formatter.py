from __future__ import annotations

from typing import Any, Dict, List


MAX_RENDERED_OUTFITS = 2
MAX_RENDERED_ITEMS_PER_OUTFIT = 3
MAX_RENDERED_SUGGESTIONS = 3


def format_turn_response_for_whatsapp(result: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(result or {})
    raw_message = str(payload.get("assistant_message") or "").strip()
    outfits = list(payload.get("outfits") or [])
    suggestions = [
        str(value).strip()
        for value in list(payload.get("follow_up_suggestions") or [])
        if str(value).strip()
    ]

    rendered_message = _build_whatsapp_message(
        raw_message=raw_message,
        outfits=outfits,
        suggestions=suggestions,
    )
    metadata = dict(payload.get("metadata") or {})
    metadata["channel_rendering"] = {
        "surface": "whatsapp",
        "raw_assistant_message": raw_message,
        "rendered_outfit_count": min(len(outfits), MAX_RENDERED_OUTFITS),
        "rendered_suggestion_count": min(len(suggestions), MAX_RENDERED_SUGGESTIONS),
    }

    payload["assistant_message"] = rendered_message
    payload["follow_up_suggestions"] = suggestions[:MAX_RENDERED_SUGGESTIONS]
    payload["metadata"] = metadata
    return payload


def _build_whatsapp_message(
    *,
    raw_message: str,
    outfits: List[Dict[str, Any]],
    suggestions: List[str],
) -> str:
    parts: List[str] = []
    if raw_message:
        parts.append(raw_message)

    rendered_outfits = list(outfits[:MAX_RENDERED_OUTFITS])
    if rendered_outfits:
        lines = ["Top options:"]
        for outfit in rendered_outfits:
            rank = int(outfit.get("rank") or 0)
            title = str(outfit.get("title") or f"Option {rank or 1}").strip()
            items = _format_outfit_items(list(outfit.get("items") or []))
            line = f"{rank}. {title}" if rank else title
            if items:
                line = f"{line}: {items}"
            lines.append(line)
        parts.append("\n".join(lines))

    rendered_suggestions = suggestions[:MAX_RENDERED_SUGGESTIONS]
    if rendered_suggestions:
        reply_lines = ["Reply with:"]
        for idx, suggestion in enumerate(rendered_suggestions, start=1):
            reply_lines.append(f"{idx}. {suggestion}")
        parts.append("\n".join(reply_lines))

    return "\n\n".join(part for part in parts if part).strip()


def _format_outfit_items(items: List[Dict[str, Any]]) -> str:
    rendered: List[str] = []
    for item in items[:MAX_RENDERED_ITEMS_PER_OUTFIT]:
        title = str(item.get("title") or "Item").strip()
        source = str(item.get("source") or "").strip().lower()
        if source == "wardrobe":
            rendered.append(f"{title} (your wardrobe)")
        elif source == "catalog":
            rendered.append(f"{title} (catalog)")
        else:
            rendered.append(title)
    return ", ".join(rendered)
