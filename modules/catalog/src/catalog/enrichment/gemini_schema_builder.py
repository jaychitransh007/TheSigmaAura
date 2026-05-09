"""Build a Gemini-2.5-Flash-compatible response_schema from the canonical
garment attributes registry.

Gemini's structured output accepts a subset of OpenAPI Schema. The
shape we need:

    {
        "type": "OBJECT",
        "properties": {
            "<AttrName>": {
                "type": "STRING",
                "enum": [...],
                "nullable": True,
            },
            "<AttrName>_confidence": {
                "type": "NUMBER",
                "minimum": 0,
                "maximum": 1,
            },
            ...
        },
        "required": [...],
    }

This mirrors the existing OpenAI flow's flat structure (one property
per attribute, plus a `_confidence` companion) so the response parser
and catalog merge writer require minimal changes.

Notes vs. OpenAI structured output:
- Type tokens are uppercase (``OBJECT`` / ``STRING`` / ``NUMBER``) per
  Gemini's API.
- ``nullable: True`` lets the model emit null for axes it can't
  determine from the image — replaces OpenAI's ``"anyOf": [{...},
  {"type": "null"}]`` pattern.
- No ``additionalProperties: false`` (Gemini doesn't honour it
  reliably; instead we list every attribute in ``required``).

The applicability separation (``{value, confidence, applicable}``
nested shape) and per-pass schemas for the 3-pass staged extraction
architecture are deferred to follow-up changes — this module is the
minimum-viable single-pass schema for the smoke-test runner.
"""
from __future__ import annotations

from typing import Any, Mapping


def build_gemini_response_schema(
    enums: Mapping[str, list[str]],
    texts: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Translate the canonical attribute registry into a Gemini
    ``response_schema`` dict suitable for passing to
    ``GenerateContentConfig(response_schema=...)``.

    ``enums`` maps attribute name -> list of allowed enum values.
    ``texts`` lists the attribute names that are free-form strings
    (PrimaryColor / SecondaryColor today).
    """
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, values in enums.items():
        properties[name] = {
            "type": "STRING",
            "enum": list(values),
            "nullable": True,
        }
        properties[f"{name}_confidence"] = {
            "type": "NUMBER",
            "minimum": 0,
            "maximum": 1,
        }
        required.extend([name, f"{name}_confidence"])

    for name in texts:
        properties[name] = {
            "type": "STRING",
            "nullable": True,
        }
        properties[f"{name}_confidence"] = {
            "type": "NUMBER",
            "minimum": 0,
            "maximum": 1,
        }
        required.extend([name, f"{name}_confidence"])

    return {
        "type": "OBJECT",
        "properties": properties,
        "required": required,
    }
