"""Phase 5x.4b — pytest entry for the open-axis extraction eval.

Two test classes:

- ``CompareExtractionTests`` exercises the pure-function ``compare_extraction``
  / ``aggregate_results`` helpers. No LLM calls — runs in CI.
- ``OpenAxisEvalIntegrationTests`` runs the full harness against real
  planner LLM calls. Skipped unless ``RUN_EVAL=1`` is set, since each
  run costs ~$0.01 in OpenAI credits.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# CI runs `python -m unittest discover` which doesn't load conftest.py
# (pytest-only). Older tests carry an inline sys.path bootstrap that
# adds modules/*/src to sys.path; that side effect makes those tests
# work under unittest discover too. This file's imports go ONE step
# further: open_axis_eval lives in tests/eval/ which isn't on sys.path
# unless we explicitly add it. Self-contained block here so this test
# works under both pytest (via conftest) and unittest discover.
_ROOT = Path(__file__).resolve().parents[1]
for _p in (_ROOT / "tests" / "eval",):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from open_axis_eval import (
    AxisStats,
    CaseResult,
    EvalCase,
    aggregate_results,
    compare_extraction,
    load_eval_set,
)


class CompareExtractionTests(unittest.TestCase):

    def test_both_empty_passes(self):
        r = compare_extraction({}, {})
        self.assertEqual(r.status, "pass")

    def test_exact_match_passes(self):
        r = compare_extraction(
            {"EmbellishmentLevel": ["heavy", "statement"]},
            {"EmbellishmentLevel": ["heavy", "statement"]},
        )
        self.assertEqual(r.status, "pass")

    def test_exact_match_unordered(self):
        # Set-equality, not list-equality.
        r = compare_extraction(
            {"EmbellishmentLevel": ["heavy", "statement"]},
            {"EmbellishmentLevel": ["statement", "heavy"]},
        )
        self.assertEqual(r.status, "pass")

    def test_value_subset_is_partial(self):
        # Planner picked a narrower subset of the expected allowed values.
        # That's the prompt's "loose mapping" land — partial, not fail.
        r = compare_extraction(
            {"FabricDrape": ["fluid", "soft_structured"]},
            {"FabricDrape": ["fluid"]},
        )
        self.assertEqual(r.status, "partial")
        self.assertEqual(r.value_partial_axes, ["FabricDrape"])

    def test_extra_value_in_shared_axis_fails(self):
        # Planner included a value not in the expected set → fail.
        r = compare_extraction(
            {"EmbellishmentLevel": ["heavy"]},
            {"EmbellishmentLevel": ["heavy", "minimal"]},
        )
        self.assertEqual(r.status, "fail")
        self.assertIn("EmbellishmentLevel", r.extra_axes)

    def test_missing_axis_is_partial(self):
        r = compare_extraction(
            {"NecklineType": ["v_neck"], "FitEase": ["fitted"]},
            {"NecklineType": ["v_neck"]},
        )
        self.assertEqual(r.status, "partial")
        self.assertEqual(r.missing_axes, ["FitEase"])

    def test_extra_axis_fails(self):
        # Over-extraction is the cardinal sin: planner invented an axis
        # the user didn't mention.
        r = compare_extraction(
            {"NecklineType": ["v_neck"]},
            {"NecklineType": ["v_neck"], "ColorTemperature": ["warm"]},
        )
        self.assertEqual(r.status, "fail")
        self.assertEqual(r.extra_axes, ["ColorTemperature"])

    def test_negative_with_actual_extracted_fails(self):
        # Negative case: expected={}; if planner extracts ANY axis, fail.
        r = compare_extraction({}, {"FabricDrape": ["fluid"]})
        self.assertEqual(r.status, "fail")
        self.assertEqual(r.extra_axes, ["FabricDrape"])

    def test_aggregate_counts_per_axis(self):
        results = [
            # case 1: NecklineType TP, FitEase TP
            compare_extraction(
                {"NecklineType": ["v_neck"], "FitEase": ["fitted"]},
                {"NecklineType": ["v_neck"], "FitEase": ["fitted"]},
                case_id="c1",
            ),
            # case 2: NecklineType TP, ColorTemperature FP (over-extraction)
            compare_extraction(
                {"NecklineType": ["v_neck"]},
                {"NecklineType": ["v_neck"], "ColorTemperature": ["warm"]},
                case_id="c2",
            ),
            # case 3: NecklineType TP, FitEase FN (under-extraction)
            compare_extraction(
                {"NecklineType": ["v_neck"], "FitEase": ["fitted"]},
                {"NecklineType": ["v_neck"]},
                case_id="c3",
            ),
        ]
        agg = aggregate_results(results)
        self.assertEqual(agg.total, 3)
        self.assertEqual(agg.pass_, 1)
        self.assertEqual(agg.fail, 1)   # c2 over-extracted
        self.assertEqual(agg.partial, 1)  # c3 under-extracted

        # NecklineType: 3 TP, 0 FP, 0 FN → precision 1.0, recall 1.0
        nt = agg.by_axis["NecklineType"]
        self.assertEqual((nt.true_positives, nt.false_positives, nt.false_negatives), (3, 0, 0))
        self.assertAlmostEqual(nt.precision, 1.0)
        self.assertAlmostEqual(nt.recall, 1.0)

        # ColorTemperature: 0 TP, 1 FP, 0 FN → precision 0.0, recall undefined
        ct = agg.by_axis["ColorTemperature"]
        self.assertEqual((ct.true_positives, ct.false_positives, ct.false_negatives), (0, 1, 0))
        self.assertAlmostEqual(ct.precision, 0.0)
        self.assertIsNone(ct.recall)

        # FitEase: 1 TP, 0 FP, 1 FN → precision 1.0, recall 0.5
        fe = agg.by_axis["FitEase"]
        self.assertEqual((fe.true_positives, fe.false_positives, fe.false_negatives), (1, 0, 1))
        self.assertAlmostEqual(fe.precision, 1.0)
        self.assertAlmostEqual(fe.recall, 0.5)


class EvalSetSchemaTests(unittest.TestCase):
    """Validate the JSONL itself — every case should load cleanly with
    the expected fields. Catches syntax errors in the data file even
    when RUN_EVAL is not set."""

    @classmethod
    def setUpClass(cls):
        cls.cases = load_eval_set()

    def test_at_least_one_case(self):
        self.assertGreaterEqual(len(self.cases), 8, "expected ≥8 eval cases")

    def test_unique_ids(self):
        ids = [c.id for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)), "duplicate case IDs")

    def test_each_case_has_required_fields(self):
        for c in self.cases:
            self.assertTrue(c.id, f"case missing id")
            self.assertTrue(c.user_message, f"case {c.id} missing user_message")
            # expected_extracted_preferences may be empty (negative case),
            # but it must be a dict and values must be lists.
            self.assertIsInstance(c.expected_extracted_preferences, dict)
            for axis, vals in c.expected_extracted_preferences.items():
                self.assertIsInstance(vals, list, f"{c.id}.{axis} values not a list")

    def test_includes_negative_cases(self):
        # The eval set should exercise over-extraction guards too.
        negatives = [c for c in self.cases if not c.expected_extracted_preferences]
        self.assertGreaterEqual(len(negatives), 1, "expected ≥1 negative case (empty expected)")

    def test_includes_multi_axis_cases(self):
        multi = [c for c in self.cases if len(c.expected_extracted_preferences) >= 2]
        self.assertGreaterEqual(len(multi), 1, "expected ≥1 multi-axis case")


@unittest.skipUnless(
    os.getenv("RUN_EVAL"),
    "set RUN_EVAL=1 to run the integration eval (incurs ~$0.01 OpenAI cost)",
)
class OpenAxisEvalIntegrationTests(unittest.TestCase):
    """Full eval against the real planner LLM. Gated on RUN_EVAL=1."""

    def test_extraction_quality_meets_floor(self):
        from open_axis_eval import run_eval, aggregate_results
        cases = load_eval_set()
        results = run_eval(cases, verbose=False)
        agg = aggregate_results(results)
        # Floor: zero hard fails (over-extraction is the cardinal sin).
        # Partials are acceptable — the prompt allows loose mappings.
        fail_cases = [r for r in results if r.status == "fail"]
        self.assertEqual(
            agg.fail, 0,
            f"hard fails: {[(r.case_id, r.extra_axes, r.actual) for r in fail_cases]}",
        )
        # Soft floor: at least 50% of cases should be exact-pass. If
        # this falls, the prompt has drifted and needs review (or the
        # eval set needs broader allowed-value mappings).
        self.assertGreaterEqual(
            agg.pass_rate, 0.5,
            f"pass rate {agg.pass_rate:.2f} below 50% floor (partials={agg.partial})",
        )


if __name__ == "__main__":
    unittest.main()
