from __future__ import annotations

from typing import Any, Iterable, Mapping


_RESTRICTED_GARMENT_TERMS = {
    "lingerie",
    "bra",
    "bralette",
    "panty",
    "panties",
    "underwear",
    "undergarment",
    "thong",
    "briefs",
    "bikini",
    "swimwear",
    "swimsuit",
    "nightie",
    "negligee",
    "corset",
}

# Only check structured category/type fields — never free-text fields
# like title, description, URL, brand, or tags. Those contain product
# names, brand names, and URLs where restricted terms appear as
# harmless substrings (e.g. "campusSutra" contains "bra").
_RECORD_CATEGORY_FIELDS = (
    "garment_category",
    "garment_subtype",
    "category",
    "subcategory",
    "product_type",
    "product_category",
    "GarmentCategory",
    "GarmentSubtype",
    "Category",
    "Subcategory",
    "ProductType",
    "ProductCategory",
)


def detect_restricted_category(*values: str) -> str:
    corpus = " ".join(str(value or "").strip().lower() for value in values if str(value or "").strip())
    for term in sorted(_RESTRICTED_GARMENT_TERMS, key=len, reverse=True):
        if term in corpus:
            return term
    return ""


def detect_restricted_record(record: Mapping[str, Any] | None = None, *extra_values: Any) -> str:
    values: list[str] = []
    payload = dict(record or {})
    for field in _RECORD_CATEGORY_FIELDS:
        value = payload.get(field)
        if isinstance(value, (list, tuple, set)):
            values.extend(str(item or "").strip() for item in value if str(item or "").strip())
        elif value is not None:
            values.append(str(value).strip())
    values.extend(str(value or "").strip() for value in extra_values if str(value or "").strip())
    return detect_restricted_category(*values)


def is_allowed_recommendation_record(record: Mapping[str, Any] | None = None, *extra_values: Any) -> bool:
    return not detect_restricted_record(record, *extra_values)


def filter_restricted_records(records: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    allowed: list[dict[str, Any]] = []
    blocked_terms: list[str] = []
    for record in records:
        matched = detect_restricted_record(record)
        if matched:
            blocked_terms.append(matched)
            continue
        allowed.append(dict(record))
    return allowed, blocked_terms


def ensure_allowed_garment_upload(*values: str) -> None:
    matched = detect_restricted_category(*values)
    if matched:
        raise ValueError("Restricted garment categories like lingerie or underwear are not allowed.")


def restricted_terms() -> set[str]:
    return set(_RESTRICTED_GARMENT_TERMS)
