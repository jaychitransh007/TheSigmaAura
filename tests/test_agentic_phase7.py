import json
import shutil
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "scripts"))

from run_release_gate import (
    CRITICAL_AGENTS,
    E2E_INTEGRITY_PASS_RATE_THRESHOLD,
    NO_PURCHASE_SIDE_EFFECT_THRESHOLD,
    check_release_gate,
    load_agent_eval_summary,
)


# ---------------------------------------------------------------------------
# Phase 7.1: CI workflow definitions exist
# ---------------------------------------------------------------------------

class CIWorkflowTests(unittest.TestCase):
    WORKFLOWS_DIR = ROOT / ".github" / "workflows"

    def test_pr_eval_workflow_exists(self) -> None:
        self.assertTrue((self.WORKFLOWS_DIR / "pr-eval.yml").exists())

    def test_nightly_eval_workflow_exists(self) -> None:
        self.assertTrue((self.WORKFLOWS_DIR / "nightly-eval.yml").exists())

    def test_weekly_eval_workflow_exists(self) -> None:
        self.assertTrue((self.WORKFLOWS_DIR / "weekly-eval.yml").exists())

    def test_pr_workflow_has_unit_tests_job(self) -> None:
        content = (self.WORKFLOWS_DIR / "pr-eval.yml").read_text()
        self.assertIn("unit-tests", content)
        self.assertIn("unittest discover", content)

    def test_pr_workflow_has_agent_evals_job(self) -> None:
        content = (self.WORKFLOWS_DIR / "pr-eval.yml").read_text()
        self.assertIn("agent-evals", content)
        self.assertIn("run_agent_evals.py", content)
        self.assertIn("--fail-on-gate", content)

    def test_pr_workflow_has_release_gate_job(self) -> None:
        content = (self.WORKFLOWS_DIR / "pr-eval.yml").read_text()
        self.assertIn("release-gate", content)
        self.assertIn("run_release_gate.py", content)

    def test_nightly_workflow_has_e2e_evals(self) -> None:
        content = (self.WORKFLOWS_DIR / "nightly-eval.yml").read_text()
        self.assertIn("e2e-evals", content)
        self.assertIn("run_conversation_eval.py", content)

    def test_nightly_workflow_has_schedule(self) -> None:
        content = (self.WORKFLOWS_DIR / "nightly-eval.yml").read_text()
        self.assertIn("schedule", content)
        self.assertIn("cron", content)

    def test_weekly_workflow_has_drift_report(self) -> None:
        content = (self.WORKFLOWS_DIR / "weekly-eval.yml").read_text()
        self.assertIn("drift-report", content)

    def test_weekly_workflow_retains_artifacts_180_days(self) -> None:
        content = (self.WORKFLOWS_DIR / "weekly-eval.yml").read_text()
        self.assertIn("retention-days: 180", content)

    def test_all_workflows_upload_artifacts(self) -> None:
        for name in ("pr-eval.yml", "nightly-eval.yml", "weekly-eval.yml"):
            content = (self.WORKFLOWS_DIR / name).read_text()
            self.assertIn("upload-artifact", content, f"{name} missing artifact upload")


# ---------------------------------------------------------------------------
# Phase 7.2: Operational dashboard spec
# ---------------------------------------------------------------------------

class OperationalDashboardTests(unittest.TestCase):
    DASHBOARD_PATH = ROOT / "ops" / "runbooks" / "OPERATIONAL_DASHBOARD.md"

    def test_dashboard_spec_exists(self) -> None:
        self.assertTrue(self.DASHBOARD_PATH.exists())

    def test_dashboard_has_all_panels(self) -> None:
        content = self.DASHBOARD_PATH.read_text()
        panels = [
            "Recommendation Funnel",
            "Add-to-Cart and Checkout",
            "Checkout Failure Reasons",
            "Mode Routing",
            "Style Constraints",
            "Policy & Trust",
            "Eval Health",
            "Daily Funnel Summary",
        ]
        for panel in panels:
            self.assertIn(panel, content, f"Missing panel: {panel}")

    def test_dashboard_has_kpi_targets(self) -> None:
        content = self.DASHBOARD_PATH.read_text()
        self.assertIn("KPI Targets", content)
        self.assertIn("engagement rate", content.lower())
        self.assertIn("completion rate", content.lower())
        self.assertIn("mode routing accuracy", content.lower())

    def test_dashboard_references_query_file(self) -> None:
        content = self.DASHBOARD_PATH.read_text()
        self.assertIn("funnel_metrics.sql", content)


# ---------------------------------------------------------------------------
# Phase 7.3: Release gate enforcement
# ---------------------------------------------------------------------------

class ReleaseGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_summary(self, data: dict) -> None:
        with open(self.tmpdir / "summary.json", "w") as f:
            json.dump(data, f)

    def test_all_pass_returns_pass(self) -> None:
        self._write_summary({
            "overall_gate": "pass",
            "agent_gates": {
                "IntentModeRouterAgent": "pass",
                "PolicyGuardrailAgent": "pass",
                "UserProfileAgent": "pass",
            },
            "total_suites": 3,
            "total_cases": 10,
            "total_successes": 10,
            "total_failures": 0,
        })
        report = check_release_gate(self.tmpdir)
        self.assertEqual("pass", report["gate_status"])
        self.assertEqual([], report["blocking_reasons"])

    def test_integrity_failure_blocks_release(self) -> None:
        self._write_summary({
            "overall_gate": "fail_integrity",
            "agent_gates": {"IntentModeRouterAgent": "fail_integrity"},
            "total_suites": 1,
            "total_cases": 5,
            "total_successes": 3,
            "total_failures": 2,
        })
        report = check_release_gate(self.tmpdir)
        self.assertEqual("blocked", report["gate_status"])
        self.assertTrue(any("Integrity" in r for r in report["blocking_reasons"]))

    def test_critical_agent_fail_blocks_release(self) -> None:
        self._write_summary({
            "overall_gate": "fail",
            "agent_gates": {
                "IntentModeRouterAgent": "fail",
                "UserProfileAgent": "pass",
            },
            "total_suites": 2,
            "total_cases": 10,
            "total_successes": 8,
            "total_failures": 2,
        })
        report = check_release_gate(self.tmpdir)
        self.assertEqual("blocked", report["gate_status"])
        self.assertTrue(any("Critical agent" in r for r in report["blocking_reasons"]))

    def test_non_critical_agent_fail_does_not_block(self) -> None:
        self._write_summary({
            "overall_gate": "fail",
            "agent_gates": {
                "UserProfileAgent": "fail",
                "IntentModeRouterAgent": "pass",
                "PolicyGuardrailAgent": "pass",
            },
            "total_suites": 3,
            "total_cases": 10,
            "total_successes": 8,
            "total_failures": 2,
        })
        report = check_release_gate(self.tmpdir)
        # Non-critical agent fail doesn't block by itself
        # (no integrity failure, no critical agent failure)
        self.assertNotEqual("blocked", report["gate_status"])

    def test_policy_guardrail_fail_blocks_via_side_effect(self) -> None:
        self._write_summary({
            "overall_gate": "fail",
            "agent_gates": {"PolicyGuardrailAgent": "fail"},
            "total_suites": 1,
            "total_cases": 5,
            "total_successes": 3,
            "total_failures": 2,
        })
        report = check_release_gate(self.tmpdir)
        self.assertEqual("blocked", report["gate_status"])
        # Should be blocked for both critical agent AND side-effect rate
        self.assertTrue(len(report["blocking_reasons"]) >= 1)

    def test_warning_agents_produce_warning_status(self) -> None:
        self._write_summary({
            "overall_gate": "warning",
            "agent_gates": {
                "IntentModeRouterAgent": "warning",
                "PolicyGuardrailAgent": "pass",
            },
            "total_suites": 2,
            "total_cases": 10,
            "total_successes": 10,
            "total_failures": 0,
        })
        report = check_release_gate(self.tmpdir)
        self.assertEqual("warning", report["gate_status"])

    def test_missing_eval_dir_blocks(self) -> None:
        missing_dir = self.tmpdir / "nonexistent"
        report = check_release_gate(missing_dir)
        self.assertEqual("blocked", report["gate_status"])

    def test_critical_agents_set_is_correct(self) -> None:
        self.assertIn("IntentModeRouterAgent", CRITICAL_AGENTS)
        self.assertIn("PolicyGuardrailAgent", CRITICAL_AGENTS)
        self.assertIn("CartAndCheckoutPrepAgent", CRITICAL_AGENTS)

    def test_thresholds_match_spec(self) -> None:
        self.assertEqual(0.99, E2E_INTEGRITY_PASS_RATE_THRESHOLD)
        self.assertEqual(1.00, NO_PURCHASE_SIDE_EFFECT_THRESHOLD)

    def test_report_contains_all_checks(self) -> None:
        self._write_summary({
            "overall_gate": "pass",
            "agent_gates": {"PolicyGuardrailAgent": "pass"},
            "total_suites": 1,
            "total_cases": 5,
            "total_successes": 5,
            "total_failures": 0,
        })
        report = check_release_gate(self.tmpdir)
        checks = report["checks"]
        self.assertIn("integrity_gate", checks)
        self.assertIn("critical_agent_gate", checks)
        self.assertIn("overall_gate", checks)
        self.assertIn("no_purchase_side_effect_rate", checks)

    def test_report_includes_timestamp(self) -> None:
        self._write_summary({
            "overall_gate": "pass",
            "agent_gates": {},
            "total_suites": 0,
            "total_cases": 0,
            "total_successes": 0,
            "total_failures": 0,
        })
        report = check_release_gate(self.tmpdir)
        self.assertIn("timestamp", report)


# ---------------------------------------------------------------------------
# Phase 7: Integration — run agent evals then release gate
# ---------------------------------------------------------------------------

class ReleaseGateIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_agent_evals_then_release_gate(self) -> None:
        for p in (
            ROOT,
            ROOT / "modules" / "catalog_enrichment" / "src",
            ROOT / "modules" / "style_engine" / "src",
            ROOT / "modules" / "user_profiler" / "src",
            ROOT / "modules" / "conversation_platform" / "src",
        ):
            sp = str(p)
            if sp not in sys.path:
                sys.path.insert(0, sp)

        from run_agent_evals import discover_suites, run

        suite_dir = ROOT / "ops" / "evals" / "agents"
        suite_paths = discover_suites(suite_dir)
        eval_out = self.tmpdir / "agent_evals"

        summary = run(
            suite_paths=suite_paths,
            out_dir=eval_out,
            fail_on_gate=False,
        )

        # Now run release gate against the eval output.
        report = check_release_gate(eval_out)
        self.assertIn(report["gate_status"], ("pass", "warning", "blocked"))
        self.assertIn("checks", report)
        self.assertIn("integrity_gate", report["checks"])


if __name__ == "__main__":
    unittest.main()
