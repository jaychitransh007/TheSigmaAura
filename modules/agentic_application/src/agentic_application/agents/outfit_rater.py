"""Outfit Rater — May 5 2026 (R7: 6 dims, 1/2/3 scale).

Second LLM stage in the new ranker pipeline. Takes the Composer's
output (up to 10 constructed outfits) plus the user request + context
and emits **six** sub-scores per outfit on a **1/2/3 scale** plus an
``unsuitable`` veto flag:

    occasion_fit, body_harmony, color_harmony, pairing,
    formality, statement

The orchestrator (via this module's ``compute_fashion_score`` helper)
blends the sub-scores into a final integer 0–100 ``fashion_score`` and
re-ranks accordingly. The 1/2/3 scale was deliberately chosen — LLMs
cluster ~70–90 on a 0–100 scale with no real discrimination; a discrete
3-point scale forces honest choices ("clear win" vs "works" vs "miss").

History:
- R6 (PR #79, May 5 2026): dropped ``archetype_match``.
- R7 (this change, May 5 2026): added ``formality`` and ``statement`` as
  their own axes (previously double-counted inside ``occasion_fit`` and
  ``inter_item_coherence``); switched scale 0–100 → 1/2/3; renamed
  ``inter_item_coherence`` → ``pairing`` (now scoped to fit + fabric
  only — formality + detail rhythm moved to the new axes).

Audit:
- model_call_logs gets the full raw request + response, plus the
  applied weight key (``fashion_score_weight_profile``).
- tool_traces gets a distilled ``rater_decision`` row with
  per-outfit scores + rationales preserved.
"""

from __future__ import annotations

import json
import logging
from functools import cached_property
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from openai import OpenAI

from platform_core.cost_estimator import extract_token_usage
from user_profiler.config import get_api_key

from ..schemas import (
    CombinedContext,
    ComposedOutfit,
    RatedOutfit,
    RaterResult,
    RetrievedProduct,
    RetrievedSet,
)
from .outfit_composer import _ITEM_ATTRS, _item_summary, _user_context_block

_log = logging.getLogger(__name__)


def _find_prompt_dir() -> Path:
    here = Path(__file__).resolve()
    for base in [here.parent] + list(here.parents):
        candidate = base / "prompt"
        if candidate.is_dir() and (candidate / "outfit_rater.md").exists():
            return candidate
    raise FileNotFoundError("Could not locate prompt/ directory containing outfit_rater.md")


def _load_prompt() -> str:
    return (_find_prompt_dir() / "outfit_rater.md").read_text(encoding="utf-8").strip()


# ── 1/2/3 scale schema ──────────────────────────────────────────────
# Each sub-score is constrained to the integer set {1, 2, 3} via the
# `enum` clause. The OpenAI structured-output gate rejects 0, 4, 50,
# etc. before the parser sees them — defensive parsing below is a belt
# in case the schema constraint ever softens.
_SUBSCORE_SCHEMA: Dict[str, Any] = {"type": "integer", "enum": [1, 2, 3]}

_RATER_JSON_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "name": "outfit_rater_result",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["ranked_outfits", "overall_assessment"],
        "properties": {
            "ranked_outfits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "composer_id",
                        "occasion_fit",
                        "body_harmony",
                        "color_harmony",
                        # R7 (May 5 2026): renamed from inter_item_coherence;
                        # now scoped to fit-type compatibility + fabric
                        # pairing only. Formality consistency moved to
                        # `formality`; detail rhythm moved to `statement`.
                        # For complete (single-item) outfits the LLM emits 3;
                        # the orchestrator drops the dim from the blend.
                        "pairing",
                        # R7: formality is its own axis now (previously
                        # double-counted inside occasion_fit and
                        # inter_item_coherence).
                        "formality",
                        # R7: pattern density + embellishment intensity.
                        "statement",
                        "rationale",
                        "unsuitable",
                    ],
                    "properties": {
                        "composer_id": {"type": "string"},
                        "occasion_fit": _SUBSCORE_SCHEMA,
                        "body_harmony": _SUBSCORE_SCHEMA,
                        "color_harmony": _SUBSCORE_SCHEMA,
                        "pairing": _SUBSCORE_SCHEMA,
                        "formality": _SUBSCORE_SCHEMA,
                        "statement": _SUBSCORE_SCHEMA,
                        "rationale": {"type": "string"},
                        "unsuitable": {"type": "boolean"},
                    },
                },
            },
            "overall_assessment": {
                "type": "string",
                "enum": ["strong", "moderate", "weak"],
            },
        },
    },
}


# ── Weight profiles for fashion_score blending ────────────────────────
# Each profile is a total-1.0 distribution over the six 1/2/3 sub-scores.
# The orchestrator picks a profile based on planner-resolved context and
# computes:
#
#     raw   = Σ subscore × weight     # ranges 1.0..3.0
#     score = ((raw − 1) / 2) × 100   # rescales to 0..100
#
# This way LLM rates simply, math handles the blend, and the user-facing
# `fashion_score_pct` stays on the familiar 0–100 scale.
#
# Adding a new profile = one entry here + one rule in `select_weight_profile`.
_DEFAULT_WEIGHT_PROFILE = "default"

WEIGHT_PROFILES: Dict[str, Dict[str, float]] = {
    "default": {
        # User-supplied weights (R7, May 5 2026): occasion-led, with
        # color a close second; formality + statement get explicit
        # weight rather than being baked into other axes.
        "occasion_fit":  0.25,
        "color_harmony": 0.20,
        "body_harmony":  0.15,
        "pairing":       0.15,
        "formality":     0.13,
        "statement":     0.12,
    },
    # Wedding / festival / ceremonial — occasion + formality dominate
    # (the user is dressing for the rules of the event).
    "ceremonial": {
        "occasion_fit":  0.32,
        "formality":     0.22,
        "color_harmony": 0.16,
        "body_harmony":  0.12,
        "pairing":       0.10,
        "statement":     0.08,
    },
    # "Make me look slimmer / taller" — body harmony leads; pairing
    # still matters because clashing fits ruin slimming.
    "slimming": {
        "body_harmony":  0.34,
        "occasion_fit":  0.20,
        "color_harmony": 0.16,
        "pairing":       0.14,
        "formality":     0.09,
        "statement":     0.07,
    },
    # "Bold / statement / colorful" — color and statement lead.
    "bold": {
        "color_harmony": 0.30,
        "statement":     0.22,
        "occasion_fit":  0.18,
        "body_harmony":  0.13,
        "pairing":       0.10,
        "formality":     0.07,
    },
    # "Comfortable / relaxed" — body comfort drives; pairing matters
    # because relaxed pieces still need to read as one outfit.
    "comfortable": {
        "body_harmony":  0.32,
        "pairing":       0.18,
        "occasion_fit":  0.18,
        "color_harmony": 0.14,
        "formality":     0.10,
        "statement":     0.08,
    },
}

# R7: pairing doesn't apply to a single-item outfit (direction_type
# ="complete" → one product). For those, drop the dim from the blend
# and renormalize the remaining five weights so they sum to 1.0.
_COMPLETE_OUTFIT_DROP_KEY = "pairing"

# All sub-score keys, in canonical order. Used by the schema, the
# blender, and tests; keep this list in sync with the prompt.
_SUBSCORE_KEYS: tuple = (
    "occasion_fit",
    "body_harmony",
    "color_harmony",
    "pairing",
    "formality",
    "statement",
)


_CEREMONIAL_OCCASIONS = frozenset({
    "wedding_traditional",
    "wedding_western",
    "wedding",
    "festival",
    "sangeet",
    "mehndi",
    "engagement",
    "ceremony",
    "ceremonial",
})

# Keyword fragments matched against the lowercased user message
# (NOT formality_hint — that's a planner classification like
# "smart_casual" which would false-positive on "casual"-style
# keywords). Each phrase is intentionally specific so we don't
# over-match.
_BOLD_KEYWORDS = ("bold", "statement", "colorful", "colourful", "stand out", "make a pop")
_SLIMMING_KEYWORDS = ("slimmer", "slimming", "taller", "look thin", "look slim")
_COMFORTABLE_KEYWORDS = ("comfortable", "comfort", "relaxed")


def select_weight_profile(
    *,
    user_message: str = "",
    occasion_signal: str = "",
    specific_needs: Sequence[str] = (),
) -> str:
    """Return the weight-profile key to apply for this turn.

    Priority:
        1. ``ceremonial`` — when the planner classified the occasion as
           wedding / festival / ceremony, occasion + formality dominate.
        2. ``slimming`` — explicit user ask to look slimmer/taller.
        3. ``bold`` — explicit user ask for a statement / colorful look.
        4. ``comfortable`` — explicit ask for relaxed/comfortable wear.
        5. ``default`` — no override.

    Order matters: ``ceremonial`` beats ``comfortable`` (a "comfortable
    wedding outfit" still cares most about occasion). Slimming and bold
    are exclusive in practice; first match wins.
    """
    occ = (occasion_signal or "").strip().lower()
    if occ in _CEREMONIAL_OCCASIONS or "ceremon" in occ or "wedding" in occ or "festival" in occ:
        return "ceremonial"
    needs_blob = " ".join(s.lower() for s in (specific_needs or []))
    msg = (user_message or "").lower()
    haystack = f"{msg} {needs_blob}"
    if any(k in haystack for k in _SLIMMING_KEYWORDS):
        return "slimming"
    if any(k in haystack for k in _BOLD_KEYWORDS):
        return "bold"
    if any(k in haystack for k in _COMFORTABLE_KEYWORDS):
        return "comfortable"
    return _DEFAULT_WEIGHT_PROFILE


def compute_fashion_score(
    *,
    occasion_fit: int,
    body_harmony: int,
    color_harmony: int,
    pairing: Optional[int] = None,
    formality: int,
    statement: int,
    direction_type: str = "paired",
    profile: str = _DEFAULT_WEIGHT_PROFILE,
) -> int:
    """Blend the six 1/2/3 sub-scores into a 0–100 ``fashion_score``.

    Math:
        raw   = Σ subscore × weight        (1.0 .. 3.0)
        score = ((raw − 1) / 2) × 100      (0 .. 100, rounded)

    All-1s outfit → 0. All-2s → 50. All-3s → 100. The threshold gate
    in the orchestrator (currently 50) rides this scale: an outfit that
    scores 2 across the board barely clears.

    ``pairing`` is dropped from the formula in two cases:
    (1) ``direction_type="complete"`` (single-item outfit — nothing to
    pair), or (2) the value is ``None`` (LLM didn't emit it). In both
    cases the remaining five weights are renormalised to sum to 1.0.

    Unknown ``profile`` falls back to ``default`` rather than raising —
    the rule is lossy-graceful so a misconfigured profile can't take
    down the recommendation pipeline.
    """
    weights = WEIGHT_PROFILES.get(profile) or WEIGHT_PROFILES[_DEFAULT_WEIGHT_PROFILE]
    drop_pairing = (
        (direction_type or "").strip().lower() == "complete"
        or pairing is None
    )
    if drop_pairing:
        kept = {k: v for k, v in weights.items() if k != _COMPLETE_OUTFIT_DROP_KEY}
        denom = sum(kept.values())
        weights = {k: v / denom for k, v in kept.items()} if denom > 0 else kept
        raw = (
            occasion_fit * weights["occasion_fit"]
            + body_harmony * weights["body_harmony"]
            + color_harmony * weights["color_harmony"]
            + formality * weights["formality"]
            + statement * weights["statement"]
        )
    else:
        raw = (
            occasion_fit * weights["occasion_fit"]
            + body_harmony * weights["body_harmony"]
            + color_harmony * weights["color_harmony"]
            + pairing * weights["pairing"]
            + formality * weights["formality"]
            + statement * weights["statement"]
        )
    score = ((raw - 1.0) / 2.0) * 100.0
    return _clamp_to_100(int(round(score)))


def _build_outfit_payload(
    composed: Sequence[ComposedOutfit],
    items_by_id: Dict[str, RetrievedProduct],
) -> List[Dict[str, Any]]:
    """For each composed outfit, expand its item_ids into the full attr
    dict the Rater will see. Anything the Rater needs to reason about
    style coherence belongs here."""
    payload: List[Dict[str, Any]] = []
    for outfit in composed:
        item_details = []
        for iid in outfit.item_ids:
            product = items_by_id.get(iid)
            if product is None:
                # Composer validation passed but we lost the product —
                # shouldn't happen. Surface a stub so the Rater can
                # still reason about what's there.
                item_details.append({
                    "item_id": iid,
                    "title": "(missing)",
                    **{k: "" for k in _ITEM_ATTRS},
                })
                continue
            item_details.append(_item_summary(iid, product))
        payload.append(
            {
                "composer_id": outfit.composer_id,
                "direction_id": outfit.direction_id,
                "direction_type": outfit.direction_type,
                "composer_rationale": outfit.rationale,
                "item_details": item_details,
            }
        )
    return payload


class OutfitRater:
    """LLM-driven outfit scorer. One gpt-5-mini call per turn.

    Inputs: the Composer's outfits + user message + user context.
    Output: ranked outfits with per-dimension scores (1/2/3), blended
    fashion_score (0–100), and unsuitable veto.
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

    def rate(
        self,
        combined_context: CombinedContext,
        composed_outfits: Sequence[ComposedOutfit],
        retrieved_sets: Sequence[RetrievedSet],
    ) -> RaterResult:
        """Score and rank the composed outfits. One LLM call.

        ``retrieved_sets`` is the same pool the Composer saw — we use it
        only to look up each item's full attributes for the Rater's
        prompt.

        The LLM only emits the six 1/2/3 sub-scores + rationale +
        unsuitable. ``fashion_score`` and ``rank`` are computed in
        Python via ``compute_fashion_score`` and the weight profile
        picked by ``select_weight_profile`` from planner-resolved
        context.
        """
        if not composed_outfits:
            return RaterResult(ranked_outfits=[], overall_assessment="weak")

        # Pick the weight profile for this turn before the LLM call so
        # the choice is logged even if the LLM call errors.
        live = combined_context.live
        weight_profile = select_weight_profile(
            user_message=getattr(live, "user_need", "") or "",
            occasion_signal=str(getattr(live, "occasion_signal", "") or ""),
            specific_needs=list(getattr(live, "specific_needs", []) or []),
        )

        items_by_id: Dict[str, RetrievedProduct] = {}
        for rs in retrieved_sets:
            for p in rs.products:
                items_by_id[p.product_id] = p

        # Past likes/dislikes are applied upstream (Architect retrieval
        # bias, Composer item selection bias). The rater scores what's
        # in front of it on its own merits — see PR #89.
        user_block = _user_context_block(combined_context)
        user_block.pop("archetypal_preferences", None)
        user_payload = json.dumps(
            {
                "user": user_block,
                "outfits": _build_outfit_payload(composed_outfits, items_by_id),
            },
            indent=2,
            default=str,
        )

        # reasoning_effort="minimal" — Rater scores 6 fixed dims per
        # outfit on a 1/2/3 enum schema; no chain-of-thought needed.
        response = self._client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": self._system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_payload}]},
            ],
            reasoning={"effort": "minimal"},
            text={"format": _RATER_JSON_SCHEMA},
        )
        usage = extract_token_usage(response) or {}
        self.last_usage = dict(usage)
        raw_text = getattr(response, "output_text", "") or "{}"
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            _log.warning("OutfitRater: JSON parse failed (%s); returning empty result", exc)
            return RaterResult(
                ranked_outfits=[], overall_assessment="weak",
                raw_response=raw_text, usage=dict(usage),
                fashion_score_weight_profile=weight_profile,
            )

        direction_by_cid = {o.composer_id: o.direction_type for o in composed_outfits}

        valid_ids = {o.composer_id for o in composed_outfits}
        ranked: List[RatedOutfit] = []
        for raw_o in raw.get("ranked_outfits", []):
            cid = str(raw_o.get("composer_id", ""))
            if cid not in valid_ids:
                _log.warning("OutfitRater: dropping unknown composer_id %s", cid)
                continue
            # Five always-on dims default to 2 ("works") on malformed
            # input — a missing field is more likely a parsing bug than
            # a "score zero" signal, and 2 is the neutral midpoint.
            # `pairing` defaults to None so compute_fashion_score drops
            # the dim and renormalises (same path as complete outfits).
            occ = _parse_subscore(raw_o.get("occasion_fit"))
            bod = _parse_subscore(raw_o.get("body_harmony"))
            col = _parse_subscore(raw_o.get("color_harmony"))
            pair: Optional[int] = _parse_optional_subscore(raw_o.get("pairing"))
            form = _parse_subscore(raw_o.get("formality"))
            stmt = _parse_subscore(raw_o.get("statement"))
            ranked.append(
                RatedOutfit(
                    composer_id=cid,
                    occasion_fit=occ,
                    body_harmony=bod,
                    color_harmony=col,
                    pairing=pair,
                    formality=form,
                    statement=stmt,
                    fashion_score=compute_fashion_score(
                        occasion_fit=occ,
                        body_harmony=bod,
                        color_harmony=col,
                        pairing=pair,
                        formality=form,
                        statement=stmt,
                        direction_type=direction_by_cid.get(cid, "paired"),
                        profile=weight_profile,
                    ),
                    rationale=str(raw_o.get("rationale", "")),
                    unsuitable=bool(raw_o.get("unsuitable", False)),
                )
            )

        ranked.sort(key=lambda r: (-r.fashion_score, _composer_id_sort_key(r.composer_id)))
        for i, r in enumerate(ranked, start=1):
            r.rank = i

        return RaterResult(
            ranked_outfits=ranked,
            overall_assessment=str(raw.get("overall_assessment") or "moderate"),
            raw_response=raw_text,
            usage=dict(usage),
            fashion_score_weight_profile=weight_profile,
        )


def _composer_id_sort_key(cid: str) -> tuple:
    """Natural-numeric tiebreak key for composer_ids of the form ``C<n>``.

    Lex sort puts ``C10`` before ``C2``; once a slate has 10 outfits
    the rank tiebreak silently inverts. Pull the digit suffix out and
    sort numerically; fall back to the raw string for unexpected formats.
    """
    cid = (cid or "").strip()
    digits = "".join(ch for ch in cid if ch.isdigit())
    try:
        return (0, int(digits)) if digits else (1, cid)
    except ValueError:
        return (1, cid)


def _clamp_to_100(value: int) -> int:
    """Clamp an int to 0..100. Defensive — the blend math should already
    land in range, but a misconfigured weight profile (sum != 1.0) could
    drift. Clamp first, calibrate later."""
    return max(0, min(100, int(value)))


def _clamp_subscore(value: int) -> int:
    """Clamp an int to {1, 2, 3}. The strict-output schema enforces this
    upstream, but defensive parsers below may produce an out-of-range
    int from malformed legacy data."""
    return max(1, min(3, int(value)))


def _safe_int_or_none(value: Any) -> Optional[int]:
    """Best-effort int conversion that returns None for any
    missing or malformed input.

    Accepts: ``int``, ``str`` numerals, ``str`` floats like ``"2.5"``
    (truncated to 2), strings with surrounding whitespace.
    Rejects: ``None``, empty / whitespace-only strings, ``"N/A"``,
    ``"None"``, booleans (which are int subclasses), inf, and any
    other string that can't be parsed as a number.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except (OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        pass
    try:
        return int(float(text))
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_subscore(raw: Any) -> int:
    """Parse one of the five always-emitted Rater sub-scores
    (occasion_fit / body_harmony / color_harmony / formality / statement)
    to a 1/2/3 int. Missing or malformed input → 2 (neutral midpoint).

    The schema enforces {1, 2, 3} via enum, so this should never see
    out-of-range values in practice. Clamp anyway as a defensive belt.
    """
    parsed = _safe_int_or_none(raw)
    return _clamp_subscore(2 if parsed is None else parsed)


def _parse_optional_subscore(raw: Any) -> Optional[int]:
    """Parse the optional ``pairing`` sub-score. Missing or malformed
    input → None, which signals ``compute_fashion_score`` to drop the
    dim and renormalise the remaining five weights — same path used
    for single-item complete outfits."""
    parsed = _safe_int_or_none(raw)
    return _clamp_subscore(parsed) if parsed is not None else None
