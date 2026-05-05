"""Outfit Composer — May 3 2026.

Replaces the deterministic OutfitAssembler's combinatorial pairing pass
with a single LLM call. Given the retrieved item pool grouped by
direction (A/B/C) plus the user's request and context, returns up to
10 coherent outfits.

Model: ``gpt-5.4`` at ``reasoning_effort="low"`` (gpt-5-mid family,
same tier as the Architect). Promoted from gpt-5-mini in PR #81 after
T7 showed the Composer doing genuinely heavy reasoning — assembling
60-item pools across multiple compatibility axes (palette, formality,
fit, fabric, occasion) into coherent outfits is structured *judgment*,
not just structured assembly. gpt-5-mini was producing low-quality
pairings on the larger pools.

Companion to OutfitRater: the Composer constructs, the Rater scores.
Both replace the old assembler+reranker pipeline; cosine similarity is
demoted to a retrieval primitive only.

The Composer:
- Calls gpt-5.4 with structured output (JSON schema, dynamic enum on direction_id).
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
import time
from functools import cached_property
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from openai import OpenAI
from pydantic import ValidationError

from platform_core.cost_estimator import extract_token_usage
from platform_core.reasoning_effort import GPT5_MID_EFFORTS
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
def _build_composer_json_schema(direction_letters: Sequence[str]) -> Dict[str, Any]:
    """Build the per-turn structured-output schema with a closed enum on
    ``direction_id``.

    Why a per-turn schema (instead of a static one): structurally
    enforcing that ``direction_id`` is one of the architect's emitted
    letters (typically ``A``, ``B``, ``C``) prevents the failure mode
    where the LLM drops a product_id into the field. ``strict: True``
    + ``enum`` makes the API reject non-conforming output rather than
    relying on prompt discipline.

    Falls back to plain ``{"type": "string"}`` when ``direction_letters``
    is empty (defensive — shouldn't happen in practice because the
    Composer always sees at least one direction).
    """
    direction_id_schema: Dict[str, Any] = {"type": "string"}
    if direction_letters:
        direction_id_schema = {
            "type": "string",
            "enum": list(direction_letters),
        }
    return {
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
                            "name",
                        ],
                        "properties": {
                            "composer_id": {"type": "string"},
                            "direction_id": direction_id_schema,
                            "direction_type": {
                                "type": "string",
                                "enum": ["complete", "paired", "three_piece"],
                            },
                            "item_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "rationale": {"type": "string"},
                            # Length-bound at the schema level so the model
                            # can't blow past the UI title slot. The prompt
                            # asks for 2-5 words; 100 chars is a defensive
                            # ceiling on top of that.
                            "name": {
                                "type": "string",
                                "description": "Short stylist-flavored title for the outfit (2-5 words, e.g. 'Sharp Navy Boardroom').",
                                "maxLength": 100,
                            },
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


_BODY_RAW_KEYS = (
    "BodyShape",
    "VisualWeight",
    "VerticalProportion",
    "ArmVolume",
    "MidsectionState",
    "BustVolume",
    "TorsoToLegRatio",
)
_DERIVED_KEYS = (
    "BodyShape",
    "SeasonalColorGroup",
    "ContrastLevel",
    "Undertone",
    "FrameStructure",
    "WaistSizeBand",
)


def _user_context_block(ctx: CombinedContext) -> Dict[str, Any]:
    """Compact user-context dict for the Composer prompt input.

    Keeps only the fields a stylist actually needs to construct outfits;
    skips the rich enrichment data that would balloon the prompt and
    add noise. The Rater also calls this helper, so any change here
    flows to both agents — that's intentional.

    R1 (PR #64, May 5 2026): expanded the body block from
    {body_shape, height_cm} to the full anatomy snapshot the user has
    on file. The Rater's `body_harmony` dimension was effectively
    guessing from BodyShape alone; surfacing visual_weight / vertical_
    proportion / arm_volume / midsection / bust / torso-to-leg / frame
    structure / waist size band / waist_cm gives it the evidence it
    needs to actually reason about silhouette flattery. Empty values
    (user hasn't completed analysis or skipped a draping question)
    are kept as empty strings so the prompt structure stays stable.
    """
    user = ctx.user

    def _value_str(source: Optional[Dict[str, Any]], key: str) -> str:
        """Pull ``key`` from a possibly-None source dict, unwrapping
        ``{"value": ..., "confidence": ...}`` shape if present.
        Returns "" when the source or key is missing — keeps the
        prompt structure stable per the docstring contract.

        Today every key surfaced through this helper is a categorical
        string (BodyShape, FrameStructure, etc.) so 0 isn't a valid
        value, but check ``is not None`` rather than truthiness so a
        future numeric anatomy field (e.g. waist_to_hip_ratio = 0)
        stringifies as "0" instead of disappearing.
        """
        val = (source or {}).get(key)
        if isinstance(val, dict):
            inner = val.get("value")
            return str(inner) if inner is not None else ""
        return str(val) if val is not None else ""

    derived = {k: _value_str(user.derived_interpretations, k) for k in _DERIVED_KEYS}
    raw_body = {k: _value_str(user.analysis_attributes, k) for k in _BODY_RAW_KEYS}

    style_pref = user.style_preference or {}
    return {
        "gender": user.gender,
        # ── Body anatomy (used by Rater.body_harmony) ─────────────────
        "height_cm": user.height_cm,
        "waist_cm": user.waist_cm,
        "body_shape": derived.get("BodyShape", "") or raw_body.get("BodyShape", ""),
        "frame_structure": derived.get("FrameStructure", ""),
        "waist_size_band": derived.get("WaistSizeBand", ""),
        "visual_weight": raw_body.get("VisualWeight", ""),
        "vertical_proportion": raw_body.get("VerticalProportion", ""),
        "arm_volume": raw_body.get("ArmVolume", ""),
        "midsection_state": raw_body.get("MidsectionState", ""),
        "bust_volume": raw_body.get("BustVolume", ""),
        "torso_to_leg_ratio": raw_body.get("TorsoToLegRatio", ""),
        # ── Color (used by Rater.color_harmony) ───────────────────────
        "palette_season": derived.get("SeasonalColorGroup", ""),
        "contrast": derived.get("ContrastLevel", ""),
        "undertone": derived.get("Undertone", ""),
        # ── Style (informs Composer item selection) ───────────────────
        # The Rater no longer scores risk_tolerance as a continuous dim
        # (R6, May 5 2026 — archetype_match dropped). It still gates the
        # `unsuitable: true` veto for severe mismatches. Composer should
        # weight item picks against this signal.
        "risk_tolerance": style_pref.get("riskTolerance", "") or "balanced",
        # ── Per-turn signals (used by Rater.occasion_fit) ─────────────
        "user_message": ctx.live.user_need,
        "occasion_signal": ctx.live.occasion_signal,
        "formality_hint": ctx.live.formality_hint,
        "time_of_day": ctx.live.time_of_day,
        "weather_context": ctx.live.weather_context,
        "style_goal": getattr(ctx.live, "style_goal", "") or "",
        # `disliked_product_ids` is NOT surfaced to the Composer.
        # The IDs are already filtered out of the retrieval pool by
        # `catalog_search_agent`, so the Composer never sees them; and
        # opaque IDs without item attributes don't help the LLM reason
        # about archetypal dislikes ("loud florals", "boxy fits").
        # ── Archetypal preferences (R4, PR #67) ───────────────────────
        # Aggregated like/dislike axes from recent feedback_events,
        # joined to catalog_enriched. Each axis lists at most 3 values
        # with count >= 2. Empty dict on cold-start users. The Rater's
        # veto rule ("previously-disliked pattern/color") now has real
        # evidence to draw on; the Composer should also avoid heavily
        # disliked attributes when constructing outfits in the first
        # place.
        "archetypal_preferences": dict(getattr(ctx, "archetypal_preferences", {}) or {}),
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
    # Distinguish between "direction_id is wrong" and "item_ids are wrong"
    # so the retry classifier in compose() can pick the right corrective
    # suffix. With the dynamic-enum schema this branch should fire rarely;
    # left in as belt-and-suspenders for legacy / non-strict-schema flows.
    if outfit.direction_id not in pool_ids_by_direction:
        return (
            f"unknown direction_id {outfit.direction_id!r} — must be one of "
            f"{sorted(pool_ids_by_direction.keys())}"
        )
    direction_pool = pool_ids_by_direction.get(outfit.direction_id, set())
    bad_ids = [iid for iid in outfit.item_ids if iid not in direction_pool]
    if bad_ids:
        return f"item_ids not in direction {outfit.direction_id} pool: {bad_ids}"
    return None


class OutfitComposer:
    """LLM-driven outfit constructor. One gpt-5.4 call per turn (plus
    an optional retry on full-pool hallucination).

    Replaces the OutfitAssembler's combinatorial pairing + heuristic
    scoring with structured judgment. Returns up to 10 outfits with
    per-outfit rationale; ordering and scoring are the OutfitRater's
    job downstream.

    Promoted from gpt-5-mini → gpt-5.4 in PR #81. The Composer is
    doing genuine multi-axis judgment (palette × formality × fit ×
    fabric × occasion) over 60-item pools — gpt-5-mid is the right
    tier. ``reasoning_effort="low"`` keeps cost manageable (the
    structured-output schema does most of the chain-of-thought).

    Allowed-effort vocabulary lives in
    ``platform_core.reasoning_effort`` so it stays in sync with the
    Architect (also gpt-5-mid).
    """

    _ALLOWED_EFFORTS = GPT5_MID_EFFORTS

    def __init__(
        self,
        model: str = "gpt-5.4",
        reasoning_effort: str = "low",
    ) -> None:
        if reasoning_effort not in self._ALLOWED_EFFORTS:
            raise ValueError(
                f"OutfitComposer reasoning_effort must be one of "
                f"{sorted(self._ALLOWED_EFFORTS)}; got {reasoning_effort!r}"
            )
        self._model = model
        self._reasoning_effort = reasoning_effort
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
        on_attempt: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> ComposerResult:
        """Build outfits from the retrieved pool. One LLM call (plus an
        optional retry on full-pool hallucination).

        Token usage for the call (summed across the retry pass when one
        runs) is returned on ``ComposerResult.usage``. The legacy
        ``self.last_usage`` is also updated for backwards-compat with
        agents that haven't migrated to the result-carried pattern.

        ``on_attempt`` is an optional callback invoked once per LLM
        invocation with a per-attempt log dict. Lets the orchestrator
        emit one ``model_call_logs`` row per attempt instead of one
        row that sums the retry, which masks which attempt did what
        (PR #80, May 5 2026 RCA — T6 turn appeared to have a 24K-token
        prompt because it was actually two 12K calls summed).
        """
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        if not retrieved_sets:
            return ComposerResult(
                outfits=[],
                overall_assessment="unsuitable",
                pool_unsuitable=True,
                attempt_count=0,
            )

        # Build the pool-id index once for validation. Each direction
        # gets a flat set of every item_id seen across all roles in
        # that direction.
        pool_ids_by_direction: Dict[str, set] = {}
        for rs in retrieved_sets:
            pool_ids_by_direction.setdefault(rs.direction_id, set()).update(
                p.product_id for p in rs.products
            )

        # Build the per-turn JSON schema with a closed enum on direction_id.
        # The architect's emitted letters are the only valid values; this
        # makes the structured-output API reject bad direction_id at the
        # contract layer, not after-the-fact in the validator.
        direction_letters = sorted(pool_ids_by_direction.keys())
        schema = _build_composer_json_schema(direction_letters)

        user_payload = _build_user_payload(combined_context, retrieved_sets)
        accumulated: Dict[str, int] = {}

        attempt_no = 1
        result, drop_reasons = self._invoke(
            user_payload, pool_ids_by_direction, schema, accumulated,
            attempt_no=attempt_no, on_attempt=on_attempt,
        )

        if not result.outfits and retry_on_hallucination and not result.pool_unsuitable:
            # Full hallucination on the first pass — every outfit was
            # rejected by the validator. The retry suffix is tailored
            # to the failure mode: bad item_ids → enumerate the pool;
            # bad direction_ids → call out the field contract; both →
            # both. Crude classification; we don't need anything fancy.
            _log.warning(
                "OutfitComposer: full hallucination on first pass; retrying. drop_reasons=%s",
                drop_reasons[:5],
            )
            suffix_parts: List[str] = ["\n\nIMPORTANT — fix these issues from your previous response:"]
            had_item_id_issue = any("item_ids not in" in r for r in drop_reasons)
            had_direction_id_issue = any("unknown direction_id" in r or "no direction" in r for r in drop_reasons)
            if had_item_id_issue:
                suffix_parts.append(
                    "- item_ids MUST be drawn EXACTLY from the pool below. Valid IDs per direction:\n"
                    + json.dumps({d: sorted(ids) for d, ids in pool_ids_by_direction.items()}, indent=2)
                )
            if had_direction_id_issue:
                suffix_parts.append(
                    f"- direction_id MUST be one of: {direction_letters}. "
                    "It is the architect's direction LETTER, not a product_id. "
                    "Never copy a SKU, brand prefix, or item title into this field."
                )
            if not (had_item_id_issue or had_direction_id_issue):
                # Safety net: if the validator returned reasons we don't
                # specifically handle, surface them verbatim.
                suffix_parts.append("- Specific issues:\n" + "\n".join(f"  • {r}" for r in drop_reasons[:10]))
            stricter = user_payload + "".join(suffix_parts)
            attempt_no += 1
            result, _drop_reasons2 = self._invoke(
                stricter, pool_ids_by_direction, schema, accumulated,
                attempt_no=attempt_no, on_attempt=on_attempt,
            )

        result.usage = dict(accumulated)
        result.attempt_count = attempt_no
        # Mirror to the legacy instance attribute. Concurrent turns
        # using the same OutfitComposer will race on this; consumers
        # that need thread-safe usage should read result.usage instead.
        self.last_usage = dict(accumulated)
        return result

    def _invoke(
        self,
        user_payload: str,
        pool_ids_by_direction: Dict[str, set],
        schema: Dict[str, Any],
        accumulated_usage: Dict[str, int],
        *,
        attempt_no: int = 1,
        on_attempt: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> tuple["ComposerResult", List[str]]:
        """Single LLM round-trip + post-processing. Internal.

        Returns ``(result, drop_reasons)`` — the second element is a
        list of validator-rejection messages for outfits the LLM
        emitted but the validator dropped, used by ``compose`` to
        tailor the retry suffix.

        ``accumulated_usage`` is a mutable dict the caller owns; this
        method adds the call's token counts into it. Lets ``compose``
        sum usage across the retry pass without leaking state through
        instance attributes.
        """
        # reasoning_effort sourced from self._reasoning_effort
        # (gpt-5-mid family vocabulary: low | medium | high | xhigh).
        # Default "low" is sufficient at this prompt size; the
        # structured-output schema enforces most of the contract.
        # PR #95 (May 5 2026): time the API call so the per-attempt
        # `on_attempt` callback can persist latency_ms onto each
        # model_call_logs row. Before this, model_call_logs.latency_ms
        # for the composer was always 0 — turn_traces had the real ~14s
        # but any panel computing composer p50/p95 from model_call_logs
        # was blind. Discovered during the T9–T12 review.
        _t_attempt = time.monotonic()
        response = self._client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": self._system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_payload}]},
            ],
            reasoning={"effort": self._reasoning_effort},
            text={"format": schema},
        )
        attempt_latency_ms = int((time.monotonic() - _t_attempt) * 1000)
        usage = extract_token_usage(response) or {}
        for k, v in usage.items():
            accumulated_usage[k] = accumulated_usage.get(k, 0) + (v or 0)

        raw_text = getattr(response, "output_text", "") or "{}"
        parse_failed = False
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            parse_failed = True
            _log.warning("OutfitComposer: JSON parse failed (%s); returning empty result", exc)
            raw = {}

        if parse_failed:
            result = ComposerResult(outfits=[], overall_assessment="unsuitable", raw_response=raw_text)
            drop_reasons: List[str] = ["json_parse_failed"]
            if on_attempt:
                on_attempt({
                    "attempt_no": attempt_no,
                    "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                    "completion_tokens": int(usage.get("completion_tokens") or 0),
                    "total_tokens": int(usage.get("total_tokens") or 0),
                    "latency_ms": attempt_latency_ms,
                    "raw_text": raw_text[:8000],
                    "outfit_count_emitted": 0,
                    "outfit_count_kept": 0,
                    "drop_reasons": drop_reasons,
                })
            return result, drop_reasons

        kept: List[ComposedOutfit] = []
        drop_reasons = []
        for raw_outfit in raw.get("outfits", []):
            try:
                outfit = ComposedOutfit(
                    composer_id=str(raw_outfit.get("composer_id", "")),
                    direction_id=str(raw_outfit.get("direction_id", "")),
                    direction_type=str(raw_outfit.get("direction_type", "")),
                    item_ids=[str(x) for x in (raw_outfit.get("item_ids") or [])],
                    rationale=str(raw_outfit.get("rationale", "")),
                    # `or ""` (not the .get default) so an explicit JSON
                    # null also folds to ""; otherwise str(None) → "None"
                    # would ship as the card title. [:100] mirrors the
                    # schema cap above as a defensive belt.
                    name=str(raw_outfit.get("name") or "").strip()[:100],
                )
            except (ValidationError, TypeError, AttributeError, ValueError) as exc:  # defensive parse
                _log.warning("OutfitComposer: malformed outfit payload (%s); skipping", exc)
                drop_reasons.append(f"malformed_payload: {exc}")
                continue
            err = _validate_outfit(outfit, pool_ids_by_direction)
            if err:
                _log.warning(
                    "OutfitComposer: dropping outfit %s (direction=%s) — %s",
                    outfit.composer_id, outfit.direction_id, err,
                )
                drop_reasons.append(err)
                continue
            kept.append(outfit)

        result = ComposerResult(
            outfits=kept,
            overall_assessment=str(raw.get("overall_assessment") or "moderate"),
            pool_unsuitable=bool(raw.get("pool_unsuitable", False)),
            raw_response=raw_text,
        )

        if on_attempt:
            on_attempt({
                "attempt_no": attempt_no,
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
                "latency_ms": attempt_latency_ms,
                "raw_text": raw_text[:8000],
                "outfit_count_emitted": len(raw.get("outfits") or []),
                "outfit_count_kept": len(kept),
                "drop_reasons": drop_reasons,
            })

        return result, drop_reasons
