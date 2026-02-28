import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.scripts.run_conversation_eval import aggregate_case_evals, evaluate_case


class ConversationEvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rubric = {
            "weights": {
                "context_occasion": 0.2,
                "context_archetype": 0.1,
                "coverage": 0.1,
                "keyword_alignment": 0.2,
                "anti_keyword_guardrail": 0.2,
                "confidence": 0.1,
                "score_quality": 0.05,
                "diversity": 0.05,
            },
            "thresholds": {
                "pass_score": 0.7,
                "warning_score": 0.55,
                "min_returned_results": 1,
                "min_avg_compatibility_confidence": 0.45,
            },
            "required_integrity_checks": [
                "turn_id",
                "recommendation_run_id",
                "recommendation_fetch_ok",
                "non_empty_recommendations",
            ],
            "occasion_guardrails": {"work_mode": {"avoid_keywords": ["sequin", "beaded"]}},
        }

    def test_evaluate_case_passes_for_well_aligned_results(self) -> None:
        case = {
            "id": "p_work",
            "prompt": "Big presentation day at work!",
            "expected_occasion": "work_mode",
            "expected_archetype_any": ["classic"],
            "preferred_title_keywords": ["sheath", "shirt"],
            "avoid_title_keywords": ["party"],
        }
        turn_result = {
            "turn_id": "t1",
            "recommendation_run_id": "run1",
            "resolved_context": {"occasion": "work_mode", "archetype": "classic"},
            "recommendations": [
                {
                    "title": "Charcoal Sheath Dress",
                    "score": 0.86,
                    "max_score": 1.0,
                    "compatibility_confidence": 0.86,
                    "recommendation_kind": "single_garment",
                    "outfit_id": "g1",
                },
                {
                    "title": "White Shirt Co-ord Set",
                    "score": 0.8,
                    "max_score": 1.0,
                    "compatibility_confidence": 0.82,
                    "recommendation_kind": "single_garment",
                    "outfit_id": "g2",
                },
                {
                    "title": "Navy Tailored Shirt Dress",
                    "score": 0.78,
                    "max_score": 1.0,
                    "compatibility_confidence": 0.79,
                    "recommendation_kind": "single_garment",
                    "outfit_id": "g3",
                },
            ],
        }

        out = evaluate_case(
            case_spec=case,
            turn_result=turn_result,
            recommendation_fetch_ok=True,
            rubric=self.rubric,
            max_results=3,
            result_filter="complete_only",
        )

        self.assertEqual("pass", out["status"])
        self.assertGreater(float(out["score"]), 0.7)
        self.assertEqual([], out["missing_integrity_checks"])
        self.assertAlmostEqual(0.0, float(out["meta"]["avoid_hit_ratio"]))

    def test_evaluate_case_flags_integrity_failures(self) -> None:
        case = {
            "id": "p_fail",
            "prompt": "Need work options",
            "expected_occasion": "work_mode",
        }
        turn_result = {
            "turn_id": "t2",
            "recommendation_run_id": "",
            "resolved_context": {"occasion": "work_mode", "archetype": "classic"},
            "recommendations": [],
        }

        out = evaluate_case(
            case_spec=case,
            turn_result=turn_result,
            recommendation_fetch_ok=False,
            rubric=self.rubric,
            max_results=3,
            result_filter="complete_only",
        )

        self.assertEqual("fail_integrity", out["status"])
        self.assertIn("recommendation_run_id", out["missing_integrity_checks"])
        self.assertIn("recommendation_fetch_ok", out["missing_integrity_checks"])
        self.assertIn("non_empty_recommendations", out["missing_integrity_checks"])

    def test_aggregate_case_evals_summarizes_dimensions(self) -> None:
        cases = [
            {
                "status": "pass",
                "score": 0.8,
                "dimensions": {"coverage": 1.0, "confidence": 0.8},
                "missing_integrity_checks": [],
            },
            {
                "status": "warning",
                "score": 0.6,
                "dimensions": {"coverage": 0.66, "confidence": 0.6},
                "missing_integrity_checks": [],
            },
            {
                "status": "fail_integrity",
                "score": 0.4,
                "dimensions": {"coverage": 0.33, "confidence": 0.3},
                "missing_integrity_checks": ["recommendation_fetch_ok"],
            },
        ]
        out = aggregate_case_evals(cases)

        self.assertEqual(3, out["case_count"])
        self.assertEqual(1, out["status_counts"]["pass"])
        self.assertEqual(1, out["status_counts"]["warning"])
        self.assertEqual(1, out["status_counts"]["fail_integrity"])
        self.assertAlmostEqual(2 / 3, float(out["integrity_pass_rate"]), places=6)
        self.assertAlmostEqual((1.0 + 0.66 + 0.33) / 3, float(out["dimension_averages"]["coverage"]), places=4)


if __name__ == "__main__":
    unittest.main()
