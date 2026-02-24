from typing import Any, Dict, List

from .config_registry import load_body_harmony_attributes, load_user_context_attributes


_VISUAL_EXTRA_ENUMS = {
    "gender": ["male", "female"],
    "age": ["18_24", "25_30", "30_35"],
}


_BODY_CFG = load_body_harmony_attributes()
_USER_CFG = load_user_context_attributes()


BODY_ENUMS: Dict[str, List[str]] = dict(_BODY_CFG.get("enum_attributes") or {})


def _dim_values(name: str) -> List[str]:
    dims = (_USER_CFG.get("dimensions") or {})
    dim = dims.get(name) or {}
    return list(dim.get("canonical_values") or [])


TEXT_ENUMS = {
    "occasion": _dim_values("occasion"),
    "archetype": _dim_values("archetype"),
}


def visual_response_format() -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required: List[str] = []

    for key, values in BODY_ENUMS.items():
        properties[key] = {"type": "string", "enum": values}
        required.append(key)

    for key, values in _VISUAL_EXTRA_ENUMS.items():
        properties[key] = {"type": "string", "enum": values}
        required.append(key)

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }

    return {
        "type": "json_schema",
        "name": "user_visual_profile",
        "strict": True,
        "schema": schema,
    }


def textual_response_format() -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required: List[str] = []

    for key, values in TEXT_ENUMS.items():
        properties[key] = {"type": "string", "enum": values}
        required.append(key)

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }

    return {
        "type": "json_schema",
        "name": "user_text_context",
        "strict": True,
        "schema": schema,
    }
