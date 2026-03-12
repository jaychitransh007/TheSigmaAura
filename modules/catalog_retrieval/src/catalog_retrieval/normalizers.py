import re


def clean_text(raw_value: object, *, max_chars: int) -> str:
    text = str(raw_value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text or "Unknown"
    clipped = text[:max_chars].rsplit(" ", 1)[0].strip()
    return clipped or text[:max_chars].strip() or "Unknown"


def safe_text(raw_value: object) -> str:
    text = str(raw_value or "").strip()
    return text or "Unknown"
