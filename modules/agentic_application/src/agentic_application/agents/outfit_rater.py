"""Outfit Rater — May 3 2026.

Second LLM stage in the new ranker pipeline. Takes the Composer's
output (up to 10 constructed outfits) plus the user request + context
and emits a four-dimension rubric score per outfit and an
``unsuitable`` veto flag. The orchestrator (or this module's
``compute_fashion_score`` helper) blends those four sub-scores into a
final integer ``fashion_score`` and re-ranks accordingly.

Replaces the deterministic Reranker. The blend weights default to
``{occasion 0.35, body 0.20, color 0.25, archetype 0.20}`` and shift
based on the planner's resolved intent (ceremonial, slimming, bold,
comfortable). R3 (May 5 2026) moved this rule out of the LLM prompt
and into Python so the math is unit-testable and the override that
fired is logged.

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
from typing import Any, Dict, List, Sequence

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
                        "archetype_match",
                        # R5 (May 5 2026): how well the items in a
                        # multi-piece outfit work together (fit, fabric,
                        # formality consistency between pieces). For
                        # single-item outfits (direction_type=complete),
                        # the LLM should emit 100 — no inter-item
                        # interaction to score — and the orchestrator
                        # drops the dim from the blend at that point.
                        "inter_item_coherence",
                        "rationale",
                        "unsuitable",
                    ],
                    "properties": {
                        "composer_id": {"type": "string"},
                        "occasion_fit": {"type": "integer"},
                        "body_harmony": {"type": "integer"},
                        "color_harmony": {"type": "integer"},
                        "archetype_match": {"type": "integer"},
                        "inter_item_coherence": {"type": "integer"},
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
# R3 (May 5 2026): the weight rule moved from the prompt into Python.
# The Rater emits four sub-scores; the orchestrator picks a profile
# based on planner-resolved context and computes:
#
#     fashion_score = round( Σ subscore × weight )
#
# Profiles are total-1.0 distributions over the four dimensions. Adding
# a new profile = one entry here + one rule in ``select_weight_profile``.
_DEFAULT_WEIGHT_PROFILE = "default"

WEIGHT_PROFILES: Dict[str, Dict[str, float]] = {
    "default": {
        "occasion_fit":         0.30,
        "body_harmony":         0.18,
        "color_harmony":        0.22,
        "archetype_match":      0.15,
        "inter_item_coherence": 0.15,
    },
    # Wedding / festival / ceremonial — occasion fit dominates; the
    # other four split the remainder.
    "ceremonial": {
        "occasion_fit":         0.40,
        "body_harmony":         0.16,
        "color_harmony":        0.18,
        "archetype_match":      0.13,
        "inter_item_coherence": 0.13,
    },
    # "Make me look slimmer / taller" — body harmony leads; inter-item
    # coherence still matters because clashing fits ruin slimming.
    "slimming": {
        "occasion_fit":         0.20,
        "body_harmony":         0.32,
        "color_harmony":        0.20,
        "archetype_match":      0.13,
        "inter_item_coherence": 0.15,
    },
    # "Bold / statement / colorful" — color leads; inter-item gets a
    # smaller share because bold looks tolerate more contrast within.
    "bold": {
        "occasion_fit":         0.18,
        "body_harmony":         0.18,
        "color_harmony":        0.32,
        "archetype_match":      0.20,
        "inter_item_coherence": 0.12,
    },
    # "Comfortable / relaxed" — body comfort + archetype drive; inter-
    # item gets a meaningful share because relaxed pieces still need
    # to read as one outfit, not two clashing items.
    "comfortable": {
        "occasion_fit":         0.20,
        "body_harmony":         0.28,
        "color_harmony":        0.18,
        "archetype_match":      0.20,
        "inter_item_coherence": 0.14,
    },
}

# R5 (May 5 2026): inter_item_coherence doesn't apply to a single-item
# outfit (direction_type="complete" → one product). For those, drop the
# dim from the blend and renormalize the remaining four weights so they
# sum to 1.0. This avoids a Python-level renorm at every callsite and
# keeps the prompt simple (LLM emits 100 for completes; the math
# ignores it).
_COMPLETE_OUTFIT_DROP_KEY = "inter_item_coherence"


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
    formality_hint: str = "",
    specific_needs: Sequence[str] = (),
) -> str:
    """Return the weight-profile key to apply for this turn.

    Priority:
        1. ``ceremonial`` — when the planner classified the occasion as
           wedding / festival / ceremony, occasion fit dominates.
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
    # formality_hint is intentionally NOT in the haystack — it's a
    # planner classification ("smart_casual", "ceremonial") rather
    # than user-expressed intent. Matching against it produces false
    # positives ("smart_casual" → "casual" keyword → wrong profile).
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
    archetype_match: int,
    inter_item_coherence: int = 100,
    direction_type: str = "paired",
    profile: str = _DEFAULT_WEIGHT_PROFILE,
) -> int:
    """Blend the five sub-scores into an integer 0–100 fashion_score.

    For ``direction_type="complete"`` outfits (single-item, e.g. a
    kurta_set or jumpsuit) ``inter_item_coherence`` doesn't apply —
    we drop it from the formula and renormalize the remaining four
    weights so they still sum to 1.0. The LLM is told to emit 100
    in that case so this branch is a no-op for it.

    Unknown ``profile`` falls back to ``default`` rather than raising —
    the rule is lossy-graceful so a misconfigured profile can't take
    down the recommendation pipeline.
    """
    weights = WEIGHT_PROFILES.get(profile) or WEIGHT_PROFILES[_DEFAULT_WEIGHT_PROFILE]
    if (direction_type or "").strip().lower() == "complete":
        # Drop inter_item_coherence and renormalise the remaining four
        # weights so they sum to 1.0.
        kept = {k: v for k, v in weights.items() if k != _COMPLETE_OUTFIT_DROP_KEY}
        denom = sum(kept.values())
        weights = {k: v / denom for k, v in kept.items()} if denom > 0 else kept
        raw = (
            occasion_fit * weights["occasion_fit"]
            + body_harmony * weights["body_harmony"]
            + color_harmony * weights["color_harmony"]
            + archetype_match * weights["archetype_match"]
        )
    else:
        raw = (
            occasion_fit * weights["occasion_fit"]
            + body_harmony * weights["body_harmony"]
            + color_harmony * weights["color_harmony"]
            + archetype_match * weights["archetype_match"]
            + inter_item_coherence * weights["inter_item_coherence"]
        )
    return _clamp_to_100(int(round(raw)))


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
                # Pad with empty strings for every attr the Rater
                # prompt promises so the schema stays consistent.
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
    Output: ranked outfits with per-dimension scores, blended
    fashion_score, and unsuitable veto.
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

        R3 (May 5 2026): the LLM only emits the four sub-scores +
        rationale + unsuitable. ``fashion_score`` and ``rank`` are
        computed in Python via ``compute_fashion_score`` and the
        weight profile picked by ``select_weight_profile`` from the
        planner-resolved context. The LLM's old ``fashion_score`` /
        ``rank`` fields are no longer in the schema.
        """
        if not composed_outfits:
            return RaterResult(ranked_outfits=[], overall_assessment="weak")

        # Pick the weight profile for this turn before the LLM call so
        # the choice is logged even if the LLM call errors. Reads from
        # combined_context.live (the planner's resolved entities).
        live = combined_context.live
        weight_profile = select_weight_profile(
            user_message=getattr(live, "user_need", "") or "",
            occasion_signal=str(getattr(live, "occasion_signal", "") or ""),
            formality_hint=str(getattr(live, "formality_hint", "") or ""),
            specific_needs=list(getattr(live, "specific_needs", []) or []),
        )

        items_by_id: Dict[str, RetrievedProduct] = {}
        for rs in retrieved_sets:
            for p in rs.products:
                items_by_id[p.product_id] = p

        user_payload = json.dumps(
            {
                "user": _user_context_block(combined_context),
                "outfits": _build_outfit_payload(composed_outfits, items_by_id),
            },
            indent=2,
            default=str,
        )

        # reasoning_effort="minimal" — Rater scores 4 fixed dims per
        # outfit on a constrained schema; no chain-of-thought needed.
        # ~2.4K reasoning tokens observed per call without this.
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
        # Mirror to last_usage for backwards-compat; consumers needing
        # thread-safe usage should read RaterResult.usage instead.
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

        # Map composer_id → direction_type so compute_fashion_score
        # can handle single-item ('complete') outfits correctly.
        direction_by_cid = {o.composer_id: o.direction_type for o in composed_outfits}

        valid_ids = {o.composer_id for o in composed_outfits}
        ranked: List[RatedOutfit] = []
        for raw_o in raw.get("ranked_outfits", []):
            cid = str(raw_o.get("composer_id", ""))
            if cid not in valid_ids:
                _log.warning("OutfitRater: dropping unknown composer_id %s", cid)
                continue
            occ = _clamp_to_100(int(raw_o.get("occasion_fit", 0) or 0))
            bod = _clamp_to_100(int(raw_o.get("body_harmony", 0) or 0))
            col = _clamp_to_100(int(raw_o.get("color_harmony", 0) or 0))
            arch = _clamp_to_100(int(raw_o.get("archetype_match", 0) or 0))
            # R5: inter_item_coherence — defaults to 100 when omitted
            # by older prompt versions or for complete outfits the LLM
            # has explicitly marked.
            inter = _clamp_to_100(int(raw_o.get("inter_item_coherence", 100) or 100))
            ranked.append(
                RatedOutfit(
                    composer_id=cid,
                    occasion_fit=occ,
                    body_harmony=bod,
                    color_harmony=col,
                    archetype_match=arch,
                    inter_item_coherence=inter,
                    fashion_score=compute_fashion_score(
                        occasion_fit=occ,
                        body_harmony=bod,
                        color_harmony=col,
                        archetype_match=arch,
                        inter_item_coherence=inter,
                        direction_type=direction_by_cid.get(cid, "paired"),
                        profile=weight_profile,
                    ),
                    rationale=str(raw_o.get("rationale", "")),
                    unsuitable=bool(raw_o.get("unsuitable", False)),
                )
            )

        # Rank by computed fashion_score desc (ties: lower composer_id
        # first — same convention the prompt used to enforce).
        ranked.sort(key=lambda r: (-r.fashion_score, r.composer_id))
        for i, r in enumerate(ranked, start=1):
            r.rank = i

        return RaterResult(
            ranked_outfits=ranked,
            overall_assessment=str(raw.get("overall_assessment") or "moderate"),
            raw_response=raw_text,
            usage=dict(usage),
            fashion_score_weight_profile=weight_profile,
        )


def _clamp_to_100(value: int) -> int:
    """Clamp an int to 0..100. Defensive — the prompt asks for 0–100 but
    the model occasionally emits 0–10 or 0–1 scores during early-stage
    drift. Clamp first, calibrate later."""
    return max(0, min(100, int(value)))
