"""Per-call cost estimator for the LLM and image-gen pipeline.

Item 4 of the Observability Hardening plan (May 1, 2026). Centralises
the pricing table so per-user / per-conversation cost rollups can run
off `model_call_logs.estimated_cost_usd` without each callsite knowing
about pricing.

Pricing units are USD per 1M tokens (text/embedding models) or USD
per image (Gemini image generation). Update this table when Anthropic
/ OpenAI / Google adjust their published rates — the assertion in the
test suite catches drift between this table and the actual invoice.

Unknown models return 0.0 so a future-model addition doesn't break
the pipeline; the operator dashboard surfaces "unknown model" as a
hint to update this table.
"""

from __future__ import annotations

from typing import Dict, Optional

# Public pricing as of May 1, 2026. Values are USD per 1M tokens.
#
# gpt-5.5 list price published by OpenAI on the developer pricing page
# (https://developers.openai.com/api/docs/pricing). The 2× input / 1.5×
# output multiplier for prompts >272K input tokens is NOT modelled here
# because Aura's typical request payloads are well under 30K — see the
# `model_call_logs.prompt_tokens` distribution. If that ever changes
# (long retrieval-augmented prompts in a capsule planner, say), revisit.
_TEXT_PRICING: Dict[str, Dict[str, float]] = {
    # OpenAI
    "gpt-5.5":                       {"input_per_1m": 5.00,  "output_per_1m": 30.00},
    "gpt-5.4":                       {"input_per_1m": 2.50,  "output_per_1m": 10.00},  # legacy — kept for historical model_call_logs
    "gpt-5-mini":                    {"input_per_1m": 0.15,  "output_per_1m": 0.60},
    "text-embedding-3-small":        {"input_per_1m": 0.02,  "output_per_1m": 0.0},
    # Anthropic — listed for completeness, not currently used by Aura
    "claude-opus-4-7":               {"input_per_1m": 15.00, "output_per_1m": 75.00},
    "claude-sonnet-4-6":             {"input_per_1m": 3.00,  "output_per_1m": 15.00},
}

_IMAGE_PRICING: Dict[str, float] = {
    # Google Gemini virtual try-on
    "gemini-3.1-flash-image-preview": 0.039,
}


def estimate_cost_usd(
    *,
    model: str,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    image_count: Optional[int] = None,
) -> float:
    """Return the estimated USD cost for a single model call.

    - Text models: ``prompt_tokens * input_per_1m + completion_tokens * output_per_1m``
      (both per-1M, hence the divide).
    - Image models: ``image_count * flat_per_image``.
    - Unknown models: 0.0.

    Returns 0.0 (not None) so downstream SUM aggregations work without
    null-handling.
    """
    if not model:
        return 0.0
    if model in _IMAGE_PRICING:
        return _IMAGE_PRICING[model] * (image_count or 0)
    pricing = _TEXT_PRICING.get(model)
    if not pricing:
        return 0.0
    p_in = (prompt_tokens or 0) * pricing["input_per_1m"] / 1_000_000.0
    p_out = (completion_tokens or 0) * pricing["output_per_1m"] / 1_000_000.0
    return round(p_in + p_out, 6)


def extract_token_usage(response_obj: object) -> Dict[str, int]:
    """Extract token counts from an OpenAI Responses-API response object.

    The OpenAI SDK exposes usage as ``response.usage.input_tokens`` /
    ``output_tokens`` / ``total_tokens``. Some legacy chat-completion
    callers expose ``prompt_tokens`` / ``completion_tokens`` instead —
    accept both shapes.

    Always returns a dict with the three keys present (zero when
    unavailable) so callers don't need to handle absence.
    """
    out = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    usage = getattr(response_obj, "usage", None)
    if usage is None and isinstance(response_obj, dict):
        usage = response_obj.get("usage")
    if usage is None:
        return out

    def _get(obj: object, *keys: str) -> int:
        for k in keys:
            if isinstance(obj, dict):
                v = obj.get(k)
            else:
                v = getattr(obj, k, None)
            if isinstance(v, (int, float)) and v >= 0:
                return int(v)
        return 0

    out["prompt_tokens"] = _get(usage, "prompt_tokens", "input_tokens")
    out["completion_tokens"] = _get(usage, "completion_tokens", "output_tokens")
    out["total_tokens"] = _get(usage, "total_tokens")
    if out["total_tokens"] == 0:
        out["total_tokens"] = out["prompt_tokens"] + out["completion_tokens"]
    return out
