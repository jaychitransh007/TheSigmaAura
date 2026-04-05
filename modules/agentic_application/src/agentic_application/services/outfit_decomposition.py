from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image
from openai import OpenAI

from user_profiler.config import get_api_key
from user_profiler.service import _extract_response_json, _image_to_input_url

_log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parents[5] / "prompt" / "outfit_decomposition.md"

_ALLOWED_CATEGORIES = frozenset({"top", "bottom", "dress", "outerwear", "shoes"})

_GARMENT_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "name": "outfit_garments",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["garments"],
        "properties": {
            "garments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "garment_category",
                        "garment_subtype",
                        "primary_color",
                        "secondary_color",
                        "pattern_type",
                        "formality_level",
                        "occasion_fit",
                        "title",
                        "visibility_pct",
                        "bbox_top_pct",
                        "bbox_left_pct",
                        "bbox_height_pct",
                        "bbox_width_pct",
                    ],
                    "properties": {
                        "garment_category": {"type": "string"},
                        "garment_subtype": {"type": "string"},
                        "primary_color": {"type": "string"},
                        "secondary_color": {"type": "string"},
                        "pattern_type": {"type": "string"},
                        "formality_level": {"type": "string"},
                        "occasion_fit": {"type": "string"},
                        "title": {"type": "string"},
                        "visibility_pct": {"type": "number"},
                        "bbox_top_pct": {"type": "number"},
                        "bbox_left_pct": {"type": "number"},
                        "bbox_height_pct": {"type": "number"},
                        "bbox_width_pct": {"type": "number"},
                    },
                },
            },
        },
    },
}


def _load_prompt() -> str:
    text = _PROMPT_PATH.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Outfit decomposition prompt is empty: {_PROMPT_PATH}")
    return text


_PAD_PCT = 10  # small padding around the detected garment


def _crop_garment(source_path: str, bbox: Dict[str, float]) -> bytes:
    """Crop tightly to the garment bbox with small padding. Natural aspect ratio.

    The UI handles display ratio via CSS object-fit. Forcing 2:3 at crop
    time always pulls in irrelevant content because worn garments are
    wider than they are tall.
    """
    img = Image.open(source_path)
    img_w, img_h = img.size

    g_top = bbox["bbox_top_pct"] / 100.0 * img_h
    g_left = bbox["bbox_left_pct"] / 100.0 * img_w
    g_h = bbox["bbox_height_pct"] / 100.0 * img_h
    g_w = bbox["bbox_width_pct"] / 100.0 * img_w
    pad_v = g_h * _PAD_PCT / 100.0
    pad_h = g_w * _PAD_PCT / 100.0

    top = max(0, int(g_top - pad_v))
    left = max(0, int(g_left - pad_h))
    bottom = min(img_h, int(g_top + g_h + pad_v))
    right = min(img_w, int(g_left + g_w + pad_h))

    cropped = img.crop((left, top, right, bottom))
    if cropped.mode in ("RGBA", "P"):
        cropped = cropped.convert("RGB")
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def decompose_outfit_image(
    image_ref: str,
    *,
    user_hints: str = "",
    model: str = "gpt-5-mini",
) -> List[Dict[str, Any]]:
    """Identify individual garments in an outfit photo, crop each, return garments with image bytes."""
    client = OpenAI(api_key=get_api_key())
    image_url = _image_to_input_url(image_ref)
    system_prompt = _load_prompt()

    user_text = "Identify every distinct garment in this outfit photo and return structured JSON."
    if user_hints:
        user_text += f"\nContext from user: {user_hints}"

    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_text},
                    {"type": "input_image", "image_url": image_url},
                ],
            },
        ],
        text={"format": _GARMENT_SCHEMA},
    )
    parsed = _extract_response_json(response)
    raw_garments = list(parsed.get("garments") or [])

    _MIN_VISIBILITY = 85  # only keep garments that are nearly fully visible

    garments: List[Dict[str, Any]] = []
    for g in raw_garments:
        cat = str(g.get("garment_category") or "").strip().lower()
        if cat not in _ALLOWED_CATEGORIES:
            continue
        visibility = float(g.get("visibility_pct") or 0)
        if visibility < _MIN_VISIBILITY:
            _log.info("Skipping %s (visibility %.0f%% < %d%%)", g.get("title"), visibility, _MIN_VISIBILITY)
            continue
        # Crop garment region using AI-detected bounding box
        try:
            cropped_bytes = _crop_garment(image_ref, g)
            cropped_b64 = base64.b64encode(cropped_bytes).decode("ascii")
            g["image_data"] = f"data:image/jpeg;base64,{cropped_b64}"
        except Exception:
            _log.warning("Failed to crop garment %s", g.get("title"), exc_info=True)
            g["image_data"] = ""
        garments.append(g)

    _log.info("Decomposed outfit into %d garments from %s", len(garments), image_ref)
    return garments
