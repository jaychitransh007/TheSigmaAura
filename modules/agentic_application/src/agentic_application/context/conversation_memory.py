from typing import Any, Dict


def merge_conversation_memory(previous: Dict[str, Any] | None, current: Dict[str, Any] | None) -> Dict[str, Any]:
    merged = dict(previous or {})
    for key, value in dict(current or {}).items():
        if value not in {"", None, [], {}}:
            merged[key] = value
    return merged


__all__ = ["merge_conversation_memory"]
