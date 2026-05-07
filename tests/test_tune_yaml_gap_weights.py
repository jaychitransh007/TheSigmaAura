"""Tests for the YAML-gap-weight tuning harness
(`ops/scripts/tune_yaml_gap_weights.py`).

Verifies the suggestion logic without needing real Supabase data:
- below-floor sample sizes return "data too sparse" with no suggestion
- high correlation (>0.7) suggests weight up
- low correlation (<0.3) suggests weight down
- middle-band correlation suggests no change
- weight nudges saturate at [0.3, 2.0]
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# CI runs python -m unittest discover (not pytest); inline sys.path bootstrap.
_ROOT = Path(__file__).resolve().parents[1]
for _p in (
    _ROOT,
    _ROOT / "ops" / "scripts",
):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from tune_yaml_gap_weights import (  # type: ignore[import-not-found]
    HIGH_CORRELATION_THRESHOLD,
    LOW_CORRELATION_THRESHOLD,
    MIN_SAMPLE_FLOOR,
    WEIGHT_STEP,
    _suggest_weight,
)


class SuggestWeightTests(unittest.TestCase):

    def test_below_floor_returns_no_suggestion(self):
        suggested, note = _suggest_weight(
            current=1.0,
            correlation=1.0,  # would otherwise be a strong "up" signal
            sample_size=MIN_SAMPLE_FLOOR - 1,
        )
        self.assertIsNone(suggested)
        self.assertIn("data too sparse", note)

    def test_high_correlation_suggests_up(self):
        suggested, note = _suggest_weight(
            current=1.0,
            correlation=HIGH_CORRELATION_THRESHOLD + 0.1,
            sample_size=MIN_SAMPLE_FLOOR + 5,
        )
        self.assertEqual(suggested, 1.0 + WEIGHT_STEP)
        self.assertIn("weight up", note)

    def test_low_correlation_suggests_down(self):
        suggested, note = _suggest_weight(
            current=1.0,
            correlation=LOW_CORRELATION_THRESHOLD - 0.1,
            sample_size=MIN_SAMPLE_FLOOR + 5,
        )
        self.assertEqual(suggested, 1.0 - WEIGHT_STEP)
        self.assertIn("weight down", note)

    def test_middle_band_no_change(self):
        suggested, note = _suggest_weight(
            current=1.0,
            correlation=0.5,
            sample_size=MIN_SAMPLE_FLOOR + 5,
        )
        self.assertIsNone(suggested)
        self.assertIn("middle band", note)

    def test_up_clamped_at_2_0(self):
        suggested, _ = _suggest_weight(
            current=1.95,
            correlation=1.0,
            sample_size=MIN_SAMPLE_FLOOR + 5,
        )
        self.assertEqual(suggested, 2.0)

    def test_down_clamped_at_0_3(self):
        suggested, _ = _suggest_weight(
            current=0.4,
            correlation=0.0,
            sample_size=MIN_SAMPLE_FLOOR + 5,
        )
        self.assertEqual(suggested, 0.3)


if __name__ == "__main__":
    unittest.main()
