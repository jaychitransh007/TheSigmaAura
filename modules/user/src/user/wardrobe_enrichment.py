from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any, Dict

from openai import OpenAI

from user_profiler.config import get_api_key
from user_profiler.service import _extract_response_json, _image_to_input_url


_GARMENT_ATTRIBUTES_PATH = (
    Path(__file__).resolve().parents[3]
    / "style_engine"
    / "configs"
    / "config"
    / "garment_attributes.json"
)
_PROMPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "catalog"
    / "src"
    / "catalog"
    / "enrichment"
    / "prompts"
    / "system_prompt.txt"
)


def _load_prompt() -> str:
    text = _PROMPT_PATH.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Prompt file is empty: {_PROMPT_PATH}")
    return text


def _load_attribute_config() -> Dict[str, Any]:
    return json.loads(_GARMENT_ATTRIBUTES_PATH.read_text(encoding="utf-8"))


def response_format() -> Dict[str, Any]:
    cfg = _load_attribute_config()
    enum_attributes = dict(cfg.get("enum_attributes") or {})
    text_attributes = list(cfg.get("text_attributes") or [])

    properties: Dict[str, Any] = {}
    required: list[str] = []

    # Phase 12D follow-up (April 9 2026): explicit non-garment detection.
    # The shared garment_attributes.json config doesn't have these fields
    # because catalog enrichment is fed clean catalog images that are
    # always garments. Wardrobe enrichment, in contrast, gets arbitrary
    # user uploads — including charts, screenshots, landscape photos,
    # etc. — so we add an explicit `is_garment_photo` boolean and a
    # `garment_present_confidence` number to the wardrobe response
    # schema. The model's vision classifies the image first, and the
    # orchestrator uses these fields to surface a "this isn't a
    # garment, please upload a clearer photo" clarification before any
    # downstream pipeline runs.
    properties["is_garment_photo"] = {"type": "boolean"}
    properties["garment_present_confidence"] = {"type": "number", "minimum": 0, "maximum": 1}
    required.extend(["is_garment_photo", "garment_present_confidence"])

    for name, enum_values in enum_attributes.items():
        properties[name] = {"anyOf": [{"type": "string", "enum": enum_values}, {"type": "null"}]}
        properties[f"{name}_confidence"] = {"type": "number", "minimum": 0, "maximum": 1}
        required.extend([name, f"{name}_confidence"])

    for name in text_attributes:
        properties[name] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
        properties[f"{name}_confidence"] = {"type": "number", "minimum": 0, "maximum": 1}
        required.extend([name, f"{name}_confidence"])

    return {
        "type": "json_schema",
        "name": "garment_attributes_with_confidence",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": required,
            "properties": properties,
        },
    }


SYSTEM_PROMPT = _load_prompt()


def infer_wardrobe_catalog_attributes(
    *,
    image_ref: str,
    title: str = "",
    description: str = "",
    garment_category: str = "",
    garment_subtype: str = "",
    primary_color: str = "",
    secondary_color: str = "",
    pattern_type: str = "",
    formality_level: str = "",
    occasion_fit: str = "",
    brand: str = "",
    notes: str = "",
    model: str = "gpt-5-mini",
) -> Dict[str, Any]:
    client = OpenAI(api_key=get_api_key())
    image_url = _image_to_input_url(image_ref)
    mime_type, _ = mimetypes.guess_type(str(image_ref))
    mime_type = mime_type or "image/jpeg"

    user_text = (
        "FIRST decide whether the image actually shows a wearable garment. "
        "If the image shows anything else — a chart, screenshot, document, "
        "landscape, food, animal, person without visible clothing, or any "
        "non-garment object — set `is_garment_photo` to `false`, set "
        "`garment_present_confidence` to a low value (≤ 0.3), and return "
        "null for ALL garment attributes (with their confidence at 0.0). "
        "Do NOT guess garment attributes for non-garment images. The user "
        "will be asked to upload a clearer photo.\n"
        "\n"
        "If the image DOES show a wearable garment, set `is_garment_photo` "
        "to `true`, set `garment_present_confidence` to a value reflecting "
        "how clearly you can see the garment (0.7+ for clear garment "
        "photos, 0.5-0.7 for partial/unclear), and proceed to extract the "
        "46 garment attributes per the rules below.\n"
        "\n"
        "Analyze this single wardrobe garment image and return the required JSON.\n"
        "The output schema must match the global catalog enrichment schema exactly.\n"
        "If user-provided hints conflict with the image, trust the image and lower confidence.\n"
        f"Title: {title}\n"
        f"Description: {description}\n"
        f"Garment Category Hint: {garment_category}\n"
        f"Garment Subtype Hint: {garment_subtype}\n"
        f"Primary Color Hint: {primary_color}\n"
        f"Secondary Color Hint: {secondary_color}\n"
        f"Pattern Hint: {pattern_type}\n"
        f"Formality Hint: {formality_level}\n"
        f"Occasion Hint: {occasion_fit}\n"
        f"Brand: {brand}\n"
        f"Notes: {notes}\n"
    ).strip()

    # reasoning_effort="minimal" — wardrobe enrichment is structured
    # vision extraction (read garment attributes from the image into a
    # fixed schema). No chain-of-thought needed.
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_text},
                    {"type": "input_image", "image_url": image_url},
                ],
            },
        ],
        reasoning={"effort": "minimal"},
        text={"format": response_format()},
    )
    parsed = _extract_response_json(response)
    return {
        "model": model,
        "image_ref": image_ref,
        "mime_type": mime_type,
        "attributes": parsed,
        "request_context": {
            "title": title,
            "description": description,
            "garment_category": garment_category,
            "garment_subtype": garment_subtype,
            "primary_color": primary_color,
            "secondary_color": secondary_color,
            "pattern_type": pattern_type,
            "formality_level": formality_level,
            "occasion_fit": occasion_fit,
            "brand": brand,
            "notes": notes,
        },
        "raw_output_text": getattr(response, "output_text", "") or json.dumps(parsed, ensure_ascii=True),
    }


def flatten_catalog_attributes(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("attributes")
    if isinstance(raw, dict):
        return dict(raw)
    return {}
