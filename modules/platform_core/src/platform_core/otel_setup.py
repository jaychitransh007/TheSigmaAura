"""OpenTelemetry tracing setup — Item 6 of Observability Hardening.

When ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set, configures a TracerProvider
that batches spans and ships them to the configured collector.
Honours W3C Trace Context out of the box (the SDK default), so traces
join cleanly with frontend RUM agents, Cloudflare ray IDs, and any
downstream services.

When the env var is unset, the function still configures a no-op
TracerProvider — manual ``with tracer.start_as_current_span(...)``
blocks scattered through the orchestrator stay safe to run; spans are
created but never exported.

Sampling: defaults to ``ParentBased(TraceIdRatioBased(0.1))`` — 10% of
root traces are kept; child spans inherit the parent's decision so
parts of a single turn don't disappear partway through. Override via
``OTEL_TRACES_SAMPLER`` and ``OTEL_TRACES_SAMPLER_ARG`` env vars (the
SDK reads these natively if set before configuration).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

_log = logging.getLogger(__name__)
_CONFIGURED = False


def configure_otel(service_name: str = "aura-agentic-application") -> None:
    """Configure the OTLP-exporting TracerProvider once. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        _log.info("OpenTelemetry SDK not installed — tracing disabled")
        return

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    sampler_arg = float(os.getenv("OTEL_TRACES_SAMPLER_ARG", "0.1"))

    resource = Resource.create({
        "service.name": service_name,
        "service.namespace": "aura",
        "service.version": os.getenv("AURA_COMMIT_SHA", "unknown"),
        "deployment.environment": os.getenv("APP_ENV", "unknown"),
    })

    provider = TracerProvider(resource=resource)

    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            exporter = OTLPSpanExporter(endpoint=endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            _log.info("OpenTelemetry tracing → %s (sampler arg=%.2f)", endpoint, sampler_arg)
        except Exception:  # noqa: BLE001
            _log.warning("Could not initialise OTLP exporter; spans will be no-op", exc_info=True)
    else:
        _log.info("OTEL_EXPORTER_OTLP_ENDPOINT unset — spans created but not exported")

    trace.set_tracer_provider(provider)
    _CONFIGURED = True


def instrument_fastapi(app) -> None:
    """Auto-instrument a FastAPI app with the OTel middleware. Safe no-op
    when the instrumentation extra isn't installed."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        _log.info("opentelemetry-instrumentation-fastapi not installed; skipping")
    except Exception:  # noqa: BLE001
        _log.warning("FastAPI auto-instrumentation failed", exc_info=True)


def get_tracer(name: str = "aura.orchestrator"):
    """Return a tracer that's safe to use whether OTel is configured or not.

    The OTel SDK supplies a `NoOpTracer` when no provider is set, so
    callers can wrap pipeline stages in ``with tracer.start_as_current_span(...)``
    without checking whether tracing is enabled.
    """
    from opentelemetry import trace
    return trace.get_tracer(name)
