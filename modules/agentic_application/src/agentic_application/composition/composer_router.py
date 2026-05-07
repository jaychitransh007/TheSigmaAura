"""Hot-path router for the composer engine (Phase 5d).

Mirrors ``router.py`` (architect router): wraps the composer call site
so the orchestrator transparently gets a ``ComposerResult`` from either
the engine (~target ≤300ms) or the LLM ``OutfitComposer`` (~12-14s).

Pre-engine eligibility gates (composer_semantics.md §10):

  a. ``anchor_present`` — pairing_request turns; engine doesn't yet
     handle anchored requests (composer_semantics.md §11 future work).
  b. ``followup_request`` — engine has no episodic context.
  c. ``has_previous_recommendations`` — same.
  d. ``architect_plan_from_cache`` — composer-specific gate. Architect
     cache hits go straight through (running the engine on top is
     double-work; the cached plan was produced under different inputs).

Engine acceptance criteria (composer_semantics.md §7.2):

  1. ``composer_result`` is None → engine self-declined (yaml_gap,
     low_picks, pool_too_sparse, low_confidence). Trust the engine's
     ``fallback_reason``; use the LLM.
  2. ``composer_result`` is populated → engine accepted; the orchestrator
     uses it directly and skips the composer cache write (engine plans
     don't pollute the LLM-cache key space).

Every decision is captured in a ``ComposerRouterDecision`` envelope so
the orchestrator can log accept-vs-fall-through events, time the engine
call, and stamp ``model_call_logs.model`` correctly.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from ..schemas import (
    CombinedContext,
    ComposerResult,
    RecommendationPlan,
    RetrievedSet,
)
from .composer_engine import (
    ComposerEngineResult,
    compose_outfits,
)
from .pairing import TupleContext
from .yaml_loader import StyleGraph, load_style_graph


# ─────────────────────────────────────────────────────────────────────────
# Outputs
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ComposerRouterDecision:
    """The composer router's outcome envelope.

    ``composer_result`` is always populated (the router falls back to
    the LLM on any rejection). ``used_engine`` is True only when the
    engine accepted; ``fallback_reason`` is set on every path that
    didn't use the engine. ``engine_confidence`` is None when the
    engine wasn't even attempted (eligibility gate, flag off); set to
    the actual confidence when it WAS attempted, even on fall-through.
    ``engine_ms`` is the wall-clock duration of compose_outfits (None
    when not attempted).

    ``provenance_summary`` aggregates the per-tuple provenance into
    counts the dashboards consume: total tuples scored, tuples kept,
    tuples picked, tuples by drop_reason. Empty when the engine wasn't
    attempted.

    ``shadow_comparison`` is populated only when ``shadow=True`` was
    passed to ``route_composer_plan`` AND the LLM ran (either via
    eligible-but-shadow-only path, or because the engine declined).
    It carries the engine's parallel composition + the head-to-head
    comparison vs the LLM result so the orchestrator can persist it
    to a ``composer_shadow_decision`` tool_trace. None on every path
    where shadow mode wasn't requested or the comparison wasn't
    runnable.
    """

    composer_result: ComposerResult
    used_engine: bool
    fallback_reason: str | None
    engine_confidence: float | None
    yaml_gaps: tuple[str, ...] = field(default_factory=tuple)
    engine_ms: int | None = None
    provenance_summary: Mapping[str, Any] = field(default_factory=dict)
    shadow_comparison: Any = None


# ─────────────────────────────────────────────────────────────────────────
# Eligibility gate
# ─────────────────────────────────────────────────────────────────────────


def is_engine_eligible(
    combined_context: CombinedContext, plan: RecommendationPlan
) -> tuple[bool, str | None]:
    """Pre-engine gate. Returns ``(eligible, fallback_reason)``.

    Mirrors the architect router's eligibility gate plus a composer-
    specific check on ``plan.plan_source``: when the architect plan
    came from cache, the composer engine doesn't run on top of it —
    the cached plan was scored against a different snapshot of the
    composer engine's behavior, and re-scoring would risk drift.
    """
    live = combined_context.live
    if getattr(live, "anchor_garment", None):
        return False, "anchor_present"
    if getattr(live, "is_followup", False):
        return False, "followup_request"
    if combined_context.previous_recommendations:
        return False, "has_previous_recommendations"
    if plan.plan_source == "cache":
        return False, "architect_plan_from_cache"
    return True, None


# ─────────────────────────────────────────────────────────────────────────
# TupleContext extraction
# ─────────────────────────────────────────────────────────────────────────


def extract_tuple_context(combined_context: CombinedContext) -> TupleContext:
    """Pull the engine's TupleContext out of CombinedContext.

    Mirrors the architect router's ``extract_engine_inputs``: engine
    sees the same planner output + user-profile signals the LLM does.
    Empty strings cascade through to evaluators that abstain on missing
    inputs (per pairing.py docstrings).
    """
    user = combined_context.user
    live = combined_context.live

    # body_shape lives on user.analysis_attributes per the Phase 4.7
    # extractor — same shape as architect's _flat_attr.
    body_attr = user.analysis_attributes.get("BodyShape") if user.analysis_attributes else None
    if isinstance(body_attr, dict):
        body_shape = str(body_attr.get("value") or "").strip()
    else:
        body_shape = str(body_attr or "").strip()

    # Palette anchors: pull from derived_interpretations.PaletteAnchors
    # if present; otherwise empty (engine skips palette_anchor_required
    # rule when anchors empty — pairing._evaluate_color_story).
    derived = user.derived_interpretations or {}
    raw_anchors = derived.get("PaletteAnchors")
    if isinstance(raw_anchors, list):
        anchors = tuple(str(a) for a in raw_anchors if a)
    elif isinstance(raw_anchors, dict):
        # Some profiles may store {"value": [...]} shape
        v = raw_anchors.get("value")
        anchors = tuple(str(a) for a in (v or ()) if a) if isinstance(v, list) else ()
    else:
        anchors = ()

    return TupleContext(
        formality_hint=str(getattr(live, "formality_hint", "") or ""),
        occasion_signal=str(getattr(live, "occasion_signal", "") or ""),
        palette_anchors=anchors,
        body_shape=body_shape,
        intent="recommendation_request",
    )


# ─────────────────────────────────────────────────────────────────────────
# Public router
# ─────────────────────────────────────────────────────────────────────────


def _summarize_provenance(result: ComposerEngineResult) -> dict[str, Any]:
    """Compact provenance for trace + dashboard ingest.

    Surfaces tuple counts (total, kept, dropped, picked) and
    drop_reason distribution so panels 25-28 can slice trends. Keeps
    cardinality tight — no per-attribute payloads here, just integers
    and a small enum-keyed dict."""
    if not result.provenance:
        return {}
    by_drop: dict[str, int] = {}
    kept = 0
    picked = 0
    for p in result.provenance:
        if p.dropped:
            reason = p.drop_reason or "unknown"
            by_drop[reason] = by_drop.get(reason, 0) + 1
        else:
            kept += 1
        if p.picked:
            picked += 1
    return {
        "total_tuples": len(result.provenance),
        "kept": kept,
        "dropped_total": sum(by_drop.values()),
        "dropped_by_reason": by_drop,
        "picked": picked,
    }


def route_composer_plan(
    *,
    plan: RecommendationPlan,
    retrieved_sets: Iterable[RetrievedSet],
    combined_context: CombinedContext,
    composer_callable: Callable[[], ComposerResult],
    enabled: bool = False,
    graph: StyleGraph | None = None,
    shadow: bool = False,
) -> ComposerRouterDecision:
    """Decide whether the composer engine or the LLM ``OutfitComposer``
    handles this turn.

    ``composer_callable`` is invoked only on fall-through paths; the
    orchestrator wraps ``self.outfit_composer.compose(combined_context,
    retrieved_sets, on_attempt=...)`` in a thunk before passing.

    ``enabled`` is the feature flag (``AURA_COMPOSER_ENGINE_ENABLED``).
    False (default) routes every turn through the LLM. True routes
    every turn through the engine first; per-turn fall-through still
    applies via composer_semantics.md §7.2 acceptance gates.

    ``shadow`` (Phase 5e) toggles shadow mode. When True, the engine
    runs in addition to the LLM regardless of ``enabled``, and the
    decision returned ALWAYS uses the LLM's result (never the engine's).
    The engine's output + a head-to-head comparison are surfaced via
    ``ComposerRouterDecision.shadow_comparison`` for the orchestrator
    to persist as a ``composer_shadow_decision`` tool_trace. When
    ``shadow`` and ``enabled`` are both True, ``enabled`` wins —
    production paths shouldn't run BOTH engine and LLM in parallel
    every turn. ``shadow`` is intended for the eval-data-gathering
    phase before the engine is flag-on for production.

    The function is total — even on engine errors it returns a populated
    ``composer_result`` from the LLM fallback. Engine exceptions don't
    propagate; they're caught and treated as a fall-through with
    ``fallback_reason="engine_error"``.
    """
    sets_list = list(retrieved_sets)

    # Production engine path (enabled=True wins over shadow).
    if enabled:
        return _route_engine_first(
            plan=plan,
            retrieved_sets=sets_list,
            combined_context=combined_context,
            composer_callable=composer_callable,
            graph=graph,
        )

    # Shadow mode: run both, return LLM, surface comparison for ops.
    if shadow:
        return _route_shadow(
            plan=plan,
            retrieved_sets=sets_list,
            combined_context=combined_context,
            composer_callable=composer_callable,
            graph=graph,
        )

    # Default disabled-and-not-shadow path: LLM only.
    return ComposerRouterDecision(
        composer_result=composer_callable(),
        used_engine=False,
        fallback_reason="engine_disabled",
        engine_confidence=None,
        yaml_gaps=(),
    )


def _route_engine_first(
    *,
    plan: RecommendationPlan,
    retrieved_sets: list[RetrievedSet],
    combined_context: CombinedContext,
    composer_callable: Callable[[], ComposerResult],
    graph: StyleGraph | None,
) -> ComposerRouterDecision:
    """Engine-first path. Eligibility → engine → fall-through to LLM."""
    eligible, reason = is_engine_eligible(combined_context, plan)
    if not eligible:
        return ComposerRouterDecision(
            composer_result=composer_callable(),
            used_engine=False,
            fallback_reason=reason,
            engine_confidence=None,
            yaml_gaps=(),
        )

    if graph is None:
        graph = load_style_graph()

    ctx = extract_tuple_context(combined_context)

    _engine_t0 = time.monotonic()
    try:
        result = compose_outfits(
            plan=plan, retrieved_sets=retrieved_sets, ctx=ctx, graph=graph,
        )
    except Exception:  # noqa: BLE001 — engine error must never break the turn
        engine_ms = int((time.monotonic() - _engine_t0) * 1000)
        return ComposerRouterDecision(
            composer_result=composer_callable(),
            used_engine=False,
            fallback_reason="engine_error",
            engine_confidence=None,
            yaml_gaps=(),
            engine_ms=engine_ms,
        )
    engine_ms = int((time.monotonic() - _engine_t0) * 1000)

    provenance_summary = _summarize_provenance(result)

    if result.composer_result is None:
        return ComposerRouterDecision(
            composer_result=composer_callable(),
            used_engine=False,
            fallback_reason=result.fallback_reason or "engine_declined",
            engine_confidence=result.confidence,
            yaml_gaps=result.yaml_gaps,
            engine_ms=engine_ms,
            provenance_summary=provenance_summary,
        )

    return ComposerRouterDecision(
        composer_result=result.composer_result,
        used_engine=True,
        fallback_reason=None,
        engine_confidence=result.confidence,
        yaml_gaps=result.yaml_gaps,
        engine_ms=engine_ms,
        provenance_summary=provenance_summary,
    )


def _route_shadow(
    *,
    plan: RecommendationPlan,
    retrieved_sets: list[RetrievedSet],
    combined_context: CombinedContext,
    composer_callable: Callable[[], ComposerResult],
    graph: StyleGraph | None,
) -> ComposerRouterDecision:
    """Shadow path: LLM is authoritative; engine runs for comparison.

    Sequential, not concurrent — keeps the implementation tractable
    and avoids the orchestrator needing to manage extra threads. The
    engine call adds ~300ms to the turn's wall time; intentional cost
    of the eval-gathering phase. Production callers should pass
    ``shadow=False``.
    """
    # Run LLM first so any LLM exception surfaces normally.
    llm_result = composer_callable()

    # Engine eligibility — if ineligible, we still ran the LLM (which
    # is the correct production behavior); just no comparison row.
    eligible, reason = is_engine_eligible(combined_context, plan)
    if not eligible:
        return ComposerRouterDecision(
            composer_result=llm_result,
            used_engine=False,
            fallback_reason=f"shadow:{reason}",
            engine_confidence=None,
            yaml_gaps=(),
            shadow_comparison=None,
        )

    if graph is None:
        graph = load_style_graph()
    ctx = extract_tuple_context(combined_context)

    _engine_t0 = time.monotonic()
    try:
        engine = compose_outfits(
            plan=plan, retrieved_sets=retrieved_sets, ctx=ctx, graph=graph,
        )
    except Exception:  # noqa: BLE001
        engine_ms = int((time.monotonic() - _engine_t0) * 1000)
        return ComposerRouterDecision(
            composer_result=llm_result,
            used_engine=False,
            fallback_reason="shadow:engine_error",
            engine_confidence=None,
            yaml_gaps=(),
            engine_ms=engine_ms,
            shadow_comparison=None,
        )
    engine_ms = int((time.monotonic() - _engine_t0) * 1000)

    # Build comparison only when engine produced output. Engine misses
    # surface as shadow_comparison=None; ops dashboards distinguish
    # via fallback_reason.
    shadow_comparison: Any = None
    if engine.composer_result is not None:
        from .quality import compare_composer_outputs

        shadow_comparison = {
            "engine_confidence": engine.confidence,
            "engine_yaml_gaps": list(engine.yaml_gaps),
            "engine_outfit_count": len(engine.composer_result.outfits),
            "llm_outfit_count": len(llm_result.outfits),
            "comparison": compare_composer_outputs(
                engine.composer_result, llm_result
            ),
        }

    return ComposerRouterDecision(
        composer_result=llm_result,
        used_engine=False,
        fallback_reason=(
            f"shadow:{engine.fallback_reason}" if engine.fallback_reason
            else "shadow:engine_accepted_but_shadow"
        ),
        engine_confidence=engine.confidence,
        yaml_gaps=engine.yaml_gaps,
        engine_ms=engine_ms,
        provenance_summary=_summarize_provenance(engine),
        shadow_comparison=shadow_comparison,
    )


__all__ = [
    "ComposerRouterDecision",
    "extract_tuple_context",
    "is_engine_eligible",
    "route_composer_plan",
]
