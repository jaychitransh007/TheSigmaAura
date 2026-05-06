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

from dataclasses import dataclass, field
from typing import Any, Dict

from ..schemas import (
    CombinedContext,
    RecommendationPlan,
    ResolvedContextBlock,
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
    engine wasn't even attempted (e.g. anchor turn, rollout-skipped
    bucket); set to the actual confidence when it WAS attempted, even
    on fall-through, so the ops layer can tell "engine tried but
    rejected" apart from "engine never ran"."""

    plan: RecommendationPlan
    used_engine: bool
    fallback_reason: str | None
    engine_confidence: float | None
    yaml_gaps: tuple[str, ...] = field(default_factory=tuple)


# ─────────────────────────────────────────────────────────────────────────
# Eligibility + acceptance gates
# ─────────────────────────────────────────────────────────────────────────


def is_engine_eligible(combined_context: CombinedContext) -> tuple[bool, str | None]:
    """Pre-engine gate. Skip the engine entirely for input shapes it
    can't handle today; the LLM keeps these turns."""
    live = combined_context.live
    if getattr(live, "anchor_garment", None):
        return False, "anchor_present"
    if getattr(live, "is_followup", False):
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
    eligible, reason = is_engine_eligible(combined_context)
    if not eligible:
        return RouterDecision(
            plan=architect_plan_callable(combined_context),
            used_engine=False,
            fallback_reason=reason,
            engine_confidence=None,
            yaml_gaps=(),
        )

    # Try the engine.
    if graph is None:
        graph = load_style_graph()
    inputs = extract_engine_inputs(combined_context)
    result = compose_direction(
        inputs=inputs, graph=graph, user=combined_context.user
    )

    accept, reject_reason = is_engine_acceptable(result)
    if not accept:
        return RouterDecision(
            plan=architect_plan_callable(combined_context),
            used_engine=False,
            fallback_reason=reject_reason,
            engine_confidence=result.confidence,
            yaml_gaps=result.yaml_gaps,
        )

    # Engine accepted.
    return RouterDecision(
        plan=_engine_plan(result, combined_context),
        used_engine=True,
        fallback_reason=None,
        engine_confidence=result.confidence,
        yaml_gaps=result.yaml_gaps,
    )
