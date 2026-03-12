from typing import Any, Dict


def build_saved_user_context(analysis_status: Dict[str, Any]) -> Dict[str, Any]:
    profile = dict(analysis_status.get("profile") or {})
    return {
        "profile": profile,
        "analysis_attributes": dict(analysis_status.get("attributes") or {}),
        "derived_interpretations": dict(analysis_status.get("derived_interpretations") or {}),
        "style_preference": dict(profile.get("style_preference") or {}),
    }


__all__ = ["build_saved_user_context"]
