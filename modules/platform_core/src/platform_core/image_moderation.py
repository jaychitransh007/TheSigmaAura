from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Dict, List

from openai import OpenAI
from user_profiler.config import get_api_key


_BLOCKLIST_TERMS = {
    "nude", "naked", "topless", "boobs", "breasts", "nipples", "nsfw",
    "explicit", "sex", "porn", "vagina", "penis", "genitals", "butt_naked",
}
_MINOR_BLOCKLIST_TERMS = {
    "child", "kid", "minor", "underage", "toddler", "baby", "teen", "schoolgirl", "schoolboy",
}
_UNSAFE_BLOCKLIST_TERMS = {
    "gore", "bloody", "blood", "selfharm", "self_harm", "suicide", "violent", "injury", "corpse",
}

_IMAGE_MODERATION_SCHEMA = {
    "type": "json_schema",
    "name": "image_upload_moderation",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["block", "reason_code", "confidence", "rationale"],
        "properties": {
            "block": {"type": "boolean"},
            "reason_code": {"type": "string", "enum": ["safe", "explicit_nudity", "unsafe_minor", "unsafe_image"]},
            "confidence": {"type": "number"},
            "rationale": {"type": "string"},
        },
    },
}


@dataclass(frozen=True)
class ImageModerationResult:
    allowed: bool
    reason_code: str = "safe"
    confidence: float = 0.0
    rationale: str = ""


class ImageModerationService:
    def __init__(self, *, model: str = "gpt-5.4") -> None:
        self._model = model

    def moderate_bytes(
        self,
        *,
        file_data: bytes,
        filename: str,
        content_type: str,
        purpose: str,
    ) -> ImageModerationResult:
        heuristic = self._heuristic_scan([filename, purpose])
        if heuristic is not None:
            return heuristic

        api_key = self._safe_api_key()
        if not api_key:
            return ImageModerationResult(allowed=True, rationale="No moderation API key configured.")

        image_url = self._data_url(file_data=file_data, content_type=content_type or "image/jpeg")
        return self._moderate_image_url(image_url=image_url, purpose=purpose, api_key=api_key)

    def moderate_url(
        self,
        *,
        image_url: str,
        purpose: str,
    ) -> ImageModerationResult:
        heuristic = self._heuristic_scan([image_url, purpose])
        if heuristic is not None:
            return heuristic

        api_key = self._safe_api_key()
        if not api_key:
            return ImageModerationResult(allowed=True, rationale="No moderation API key configured.")
        return self._moderate_image_url(image_url=image_url, purpose=purpose, api_key=api_key)

    def _moderate_image_url(
        self,
        *,
        image_url: str,
        purpose: str,
        api_key: str,
    ) -> ImageModerationResult:
        try:
            client = OpenAI(api_key=api_key)
            response = client.responses.create(
                model=self._model,
                input=[
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "You are a safety classifier for a fashion assistant. "
                                    "Block only if the image contains explicit nudity, visible genitals, visible nipples, or explicit sexual exposure. "
                                    "Allow normal clothed fashion photos, outfit checks, and standard product images."
                                ),
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": f"Purpose: {purpose}"},
                            {"type": "input_image", "image_url": image_url},
                        ],
                    },
                ],
                reasoning={"effort": "low"},
                text={"format": _IMAGE_MODERATION_SCHEMA},
            )
            parsed = self._extract_response_json(response)
            blocked = bool(parsed.get("block"))
            reason = str(parsed.get("reason_code") or "safe")
            return ImageModerationResult(
                allowed=not blocked,
                reason_code=reason if blocked else "safe",
                confidence=float(parsed.get("confidence") or 0.0),
                rationale=str(parsed.get("rationale") or ""),
            )
        except Exception:
            return ImageModerationResult(allowed=True, rationale="Moderation provider unavailable.")

    def _heuristic_scan(self, values: List[str]) -> ImageModerationResult | None:
        corpus = " ".join(str(value or "").strip().lower() for value in values if str(value or "").strip())
        if any(term in corpus for term in _MINOR_BLOCKLIST_TERMS):
            return ImageModerationResult(
                allowed=False,
                reason_code="unsafe_minor",
                confidence=0.98,
                rationale="Blocked by minor-safety keyword heuristic.",
            )
        if any(term in corpus for term in _UNSAFE_BLOCKLIST_TERMS):
            return ImageModerationResult(
                allowed=False,
                reason_code="unsafe_image",
                confidence=0.98,
                rationale="Blocked by unsafe-image keyword heuristic.",
            )
        if any(term in corpus for term in _BLOCKLIST_TERMS):
            return ImageModerationResult(
                allowed=False,
                reason_code="explicit_nudity",
                confidence=0.98,
                rationale="Blocked by explicit-image keyword heuristic.",
            )
        return None

    @staticmethod
    def _safe_api_key() -> str:
        try:
            return str(get_api_key() or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _data_url(*, file_data: bytes, content_type: str) -> str:
        encoded = base64.b64encode(file_data).decode("utf-8")
        return f"data:{content_type};base64,{encoded}"

    @staticmethod
    def _extract_response_json(response: object) -> Dict[str, object]:
        output = getattr(response, "output", None) or []
        for item in output:
            for content in getattr(item, "content", None) or []:
                text = getattr(content, "text", None)
                if text:
                    import json

                    return dict(json.loads(text))
        raise ValueError("Moderation response did not include JSON output.")


def image_block_message(reason_code: str) -> str:
    reason = str(reason_code or "").strip()
    if reason == "unsafe_minor":
        return "Images of minors are not allowed."
    if reason == "unsafe_image":
        return "Unsafe or graphic images are not allowed."
    return "Explicit nude images are not allowed."
