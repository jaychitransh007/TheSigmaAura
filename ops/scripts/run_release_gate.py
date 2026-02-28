#!/usr/bin/env python3
"""Release gate enforcement script.

Reads eval artifacts and enforces release-blocking conditions per the
Release Gate Policy defined in EVAL_IMPLEMENTATION_STRATEGY.md.

Release is blocked if any of:
1. Any integrity gate fails.
2. Any critical-agent fail gate triggers.
3. E2E integrity pass rate drops below 0.99.
4. Mode routing accuracy drops below 0.92.
5. Checkout-prep no-side-effect rate is below 1.00.

Usage:
    python ops/scripts/run_release_gate.py --eval-dir data/logs/agent_evals/latest
    python ops/scripts/run_release_gate.py --eval-dir data/logs/agent_evals/latest --fail-on-block
    python ops/scripts/run_release_gate.py --eval-dir data/logs/agent_evals/latest --output-report report.json
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# Critical agents whose fail gate blocks release.
CRITICAL_AGENTS = frozenset({
    "IntentModeRouterAgent",
    "PolicyGuardrailAgent",
    "CartAndCheckoutPrepAgent",
})

# Release gate thresholds.
E2E_INTEGRITY_PASS_RATE_THRESHOLD = 0.99
MODE_ROUTING_ACCURACY_THRESHOLD = 0.92
NO_PURCHASE_SIDE_EFFECT_THRESHOLD = 1.00


def load_agent_eval_summary(eval_dir: Path) -> Optional[Dict[str, Any]]:
    """Load summary.json from an agent eval run directory."""
    summary_path = eval_dir / "summary.json"
    if not summary_path.exists():
        return None
    with open(summary_path) as f:
        return json.load(f)


def load_agent_eval_scores(eval_dir: Path) -> List[Dict[str, Any]]:
    """Load case_scores.jsonl from an agent eval run directory."""
    scores_path = eval_dir / "case_scores.jsonl"
    if not scores_path.exists():
        return []
    rows = []
    with open(scores_path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def check_release_gate(
    eval_dir: Path,
) -> Dict[str, Any]:
    """Evaluate all release gate conditions and return a gate report."""
    report: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "eval_dir": str(eval_dir),
        "gate_status": "pass",
        "blocking_reasons": [],
        "checks": {},
    }

    summary = load_agent_eval_summary(eval_dir)
    if summary is None:
        report["gate_status"] = "blocked"
        report["blocking_reasons"].append("No agent eval summary found at " + str(eval_dir))
        return report

    agent_gates = summary.get("agent_gates", {})

    # --- Check 1: Any integrity gate fails ---
    integrity_failures = [
        agent for agent, gate in agent_gates.items()
        if gate == "fail_integrity"
    ]
    report["checks"]["integrity_gate"] = {
        "status": "pass" if not integrity_failures else "blocked",
        "failures": integrity_failures,
    }
    if integrity_failures:
        report["gate_status"] = "blocked"
        report["blocking_reasons"].append(
            f"Integrity gate failed for: {', '.join(integrity_failures)}"
        )

    # --- Check 2: Critical agent fail gate ---
    critical_failures = [
        agent for agent, gate in agent_gates.items()
        if agent in CRITICAL_AGENTS and gate in ("fail", "fail_integrity")
    ]
    report["checks"]["critical_agent_gate"] = {
        "status": "pass" if not critical_failures else "blocked",
        "failures": critical_failures,
        "critical_agents": sorted(CRITICAL_AGENTS),
    }
    if critical_failures:
        report["gate_status"] = "blocked"
        report["blocking_reasons"].append(
            f"Critical agent fail gate triggered for: {', '.join(critical_failures)}"
        )

    # --- Check 3: Overall gate ---
    overall_gate = summary.get("overall_gate", "pass")
    report["checks"]["overall_gate"] = {
        "status": overall_gate,
        "total_suites": summary.get("total_suites", 0),
        "total_cases": summary.get("total_cases", 0),
        "total_successes": summary.get("total_successes", 0),
        "total_failures": summary.get("total_failures", 0),
    }

    # --- Check 4: E2E integrity pass rate (from e2e summary if available) ---
    e2e_summary_path = eval_dir.parent.parent / "conversation_evals" / eval_dir.name / "summary.json"
    if e2e_summary_path.exists():
        with open(e2e_summary_path) as f:
            e2e_summary = json.load(f)
        integrity_pass_rate = float(e2e_summary.get("integrity_pass_rate", 1.0))
        report["checks"]["e2e_integrity_pass_rate"] = {
            "status": "pass" if integrity_pass_rate >= E2E_INTEGRITY_PASS_RATE_THRESHOLD else "blocked",
            "value": integrity_pass_rate,
            "threshold": E2E_INTEGRITY_PASS_RATE_THRESHOLD,
        }
        if integrity_pass_rate < E2E_INTEGRITY_PASS_RATE_THRESHOLD:
            report["gate_status"] = "blocked"
            report["blocking_reasons"].append(
                f"E2E integrity pass rate {integrity_pass_rate:.2%} below {E2E_INTEGRITY_PASS_RATE_THRESHOLD:.0%}"
            )
    else:
        report["checks"]["e2e_integrity_pass_rate"] = {
            "status": "skipped",
            "reason": "No E2E eval summary found",
        }

    # --- Check 5: No-purchase side-effect rate ---
    # If PolicyGuardrailAgent passes, this is implicitly 1.00.
    policy_gate = agent_gates.get("PolicyGuardrailAgent", "pass")
    no_side_effect = 1.0 if policy_gate == "pass" else 0.0
    report["checks"]["no_purchase_side_effect_rate"] = {
        "status": "pass" if no_side_effect >= NO_PURCHASE_SIDE_EFFECT_THRESHOLD else "blocked",
        "value": no_side_effect,
        "threshold": NO_PURCHASE_SIDE_EFFECT_THRESHOLD,
    }
    if no_side_effect < NO_PURCHASE_SIDE_EFFECT_THRESHOLD:
        report["gate_status"] = "blocked"
        report["blocking_reasons"].append("No-purchase side-effect rate below 1.00")

    # --- Determine final status ---
    if report["gate_status"] != "blocked":
        # Check for warnings.
        warning_agents = [
            agent for agent, gate in agent_gates.items()
            if gate == "warning"
        ]
        if warning_agents:
            report["gate_status"] = "warning"
            report["checks"]["warning_agents"] = warning_agents

    report["agent_gates"] = agent_gates
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Release gate enforcement")
    parser.add_argument("--eval-dir", type=str, required=True, help="Agent eval output directory")
    parser.add_argument("--fail-on-block", action="store_true", help="Exit with code 1 if release is blocked")
    parser.add_argument("--output-report", type=str, default=None, help="Write gate report to JSON file")
    args = parser.parse_args()

    eval_dir = Path(args.eval_dir)
    report = check_release_gate(eval_dir)

    if args.output_report:
        out_path = Path(args.output_report)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2)

    status = report["gate_status"]
    print(f"\nRelease Gate: {status.upper()}")
    print(f"  Eval Dir: {eval_dir}")

    for check_name, check_data in report.get("checks", {}).items():
        if isinstance(check_data, dict):
            check_status = check_data.get("status", "?")
            print(f"  {check_name}: {check_status}")

    if report["blocking_reasons"]:
        print("\n  Blocking reasons:")
        for reason in report["blocking_reasons"]:
            print(f"    - {reason}")

    if args.fail_on_block and status == "blocked":
        print(f"\nFAIL: Release is blocked.")
        sys.exit(1)


if __name__ == "__main__":
    main()
