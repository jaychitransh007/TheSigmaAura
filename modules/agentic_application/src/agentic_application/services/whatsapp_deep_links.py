from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlencode


def build_whatsapp_deep_link(
    *,
    base_app_url: str,
    user_id: str,
    conversation_id: str = "",
    task: str = "",
    previous_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous_context = dict(previous_context or {})
    onboarding_required = bool((previous_context.get("last_response_metadata") or {}).get("onboarding_required"))
    resolved_task = str(task or "").strip()
    if not resolved_task:
        if onboarding_required:
            resolved_task = "complete_onboarding"
        elif str(previous_context.get("last_intent") or "") == "virtual_tryon_request":
            resolved_task = "review_tryon"
        elif str(previous_context.get("last_intent") or "") == "capsule_or_trip_planning":
            resolved_task = "capsule_planner"
        elif int(((previous_context.get("memory") or {}).get("wardrobe_item_count") or 0)) > 0:
            resolved_task = "manage_wardrobe"
        else:
            resolved_task = "chat"

    focus = _task_focus(resolved_task)
    if resolved_task == "complete_onboarding":
        path = "/onboard"
    elif resolved_task == "improve_profile":
        path = "/onboard/processing"
    else:
        path = "/"

    app_base_url = str(base_app_url or "").rstrip("/")
    if app_base_url.endswith("/rest/v1"):
        app_base_url = app_base_url[: -len("/rest/v1")]

    query = {
        "user": user_id,
        "source": "whatsapp",
        "focus": focus,
    }
    if conversation_id:
        query["conversation_id"] = conversation_id
    url = f"{app_base_url}{path}?{urlencode(query)}"

    return {
        "task": resolved_task,
        "deep_link_url": url,
        "assistant_message": _task_message(resolved_task),
        "metadata": {
            "focus": focus,
            "path": path,
            "has_conversation_context": bool(conversation_id),
        },
    }


def _task_focus(task: str) -> str:
    mapping = {
        "complete_onboarding": "onboarding",
        "improve_profile": "profile",
        "manage_wardrobe": "wardrobe",
        "review_tryon": "tryon",
        "capsule_planner": "planner",
        "chat": "chat",
    }
    return mapping.get(task, "chat")


def _task_message(task: str) -> str:
    mapping = {
        "complete_onboarding": "Finish onboarding on the web to unlock full WhatsApp styling support.",
        "improve_profile": "Open the web profile flow to improve your styling accuracy.",
        "manage_wardrobe": "Open the web app to review and manage your saved wardrobe in detail.",
        "review_tryon": "Open the web app to review your try-on result with the full visual interface.",
        "capsule_planner": "Open the web app to plan your capsule or trip with the richer planner view.",
        "chat": "Open the web app to continue this conversation with the full visual interface.",
    }
    return mapping.get(task, mapping["chat"])
