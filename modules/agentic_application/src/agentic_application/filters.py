from __future__ import annotations

import re
from typing import Any, Dict, Iterable

from .schemas import UserContext


_QUERY_FILTER_MAPPING = {
    "GarmentSubtype": "garment_subtype",
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


# Maps user-facing garment terms to (garment_category, garment_subtype) filter values.
GARMENT_TERM_TO_FILTER: Dict[str, tuple[str, str]] = {
    "shirt": ("top", "shirt"),
    "shirts": ("top", "shirt"),
    "blouse": ("top", "blouse"),
    "tee": ("top", "tee"),
    "tees": ("top", "tee"),
    "t-shirt": ("top", "tee"),
    "top": ("top", ""),
    "tops": ("top", ""),
    "sweater": ("top", "sweater"),
    "sweaters": ("top", "sweater"),
    "trouser": ("bottom", "trousers"),
    "trousers": ("bottom", "trousers"),
    "pant": ("bottom", "trousers"),
    "pants": ("bottom", "trousers"),
    "jean": ("bottom", "jeans"),
    "jeans": ("bottom", "jeans"),
    "skirt": ("bottom", "skirt"),
    "skirts": ("bottom", "skirt"),
    "short": ("bottom", "shorts"),
    "shorts": ("bottom", "shorts"),
    "blazer": ("outerwear", "blazer"),
    "blazers": ("outerwear", "blazer"),
    "jacket": ("outerwear", "jacket"),
    "jackets": ("outerwear", "jacket"),
    "coat": ("outerwear", "coat"),
    "coats": ("outerwear", "coat"),
    "cardigan": ("outerwear", "cardigan"),
    "cardigans": ("outerwear", "cardigan"),
    "hoodie": ("outerwear", "hoodie"),
    "hoodies": ("outerwear", "hoodie"),
    "shoe": ("shoe", ""),
    "shoes": ("shoe", ""),
    "sneaker": ("shoe", "sneaker"),
    "sneakers": ("shoe", "sneaker"),
    "boot": ("shoe", "boot"),
    "boots": ("shoe", "boot"),
    "heel": ("shoe", "heel"),
    "heels": ("shoe", "heel"),
    "sandal": ("shoe", "sandal"),
    "sandals": ("shoe", "sandal"),
    "loafer": ("shoe", "loafer"),
    "loafers": ("shoe", "loafer"),
    "dress": ("complete", "dress"),
    "dresses": ("complete", "dress"),
    "jumpsuit": ("complete", "jumpsuit"),
    "jumpsuits": ("complete", "jumpsuit"),
    "romper": ("complete", "romper"),
    "rompers": ("complete", "romper"),
}


def resolve_garment_filters(detected_garments: list[str]) -> Dict[str, str]:
    """Map detected garment terms to hard filter values for catalog search."""
    for term in detected_garments:
        key = term.strip().lower()
        if key in GARMENT_TERM_TO_FILTER:
            category, subtype = GARMENT_TERM_TO_FILTER[key]
            filters: Dict[str, str] = {}
            if category:
                filters["garment_category"] = category
            if subtype:
                filters["garment_subtype"] = subtype
            return filters
    return {}


def drop_filter_keys(filters: Dict[str, str], keys: Iterable[str]) -> Dict[str, str]:
    blocked = {str(key or "").strip() for key in keys}
    return {
        key: value
        for key, value in filters.items()
        if key not in blocked
    }
