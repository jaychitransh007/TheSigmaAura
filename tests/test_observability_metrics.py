"""Tests for the new Phase 4 observability metric helpers.

The helpers all degrade to no-ops when prometheus_client is absent
(the existing _NoOp pattern in metrics.py). When it's installed, the
counters increment as documented and labels stay within the bounded
domain agreed on at design time."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "platform_core" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from platform_core.metrics import (
    observe_composition_attribute_status,
    observe_composition_canonicalize_duration,
    observe_composition_canonicalize_result,
    observe_tool_traces_insert_failure,
)


def _prometheus_available() -> bool:
    try:
        import prometheus_client  # noqa: F401
        return True
    except ImportError:
        return False


class CanonicalizeResultCounterTests(unittest.TestCase):
    def test_helper_safe_without_prometheus(self):
        observe_composition_canonicalize_result(axis="occasion", result="exact")
        observe_composition_canonicalize_result(axis="weather", result="matched_above_threshold")
        observe_composition_canonicalize_result(axis="archetype", result="matched_below_threshold")
        observe_composition_canonicalize_result(axis="risk_tolerance", result="api_error")

    def test_increments_when_prometheus_installed(self):
        if not _prometheus_available():
            self.skipTest("prometheus_client not installed")
        from platform_core.metrics import (
            aura_composition_canonicalize_result_total,
        )
        before = aura_composition_canonicalize_result_total.labels(
            axis="occasion", result="exact",
        )._value.get()
        observe_composition_canonicalize_result(axis="occasion", result="exact")
        after = aura_composition_canonicalize_result_total.labels(
            axis="occasion", result="exact",
        )._value.get()
        self.assertEqual(after - before, 1)

    def test_empty_axis_or_result_coerces_to_empty_string_label(self):
        # Prometheus rejects None labels; the helper coerces both args
        # to "" so a malformed call still increments cleanly. Bounded
        # cardinality (one label series instead of a crash).
        observe_composition_canonicalize_result(axis="", result="")
        observe_composition_canonicalize_result(axis=None, result=None)  # type: ignore[arg-type]


class CanonicalizeDurationHistogramTests(unittest.TestCase):
    def test_helper_safe_without_prometheus(self):
        observe_composition_canonicalize_duration(150)

    def test_none_skipped(self):
        # No-op on None — caller hands None when no embed call fired.
        observe_composition_canonicalize_duration(None)

    def test_negative_skipped(self):
        observe_composition_canonicalize_duration(-5)

    def test_zero_recorded(self):
        # Zero is a meaningful observation (every input exact-matched,
        # batched-embed call took ~0ms wall-clock). Don't skip it.
        observe_composition_canonicalize_duration(0)


class ToolTracesInsertFailureCounterTests(unittest.TestCase):
    def test_helper_safe_without_prometheus(self):
        observe_tool_traces_insert_failure("tryon_render")

    def test_increments_when_prometheus_installed(self):
        if not _prometheus_available():
            self.skipTest("prometheus_client not installed")
        from platform_core.metrics import (
            aura_tool_traces_insert_failure_total,
        )
        before = aura_tool_traces_insert_failure_total.labels(
            tool_name="tryon_render",
        )._value.get()
        observe_tool_traces_insert_failure("tryon_render")
        after = aura_tool_traces_insert_failure_total.labels(
            tool_name="tryon_render",
        )._value.get()
        self.assertEqual(after - before, 1)

    def test_empty_tool_name_coerces_to_unknown(self):
        observe_tool_traces_insert_failure("")
        observe_tool_traces_insert_failure(None)  # type: ignore[arg-type]


class CompositionAttributeStatusCounterTests(unittest.TestCase):
    def test_helper_safe_without_prometheus(self):
        for s in ("clean", "soft_relaxed", "hard_widened", "omitted"):
            observe_composition_attribute_status(s)

    def test_increments_when_prometheus_installed(self):
        if not _prometheus_available():
            self.skipTest("prometheus_client not installed")
        from platform_core.metrics import (
            aura_composition_attribute_status_total,
        )
        before = aura_composition_attribute_status_total.labels(
            status="omitted",
        )._value.get()
        observe_composition_attribute_status("omitted")
        observe_composition_attribute_status("omitted")
        after = aura_composition_attribute_status_total.labels(
            status="omitted",
        )._value.get()
        self.assertEqual(after - before, 2)


if __name__ == "__main__":
    unittest.main()
