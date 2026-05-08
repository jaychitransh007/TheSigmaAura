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
    observe_composition_yaml_gap_impact,
    observe_followup_intent_routing,
    observe_retrieval_relaxation,
    observe_tool_traces_insert_failure,
    observe_tryon_flag_state,
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


class TryonFlagStateCounterTests(unittest.TestCase):
    def test_helper_safe_without_prometheus(self):
        observe_tryon_flag_state(enabled=True)
        observe_tryon_flag_state(enabled=False)

    def test_increments_when_prometheus_installed(self):
        if not _prometheus_available():
            self.skipTest("prometheus_client not installed")
        from platform_core.metrics import aura_tryon_flag_total
        before_on = aura_tryon_flag_total.labels(enabled="true")._value.get()
        before_off = aura_tryon_flag_total.labels(enabled="false")._value.get()
        observe_tryon_flag_state(enabled=True)
        observe_tryon_flag_state(enabled=False)
        observe_tryon_flag_state(enabled=False)
        after_on = aura_tryon_flag_total.labels(enabled="true")._value.get()
        after_off = aura_tryon_flag_total.labels(enabled="false")._value.get()
        self.assertEqual(after_on - before_on, 1)
        self.assertEqual(after_off - before_off, 2)


class RetrievalRelaxationCounterTests(unittest.TestCase):
    def test_helper_safe_without_prometheus(self):
        for outcome in (
            "not_needed",
            "succeeded_level_1",
            "succeeded_level_2",
            "succeeded_level_3",
            "exhausted",
        ):
            observe_retrieval_relaxation(outcome=outcome)

    def test_increments_when_prometheus_installed(self):
        if not _prometheus_available():
            self.skipTest("prometheus_client not installed")
        from platform_core.metrics import aura_retrieval_relaxation_total
        before = aura_retrieval_relaxation_total.labels(
            outcome="exhausted",
        )._value.get()
        observe_retrieval_relaxation(outcome="exhausted")
        after = aura_retrieval_relaxation_total.labels(
            outcome="exhausted",
        )._value.get()
        self.assertEqual(after - before, 1)

    def test_unknown_outcome_recorded(self):
        # Future-proofing: an unrecognized outcome label still records
        # rather than getting silently dropped, so a sequence change
        # can't lose data without showing up as a new label series.
        observe_retrieval_relaxation(outcome="future_value")


class FollowupIntentRoutingCounterTests(unittest.TestCase):
    def test_helper_safe_without_prometheus(self):
        observe_followup_intent_routing(
            followup_intent="more_options", used_engine=True,
        )

    def test_increments_when_prometheus_installed(self):
        if not _prometheus_available():
            self.skipTest("prometheus_client not installed")
        from platform_core.metrics import aura_followup_intent_routing_total
        before = aura_followup_intent_routing_total.labels(
            followup_intent="change_color", used_engine="true",
        )._value.get()
        observe_followup_intent_routing(
            followup_intent="change_color", used_engine=True,
        )
        after = aura_followup_intent_routing_total.labels(
            followup_intent="change_color", used_engine="true",
        )._value.get()
        self.assertEqual(after - before, 1)

    def test_empty_intent_coerces_to_none(self):
        observe_followup_intent_routing(followup_intent="", used_engine=False)
        observe_followup_intent_routing(followup_intent=None, used_engine=False)


class CompositionYamlGapImpactCounterTests(unittest.TestCase):
    def test_helper_safe_without_prometheus(self):
        observe_composition_yaml_gap_impact(axis="body_shape", impact=0.30)

    def test_increments_when_prometheus_installed(self):
        if not _prometheus_available():
            self.skipTest("prometheus_client not installed")
        from platform_core.metrics import (
            aura_composition_yaml_gap_impact_total,
        )
        before = aura_composition_yaml_gap_impact_total.labels(
            axis="body_shape",
        )._value.get()
        observe_composition_yaml_gap_impact(axis="body_shape", impact=0.30)
        observe_composition_yaml_gap_impact(axis="body_shape", impact=0.30)
        after = aura_composition_yaml_gap_impact_total.labels(
            axis="body_shape",
        )._value.get()
        # Counter accumulates the impact value (a Counter.inc(amount)).
        self.assertAlmostEqual(after - before, 0.60, places=4)

    def test_zero_or_negative_skipped(self):
        # The accounting expects strictly-positive impact values.
        # Zero / negative would corrupt the running sum and probably
        # signals a bug upstream — silently drop rather than record.
        observe_composition_yaml_gap_impact(axis="body_shape", impact=0)
        observe_composition_yaml_gap_impact(axis="body_shape", impact=-0.1)


if __name__ == "__main__":
    unittest.main()
