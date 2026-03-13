from __future__ import annotations

import base64
import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.request import urlopen, Request

from google import genai
from google.genai import types

_log = logging.getLogger(__name__)

MAX_IMAGE_DIMENSION = 1024

TRYON_PROMPT = (
    "Virtual try-on: replace only the clothing on the person with the target garment.\n\n"
    "The person in the image must remain exactly the same. "
    "Preserve the original identity, pose, body shape, body proportions, and body silhouette.\n\n"
    "The body geometry is fixed and must not change.\n\n"
    "Preserve exactly:\n"
    "- waist width\n"
    "- torso width\n"
    "- torso length\n"
    "- hip width\n"
    "- shoulder width\n"
    "- arm thickness\n"
    "- leg thickness\n"
    "- leg length\n"
    "- overall body proportions\n\n"
    "The outer contour of the body must remain identical to the input image.\n\n"
    "Do not modify the body outline, including the waist, hips, torso, shoulders, arms, or legs.\n\n"
    "The garment must adapt to the existing body shape. The body must NOT change to fit the garment.\n\n"
    "Important rule: treat the person's body as immutable geometry.\n\n"
    "Only replace the clothing with the target garment while keeping the same body silhouette.\n\n"
    "Preserve:\n"
    "- original pose and posture\n"
    "- camera perspective\n"
    "- background structure\n"
    "- scene lighting\n\n"
    "The output must look like the same person wearing the new garment while maintaining "
    "the exact same body shape and silhouette as the original image. "
    "The garment must drape naturally over the body and must not pull inward at the waist or torso. "
    "Maintain the same waist-to-hip ratio and torso proportions as in the original image."
)


class TryonService:
    """Virtual try-on using Gemini image generation."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
        self._client: Any = None
        self._model = "gemini-3.1-flash-image-preview"

    def _get_client(self) -> Any:
        if self._client is None:
            key = self._api_key or os.getenv("GEMINI_API_KEY", "").strip()
            if not key:
                raise RuntimeError("GEMINI_API_KEY is required for virtual try-on.")
            self._client = genai.Client(api_key=key)
        return self._client

    def generate_tryon(
        self,
        person_image_path: str,
        product_image_url: str,
    ) -> Dict[str, Any]:
        person_bytes, person_mime = self._load_local_image(person_image_path)
        product_bytes, product_mime = self._download_image(product_image_url)

        # Resize to constrain dimensions — improves model quality and speed
        person_bytes, person_mime = self._maybe_resize(person_bytes, person_mime)
        product_bytes, product_mime = self._maybe_resize(product_bytes, product_mime)

        client = self._get_client()
        response = client.models.generate_content(
            model=self._model,
            contents=[
                TRYON_PROMPT,
                "This is the PERSON photo. Put the target garment on THIS person:",
                types.Part.from_bytes(data=person_bytes, mime_type=person_mime),
                "This is the TARGET GARMENT to dress the person in:",
                types.Part.from_bytes(data=product_bytes, mime_type=product_mime),
            ],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                image_data = part.inline_data.data
                image_mime = part.inline_data.mime_type or "image/png"
                b64 = base64.b64encode(image_data).decode("ascii")
                return {
                    "success": True,
                    "image_base64": b64,
                    "mime_type": image_mime,
                    "data_url": f"data:{image_mime};base64,{b64}",
                }

        text_parts = [
            part.text for part in response.candidates[0].content.parts
            if hasattr(part, "text") and part.text
        ]
        return {
            "success": False,
            "error": text_parts[0] if text_parts else "No image generated.",
        }

    @staticmethod
    def _maybe_resize(data: bytes, mime: str) -> tuple[bytes, str]:
        """Resize image so longest side is at most MAX_IMAGE_DIMENSION pixels."""
        try:
            from PIL import Image

            img = Image.open(BytesIO(data))
            w, h = img.size
            if max(w, h) <= MAX_IMAGE_DIMENSION:
                return data, mime
            ratio = MAX_IMAGE_DIMENSION / max(w, h)
            new_size = (int(w * ratio), int(h * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            buf = BytesIO()
            fmt = "PNG" if mime == "image/png" else "JPEG"
            img.save(buf, format=fmt, quality=90)
            out_mime = "image/png" if fmt == "PNG" else "image/jpeg"
            return buf.getvalue(), out_mime
        except ImportError:
            _log.debug("Pillow not available, skipping resize")
            return data, mime

    @staticmethod
    def _load_local_image(path: str) -> tuple[bytes, str]:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Person image not found: {path}")
        suffix = p.suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
        mime = mime_map.get(suffix, "image/jpeg")
        return p.read_bytes(), mime

    @staticmethod
    def _download_image(url: str) -> tuple[bytes, str]:
        req = Request(url, headers={"User-Agent": "AuraTryon/1.0"})
        with urlopen(req, timeout=15) as resp:
            data = resp.read()
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            mime = content_type.split(";")[0].strip()
        return data, mime
