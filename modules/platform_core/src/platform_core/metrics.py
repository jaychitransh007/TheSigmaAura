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
    labelnames=("intent", "action", "status"),
)

aura_turn_duration_seconds = Histogram(
    "aura_turn_duration_seconds",
    "Per-stage turn latency (seconds).",
    labelnames=("stage",),
    buckets=_PIPELINE_BUCKETS,
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


def observe_turn_outcome(*, intent: str, action: str, status: str) -> None:
    try:
        aura_turn_total.labels(intent=intent or "", action=action or "", status=status).inc()
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
