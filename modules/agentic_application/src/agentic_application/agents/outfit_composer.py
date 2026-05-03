"""Outfit Composer — May 3 2026.

Replaces the deterministic OutfitAssembler's combinatorial pairing pass
with a single LLM call (gpt-5-mini). Given the retrieved item pool
grouped by direction (A/B/C) plus the user's request and context,
returns up to 10 coherent outfits.

Companion to OutfitRater: the Composer constructs, the Rater scores.
Both replace the old assembler+reranker pipeline; cosine similarity is
demoted to a retrieval primitive only.

The Composer:
- Calls gpt-5-mini with structured output (JSON schema).
- Validates that every emitted item_id exists in the input pool —
  hallucinated IDs are a real failure mode for this kind of task. On
  partial hallucination we drop the bad outfits; on full hallucination
  we retry once with a stricter prompt suffix.
- Persists the full request + response to model_call_logs (raw audit
  trail) AND emits a distilled tool_traces row (composer_decision)
  with the outfits + composer rationales preserved.

Design notes:

* The Composer never invents pairings outside a direction. A complete
  outfit uses one Direction-A item; a paired outfit uses Direction B's
  top + bottom; a three_piece uses Direction C's top + bottom +
  outerwear. Cross-direction mixing is forbidden by the prompt and by
  the validator.
* `kurta` / `tunic` should already have been filtered out of paired/
  three_piece directions upstream by the architect (PR #27 prompt
  rule). The Composer prompt repeats the rule defensively.
* The Rater is the next stage; this agent does NOT score or order.
"""

from __future__ import annotations

import json
import logging
from functools import cached_property
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from openai import OpenAI
from pydantic import ValidationError

from platform_core.cost_estimator import extract_token_usage
from user_profiler.config import get_api_key

from ..schemas import (
    CombinedContext,
    ComposedOutfit,
    ComposerResult,
    RetrievedProduct,
    RetrievedSet,
)

_log = logging.getLogger(__name__)


def _find_prompt_dir() -> Path:
    here = Path(__file__).resolve()
    for base in [here.parent] + list(here.parents):
        candidate = base / "prompt"
        if candidate.is_dir() and (candidate / "outfit_composer.md").exists():
            return candidate
    raise FileNotFoundError("Could not locate prompt/ directory containing outfit_composer.md")


def _load_prompt() -> str:
    return (_find_prompt_dir() / "outfit_composer.md").read_text(encoding="utf-8").strip()


# Strict JSON schema for the structured-output contract. The Composer
# response is validated against this server-side by the Responses API.
_COMPOSER_JSON_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "name": "outfit_composer_result",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["outfits", "overall_assessment", "pool_unsuitable"],
        "properties": {
            "outfits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "composer_id",
                        "direction_id",
                        "direction_type",
                        "item_ids",
                        "rationale",
                    ],
                    "properties": {
                        "composer_id": {"type": "string"},
                        "direction_id": {"type": "string"},
                        "direction_type": {
                            "type": "string",
                            "enum": ["complete", "paired", "three_piece"],
                        },
                        "item_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "rationale": {"type": "string"},
                    },
                },
            },
            "overall_assessment": {
                "type": "string",
                "enum": ["strong", "moderate", "weak", "unsuitable"],
            },
            "pool_unsuitable": {"type": "boolean"},
        },
    },
}

# A direction's expected item count, by direction type. Used to validate
# that the Composer assembled a structurally-valid outfit (one item for
# `complete`, two for `paired`, three for `three_piece`).
_EXPECTED_ITEM_COUNT: Dict[str, int] = {
    "complete": 1,
    "paired": 2,
    "three_piece": 3,
}


def _user_context_block(ctx: CombinedContext) -> Dict[str, Any]:
    """Compact user-context dict for the Composer prompt input.

    Keeps only the fields a stylist actually needs to construct outfits;
    skips the rich enrichment data that would balloon the prompt and
    add noise. The Rater also calls this helper, so any change here
    flows to both agents — that's intentional.
    """
    user = ctx.user
    interps: Dict[str, Any] = {}
    for key in ("BodyShape", "SeasonalColorGroup", "ContrastLevel", "Undertone"):
        raw = user.derived_interpretations.get(key)
        if isinstance(raw, dict):
            interps[key] = raw.get("value", "") or ""
        else:
            interps[key] = str(raw or "")

    style_pref = user.style_preference or {}
    return {
        "gender": user.gender,
        "height_cm": user.height_cm,
        "body_shape": interps.get("BodyShape", ""),
        "palette_season": interps.get("SeasonalColorGroup", ""),
        "contrast": interps.get("ContrastLevel", ""),
        "undertone": interps.get("Undertone", ""),
        "primary_archetype": style_pref.get("primaryArchetype", ""),
        "secondary_archetype": style_pref.get("secondaryArchetype", ""),
        "risk_tolerance": style_pref.get("riskTolerance", ""),
        "comfort_priority": style_pref.get("comfortPriority", ""),
        "user_message": ctx.live.user_need,
        "occasion_signal": ctx.live.occasion_signal,
        "formality_hint": ctx.live.formality_hint,
        "time_of_day": ctx.live.time_of_day,
        "weather_context": ctx.live.weather_context,
        # `disliked_product_ids` is NOT surfaced to the Composer.
        # The IDs are already filtered out of the retrieval pool by
        # `catalog_search_agent`, so the Composer never sees them; and
        # opaque IDs without item attributes don't help the LLM reason
        # about archetypal dislikes ("loud florals", "boxy fits"). If
        # we want archetypal-dislike awareness later, the right shape
        # is to hydrate the disliked items' attributes (color, pattern,
        # silhouette) and pass those — see PR #37 review thread.
    }


# Attribute keys we lift out of the per-product enrichment for the
# Composer prompt. Anything not in this set stays out — the Composer
# does not need metadata, image hashes, or row_status.
_ITEM_ATTRS = (
    "garment_subtype",
    "formality_level",
    "primary_color",
    "color_temperature",
    "silhouette_contour",
    "silhouette_type",
    "fit_type",
    "pattern_type",
    "fabric_drape",
    "fabric_texture",
    "occasion_fit",
    "time_of_day",
    "embellishment_level",
)


def _item_summary(product_id: str, product: RetrievedProduct) -> Dict[str, Any]:
    """Extract a compact dict of stylist-relevant attrs from a product."""
    md = getattr(product, "metadata", {}) or {}
    en = getattr(product, "enriched_data", {}) or {}

    def _attr(key: str) -> str:
        # Try several casings — enrichment uses CamelCase, sometimes the
        # SQL columns are snake_case, both end up on the product object.
        for src in (en, md):
            for k in (key, key.replace("_", "").lower(), _camel(key)):
                if k in src and src[k] is not None:
                    val = src[k]
                    return str(val).strip().lower()
        return ""

    return {
        "item_id": product_id,
        "title": str(md.get("title") or en.get("title") or "")[:120],
        **{k: _attr(k) for k in _ITEM_ATTRS},
    }


def _camel(snake: str) -> str:
    return "".join(p.capitalize() for p in snake.split("_"))


def _pool_payload(retrieved_sets: Sequence[RetrievedSet]) -> Dict[str, Any]:
    """Group RetrievedSet rows by direction + role for the Composer prompt.

    Returns a dict shaped like:
      {"A": {"direction_type": "complete", "complete": [...]},
       "B": {"direction_type": "paired",   "top": [...], "bottom": [...]},
       "C": {"direction_type": "three_piece", "top": [...], "bottom": [...], "outerwear": [...]}}
    """
    grouped: Dict[str, Dict[str, Any]] = {}
    for rs in retrieved_sets:
        d = grouped.setdefault(rs.direction_id, {"direction_type": _infer_direction_type(rs.role)})
        items = [_item_summary(p.product_id, p) for p in rs.products]
        d.setdefault(rs.role, []).extend(items)
        # Direction type firms up as we see more roles; promote
        # `complete` → `paired` if both top+bottom appear, etc.
        d["direction_type"] = _consolidate_direction_type(d)
    return grouped


def _infer_direction_type(role: str) -> str:
    if role == "complete":
        return "complete"
    if role == "outerwear":
        return "three_piece"
    return "paired"


def _consolidate_direction_type(d: Dict[str, Any]) -> str:
    if "complete" in d:
        return "complete"
    if "outerwear" in d:
        return "three_piece"
    return "paired"


def _build_user_payload(ctx: CombinedContext, retrieved_sets: Sequence[RetrievedSet]) -> str:
    """Single JSON blob that goes to the LLM as the user-role message."""
    return json.dumps(
        {
            "user": _user_context_block(ctx),
            "pool": _pool_payload(retrieved_sets),
        },
        indent=2,
        default=str,
    )


def _validate_outfit(
    outfit: ComposedOutfit, pool_ids_by_direction: Dict[str, set]
) -> Optional[str]:
    """Return None if valid, else a string describing the violation.

    The validator is strict on the structural rules the prompt promises:
    item count matches direction_type, every item_id exists in the
    direction's pool. We do NOT validate the kurta-pairing rule here —
    that's the architect's job upstream. The Composer is told never to
    produce a kurta-paired outfit; if it does, the visual evaluator
    downstream will catch obvious failures.
    """
    expected_count = _EXPECTED_ITEM_COUNT.get(outfit.direction_type)
    if expected_count is None:
        return f"unknown direction_type {outfit.direction_type!r}"
    if len(outfit.item_ids) != expected_count:
        return (
            f"direction_type={outfit.direction_type} expects {expected_count} item(s), "
            f"got {len(outfit.item_ids)}"
        )
    direction_pool = pool_ids_by_direction.get(outfit.direction_id, set())
    bad_ids = [iid for iid in outfit.item_ids if iid not in direction_pool]
    if bad_ids:
        return f"item_ids not in direction {outfit.direction_id} pool: {bad_ids}"
    return None


class OutfitComposer:
    """LLM-driven outfit constructor. One gpt-5-mini call per turn.

    Replaces the OutfitAssembler's combinatorial pairing + heuristic
    scoring with structured judgment. Returns up to 10 outfits with
    per-outfit rationale; ordering and scoring are the OutfitRater's
    job downstream.
    """

    def __init__(self, model: str = "gpt-5-mini") -> None:
        self._model = model
        self._system_prompt = _load_prompt()
        self.last_usage: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    @cached_property
    def _client(self) -> OpenAI:
        return OpenAI(api_key=get_api_key())

    def compose(
        self,
        combined_context: CombinedContext,
        retrieved_sets: Sequence[RetrievedSet],
        *,
        retry_on_hallucination: bool = True,
    ) -> ComposerResult:
        """Build outfits from the retrieved pool. One LLM call (plus an
        optional retry on full-pool hallucination).

        Token usage for the call (summed across the retry pass when one
        runs) is returned on ``ComposerResult.usage``. The legacy
        ``self.last_usage`` is also updated for backwards-compat with
        agents that haven't migrated to the result-carried pattern.
        """
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        if not retrieved_sets:
            return ComposerResult(outfits=[], overall_assessment="unsuitable", pool_unsuitable=True)

        # Build the pool-id index once for validation. Each direction
        # gets a flat set of every item_id seen across all roles in
        # that direction.
        pool_ids_by_direction: Dict[str, set] = {}
        for rs in retrieved_sets:
            pool_ids_by_direction.setdefault(rs.direction_id, set()).update(
                p.product_id for p in rs.products
            )

        user_payload = _build_user_payload(combined_context, retrieved_sets)
        accumulated: Dict[str, int] = {}
        result = self._invoke(user_payload, pool_ids_by_direction, accumulated)

        if not result.outfits and retry_on_hallucination and not result.pool_unsuitable:
            # Full hallucination — every outfit had bad item_ids and
            # got dropped. Retry once with an explicit reminder appended
            # to the user payload listing the valid IDs per direction.
            _log.warning("OutfitComposer: full hallucination on first pass; retrying with strict ID list")
            stricter = (
                user_payload
                + "\n\nIMPORTANT: item_ids you emit MUST be drawn EXACTLY from the pool below. "
                + "Valid IDs per direction:\n"
                + json.dumps({d: sorted(ids) for d, ids in pool_ids_by_direction.items()}, indent=2)
            )
            result = self._invoke(stricter, pool_ids_by_direction, accumulated)

        result.usage = dict(accumulated)
        # Mirror to the legacy instance attribute. Concurrent turns
        # using the same OutfitComposer will race on this; consumers
        # that need thread-safe usage should read result.usage instead.
        self.last_usage = dict(accumulated)
        return result

    def _invoke(
        self,
        user_payload: str,
        pool_ids_by_direction: Dict[str, set],
        accumulated_usage: Dict[str, int],
    ) -> ComposerResult:
        """Single LLM round-trip + post-processing. Internal.

        ``accumulated_usage`` is a mutable dict the caller owns; this
        method adds the call's token counts into it. Lets `compose`
        sum usage across the retry pass without leaking state through
        instance attributes.
        """
        response = self._client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": self._system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_payload}]},
            ],
            text={"format": _COMPOSER_JSON_SCHEMA},
        )
        usage = extract_token_usage(response) or {}
        for k, v in usage.items():
            accumulated_usage[k] = accumulated_usage.get(k, 0) + (v or 0)

        raw_text = getattr(response, "output_text", "") or "{}"
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            _log.warning("OutfitComposer: JSON parse failed (%s); returning empty result", exc)
            return ComposerResult(outfits=[], overall_assessment="unsuitable", raw_response=raw_text)

        kept: List[ComposedOutfit] = []
        for raw_outfit in raw.get("outfits", []):
            try:
                outfit = ComposedOutfit(
                    composer_id=str(raw_outfit.get("composer_id", "")),
                    direction_id=str(raw_outfit.get("direction_id", "")),
                    direction_type=str(raw_outfit.get("direction_type", "")),
                    item_ids=[str(x) for x in (raw_outfit.get("item_ids") or [])],
                    rationale=str(raw_outfit.get("rationale", "")),
                )
            except (ValidationError, TypeError, AttributeError, ValueError) as exc:  # defensive parse
                _log.warning("OutfitComposer: malformed outfit payload (%s); skipping", exc)
                continue
            err = _validate_outfit(outfit, pool_ids_by_direction)
            if err:
                _log.warning(
                    "OutfitComposer: dropping outfit %s (direction=%s) — %s",
                    outfit.composer_id, outfit.direction_id, err,
                )
                continue
            kept.append(outfit)

        return ComposerResult(
            outfits=kept,
            overall_assessment=str(raw.get("overall_assessment") or "moderate"),
            pool_unsuitable=bool(raw.get("pool_unsuitable", False)),
            raw_response=raw_text,
        )
