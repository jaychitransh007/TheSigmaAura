"""Tests for OpenTelemetry setup (Item 6, May 1, 2026)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


class OtelSetupTests(unittest.TestCase):
    def test_get_tracer_returns_a_tracer_when_otel_unconfigured(self) -> None:
        from platform_core.otel_setup import get_tracer
        # Even without configure_otel, get_tracer must return something
        # callable that supports start_as_current_span.
        tracer = get_tracer("aura.test")
        self.assertTrue(hasattr(tracer, "start_as_current_span"))
        with tracer.start_as_current_span("test-span"):
            pass

    def test_configure_otel_no_op_when_endpoint_unset(self) -> None:
        """No exporter is added when OTEL_EXPORTER_OTLP_ENDPOINT is unset.
        configure_otel still installs a TracerProvider so callers can
        create spans without raising."""
        from platform_core import otel_setup
        # Reset module state to allow re-configure in test
        otel_setup._CONFIGURED = False
        with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_ENDPOINT": ""}, clear=False):
            otel_setup.configure_otel("aura-test")
        # Should be configured now (idempotent on repeat call)
        self.assertTrue(otel_setup._CONFIGURED)

    def test_configure_otel_is_idempotent(self) -> None:
        from platform_core import otel_setup
        otel_setup._CONFIGURED = False
        otel_setup.configure_otel("aura-test")
        otel_setup.configure_otel("aura-test")  # Second call should no-op
        self.assertTrue(otel_setup._CONFIGURED)

    def test_span_attributes_persist_in_inmemory_exporter(self) -> None:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        # Build an isolated provider for this test (don't pollute global state)
        provider = TracerProvider()
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("aura.test")

        with tracer.start_as_current_span("aura.process_turn") as span:
            span.set_attribute("aura.turn_id", "t-42")
            span.set_attribute("aura.intent", "occasion_recommendation")
            with tracer.start_as_current_span("aura.copilot_planner") as child:
                child.set_attribute("aura.model", "gpt-5.4")

        spans = exporter.get_finished_spans()
        self.assertEqual(2, len(spans))
        names = {s.name for s in spans}
        self.assertEqual({"aura.process_turn", "aura.copilot_planner"}, names)
        # Find the parent span and verify attribute
        parent = next(s for s in spans if s.name == "aura.process_turn")
        self.assertEqual("t-42", parent.attributes["aura.turn_id"])


if __name__ == "__main__":
    unittest.main()
