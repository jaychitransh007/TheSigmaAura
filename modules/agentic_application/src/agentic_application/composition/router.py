"""Hot-path router for the composition engine (Phase 4.9).

Wraps ``OutfitArchitect.plan()`` so the orchestrator can transparently
get a ``RecommendationPlan`` from either the engine (~target ≤500ms) or
the LLM architect (~12s with the gpt-5.2 swap, ~19s before). The router
encodes the spec §9 fall-through criteria:

  Fall through to the LLM architect when ANY of:
    1. Engine returns confidence < 0.60
    2. Engine returns no DirectionSpec (full failure)
    3. Genuine YAML gap (input value not in any YAML)
    4. Provenance shows ≥2 hard-source widenings on a single attribute
       (semantic drift risk)

Plus two pre-engine eligibility gates the router applies before even
attempting the engine:

    a. Anchor-garment turns (pairing_request) — the engine doesn't yet
       handle anchored requests; let the LLM keep them.
    b. Follow-up turns (``live.is_followup`` true OR
       ``previous_recommendations`` non-empty) — same reason.

Every decision is captured in a ``RouterDecision`` envelope so the
orchestrator can log accept-vs-fall-through events for ops audit. The
router itself is pure-ish — it calls ``architect.plan()`` (which is the
side effect) only on fall-through paths.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping

from ..schemas import (
    CombinedContext,
    RecommendationPlan,
    ResolvedContextBlock,
)
from .canonicalize import (
    CanonicalEmbeddings,
    EmbedClient,
    canonicalize_inputs,
    load_canonical_embeddings,
)
from .engine import (
    CONFIDENCE_THRESHOLD,
    CompositionInputs,
    CompositionResult,
    compose_direction,
)
from .yaml_loader import StyleGraph, load_style_graph


# ─────────────────────────────────────────────────────────────────────────
# Spec-derived constants
# ─────────────────────────────────────────────────────────────────────────


# §9 item 4 — fall through when any single attribute needed ≥2 hard
# widenings. Spec rationale: "semantic drift risk".
MAX_HARD_WIDENINGS_PER_ATTR = 2


# Canonical archetype values from archetype.yaml's primary_archetype
# dimension. Used by ``_canonical_archetype()`` to map free-text
# style_goal to a YAML key. Keys must match the YAML exactly.
_CANONICAL_ARCHETYPES: frozenset[str] = frozenset({
    "bohemian",
    "classic",
    "creative",
    "dramatic",
    "edgy",
    "glamorous",
    "minimalist",
    "modern_professional",
    "natural",
    "romantic",
    "sporty",
    "trend_forward",
})


# ─────────────────────────────────────────────────────────────────────────
# Outputs
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RouterDecision:
    """The router's outcome envelope.

    ``plan`` is always populated (the router falls back to the LLM on
    any rejection). ``used_engine`` is True only when every acceptance
    criterion passed; ``fallback_reason`` is set on every path that
    didn't use the engine. ``engine_confidence`` is None when the
    engine wasn't even attempted (e.g. anchor turn, flag disabled);
    set to the actual confidence when it WAS attempted, even on
    fall-through, so the ops layer can tell "engine tried but
    rejected" apart from "engine never ran". ``engine_ms`` carries
    the wall-clock duration of the compose_direction call (None when
    the engine wasn't attempted).

    ``provenance_summary`` carries the compact per-attribute trail
    from the engine's ProvenanceEntry list — only attributes that
    needed relaxation or were omitted are surfaced (clean attributes
    are the bulk and the absence of a label is the signal). Three
    keys: ``omitted`` (final_flatters empty), ``hard_widened``
    (≥1 hard source widened), ``soft_relaxed`` (≥1 soft dropped).
    Each maps to a tuple of attribute names. Empty when the engine
    didn't run (flag off / eligibility fail).

    ``per_axis_gap_impact`` mirrors ``CompositionResult.per_axis_gap_impact``:
    ``{axis: confidence_loss}`` for the gaps that fired on this turn.
    Empty when the engine didn't run or accepted clean. Surfaced both
    in the per-axis Prometheus impact counter and in distillation_traces
    so tuning ``_YAML_GAP_AXIS_WEIGHTS`` can be driven by actual impact."""

    plan: RecommendationPlan
    used_engine: bool
    fallback_reason: str | None
    engine_confidence: float | None
    yaml_gaps: tuple[str, ...] = field(default_factory=tuple)
    engine_ms: int | None = None
    provenance_summary: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    per_axis_gap_impact: Mapping[str, float] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────
# Eligibility + acceptance gates
# ─────────────────────────────────────────────────────────────────────────


# Single-source-of-truth list of follow-up intents the engine can
# serve. Lives in intent_registry.py so the composer router shares
# the same set.
from ..intent_registry import ENGINE_FRIENDLY_FOLLOWUP_INTENTS


# ─────────────────────────────────────────────────────────────────────────
# Anchor classification — shared between orchestrator + engine eligibility
# ─────────────────────────────────────────────────────────────────────────


# Categories whose anchor occupies a top/bottom role in the final outfit.
# These trigger the orchestrator's pool-injection path (anchor's role
# stripped from queries, anchor injected as the sole item for that role).
# The composition engine cannot handle these today — the engine's tuple
# scorer doesn't differentiate "fixed slot" anchor items from candidates
# (T3 territory). Engine eligibility rejects these.
_TOP_ANCHOR_CATEGORIES = frozenset({"top", "shirt", "blouse"})
_BOTTOM_ANCHOR_CATEGORIES = frozenset({"bottom", "trouser", "pant", "jeans", "skirt"})


def classify_anchor_role(anchor: Mapping[str, Any] | None) -> tuple[str, str]:
    """Map an anchor garment to ``(role_in_pool, render_role)``.

    ``role_in_pool`` is non-empty only when the anchor occupies a
    top/bottom slot in the final outfit — those anchors get injected
    into the composer's pool by the orchestrator. Outerwear, dresses,
    co_ords, shoes, accessories and unknown categories return
    ``role_in_pool=""`` — those get prepended to the response card at
    render time (PR #208) without entering the pool.

    Single source of truth for the orchestrator's anchor-handling
    block (``orchestrator.py:_handle_planner_pipeline``) AND the
    engine eligibility gates here + in ``composer_router.py``. Adding
    a category in one place must take effect in all three; the helper
    keeps them in sync."""
    if not anchor:
        return "", ""
    category = str(anchor.get("garment_category") or "").lower().strip()
    if category in _TOP_ANCHOR_CATEGORIES:
        return "top", "top"
    if category in _BOTTOM_ANCHOR_CATEGORIES:
        return "bottom", "bottom"
    if category in ("outerwear", "blazer", "jacket", "coat"):
        return "", "outerwear"
    # Unknown category (dress, one_piece, co_ord_set, shoe, accessory,
    # ...) — render-time prepend only, surface the raw category as the
    # role label so the UI can slot it sensibly.
    return "", category or "anchor"


def is_engine_eligible(
    combined_context: CombinedContext,
    *,
    allow_pool_anchor: bool = False,
) -> tuple[bool, str | None]:
    """Pre-engine gate. Skip the engine entirely for input shapes it
    can't handle today; the LLM keeps these turns.

    May 8 follow-up T2: render-prepended anchors (outerwear / dress /
    co_ord / shoe / accessory) are eligible — the architect's plan is
    shape-identical to an occasion turn (top + bottom queries built
    UNDER the anchor layer per the architect anchor-prompt §3), so the
    engine handles them cleanly.

    Pool-injected anchors (top / bottom) ALWAYS fall through to the
    LLM architect. The T3 ``allow_pool_anchor`` experiment (May 8 follow-up)
    was flipped on in staging and surfaced a structural bug: the engine
    emitted a "paired" direction with two queries (top + bottom) sharing
    identical ``hard_attrs`` — most of them top-only axes (NecklineType,
    ShoulderStructure, EmbellishmentZone, ...) that bottom catalog rows
    are NULL on. The bottom query therefore matched almost nothing, and
    the composer received a top-heavy pool it couldn't assemble against
    the user's anchor. The flag is kept in the signature so the composer
    router (which has different semantics for pool-injected anchors) can
    keep its experimental path, but the architect router no longer honors
    it — once the engine learns anchor-aware planning (single role-specific
    query with role-appropriate attributes), revisit this gate."""
    live = combined_context.live
    anchor = getattr(live, "anchor_garment", None)
    if anchor:
        role_in_pool, _render_role = classify_anchor_role(anchor)
        if role_in_pool:
            return False, "anchor_pool_injected"
        # else: render-prepended (T2) — engine handles cleanly
    if getattr(live, "is_followup", False):
        # May 8 2026: engine-friendly follow-ups (formality changes,
        # more_options) get served by the engine. The planner emits an
        # adjusted formality_hint or signals "show me more in the same
        # space" — both are clean engine inputs. The orchestrator's
        # catalog_search already excludes previously-shown items via
        # prev_rec_ids, so engine-friendly follow-ups also skip the
        # has_previous_recommendations check below (otherwise they'd
        # be blocked there since follow-ups always have prior recs in
        # context).
        followup_intent = str(getattr(live, "followup_intent", "") or "").strip()
        if followup_intent in ENGINE_FRIENDLY_FOLLOWUP_INTENTS:
            return True, None
        return False, "followup_request"
    if combined_context.previous_recommendations:
        return False, "has_previous_recommendations"
    return True, None


def is_engine_acceptable(result: CompositionResult) -> tuple[bool, str | None]:
    """Apply spec §9 fall-through criteria to a CompositionResult.

    The engine itself sets ``fallback_reason="low_confidence"`` /
    ``"yaml_gap"`` when applicable. This function surfaces those plus
    a defensive ``confidence < CONFIDENCE_THRESHOLD`` check (in case the
    engine ever stops self-reporting), needs_disambiguation (per spec
    §7), and the per-attribute excessive-widening guard (spec §9 #4)."""
    if result.direction is None:
        return False, "no_direction"
    if result.fallback_reason:
        # Engine self-reported (yaml_gap | low_confidence). Trust it.
        return False, result.fallback_reason
    if result.confidence < CONFIDENCE_THRESHOLD:
        # Belt-and-suspenders against engine drift: today the engine
        # always self-reports low_confidence above, but a future refactor
        # that drops that self-report shouldn't silently start passing
        # sub-threshold results.
        return False, "low_confidence"
    # needs_disambiguation: spec §7 — emit fall-through even when the
    # confidence score would otherwise pass.
    if result.needs_disambiguation:
        return False, "needs_disambiguation"
    for entry in result.provenance:
        if len(entry.widened_hards) >= MAX_HARD_WIDENINGS_PER_ATTR:
            return False, "excessive_widening"
    return True, None


# ─────────────────────────────────────────────────────────────────────────
# Input extraction
# ─────────────────────────────────────────────────────────────────────────


def _flat_attr(payload: Dict[str, Any], key: str) -> str:
    """Match the architect's ``_extract_value`` semantics: the analysis
    attributes can be either {"value": "..."} dicts or bare strings."""
    raw = payload.get(key) if isinstance(payload, dict) else None
    if isinstance(raw, dict):
        return str(raw.get("value") or "").strip()
    return str(raw or "").strip()


def _canonical_archetype(style_goal: str) -> str | None:
    """Map a free-text style_goal to a canonical primary_archetype key,
    or None when no canonical match is found.

    The planner emits ``style_goal`` as a free-text directional cue
    (e.g. "edgy", "modern_professional", "old-money classic"). The
    composition engine uses canonical archetype keys from
    ``archetype.yaml``. This function does a normalize-then-exact-match
    lookup; anything else returns None (the engine treats archetype
    as optional, so absence is fine)."""
    s = (style_goal or "").strip().lower().replace(" ", "_").replace("-", "_")
    if s in _CANONICAL_ARCHETYPES:
        return s
    return None


def extract_engine_inputs(
    combined_context: CombinedContext,
    *,
    direction_id: str = "A",
) -> CompositionInputs:
    """Pull the 11 spec §1 input axes out of CombinedContext.

    The mapping mirrors what the LLM architect's ``_build_user_payload``
    already does (so engine + LLM see the same signals). Fields that
    aren't available on the user produce empty strings, which the
    engine treats as YAML gaps — those propagate to confidence as the
    spec §8 0.45 penalty and the router falls through cleanly."""
    user = combined_context.user
    live = combined_context.live

    body_shape = _flat_attr(user.analysis_attributes, "BodyShape")
    derived = user.derived_interpretations or {}
    frame_structure = _flat_attr(derived, "FrameStructure")
    seasonal_color_group = _flat_attr(derived, "SeasonalColorGroup")

    risk_tolerance = ""
    if isinstance(user.style_preference, dict):
        risk_tolerance = str(
            user.style_preference.get("riskTolerance") or ""
        ).strip()
    if not risk_tolerance:
        risk_tolerance = "moderate"

    return CompositionInputs(
        gender=user.gender or "",
        body_shape=body_shape,
        frame_structure=frame_structure,
        seasonal_color_group=seasonal_color_group,
        archetype=_canonical_archetype(getattr(live, "style_goal", "") or ""),
        risk_tolerance=risk_tolerance,
        occasion_signal=str(live.occasion_signal or ""),
        formality_hint=str(live.formality_hint or ""),
        weather_context=str(getattr(live, "weather_context", "") or ""),
        time_of_day=str(getattr(live, "time_of_day", "") or ""),
        style_goal=str(getattr(live, "style_goal", "") or ""),
        direction_id=direction_id,
        intent="occasion_recommendation",
    )


# ─────────────────────────────────────────────────────────────────────────
# Public router
# ─────────────────────────────────────────────────────────────────────────


def _build_resolved_context(
    combined_context: CombinedContext,
) -> ResolvedContextBlock:
    live = combined_context.live
    return ResolvedContextBlock(
        occasion_signal=live.occasion_signal,
        formality_hint=live.formality_hint,
        time_hint=live.time_hint or getattr(live, "time_of_day", "") or None,
        specific_needs=list(live.specific_needs or []),
        is_followup=bool(live.is_followup),
        followup_intent=live.followup_intent,
    )


def _engine_plan(
    result: CompositionResult,
    combined_context: CombinedContext,
) -> RecommendationPlan:
    """Wrap one accepted CompositionResult into a RecommendationPlan.

    For now the engine emits ONE direction (A); spec §7 leaves room for
    1-3 directions but the multi-direction extension waits until the
    inputs carry per-direction variation. ``plan_source="engine"`` lets
    the orchestrator's cache + log layers slice on origin."""
    assert result.direction is not None
    return RecommendationPlan(
        retrieval_count=5,
        directions=[result.direction],
        plan_source="engine",
        resolved_context=_build_resolved_context(combined_context),
    )


def route_recommendation_plan(
    *,
    combined_context: CombinedContext,
    architect_plan_callable,
    enabled: bool = False,
    graph: StyleGraph | None = None,
    canonical_embeddings: CanonicalEmbeddings | None = None,
    embed_client: EmbedClient | None = None,
    allow_pool_anchor: bool = False,
) -> RouterDecision:
    """Decide whether to use the engine or the LLM architect for this turn.

    ``architect_plan_callable`` is invoked only on fall-through paths;
    the test suite passes a Mock to avoid the real OpenAI call. In
    production the orchestrator passes ``self.outfit_architect.plan``.

    ``enabled`` (Phase 4.10) is the feature flag. False (default) means
    "never use the engine" — the router goes straight to the LLM. True
    routes every turn through the engine first; per-turn fall-through
    on confidence / YAML gap / disambiguation still applies via the
    spec §9 acceptance gates.

    ``canonical_embeddings`` + ``embed_client`` enable the canonicalize
    layer: the router maps free-text planner output to YAML-canonical
    keys before invoking compose_direction. Both default to None;
    callers that want the optimization pass them in. With both None,
    the engine sees raw planner output and gaps on any non-canonical
    value (the pre-canonicalize behavior).

    ``allow_pool_anchor`` (T3, May 8 follow-up) lets the engine accept
    pool-injected (top/bottom) anchor turns. Default False keeps those
    on the LLM path. Env-mapped to ``AURA_ENGINE_ALLOW_POOL_ANCHOR``
    via ``AuraRuntimeConfig.engine_allow_pool_anchor``.
    """
    # Phase 4.10 flag — stop here on disabled, before any work.
    if not enabled:
        return RouterDecision(
            plan=architect_plan_callable(combined_context),
            used_engine=False,
            fallback_reason="engine_disabled",
            engine_confidence=None,
            yaml_gaps=(),
        )

    # Pre-engine eligibility gate.
    eligible, reason = is_engine_eligible(
        combined_context, allow_pool_anchor=allow_pool_anchor,
    )
    if not eligible:
        return RouterDecision(
            plan=architect_plan_callable(combined_context),
            used_engine=False,
            fallback_reason=reason,
            engine_confidence=None,
            yaml_gaps=(),
        )

    # Try the engine. Time the compose_direction call so the
    # orchestrator can emit per-call latency to the existing
    # aura_turn_duration_seconds histogram under stage="composition_engine".
    if graph is None:
        graph = load_style_graph()
    inputs = extract_engine_inputs(combined_context)

    # Canonicalize free-text planner output → YAML-canonical keys
    # before the engine sees them. Skipped when the caller didn't
    # provide the embedding bank (tests, or canonicalize disabled).
    # Embedding lookup only fires for axes that DON'T exact-match a
    # YAML key, so the cheap path adds 0ms.
    if canonical_embeddings is not None:
        inputs, _canon_result = canonicalize_inputs(
            inputs,
            graph=graph,
            embeddings=canonical_embeddings,
            embed_client=embed_client,
        )

    _engine_t0 = time.monotonic()
    result = compose_direction(
        inputs=inputs, graph=graph, user=combined_context.user
    )
    engine_ms = int((time.monotonic() - _engine_t0) * 1000)

    # Compact per-attribute trail — surface only the non-clean entries
    # so the trace + metrics ingest doesn't get flooded with "all 35
    # attributes status=clean" noise. Three buckets so dashboards can
    # slice trend lines without parsing string statuses.
    _omitted = tuple(
        p.attribute for p in result.provenance if p.status == "omitted"
    )
    _widened = tuple(
        p.attribute for p in result.provenance if p.status == "hard_widened"
    )
    _relaxed = tuple(
        p.attribute for p in result.provenance if p.status == "soft_relaxed"
    )
    provenance_summary = {
        "omitted": _omitted,
        "hard_widened": _widened,
        "soft_relaxed": _relaxed,
    }

    accept, reject_reason = is_engine_acceptable(result)
    if not accept:
        return RouterDecision(
            plan=architect_plan_callable(combined_context),
            used_engine=False,
            fallback_reason=reject_reason,
            engine_confidence=result.confidence,
            yaml_gaps=result.yaml_gaps,
            engine_ms=engine_ms,
            provenance_summary=provenance_summary,
            per_axis_gap_impact=dict(result.per_axis_gap_impact),
        )

    # Engine accepted.
    return RouterDecision(
        plan=_engine_plan(result, combined_context),
        used_engine=True,
        fallback_reason=None,
        engine_confidence=result.confidence,
        yaml_gaps=result.yaml_gaps,
        engine_ms=engine_ms,
        provenance_summary=provenance_summary,
        per_axis_gap_impact=dict(result.per_axis_gap_impact),
    )
