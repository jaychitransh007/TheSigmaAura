from __future__ import annotations

import re
from typing import Any, Dict, Iterable

from .schemas import UserContext


def normalize_filter_value(value: str) -> str:
    """Normalize a raw filter value to a lowered snake_case token."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered in {"unknown", "unspecified", "n/a", "none", "null"}:
        return ""
    lowered = lowered.split(",")[0].strip()
    lowered = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return lowered


def build_global_hard_filters(user: UserContext) -> Dict[str, str]:
    """Build the always-applied hard filters from user context."""
    filters: Dict[str, str] = {}
    gender = user.gender.strip().lower()
    if gender == "male":
        filters["gender_expression"] = "masculine"
    elif gender == "female":
        filters["gender_expression"] = "feminine"
    return filters


def merge_filters(*filter_dicts: Dict[str, Any]) -> Dict[str, Any]:
    """Merge multiple filter dicts; later dicts override earlier ones.

    Values can be strings (single value) or lists (multi-value). Lists
    are preserved as-is for the SQL function's array matching. Empty
    values are skipped.
    """
    merged: Dict[str, Any] = {}
    for d in filter_dicts:
        for key, value in d.items():
            if isinstance(value, list):
                # Multi-value filter: normalize each element, drop empties
                normalized_list = [normalize_filter_value(v) for v in value if v]
                normalized_list = [v for v in normalized_list if v]
                if normalized_list:
                    merged[key] = normalized_list
            else:
                normalized = normalize_filter_value(value) if value else ""
                if normalized:
                    merged[key] = normalized
    return merged


def build_directional_filters(direction_type: str, role: str) -> Dict[str, Any]:
    if direction_type == "complete" or role == "complete":
        return {"styling_completeness": "complete"}
    if role == "outerwear":
        return {"styling_completeness": ["needs_innerwear"]}
    if role == "top":
        return {"styling_completeness": "needs_bottomwear"}
    if role == "bottom":
        return {"styling_completeness": "needs_topwear"}
    if direction_type in ("paired", "three_piece"):
        return {}
    return {}


def drop_filter_keys(filters: Dict[str, str], keys: Iterable[str]) -> Dict[str, str]:
    blocked = {str(key or "").strip() for key in keys}
    return {
        key: value
        for key, value in filters.items()
        if key not in blocked
    }
