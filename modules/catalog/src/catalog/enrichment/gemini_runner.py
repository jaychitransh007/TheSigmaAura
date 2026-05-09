"""Gemini-2.5-Flash catalog enrichment runner.

Replaces the OpenAI batch API path with concurrent sync calls. Used by
``ops/scripts/run_gemini_enrichment.py`` for the smoke-test workflow
on 5-10 catalog rows.

Architecture today is **single-pass**: one Gemini call per row,
emitting the full attribute set + confidences. The 3-pass staged
extraction architecture (Pass 1 structural, Pass 2 observable, Pass 3
conditional advanced) outlined in the migration spec is deferred to
a follow-up — single-pass is enough to validate the schema + Gemini
SDK + response-parsing pipeline end-to-end on a small sample.

Other follow-ups deferred:
- Image-hash + title-hash dedup before invoking the model.
- Hybrid confidence (model-prompted + heuristic overlay).
- Resumable checkpointing for long full-catalog runs.
- Applicability separation (``{value, confidence, applicable}``).

Out of scope: writing back to the catalog_enriched table. The runner
emits parsed payloads as JSONL; the caller decides what to do with
them. For full re-enrichment, a separate writer is needed (or extend
the existing ``merge_writer.py`` pattern).
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from google import genai
from google.genai import types

from .config import PipelineConfig, get_gemini_api_key
from .config_registry import load_garment_attributes
from .gemini_schema_builder import build_gemini_response_schema


_log = logging.getLogger(__name__)


# Reuse the existing system prompt (already updated for Path B-rationalised
# canonical schema in PR #239). The 3-pass split into separate prompts
# is a follow-up — for the smoke test we send the full prompt as a
# system instruction and the full schema as the response schema.
_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "system_prompt.txt"
)


def _load_system_prompt() -> str:
    with _PROMPT_PATH.open("r", encoding="utf-8") as f:
        prompt = f.read().strip()
    if not prompt:
        raise ValueError(f"System prompt file is empty: {_PROMPT_PATH}")
    return prompt


def _normalize_image_url(url: str) -> str:
    """Force ``width=768`` query param so the vision model gets a
    consistent resolution — same approach as ``batch_builder.py``.
    """
    if not url:
        return url
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["width"] = "768"
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def _download_image(url: str, timeout: int) -> tuple[bytes, str]:
    req = Request(
        url,
        headers={"User-Agent": "Aura/1.0 catalog-enrichment"},
    )
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        mime = resp.headers.get("Content-Type", "image/jpeg")
    return data, mime


class GeminiEnrichmentRunner:
    """Concurrent Gemini-2.5-Flash runner."""

    def __init__(
        self,
        api_key: str | None = None,
        config: PipelineConfig | None = None,
    ) -> None:
        self._api_key = api_key or get_gemini_api_key()
        self._config = config or PipelineConfig()
        self._client = genai.Client(api_key=self._api_key)
        enums, texts = load_garment_attributes()
        self._response_schema = build_gemini_response_schema(enums, texts)
        self._system_prompt = _load_system_prompt()

    def enrich_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Enrich a single catalog row. Always returns a dict with at
        least ``custom_id``, ``row_status`` (``ok`` / ``error``) and
        ``error_reason`` keys.
        """
        custom_id = str(
            row.get("source_row_number")
            or row.get("product_id")
            or row.get("id")
            or "unknown"
        )
        try:
            return self._enrich_one(custom_id, row)
        except Exception as exc:  # noqa: BLE001 — never let one row crash the runner
            _log.warning(
                "Gemini enrichment failed for %s: %s", custom_id, exc, exc_info=True,
            )
            return {
                "custom_id": custom_id,
                "row_status": "error",
                "error_reason": f"{type(exc).__name__}: {exc}",
            }

    def _enrich_one(self, custom_id: str, row: dict[str, Any]) -> dict[str, Any]:
        text_blob = (
            f"Description: {row.get('description', '') or ''}\n"
            f"Store: {row.get('store', '') or ''}\n"
            f"Product URL: {row.get('url', '') or ''}\n"
            "You must use both images together when inferring every attribute."
        )

        image_0 = _normalize_image_url(str(row.get("images__0__src", "") or "").strip())
        image_1 = _normalize_image_url(str(row.get("images__1__src", "") or "").strip())

        contents: list[Any] = [text_blob]
        downloaded = 0
        for label, url in (("Image 1:", image_0), ("Image 2:", image_1)):
            if not url:
                continue
            try:
                img_bytes, img_mime = _download_image(
                    url, timeout=self._config.image_download_timeout_seconds,
                )
            except (URLError, OSError, TimeoutError) as exc:
                _log.warning(
                    "Image download failed for %s (%s): %s", custom_id, url, exc,
                )
                continue
            contents.append(label)
            contents.append(
                types.Part.from_bytes(data=img_bytes, mime_type=img_mime)
            )
            downloaded += 1

        if downloaded == 0:
            return {
                "custom_id": custom_id,
                "row_status": "error",
                "error_reason": "No accessible product images; cannot enrich.",
            }

        response = self._client.models.generate_content(
            model=self._config.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=self._system_prompt,
                response_mime_type="application/json",
                response_schema=self._response_schema,
            ),
        )

        return self._parse_response(custom_id, response)

    def _parse_response(self, custom_id: str, response: Any) -> dict[str, Any]:
        try:
            raw_text = response.text
        except AttributeError:
            return {
                "custom_id": custom_id,
                "row_status": "error",
                "error_reason": "Gemini response missing .text attribute",
            }
        if not raw_text:
            return {
                "custom_id": custom_id,
                "row_status": "error",
                "error_reason": "Gemini response empty",
            }
        try:
            payload: dict[str, Any] = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return {
                "custom_id": custom_id,
                "row_status": "error",
                "error_reason": f"Gemini response not valid JSON: {exc}",
                "raw_response_excerpt": raw_text[:500],
            }
        payload["custom_id"] = custom_id
        payload["row_status"] = "ok"
        payload["error_reason"] = ""
        return payload

    def enrich_rows(
        self,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Concurrent enrichment. Returns results in input order."""
        if not rows:
            return []
        max_workers = max(1, self._config.max_concurrent_requests)
        results: dict[int, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self.enrich_row, row): idx
                for idx, row in enumerate(rows)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                results[idx] = future.result()
        return [results[idx] for idx in range(len(rows))]


__all__ = [
    "GeminiEnrichmentRunner",
]
