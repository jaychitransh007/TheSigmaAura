from __future__ import annotations

import re
from typing import Dict, Iterable

from .schemas import UserContext


_QUERY_FILTER_MAPPING = {
    "GarmentCategory": "garment_category",
    "GarmentSubtype": "garment_subtype",
    "StylingCompleteness": "styling_completeness",
}


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


def merge_filters(*filter_dicts: Dict[str, str]) -> Dict[str, str]:
    """Merge multiple filter dicts; later dicts override earlier ones. Empty values are skipped."""
    merged: Dict[str, str] = {}
    for d in filter_dicts:
        for key, value in d.items():
            normalized = normalize_filter_value(value) if value else ""
            if normalized:
                merged[key] = normalized
    return merged


def extract_query_document_filters(document: str) -> Dict[str, str]:
    """Extract hard-filter candidates from structured query documents."""
    filters: Dict[str, str] = {}
    for line in document.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        label, raw_value = stripped[2:].split(":", 1)
        key = _QUERY_FILTER_MAPPING.get(label.strip())
        if not key:
            continue
        normalized = normalize_filter_value(raw_value)
        if normalized:
            filters[key] = normalized
    return filters


def build_directional_filters(direction_type: str, role: str) -> Dict[str, str]:
    if direction_type == "complete" or role == "complete":
        return {"styling_completeness": "complete"}
    if role == "top":
        return {"styling_completeness": "needs_bottomwear"}
    if role == "bottom":
        return {"styling_completeness": "needs_topwear"}
    if direction_type == "paired":
        return {}
    return {}


def drop_filter_keys(filters: Dict[str, str], keys: Iterable[str]) -> Dict[str, str]:
    blocked = {str(key or "").strip() for key in keys}
    return {
        key: value
        for key, value in filters.items()
        if key not in blocked
    }
