import json
import shutil
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "catalog_enrichment" / "src",
    ROOT / "modules" / "style_engine" / "src",
    ROOT / "modules" / "user_profiler" / "src",
    ROOT / "modules" / "conversation_platform" / "src",
    ROOT / "modules" / "onboarding" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

sys.path.insert(0, str(ROOT / "ops" / "scripts"))

from run_agent_evals import (
    GATE_FAIL,
    GATE_FAIL_INTEGRITY,
    GATE_PASS,
    GATE_WARNING,
    aggregate_results,
    discover_suites,
    execute_case,
    load_suite,
    run,
    score_suite,
    worse_gate,
    write_artifacts,
)


# ---------------------------------------------------------------------------
# Phase 6.1: Per-agent eval suites exist and are valid
# ---------------------------------------------------------------------------

class AgentSuiteFileTests(unittest.TestCase):
    AGENTS_DIR = ROOT / "ops" / "evals" / "agents"

    EXPECTED_SUITES = [
        "intent_mode_router_v1.json",
        "profile_agent_v1.json",
        "body_harmony_v1.json",
        "style_agent_v1.json",
        "catalog_agent_v1.json",
        "budget_agent_v1.json",
        "checkout_prep_v1.json",
        "policy_agent_v1.json",
        "telemetry_agent_v1.json",
    ]

    def test_agents_directory_exists(self) -> None:
        self.assertTrue(self.AGENTS_DIR.is_dir())

    def test_all_expected_suites_exist(self) -> None:
        for name in self.EXPECTED_SUITES:
            path = self.AGENTS_DIR / name
            self.assertTrue(path.exists(), f"Missing suite: {name}")

    def test_all_suites_are_valid_json(self) -> None:
        for name in self.EXPECTED_SUITES:
            path = self.AGENTS_DIR / name
            with open(path) as f:
                data = json.load(f)
            self.assertIn("suite_id", data, f"{name} missing suite_id")
            self.assertIn("agent", data, f"{name} missing agent")
            self.assertIn("cases", data, f"{name} missing cases")
            self.assertIsInstance(data["cases"], list, f"{name} cases not a list")
            self.assertTrue(len(data["cases"]) > 0, f"{name} has no cases")

    def test_all_suites_have_thresholds(self) -> None:
        for name in self.EXPECTED_SUITES:
            path = self.AGENTS_DIR / name
            with open(path) as f:
                data = json.load(f)
            thresholds = data.get("thresholds", {})
            self.assertIn("pass", thresholds, f"{name} missing pass thresholds")
            self.assertIn("warning", thresholds, f"{name} missing warning thresholds")
            self.assertIn("fail_condition", thresholds, f"{name} missing fail_condition")

    def test_all_cases_have_required_fields(self) -> None:
        for name in self.EXPECTED_SUITES:
            path = self.AGENTS_DIR / name
            with open(path) as f:
                data = json.load(f)
            for case in data["cases"]:
                self.assertIn("id", case, f"{name} case missing id")
                self.assertIn("input", case, f"{name} case {case.get('id')} missing input")
                self.assertIn("expected", case, f"{name} case {case.get('id')} missing expected")

    def test_suite_discovery(self) -> None:
        found = discover_suites(self.AGENTS_DIR)
        self.assertTrue(len(found) >= len(self.EXPECTED_SUITES))


# ---------------------------------------------------------------------------
# Phase 6.2: Per-agent runner
# ---------------------------------------------------------------------------

class RunnerCaseExecutionTests(unittest.TestCase):
    def test_execute_intent_mode_router_case(self) -> None:
        suite = {"agent": "IntentModeRouterAgent"}
        case = {
            "id": "test_001",
            "input": {"mode_preference": "garment", "request_text": "shirts"},
            "expected": {"resolved_mode": "garment"},
        }
        output = execute_case(suite, case)
        self.assertTrue(output["success"])
        self.assertEqual("garment", output["decision_snapshot"]["resolved_mode"])

    def test_execute_user_profile_agent_merge(self) -> None:
        suite = {"agent": "UserProfileAgent"}
        case = {
            "id": "test_002",
            "input": {"existing": None, "initial_profile": {"sizes": {"top_size": "M"}}},
            "expected": {},
        }
        output = execute_case(suite, case)
        self.assertTrue(output["success"])
        self.assertEqual("M", output["decision_snapshot"]["sizes"]["top_size"])

    def test_execute_body_harmony_constraints(self) -> None:
        suite = {"agent": "BodyHarmonyAgent"}
        case = {
            "id": "test_003",
            "input": {"profile": {"HeightCategory": "tall"}},
            "expected": {"style_constraints": ["body_harmony"]},
        }
        output = execute_case(suite, case)
        self.assertTrue(output["success"])
        self.assertEqual(["body_harmony"], output["decision_snapshot"]["style_constraints"])

    def test_execute_policy_guardrail_blocked(self) -> None:
        suite = {"agent": "PolicyGuardrailAgent"}
        case = {
            "id": "test_004",
            "input": {"action": "execute_purchase"},
            "expected": {"allowed": False},
        }
        output = execute_case(suite, case)
        self.assertTrue(output["success"])
        self.assertFalse(output["decision_snapshot"]["allowed"])

    def test_execute_telemetry_agent(self) -> None:
        suite = {"agent": "TelemetryAgent"}
        case = {
            "id": "test_005",
            "input": {"event_type": "buy"},
            "expected": {"reward_positive": True},
        }
        output = execute_case(suite, case)
        self.assertTrue(output["success"])
        self.assertTrue(output["decision_snapshot"]["reward_positive"])

    def test_execute_style_interpreter(self) -> None:
        suite = {"agent": "StyleRequirementInterpreter"}
        case = {
            "id": "test_006",
            "input": {"request_text": "office", "context": {"occasion": "work_mode"}},
            "expected": {"occasion": "work_mode"},
        }
        output = execute_case(suite, case)
        self.assertTrue(output["success"])
        self.assertEqual("work_mode", output["decision_snapshot"]["occasion"])

    def test_metric_hints_match(self) -> None:
        suite = {"agent": "PolicyGuardrailAgent"}
        case = {
            "id": "test_007",
            "input": {"action": "execute_purchase"},
            "expected": {"allowed": False},
        }
        output = execute_case(suite, case)
        self.assertIn("allowed", output["metric_hints"]["matches"])

    def test_metric_hints_mismatch(self) -> None:
        suite = {"agent": "PolicyGuardrailAgent"}
        case = {
            "id": "test_008",
            "input": {"action": "execute_purchase"},
            "expected": {"allowed": True},
        }
        output = execute_case(suite, case)
        self.assertIn("allowed", output["metric_hints"]["mismatches"])


# ---------------------------------------------------------------------------
# Phase 6.3: Threshold and fail-gate enforcement
# ---------------------------------------------------------------------------

class GateSemanticsTests(unittest.TestCase):
    def test_worse_gate_pass_pass(self) -> None:
        self.assertEqual(GATE_PASS, worse_gate(GATE_PASS, GATE_PASS))

    def test_worse_gate_pass_warning(self) -> None:
        self.assertEqual(GATE_WARNING, worse_gate(GATE_PASS, GATE_WARNING))

    def test_worse_gate_warning_fail(self) -> None:
        self.assertEqual(GATE_FAIL, worse_gate(GATE_WARNING, GATE_FAIL))

    def test_worse_gate_fail_integrity(self) -> None:
        self.assertEqual(GATE_FAIL_INTEGRITY, worse_gate(GATE_FAIL, GATE_FAIL_INTEGRITY))

    def test_worse_gate_symmetric(self) -> None:
        self.assertEqual(worse_gate(GATE_PASS, GATE_FAIL), worse_gate(GATE_FAIL, GATE_PASS))


class SuiteScoringTests(unittest.TestCase):
    def test_all_passing_cases_gate_pass(self) -> None:
        suite = {
            "suite_id": "test",
            "agent": "TestAgent",
            "thresholds": {
                "pass": {"accuracy": 0.95},
                "warning": {"accuracy": 0.90},
                "fail_condition": "below warning",
            },
        }
        outputs = [
            {"case_id": "c1", "success": True, "metric_hints": {"matches": {"k1": True}, "mismatches": {}}},
            {"case_id": "c2", "success": True, "metric_hints": {"matches": {"k1": True}, "mismatches": {}}},
        ]
        result = score_suite(suite, outputs)
        self.assertEqual(GATE_PASS, result["gate"])
        self.assertEqual(1.0, result["metrics"]["match_rate"])

    def test_execution_failure_triggers_integrity_gate(self) -> None:
        suite = {
            "suite_id": "test",
            "agent": "TestAgent",
            "thresholds": {"pass": {}, "warning": {}, "fail_condition": ""},
        }
        outputs = [
            {"case_id": "c1", "success": False, "metric_hints": {"matches": {}, "mismatches": {}}},
        ]
        result = score_suite(suite, outputs)
        self.assertEqual(GATE_FAIL_INTEGRITY, result["gate"])

    def test_mismatches_below_warning_trigger_fail(self) -> None:
        suite = {
            "suite_id": "test",
            "agent": "TestAgent",
            "thresholds": {
                "pass": {"accuracy": 0.95},
                "warning": {"accuracy": 0.90},
                "fail_condition": "below warning",
            },
        }
        # 1 match, 9 mismatches = 10% match rate, way below warning
        outputs = [
            {
                "case_id": "c1",
                "success": True,
                "metric_hints": {
                    "matches": {"k1": True},
                    "mismatches": {f"k{i}": {} for i in range(2, 11)},
                },
            },
        ]
        result = score_suite(suite, outputs)
        self.assertEqual(GATE_FAIL, result["gate"])


class AggregationTests(unittest.TestCase):
    def test_aggregate_multiple_suites(self) -> None:
        results = [
            {"suite_id": "s1", "agent": "A1", "gate": GATE_PASS, "metrics": {"total_cases": 3, "successes": 3}},
            {"suite_id": "s2", "agent": "A2", "gate": GATE_WARNING, "metrics": {"total_cases": 2, "successes": 2}},
        ]
        agg = aggregate_results(results)
        self.assertEqual(GATE_WARNING, agg["overall_gate"])
        self.assertEqual(5, agg["total_cases"])
        self.assertEqual(5, agg["total_successes"])
        self.assertEqual(2, agg["total_suites"])

    def test_aggregate_fail_dominates(self) -> None:
        results = [
            {"suite_id": "s1", "agent": "A1", "gate": GATE_PASS, "metrics": {"total_cases": 1, "successes": 1}},
            {"suite_id": "s2", "agent": "A2", "gate": GATE_FAIL, "metrics": {"total_cases": 1, "successes": 0}},
        ]
        agg = aggregate_results(results)
        self.assertEqual(GATE_FAIL, agg["overall_gate"])


# ---------------------------------------------------------------------------
# Phase 6: Artifact contract
# ---------------------------------------------------------------------------

class ArtifactContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_write_artifacts_creates_all_files(self) -> None:
        summary = {
            "overall_gate": GATE_PASS,
            "total_suites": 1,
            "total_cases": 1,
            "total_successes": 1,
            "total_failures": 0,
            "timestamp": "2026-03-01T00:00:00Z",
            "agent_gates": {"TestAgent": GATE_PASS},
        }
        suite_results = [
            {"suite_id": "test", "agent": "TestAgent", "gate": GATE_PASS, "metrics": {"total_cases": 1, "match_rate": 1.0}},
        ]
        integrity = write_artifacts(
            self.tmpdir,
            suite_results,
            [{"suite_id": "test", "case_id": "c1"}],
            [{"case_id": "c1", "success": True}],
            [{"case_id": "c1", "gate": GATE_PASS}],
            summary,
        )
        self.assertTrue(integrity["all_present"])
        expected_files = [
            "run_manifest.json",
            "case_inputs.jsonl",
            "case_outputs.jsonl",
            "case_scores.jsonl",
            "case_scores.csv",
            "summary.json",
            "summary.md",
            "artifact_integrity.json",
        ]
        for fname in expected_files:
            self.assertTrue((self.tmpdir / fname).exists(), f"Missing: {fname}")


class FullRunnerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_run_single_suite(self) -> None:
        suite_path = ROOT / "ops" / "evals" / "agents" / "policy_agent_v1.json"
        summary = run(
            suite_paths=[suite_path],
            out_dir=self.tmpdir,
            fail_on_gate=False,
        )
        self.assertEqual(1, summary["total_suites"])
        self.assertTrue(summary["total_cases"] > 0)
        self.assertEqual(summary["total_successes"], summary["total_cases"])
        self.assertEqual(GATE_PASS, summary["overall_gate"])
        self.assertTrue((self.tmpdir / "summary.json").exists())

    def test_run_all_suites(self) -> None:
        suite_dir = ROOT / "ops" / "evals" / "agents"
        suite_paths = discover_suites(suite_dir)
        summary = run(
            suite_paths=suite_paths,
            out_dir=self.tmpdir,
            fail_on_gate=False,
        )
        self.assertEqual(9, summary["total_suites"])
        self.assertTrue(summary["total_cases"] > 0)
        self.assertTrue((self.tmpdir / "artifact_integrity.json").exists())
        integrity = json.loads((self.tmpdir / "artifact_integrity.json").read_text())
        self.assertTrue(integrity["all_present"])

    def test_run_with_max_cases(self) -> None:
        suite_path = ROOT / "ops" / "evals" / "agents" / "intent_mode_router_v1.json"
        summary = run(
            suite_paths=[suite_path],
            out_dir=self.tmpdir,
            fail_on_gate=False,
            max_cases=2,
        )
        self.assertEqual(2, summary["total_cases"])


if __name__ == "__main__":
    unittest.main()
