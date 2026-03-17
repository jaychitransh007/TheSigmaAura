from typing import Dict, Any

from .attributes import ENUM_ATTRIBUTES, TEXT_ATTRIBUTES


def build_schema() -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required = []

    for name, enum_values in ENUM_ATTRIBUTES.items():
        properties[name] = {
            "anyOf": [
                {"type": "string", "enum": enum_values},
                {"type": "null"},
            ]
        }
        properties[f"{name}_confidence"] = {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        }
        required.extend([name, f"{name}_confidence"])

    for name in TEXT_ATTRIBUTES:
        properties[name] = {
            "anyOf": [
                {"type": "string"},
                {"type": "null"},
            ]
        }
        properties[f"{name}_confidence"] = {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        }
        required.extend([name, f"{name}_confidence"])

    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


def response_format() -> Dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "garment_attributes_with_confidence",
        "strict": True,
        "schema": build_schema(),
    }
