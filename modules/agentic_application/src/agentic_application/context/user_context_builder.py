from typing import Any, Dict

from user.context import build_saved_user_context


def build_agent_input_context(analysis_status: Dict[str, Any], user_need: str, extra_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        **build_saved_user_context(analysis_status),
        "user_need": user_need,
        "request_context": dict(extra_context or {}),
    }


__all__ = ["build_agent_input_context"]
