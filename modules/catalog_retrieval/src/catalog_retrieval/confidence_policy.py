def normalize_confidence(raw_value: object) -> float:
    try:
        value = float(raw_value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, value))


def confidence_aware_value(
    raw_value: object,
    raw_confidence: object,
    *,
    min_keep_value: float,
    min_mark_uncertain: float,
) -> str:
    value = str(raw_value or "").strip()
    confidence = normalize_confidence(raw_confidence)
    if not value:
        return "Unknown"
    if confidence >= min_keep_value:
        return value
    if confidence >= min_mark_uncertain:
        return f"Uncertain({value})"
    return "Unknown"
