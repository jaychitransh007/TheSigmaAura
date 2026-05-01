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
