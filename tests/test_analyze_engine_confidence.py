"""Tests for the engine-confidence analysis harness
(``ops/scripts/analyze_engine_confidence.py``).

Verifies the pure analysis function on synthetic ``composition_router_decision``
output_json shapes without needing real Supabase data:

- accepted vs fallback counting
- fallback-reason distribution
- recoverable-only filtering (low_confidence + yaml_gap)
- per-axis impact accumulation
- provenance hot-spot tallies
- thin-sample suppression in the report
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (_ROOT, _ROOT / "ops" / "scripts"):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from analyze_engine_confidence import (  # type: ignore[import-not-found]
    CONFIDENCE_THRESHOLD,
    MIN_REJECTIONS_FOR_RANKING,
    _analyze,
    _format_report,
    _is_recoverable_rejection,
)


def _row(
    used_engine: bool,
    fallback_reason: str | None = None,
    engine_confidence: float | None = None,
    yaml_gaps: list[str] | None = None,
    per_axis_gap_impact: dict | None = None,
    provenance_summary: dict | None = None,
) -> dict:
    return {
        "output_json": {
            "used_engine": used_engine,
            "fallback_reason": fallback_reason,
            "engine_confidence": engine_confidence,
            "yaml_gaps": yaml_gaps or [],
            "per_axis_gap_impact": per_axis_gap_impact or {},
            "provenance_summary": provenance_summary or {},
        }
    }


class IsRecoverableRejectionTests(unittest.TestCase):
    def test_low_confidence_is_recoverable(self):
        self.assertTrue(_is_recoverable_rejection("low_confidence"))

    def test_yaml_gap_is_recoverable(self):
        self.assertTrue(_is_recoverable_rejection("yaml_gap"))

    def test_anchor_present_is_not_recoverable(self):
        # Input-shape rejection — no weight tuning would change this.
        self.assertFalse(_is_recoverable_rejection("anchor_present"))

    def test_engine_disabled_is_not_recoverable(self):
        self.assertFalse(_is_recoverable_rejection("engine_disabled"))

    def test_none_is_not_recoverable(self):
        self.assertFalse(_is_recoverable_rejection(None))


class AnalyzeTests(unittest.TestCase):
    def test_empty_input(self):
        out = _analyze([])
        self.assertEqual(0, out["n_total"])
        self.assertEqual(0, out["n_engine"])
        self.assertEqual(0, out["n_fallback"])
        self.assertEqual(0, out["n_recoverable"])

    def test_pure_accept_population(self):
        rows = [_row(used_engine=True), _row(used_engine=True), _row(used_engine=True)]
        out = _analyze(rows)
        self.assertEqual(3, out["n_total"])
        self.assertEqual(3, out["n_engine"])
        self.assertEqual(0, out["n_fallback"])
        self.assertEqual(0, out["n_recoverable"])

    def test_mixed_accept_and_reject(self):
        rows = [
            _row(used_engine=True),
            _row(used_engine=False, fallback_reason="anchor_present"),
            _row(used_engine=False, fallback_reason="low_confidence",
                 engine_confidence=0.3,
                 per_axis_gap_impact={"weather_context": 0.16}),
            _row(used_engine=False, fallback_reason="yaml_gap",
                 engine_confidence=0.4,
                 per_axis_gap_impact={"occasion_signal": 0.24}),
        ]
        out = _analyze(rows)
        self.assertEqual(4, out["n_total"])
        self.assertEqual(1, out["n_engine"])
        self.assertEqual(3, out["n_fallback"])
        # anchor_present is NOT recoverable; low_confidence + yaml_gap are.
        self.assertEqual(2, out["n_recoverable"])
        self.assertEqual([0.3, 0.4], sorted(out["rec_confidences"]))
        self.assertAlmostEqual(0.16, out["rec_axis_impact"]["weather_context"], places=3)
        self.assertAlmostEqual(0.24, out["rec_axis_impact"]["occasion_signal"], places=3)

    def test_per_axis_impact_accumulates_across_turns(self):
        rows = [
            _row(used_engine=False, fallback_reason="low_confidence",
                 engine_confidence=0.2,
                 per_axis_gap_impact={"weather_context": 0.16}),
            _row(used_engine=False, fallback_reason="low_confidence",
                 engine_confidence=0.3,
                 per_axis_gap_impact={"weather_context": 0.16, "occasion_signal": 0.24}),
        ]
        out = _analyze(rows)
        self.assertAlmostEqual(0.32, out["rec_axis_impact"]["weather_context"], places=3)
        self.assertAlmostEqual(0.24, out["rec_axis_impact"]["occasion_signal"], places=3)
        self.assertEqual(2, out["rec_axis_count"]["weather_context"])
        self.assertEqual(1, out["rec_axis_count"]["occasion_signal"])

    def test_provenance_hot_spots_tallied(self):
        rows = [
            _row(used_engine=False, fallback_reason="low_confidence",
                 engine_confidence=0.3,
                 provenance_summary={
                     "omitted": ["FabricDrape"],
                     "hard_widened": ["FormalityLevel", "SleeveLength"],
                     "soft_relaxed": [],
                 }),
            _row(used_engine=False, fallback_reason="low_confidence",
                 engine_confidence=0.3,
                 provenance_summary={
                     "omitted": ["FabricDrape", "PatternScale"],
                     "hard_widened": ["FormalityLevel"],
                     "soft_relaxed": ["ColorSaturation"],
                 }),
        ]
        out = _analyze(rows)
        self.assertEqual(2, out["rec_omitted"]["FabricDrape"])
        self.assertEqual(1, out["rec_omitted"]["PatternScale"])
        self.assertEqual(2, out["rec_hard_widened"]["FormalityLevel"])
        self.assertEqual(1, out["rec_soft_relaxed"]["ColorSaturation"])

    def test_non_recoverable_rejection_does_not_pollute_axis_impact(self):
        # anchor_present rejection has per_axis_gap_impact too (in
        # principle), but it shouldn't bleed into recoverable analysis.
        rows = [
            _row(used_engine=False, fallback_reason="anchor_present",
                 per_axis_gap_impact={"occasion_signal": 0.99}),
            _row(used_engine=False, fallback_reason="low_confidence",
                 engine_confidence=0.4,
                 per_axis_gap_impact={"occasion_signal": 0.10}),
        ]
        out = _analyze(rows)
        # Only the low_confidence row's impact is counted.
        self.assertAlmostEqual(0.10, out["rec_axis_impact"]["occasion_signal"], places=3)
        self.assertEqual(1, out["rec_axis_count"]["occasion_signal"])


class FormatReportTests(unittest.TestCase):
    def test_empty_window_renders_actionable_message(self):
        analysis = _analyze([])
        report = _format_report(analysis, "test window")
        self.assertIn("No `composition_router_decision` rows found", report)
        # Sanity — actionable next-step hints should appear:
        self.assertIn("AURA_COMPOSITION_ENGINE_ENABLED", report)

    def test_thin_recoverable_sample_suppresses_axis_ranking(self):
        # Only 2 recoverable rejections — well below MIN_REJECTIONS_FOR_RANKING.
        rows = [
            _row(used_engine=False, fallback_reason="low_confidence",
                 engine_confidence=0.3,
                 per_axis_gap_impact={"occasion_signal": 0.20}),
            _row(used_engine=False, fallback_reason="low_confidence",
                 engine_confidence=0.4,
                 per_axis_gap_impact={"occasion_signal": 0.20}),
        ]
        analysis = _analyze(rows)
        report = _format_report(analysis, "test window")
        # Header still renders; ranking section explicitly suppressed.
        self.assertIn("Recoverable rejections", report)
        self.assertIn("Sample size 2", report)
        self.assertIn("ranking suppressed", report)
        # Top-axes table should NOT appear.
        self.assertNotIn("Top axes by cumulative confidence loss", report)

    def test_full_sample_shows_axis_ranking(self):
        # Generate 25 recoverable rejections, all attributing impact to
        # one axis ("occasion_signal") — should clear the floor and
        # surface the ranking table.
        rows = []
        for _ in range(25):
            rows.append(_row(
                used_engine=False, fallback_reason="low_confidence",
                engine_confidence=0.30,
                per_axis_gap_impact={"occasion_signal": 0.24},
            ))
        # Add a couple of accepted turns so accept rate is non-100%.
        rows.extend([_row(used_engine=True), _row(used_engine=True)])
        analysis = _analyze(rows)
        self.assertGreaterEqual(analysis["n_recoverable"], MIN_REJECTIONS_FOR_RANKING)
        report = _format_report(analysis, "test window")
        self.assertIn("Top axes by cumulative confidence loss", report)
        self.assertIn("`occasion_signal`", report)
        # Heuristic recovery section also renders for non-thin samples.
        self.assertIn("Heuristic recovery estimate", report)


if __name__ == "__main__":
    unittest.main()
