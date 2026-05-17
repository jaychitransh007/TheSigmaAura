"""Prometheus metric definitions — Item 5 of Observability Hardening.

Centralises every metric the runtime emits so the `/metrics` endpoint,
the orchestrator stage hooks, and the LLM call sites all reference the
same `Counter` / `Histogram` / `Gauge` objects. Importing this module
twice is safe — `prometheus_client` deduplicates by name.

Naming follows the Prometheus best-practices guide:
    aura_<noun>_<unit_or_total>{label1, label2}

The histogram bucket lists are tuned for the latency profiles we've
observed in `turn_traces.steps[].latency_ms` so the percentile
estimates are accurate without an explosion in cardinality.
"""

from __future__ import annotations

from typing import Optional

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover — optional dep, but listed in requirements.txt
    _PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain"

    def generate_latest() -> bytes:
        return b"# prometheus_client not installed\n"

    class _NoOp:
        def labels(self, *args, **kwargs): return self
        def inc(self, *args, **kwargs): pass
        def dec(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
        def set(self, *args, **kwargs): pass
        def time(self):
            class _Ctx:
                def __enter__(self_inner): return self_inner
                def __exit__(self_inner, *a): pass
            return _Ctx()

    Counter = Histogram = Gauge = _NoOp  # type: ignore[assignment,misc]


# ── Bucket presets ────────────────────────────────────────────────────
# Pipeline-stage latencies span hundreds of ms (catalog search) to
# tens of seconds (parallel try-on rendering). 60s upper bound covers
# the long tail without losing precision near the typical mode.
_PIPELINE_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)

# LLM calls are slower on average but rarely above 30s.
_LLM_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0)

# External REST calls (Supabase) are fast — sub-second is typical.
_EXTERNAL_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0)


# ── RED metrics ───────────────────────────────────────────────────────

aura_turn_total = Counter(
    "aura_turn_total",
    "Total turns processed by the orchestrator, labelled by outcome.",
    # channel: "web" (legacy onboarding-gated) or "vibe_storefront" (Shopify
    # App Proxy chat that bypasses the gate). Added 2026-05-16 so operators
    # can slice success rates / response_type mix by channel — until then
    # vibe_storefront turns were indistinguishable from web in dashboards.
    labelnames=("intent", "action", "status", "channel"),
)

aura_turn_duration_seconds = Histogram(
    "aura_turn_duration_seconds",
    "Per-stage turn latency (seconds).",
    labelnames=("stage",),
    buckets=_PIPELINE_BUCKETS,
)

# D.S.3b — POST /v1/users/merge audit signal. The merge endpoint
# mutates conversations + four history tables; without this counter
# operators have no way to spot failed merges, stuck merges, or no-op
# merges. Labels:
#   status="success" — repo.merge_external_user_identity returned
#   status="noop"    — canonical == alias, short-circuited
#   status="failed"  — repo raised (Supabase / runtime error)
aura_user_merge_total = Counter(
    "aura_user_merge_total",
    "User-identity merges via /v1/users/merge, labelled by outcome.",
    labelnames=("status",),
)

aura_llm_call_total = Counter(
    "aura_llm_call_total",
    "Total LLM calls (and image-gen calls) by model and outcome.",
    labelnames=("service", "model", "status"),
)

aura_llm_call_duration_seconds = Histogram(
    "aura_llm_call_duration_seconds",
    "LLM call wall-clock latency (seconds).",
    labelnames=("service", "model"),
    buckets=_LLM_BUCKETS,
)

aura_llm_call_cost_usd = Counter(
    "aura_llm_call_cost_usd_total",
    "Total estimated USD cost across LLM calls (running sum).",
    labelnames=("service", "model"),
)

aura_external_call_duration_seconds = Histogram(
    "aura_external_call_duration_seconds",
    "Wall-clock latency for outbound HTTP calls to dependencies.",
    labelnames=("service", "operation", "status"),
    buckets=_EXTERNAL_BUCKETS,
)

aura_tryon_quality_gate_total = Counter(
    "aura_tryon_quality_gate_total",
    "Try-on quality gate evaluations.",
    labelnames=("passed",),
)

aura_in_flight_turns = Gauge(
    "aura_in_flight_turns",
    "Number of turns currently being processed by the orchestrator.",
)


# ── Composition engine (Phase 4.7+) ───────────────────────────────────
# The router emits one decision per cache-miss architect turn. Slicing
# by used_engine + fallback_reason gives the operational read-out for
# flag-on rollouts: how often the engine is accepted, which reasons
# dominate the fall-throughs (yaml_gap → stylist YAML expansion;
# needs_disambiguation → spec §4.2 review; low_confidence → §8
# threshold calibration). fallback_reason cardinality is bounded by
# the router's enum (currently 9 values + "none" sentinel) so this
# label is safe.
aura_composition_router_decision_total = Counter(
    "aura_composition_router_decision_total",
    "Composition router decisions, sliced by engine usage + fallback reason.",
    labelnames=("used_engine", "fallback_reason"),
)

# YAML load failures disable the engine for the rest of the process
# (orchestrator catches the exception, flips the flag off in-process).
# This counter exists so an alert can fire if the metric ticks at all,
# even though the user-visible behaviour is graceful (turn falls
# through to LLM). One increment per process per failure.
aura_composition_yaml_load_failure_total = Counter(
    "aura_composition_yaml_load_failure_total",
    "Composition engine YAML load failures (engine disabled in-process).",
)


# Canonicalize: per-axis result of the input-canonicalization pass.
# Tracks where the engine's vocabulary bridge fires and where it
# bottoms out at the threshold. The four results map to the four
# operational situations:
#   - exact: input already matches a YAML key (no embed call, free)
#   - matched_above_threshold: embedded + nearest-neighbour ≥ floor
#   - matched_below_threshold: embedded + nearest-neighbour < floor
#                              (engine flags YAML gap, falls through)
#   - api_error: embed call raised — input passes through raw
# Cardinality: 4 results × 5 axes = 20 series. Bounded and small.
aura_composition_canonicalize_result_total = Counter(
    "aura_composition_canonicalize_result_total",
    "Canonicalize per-axis result, sliced by axis + outcome.",
    labelnames=("axis", "result"),
)

# Wall-clock latency of the (single, batched) canonicalize embed call
# per turn. 0 entries mean every input exact-matched; non-zero entries
# correspond to the ~150ms text-embedding-3-small call. Reuses the
# external-bucket preset so dashboards have sub-second precision.
aura_composition_canonicalize_duration_seconds = Histogram(
    "aura_composition_canonicalize_duration_seconds",
    "Canonicalize wall-clock duration per turn (batched embed call).",
    buckets=_EXTERNAL_BUCKETS,
)


# Tool-trace insert failures: exists because the surrounding
# try/except in the orchestrator's trace-write call sites would
# otherwise hide a regression. PR #152 fixed the cache_hit
# constraint violation; if a future change reintroduces a
# constraint-violating value (or any other failure), this counter
# ticks and the alert pages.
aura_tool_traces_insert_failure_total = Counter(
    "aura_tool_traces_insert_failure_total",
    "tool_traces insert failures (caught + warning-logged in orchestrator).",
    labelnames=("tool_name",),
)


# Per-attribute composition status: counts how often each attribute
# survives clean vs needs relaxation vs gets omitted across engine
# turns. Aggregated WITHOUT the attribute label (3 series only) to
# keep cardinality flat — per-attribute granularity flows through
# the distillation_traces JSON for SQL drill-down.
aura_composition_attribute_status_total = Counter(
    "aura_composition_attribute_status_total",
    "Per-engine-turn count of attributes by relaxation status.",
    labelnames=("status",),
)

# Phase 5d — composer router decision counter. Same shape and rationale
# as aura_composition_router_decision_total; sliced by engine-acceptance
# and fallback_reason. fallback_reason cardinality is bounded by the
# composer router's enum (engine_disabled | anchor_present |
# followup_request | has_previous_recommendations |
# architect_plan_from_cache | engine_error | yaml_gap | low_picks |
# pool_too_sparse | low_confidence | engine_declined) so this label is
# safe.
aura_composer_router_decision_total = Counter(
    "aura_composer_router_decision_total",
    "Composer router decisions, sliced by engine usage + fallback reason.",
    labelnames=("used_engine", "fallback_reason"),
)

# Phase 5x.4a — open-axis user preferences observability.
# Cap-hit fires when a single item / tuple's cumulative hard_attr penalty
# would exceed _HARD_ATTR_PENALTY_CAP (currently 0.40) and gets clipped.
# Watching this tells us whether the cap is the right magnitude:
# - Frequent hits → cap is too tight, demoting items the user wanted
# - Never hits   → cap is unreachable, can be tightened or removed
# `stage` is "retrieval" (catalog_search_agent) or "tuple" (composer).
aura_hard_attr_penalty_cap_hit_total = Counter(
    "aura_hard_attr_penalty_cap_hit_total",
    "Hard-attr penalty cap clip events, sliced by stage.",
    labelnames=("stage",),
)

# Override fires when _apply_user_preferences_to_plan replaces a value
# the architect engine had derived from a YAML source (occasion default,
# weather rule, etc.) with the user's explicit preference. High override
# rate means user prefs are dominating; low rate means they're marginal.
# `attribute` is the PascalCase catalog attr (EmbellishmentLevel, etc.).
# Cardinality is bounded by the planner-prompt glossary (~15 attrs).
aura_user_preference_override_total = Counter(
    "aura_user_preference_override_total",
    "User-explicit preferences overriding architect-derived hard_attrs.",
    labelnames=("attribute",),
)

# Phase 5x.4 follow-up — per-attribute retrieval-stage violation
# counter. Ticks once per (item, attribute) that violated the
# architect's resolved allowed-value list during rerank. Lets us
# answer "which axis is doing all the work?" — high count for one
# attribute means it's driving most of the demotion; if its count
# is near-zero, the axis is dead weight and can be dropped from the
# whitelist without behavior change. Cardinality is bounded by the
# ~20 PascalCase keys in HARD_ATTR_TO_ITEM_FIELD.
aura_retrieval_attr_violation_total = Counter(
    "aura_retrieval_attr_violation_total",
    "Retrieval-stage hard_attr violations counted per attribute.",
    labelnames=("attribute",),
)


# May 11 2026 — composer-side per-rule violation counter. Companion to
# aura_retrieval_attr_violation_total but for the COMPOSER side of the
# pipeline. Ticks once per Violation emitted by score_tuple, labelled
# by rule name + is_hard. Lets dashboards / alerts answer in real-time:
#   - which pairing rule is firing the most?
#   - what's the hard-rule drop rate vs soft-rule penalty rate?
# Before this counter, that data only existed in distillation_traces
# JSON — visible only via Panel 26 SQL drill-down, never as a Prometheus
# alert trigger.
# Cardinality: ~15-20 series (current rule count × {hard, soft}); the
# is_hard label is a string ("true" / "false") because Prometheus labels
# don't accept bools.
aura_composer_rule_violation_total = Counter(
    "aura_composer_rule_violation_total",
    "Composer-stage pairing-rule violations per (rule, is_hard).",
    labelnames=("rule", "is_hard"),
)


# May 11 2026 — composer-side exception-applied counter. Ticks once
# per tuple per exception that fired (e.g., distributed_statement_
# exception suspending a rule, metallic_neutral_exception excluding
# items from a count). Exceptions currently SUPPRESS a violation
# rather than emit a positive signal, so without this counter an
# overly-lenient exception is invisible in dashboards. Cardinality:
# ~6 series (one per exception name × parent rule).
aura_composer_rule_exception_applied_total = Counter(
    "aura_composer_rule_exception_applied_total",
    "Composer-stage rule exceptions that suppressed or modified a violation.",
    labelnames=("rule", "exception"),
)


# May 11 2026 — planner-cache decision counter. Ticks once per
# orchestrator turn that consulted the planner_output_cache, labelled
# by outcome:
#   - hit:   cached CopilotPlanResult was served; planner LLM skipped
#   - miss:  no cache entry; planner LLM ran normally and the result
#            was written to the cache
#   - error: cache lookup threw (treated as miss, but tracked
#            separately so a degraded-DB spike doesn't masquerade as
#            a low hit-rate trend)
# Cardinality: 3 series, hard-bounded.
aura_planner_cache_decision_total = Counter(
    "aura_planner_cache_decision_total",
    "copilot_planner output-cache decisions per turn.",
    labelnames=("outcome",),
)


# May 8 2026 — try-on flag state counter (PR #185 observability gap).
# Ticks once per turn that reaches the try-on gate, labelled by whether
# the AURA_TRYON_ENABLED flag was on. Without this, "tryon stage slow"
# in production can't be distinguished from "tryon stage skipped" — the
# absence of latency observations is identical in both cases. Cardinality:
# 2 series (enabled=true|false). Bounded.
aura_tryon_flag_total = Counter(
    "aura_tryon_flag_total",
    "Try-on flag-gate decisions per turn (enabled=true means the stage ran).",
    labelnames=("enabled",),
)


# May 8 2026 — empty-retrieval relaxation outcome counter (PR #192
# observability gap). Ticks once per architect plan, labelled by the
# relaxation outcome: not_needed (first pass returned products),
# succeeded_level_N (N filters dropped before products surfaced),
# exhausted (all 3 levels dropped, still empty). Lets ops answer "is
# relaxation firing too often" (catalog content gap signal) and "is
# the sequence ordered right" (if level_3 dominates, earlier levels
# are pulling weight that the sequence should reflect). Cardinality:
# 5 series (not_needed | succeeded_level_1 | succeeded_level_2 |
# succeeded_level_3 | exhausted).
aura_retrieval_relaxation_total = Counter(
    "aura_retrieval_relaxation_total",
    "Empty-retrieval auto-relaxation outcomes per architect plan.",
    labelnames=("outcome",),
)


# May 8 2026 — catalog-search worker failure counter. Ticks once per
# query whose worker thread bubbled an exception past the inner
# similarity_search retry. Pre-fix the orchestrator just persisted
# "worker_failed" with no exception type; production turns
# c801683a / 3c85f046 / c688ebf7 all hit this path silently and the
# user got "couldn't find a strong match" with zero ops signal.
# Cardinality: bounded by exception-class names hit at runtime
# (typically <10 in practice). Truncated/sanitised at the call site.
aura_retrieval_worker_failure_total = Counter(
    "aura_retrieval_worker_failure_total",
    "Catalog-search worker thread failures per query, labelled by exception type.",
    labelnames=("error_type",),
)


# May 8 2026 — follow-up intent routing counter (PR #186/#190/#191/
# #198/#199 observability gap). Ticks once per follow-up turn at the
# composition router, labelled by intent + engine acceptance. The
# existing aura_composition_router_decision_total has used_engine and
# fallback_reason but no intent label, so per-intent acceptance rate
# (e.g., "is more_options actually 90% engine, or did the gate
# regress?") can't be answered from Prometheus today. This counter
# only ticks on follow-up turns; non-followup routing is already
# fully observable via the existing counter. Cardinality: 8 intents ×
# 2 (used_engine) = 16 series. Bounded by the ENGINE_FRIENDLY_FOLLOWUP_
# INTENTS set + the literal "none" sentinel for unrecognized intents.
aura_followup_intent_routing_total = Counter(
    "aura_followup_intent_routing_total",
    "Follow-up turn router decisions, sliced by intent and engine acceptance.",
    labelnames=("followup_intent", "used_engine"),
)


# May 8 2026 — per-axis YAML-gap confidence-loss counter (PRs #194/#197
# observability gap). For each YAML gap on each engine turn, ticks the
# counter for the gap's axis by the confidence delta the gap added
# (weight × YAML_GAP_PENALTY). Read with rate() to compute "average
# confidence loss attributable to body_shape gaps in the last hour"
# without joining gap-frequency to gap-impact. Pairs with the existing
# per-axis gap-frequency surfaced in distillation_traces (Panel 22) —
# this counter answers the impact question, that one answers the
# frequency question. Cardinality: 9 series (the keys of
# _YAML_GAP_AXIS_WEIGHTS) plus an "unknown" sentinel.
aura_composition_yaml_gap_impact_total = Counter(
    "aura_composition_yaml_gap_impact_total",
    "Cumulative YAML-gap confidence-loss per axis (sum of weight × YAML_GAP_PENALTY).",
    labelnames=("axis",),
)


# ── Convenience helpers ───────────────────────────────────────────────


def observe_turn_stage(stage: str, latency_ms: Optional[float]) -> None:
    """Record a pipeline stage latency. Tolerates ``None`` from the trace."""
    if latency_ms is None:
        return
    try:
        aura_turn_duration_seconds.labels(stage=stage).observe(float(latency_ms) / 1000.0)
    except Exception:  # noqa: BLE001 — never break the pipeline on metrics
        pass


def observe_llm_call(
    *,
    service: str,
    model: str,
    status: str,
    latency_ms: Optional[float],
    estimated_cost_usd: Optional[float] = None,
) -> None:
    """Record an LLM/image-gen call. Increments counter + histogram + cost."""
    try:
        aura_llm_call_total.labels(service=service, model=model, status=status).inc()
        if latency_ms is not None:
            aura_llm_call_duration_seconds.labels(service=service, model=model).observe(
                float(latency_ms) / 1000.0
            )
        if estimated_cost_usd is not None and estimated_cost_usd > 0:
            aura_llm_call_cost_usd.labels(service=service, model=model).inc(float(estimated_cost_usd))
    except Exception:  # noqa: BLE001
        pass


def observe_external_call(
    *,
    service: str,
    operation: str,
    status: str,
    latency_ms: Optional[float],
) -> None:
    if latency_ms is None:
        return
    try:
        aura_external_call_duration_seconds.labels(
            service=service, operation=operation, status=status,
        ).observe(float(latency_ms) / 1000.0)
    except Exception:  # noqa: BLE001
        pass


def observe_turn_outcome(
    *,
    intent: str,
    action: str,
    status: str,
    channel: str = "web",
) -> None:
    """Increment the turn-outcome counter.

    `channel` defaults to "web" so existing legacy callers (and
    pre-2026-05-16 tests) keep working without modification. The
    orchestrator passes the real channel (web or vibe_storefront)
    when invoking via the public process_turn path.
    """
    try:
        aura_turn_total.labels(
            intent=intent or "",
            action=action or "",
            # `or ""` mirrors the other label fallbacks above —
            # prometheus_client raises ValueError on a None label
            # value, which would lose the metric inside our try/except.
            status=status or "",
            channel=channel or "web",
        ).inc()
    except Exception:  # noqa: BLE001
        pass


def observe_user_merge(*, status: str) -> None:
    """Record a user-merge outcome. status ∈ {success, noop, failed}.
    Idempotent on the Counter side; safe to call from any code path."""
    try:
        aura_user_merge_total.labels(status=status or "unknown").inc()
    except Exception:  # noqa: BLE001
        pass


def observe_tryon_quality_gate(*, passed: bool) -> None:
    try:
        aura_tryon_quality_gate_total.labels(passed="true" if passed else "false").inc()
    except Exception:  # noqa: BLE001
        pass


def observe_composition_router_decision(
    *, used_engine: bool, fallback_reason: Optional[str]
) -> None:
    """Increment the router decision counter.

    ``fallback_reason`` is None on the engine-accepted path; the metric
    coerces None to ``"none"`` so the label set is never empty. All
    expected fallback-reason strings are bounded by the router's enum
    (engine_disabled | anchor_present | followup_request |
    has_previous_recommendations | no_direction | yaml_gap |
    low_confidence | needs_disambiguation | excessive_widening) so
    cardinality stays low."""
    try:
        aura_composition_router_decision_total.labels(
            used_engine="true" if used_engine else "false",
            fallback_reason=fallback_reason or "none",
        ).inc()
    except Exception:  # noqa: BLE001
        pass


def observe_composer_router_decision(
    *, used_engine: bool, fallback_reason: Optional[str]
) -> None:
    """Increment the composer router decision counter.

    ``fallback_reason`` is None on the engine-accepted path; coerced to
    ``"none"`` so the label set is never empty. Mirrors
    ``observe_composition_router_decision`` for symmetry."""
    try:
        aura_composer_router_decision_total.labels(
            used_engine="true" if used_engine else "false",
            fallback_reason=fallback_reason or "none",
        ).inc()
    except Exception:  # noqa: BLE001
        pass


def observe_composition_yaml_load_failure() -> None:
    """Tick the YAML load failure counter. Called from the orchestrator
    when load_style_graph raises; the engine is then disabled for the
    rest of the process and turns silently fall through to the LLM."""
    try:
        aura_composition_yaml_load_failure_total.inc()
    except Exception:  # noqa: BLE001
        pass


def observe_composition_canonicalize_result(*, axis: str, result: str) -> None:
    """Tick the per-axis canonicalize counter. ``result`` should be one
    of: ``"exact"`` (input matched a YAML key directly, no embed call),
    ``"matched_above_threshold"`` (embed + nearest-neighbour cleared the
    floor and replaced the input), ``"matched_below_threshold"`` (embed
    fired but no neighbour cleared the floor; raw value passes through
    and the engine flags a YAML gap), ``"api_error"`` (embed call
    raised). Unknown values still record so a future result label can't
    silently drop on the floor."""
    try:
        aura_composition_canonicalize_result_total.labels(
            axis=axis or "", result=result or "",
        ).inc()
    except Exception:  # noqa: BLE001
        pass


def observe_composition_canonicalize_duration(latency_ms: Optional[float]) -> None:
    """Record the canonicalize wall-clock duration. None / 0 / negative
    inputs are tolerated and skipped (no histogram observation)."""
    if latency_ms is None or latency_ms < 0:
        return
    try:
        aura_composition_canonicalize_duration_seconds.observe(
            float(latency_ms) / 1000.0
        )
    except Exception:  # noqa: BLE001
        pass


def observe_tool_traces_insert_failure(tool_name: str) -> None:
    """Tick the tool_traces insert failure counter. Called from the
    orchestrator's trace-write warning catch sites so a future
    regression that reintroduces a constraint violation is paged on."""
    try:
        aura_tool_traces_insert_failure_total.labels(
            tool_name=tool_name or "unknown",
        ).inc()
    except Exception:  # noqa: BLE001
        pass


def observe_hard_attr_penalty_cap_hit(stage: str) -> None:
    """Tick the hard-attr penalty-cap clip counter. ``stage`` is
    "retrieval" (catalog rerank) or "tuple" (composer scoring).
    Watch the rate to tune ``_HARD_ATTR_PENALTY_CAP`` — frequent hits
    suggest the cap is too tight, never hits suggest it's unreachable
    and can be removed."""
    try:
        aura_hard_attr_penalty_cap_hit_total.labels(
            stage=stage or "unknown",
        ).inc()
    except Exception:  # noqa: BLE001
        pass


def observe_user_preference_override(attribute: str) -> None:
    """Tick the user-preference-override counter, sliced by the
    PascalCase catalog attribute (EmbellishmentLevel, ContrastLevel,
    NecklineType, ...). Fires from
    ``_apply_user_preferences_to_plan`` whenever the planner's
    extracted_preferences value replaces an architect-derived
    hard_attrs value for the same attribute."""
    try:
        aura_user_preference_override_total.labels(
            attribute=attribute or "unknown",
        ).inc()
    except Exception:  # noqa: BLE001
        pass


def observe_retrieval_attr_violation(attribute: str, count: int = 1) -> None:
    """Tick the per-attribute retrieval violation counter.
    ``count`` lets callers batch-emit (e.g. "12 items in this
    RetrievedSet violated SleeveLength") with a single metric call
    rather than 12 individual ticks. Default 1 keeps single-event
    callers ergonomic. Negative or zero counts are skipped."""
    if count <= 0:
        return
    try:
        aura_retrieval_attr_violation_total.labels(
            attribute=attribute or "unknown",
        ).inc(count)
    except Exception:  # noqa: BLE001
        pass


def observe_composition_attribute_status(status: str) -> None:
    """Tick the per-attribute composition status counter. ``status``
    is one of: ``"clean"`` | ``"soft_relaxed"`` | ``"hard_widened"``
    | ``"omitted"``. Aggregates without per-attribute granularity to
    keep cardinality flat (3-4 series total)."""
    try:
        aura_composition_attribute_status_total.labels(
            status=status or "unknown",
        ).inc()
    except Exception:  # noqa: BLE001
        pass


def observe_tryon_flag_state(*, enabled: bool) -> None:
    """Tick the try-on flag state counter once per turn that reaches
    the try-on gate. ``enabled`` is the runtime value of
    AURA_TRYON_ENABLED for the orchestrator handling this turn."""
    try:
        aura_tryon_flag_total.labels(
            enabled="true" if enabled else "false",
        ).inc()
    except Exception:  # noqa: BLE001
        pass


def observe_retrieval_relaxation(*, outcome: str) -> None:
    """Tick the relaxation outcome counter. ``outcome`` is one of:
    ``"not_needed"`` | ``"succeeded_level_1"`` | ``"succeeded_level_2"``
    | ``"succeeded_level_3"`` | ``"exhausted"``. Unknown outcomes are
    still recorded under their literal label so a future relaxation-
    sequence change doesn't silently drop on the floor."""
    try:
        aura_retrieval_relaxation_total.labels(
            outcome=outcome or "unknown",
        ).inc()
    except Exception:  # noqa: BLE001
        pass


def observe_retrieval_worker_failure(error_type: str) -> None:
    """Tick the catalog-search worker-failure counter, labelled by
    exception type (e.g. ``KeyError``, ``ValidationError``, ``TypeError``).
    Empty / non-string types coerce to ``"unknown"`` so the label set
    stays well-formed."""
    try:
        aura_retrieval_worker_failure_total.labels(
            error_type=str(error_type or "").strip() or "unknown",
        ).inc()
    except Exception:  # noqa: BLE001
        pass


def observe_followup_intent_routing(
    *, followup_intent: Optional[str], used_engine: bool
) -> None:
    """Tick the per-intent follow-up routing counter. Call ONLY on
    follow-up turns (``is_followup=true``); non-followup turns are
    already covered by ``observe_composition_router_decision``.
    ``followup_intent`` may be None or empty when the planner failed
    to identify an intent — coerced to ``"none"`` so the label set
    stays well-formed."""
    try:
        aura_followup_intent_routing_total.labels(
            followup_intent=(followup_intent or "").strip() or "none",
            used_engine="true" if used_engine else "false",
        ).inc()
    except Exception:  # noqa: BLE001
        pass


def observe_composition_yaml_gap_impact(*, axis: str, impact: float) -> None:
    """Increment the per-axis confidence-loss counter by ``impact``
    (the value the gap subtracted from confidence — i.e. axis weight ×
    YAML_GAP_PENALTY). One call per gap per engine turn. Negative or
    zero impacts are skipped — confidence loss is a strictly positive
    delta in the engine's accounting."""
    if impact <= 0:
        return
    try:
        aura_composition_yaml_gap_impact_total.labels(
            axis=axis or "unknown",
        ).inc(float(impact))
    except Exception:  # noqa: BLE001
        pass


# ── Wave 2 (May 12 2026) — visibility for the wardrobe-anchor fallback
# chain introduced across PRs #275–#293 ─────────────────────────────────

# How often does each fallback path actually fire? Before this counter,
# we had no metric for "vision succeeded vs planner anchor took over vs
# no anchor at all" — only log lines. Three terminal sources, plus a
# catch-all when the orchestrator couldn't form an anchor from anything.
aura_wardrobe_enrichment_fallback_total = Counter(
    "aura_wardrobe_enrichment_fallback_total",
    "Per-turn wardrobe-anchor source after vision + planner fallback chain.",
    labelnames=("source",),  # vision_ok | planner_anchor | none
)


def observe_wardrobe_enrichment_fallback(*, source: str) -> None:
    """Record where this turn's wardrobe anchor came from.

    `source` is one of:
      - "vision_ok"      : gpt-5.2 vision returned non-empty category
      - "planner_anchor" : vision returned null/empty/timed-out,
                           planner.resolved_context.anchor_garment used
      - "none"           : neither path produced a usable anchor
                           (turn falls through to ask_clarification or
                           a generic recommendation without an anchor)
    """
    if not source:
        return
    try:
        aura_wardrobe_enrichment_fallback_total.labels(source=source).inc()
    except Exception:  # noqa: BLE001
        pass


# Counts catalog rows skipped because they're tagged deleted_from_source.
# Two paths can skip a row: the orchestrator's wardrobe-first fallback
# (Postgrest filter at fetch time) and the catalog_search vector path
# (Python filter at hydration time). Splitting by path so a regression
# in one doesn't hide behind the other's rate.
aura_catalog_deleted_skipped_total = Counter(
    "aura_catalog_deleted_skipped_total",
    "Catalog rows excluded from recommendations because row_status="
    "'deleted_from_source' (404 / Product-Not-Found on merchant URL).",
    labelnames=("path",),  # orchestrator_rows | catalog_search
)


def observe_catalog_deleted_skipped(*, path: str, count: int = 1) -> None:
    """Record N catalog rows excluded for being deleted-from-source."""
    if not path or count <= 0:
        return
    try:
        aura_catalog_deleted_skipped_total.labels(path=path).inc(count)
    except Exception:  # noqa: BLE001
        pass


# Histogram of planner-emitted anchor_garment.confidence. Used to
# calibrate _PLANNER_ANCHOR_CONFIDENCE_THRESHOLD (currently 0.5).
# Buckets in 0.1 steps from 0 to 1 — the field is bounded so finer
# buckets don't buy resolution and would inflate cardinality.
aura_planner_anchor_confidence = Histogram(
    "aura_planner_anchor_confidence",
    "Distribution of planner-emitted anchor_garment.confidence per turn.",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)


def observe_planner_anchor_confidence(confidence: Optional[float]) -> None:
    """Record the planner's anchor_garment.confidence for this turn.

    Skip when the planner didn't extract an anchor at all (confidence=0
    AND empty category/subtype) — that's a different signal from "low
    confidence on an extracted anchor". Callers should pass None or
    skip the call entirely in the no-anchor case.
    """
    if confidence is None:
        return
    try:
        aura_planner_anchor_confidence.observe(float(confidence))
    except Exception:  # noqa: BLE001
        pass


# PR #330 follow-up — wardrobe shoe-filter counter. Ticks once per turn
# with the count of shoe items stripped from the user's wardrobe before
# planning. Shoes aren't styled by the system (no pairing rules, no
# catalog coverage), so they're filtered at process_turn entry. This
# counter answers two questions: (1) what fraction of users have shoes
# saved? (signal for whether shoe support is worth building), and (2)
# is the filter actually doing anything? (sudden zero = regression).
# Cardinality: unbounded label values are NOT used — the count is
# observed into a histogram. Bucketed to capture 0 / 1-2 / 3-5 / 6+
# patterns without label cardinality.
aura_wardrobe_shoe_filter_count = Histogram(
    "aura_wardrobe_shoe_filter_count",
    "Number of shoe items filtered from the wardrobe per turn (0 when no shoes).",
    buckets=(0, 1, 2, 3, 5, 10, 20),
)


def observe_wardrobe_shoe_filter(*, filtered_count: int) -> None:
    """Record how many shoe items were filtered from the wardrobe on
    this turn. Always called once per turn, including 0 (which is the
    common case — most users don't have shoes saved).
    """
    try:
        aura_wardrobe_shoe_filter_count.observe(max(0, int(filtered_count or 0)))
    except Exception:  # noqa: BLE001
        pass


# 2026-05-17 — Vibe onboarding endpoint observability. Until now the
# in-chat onboarding endpoints (profile/ensure, profile/partial,
# images/{category}, status/{user_id}, wardrobe/{user_id},
# analysis/start-phase{1,2}, analysis/{user_id}) emitted zero metrics
# and zero structured logs. If a customer reports "onboarding broke"
# in production we have no way to slice request volume, error rate, or
# 404-vs-error breakdown — the symmetric opposite of the turn loop
# which is well-instrumented via aura_turn_total.
#
# Labels:
#   endpoint: short stable name for the route (profile_ensure,
#             profile_partial, image_upload, status_read, wardrobe_list,
#             analysis_start_phase1, analysis_start_phase2,
#             analysis_status_read). Cardinality: ~10 series.
#   status:   coarse outcome — "success" (2xx), "not_found" (404),
#             "bad_request" (4xx other than 401/404), "unauthorized"
#             (401/403), "failed" (5xx / unhandled). Five values.
#   channel:  "web" (default for engine-direct/agentic-app traffic) or
#             "vibe_storefront" (request was made by the Vibe Shopify
#             app and the route received ?channel=vibe_storefront).
#             Same convention as aura_turn_total.channel.
# Cardinality: ~10 × 5 × 2 = 100 series. Well bounded.
aura_onboarding_endpoint_total = Counter(
    "aura_onboarding_endpoint_total",
    "Vibe onboarding endpoint outcomes per (endpoint, status, channel).",
    labelnames=("endpoint", "status", "channel"),
)


def observe_onboarding_endpoint(
    *, endpoint: str, status: str, channel: str = "web",
) -> None:
    """Tick the onboarding endpoint outcome counter.

    Call once per request — typically on the success return path AND on
    the HTTPException-raising paths so the success/failure split is
    accurate. status should be the coarse outcome label, not the raw
    HTTP code: pass "success" / "not_found" / "bad_request" /
    "unauthorized" / "failed". Unknown values still record (no crash)
    so a future label addition doesn't drop on the floor."""
    try:
        aura_onboarding_endpoint_total.labels(
            endpoint=endpoint or "unknown",
            status=status or "unknown",
            channel=channel or "web",
        ).inc()
    except Exception:  # noqa: BLE001
        pass


# Companion histogram for /images/{category} uploads. Image size is a
# meaningful operational signal: if p99 trends toward the 10MB limit,
# customers are routinely hitting 413s; if p50 drops sharply, the
# client-side crop pipeline likely regressed. Buckets cover 50KB
# (tiny / heavily-compressed) to 10MB (the route's hard cap) on a
# log-ish scale. Cardinality: 2 categories × 2 channels = 4 series.
aura_onboarding_image_bytes = Histogram(
    "aura_onboarding_image_bytes",
    "Onboarding photo upload size in bytes, sliced by category + channel.",
    labelnames=("category", "channel"),
    buckets=(
        50_000,
        200_000,
        500_000,
        1_000_000,
        2_000_000,
        5_000_000,
        10_000_000,
    ),
)


def observe_onboarding_image_bytes(
    *, category: str, size_bytes: int, channel: str = "web",
) -> None:
    """Record an onboarding image upload's byte size. Negative / zero /
    non-int sizes are skipped (the upload path validates >0 before we
    get here, but be defensive)."""
    try:
        n = int(size_bytes)
    except Exception:  # noqa: BLE001
        return
    if n <= 0:
        return
    try:
        aura_onboarding_image_bytes.labels(
            category=category or "unknown",
            channel=channel or "web",
        ).observe(n)
    except Exception:  # noqa: BLE001
        pass


# PR #333 follow-up — item description source counter. Ticks once per
# item shipped on an outfit card, labelled by where the description
# came from: ``llm`` (composer emitted ``item_descriptions``) or
# ``synthesized`` (deterministic template from catalog attributes).
# The split tracks how often the LLM composer ran vs. the engine
# path — a quality signal because synthesized copy is uniform-tone
# templated, whereas LLM copy is stylist-voice. If the ratio shifts
# unexpectedly toward "synthesized" we're shipping more uniform-tone
# cards than expected. Cardinality: 2 series.
aura_item_description_source_total = Counter(
    "aura_item_description_source_total",
    "Items shipped per turn labelled by description source (llm | synthesized).",
    labelnames=("source",),
)


def observe_item_description_source(*, source: str) -> None:
    """Tick the description-source counter for one item. ``source`` is
    one of ``"llm"`` | ``"synthesized"``. Unknown values still pass
    through under their literal label so a future source addition
    doesn't silently drop on the floor."""
    try:
        aura_item_description_source_total.labels(
            source=source or "unknown",
        ).inc()
    except Exception:  # noqa: BLE001
        pass
