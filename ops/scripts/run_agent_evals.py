#!/usr/bin/env python3
"""Per-agent eval runner.

Loads agent eval suites from ops/evals/agents/, executes cases in fixture mode,
scores against thresholds, enforces fail gates, and writes artifact contract.

Usage:
    python ops/scripts/run_agent_evals.py --suite-dir ops/evals/agents --out-dir data/logs/agent_evals
    python ops/scripts/run_agent_evals.py --suite ops/evals/agents/intent_mode_router_v1.json
    python ops/scripts/run_agent_evals.py --suite-dir ops/evals/agents --fail-on-gate
"""
import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Gate semantics
# ---------------------------------------------------------------------------

GATE_PASS = "pass"
GATE_WARNING = "warning"
GATE_FAIL = "fail"
GATE_FAIL_INTEGRITY = "fail_integrity"

GATE_SEVERITY_ORDER = [GATE_PASS, GATE_WARNING, GATE_FAIL, GATE_FAIL_INTEGRITY]


def worse_gate(a: str, b: str) -> str:
    """Return the more severe of two gate statuses."""
    a_idx = GATE_SEVERITY_ORDER.index(a) if a in GATE_SEVERITY_ORDER else 0
    b_idx = GATE_SEVERITY_ORDER.index(b) if b in GATE_SEVERITY_ORDER else 0
    return GATE_SEVERITY_ORDER[max(a_idx, b_idx)]


# ---------------------------------------------------------------------------
# Suite loading
# ---------------------------------------------------------------------------

def load_suite(path: Path) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def discover_suites(suite_dir: Path) -> List[Path]:
    if not suite_dir.is_dir():
        return []
    return sorted(suite_dir.glob("*.json"))


# ---------------------------------------------------------------------------
# Case execution (fixture / deterministic mode)
# ---------------------------------------------------------------------------

def execute_case(suite: Dict[str, Any], case: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a single eval case and return output snapshot.

    In fixture mode, we run the agent method directly when possible and
    return the deterministic output. For cases that require live API calls,
    we return a placeholder indicating fixture-only execution.
    """
    case_id = case.get("id", "unknown")
    agent_name = suite.get("agent", "")
    case_input = case.get("input", {})
    expected = case.get("expected", {})

    output: Dict[str, Any] = {
        "case_id": case_id,
        "agent": agent_name,
        "success": True,
        "error_code": None,
        "decision_snapshot": {},
        "metric_hints": {},
    }

    try:
        result = _run_agent_fixture(agent_name, case_input)
        output["decision_snapshot"] = result
        output["metric_hints"] = _compute_metric_hints(result, expected)
    except Exception as exc:
        output["success"] = False
        output["error_code"] = type(exc).__name__
        output["decision_snapshot"] = {"error": str(exc)}

    return output


def _run_agent_fixture(agent_name: str, case_input: Dict[str, Any]) -> Dict[str, Any]:
    """Run agent in fixture mode using local imports."""
    # Ensure module paths are available.
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

    if agent_name == "IntentModeRouterAgent":
        from conversation_platform.agents import IntentModeRouterAgent
        router = IntentModeRouterAgent()
        return router.resolve_mode(
            mode_preference=case_input.get("mode_preference", "auto"),
            target_garment_type=case_input.get("target_garment_type"),
            request_text=case_input.get("request_text", ""),
        )

    if agent_name == "UserProfileAgent":
        from conversation_platform.agents import UserProfileAgent
        if "profile" in case_input:
            return {"fields_used": UserProfileAgent.profile_fields_used(case_input["profile"])}
        return UserProfileAgent.merge_profile(
            existing=case_input.get("existing"),
            size_overrides=case_input.get("size_overrides"),
            initial_profile=case_input.get("initial_profile"),
        )

    if agent_name == "BodyHarmonyAgent":
        from conversation_platform.agents import BodyHarmonyAgent, ProfileAgent
        from user_profiler.schemas import BODY_ENUMS
        if "profile" in case_input:
            return {"style_constraints": BodyHarmonyAgent.style_constraints_from_profile(case_input["profile"])}
        if not case_input:
            return {"alias_valid": ProfileAgent is BodyHarmonyAgent}
        visual = {key: values[0] for key, values in BODY_ENUMS.items()}
        visual["gender"] = "female"
        visual["age"] = "25_30"
        profile = BodyHarmonyAgent.extract_body_profile(visual)
        return {
            "profile": profile,
            "has_all_body_enum_keys": all(k in profile for k in BODY_ENUMS),
            "has_color_preferences": "color_preferences" in profile,
            "excludes_gender": "gender" not in profile,
            "excludes_age": "age" not in profile,
        }

    if agent_name == "StyleRequirementInterpreter":
        from conversation_platform.agents import (
            CatalogFilterSubAgent,
            GarmentRankerSubAgent,
            StyleRequirementInterpreter,
        )
        if "request_text" in case_input:
            return StyleRequirementInterpreter.interpret(
                request_text=case_input["request_text"],
                context=case_input.get("context", {}),
            )
        # Contract checks for sub-agents.
        catalog = CatalogFilterSubAgent()
        ranker = GarmentRankerSubAgent()
        return {
            "tier1_rules_type": type(catalog.tier1_rules).__name__,
            "tier1_rules_not_empty": bool(catalog.tier1_rules),
            "tier2_rules_type": type(ranker.tier2_rules).__name__,
            "tier2_rules_not_empty": bool(ranker.tier2_rules),
        }

    if agent_name == "CatalogFilterSubAgent":
        from conversation_platform.agents import (
            BrandVarianceComfortSubAgent,
            CatalogFilterSubAgent,
            IntentPolicySubAgent,
        )
        if "request_text" in case_input:
            result = IntentPolicySubAgent.resolve(
                request_text=case_input["request_text"],
                context=case_input.get("context", {}),
            )
            return {"has_policy_id": "policy_id" in result, "result_type": type(result).__name__}
        if "items" in case_input:
            output = BrandVarianceComfortSubAgent.apply(case_input["items"])
            return {"output_equals_input": output == case_input["items"]}
        agent = CatalogFilterSubAgent()
        return {"tier1_rules_loaded": bool(agent.tier1_rules)}

    if agent_name == "PolicyGuardrailAgent":
        from conversation_platform.agents import PolicyGuardrailAgent
        result = PolicyGuardrailAgent.check_action(case_input.get("action", ""))
        result["has_reason"] = bool(result.get("reason"))
        return result

    if agent_name == "TelemetryAgent":
        from conversation_platform.agents import TelemetryAgent
        agent = TelemetryAgent()
        if "event_type" in case_input:
            reward = agent.reward_for_event(case_input["event_type"])
            max_reward = max(agent.reward_map.values())
            return {
                "reward": reward,
                "reward_positive": reward > 0,
                "reward_negative": reward < 0,
                "reward_max": reward == max_reward,
            }
        return {
            "event_types": sorted(agent.reward_map.keys()),
            "skip_equals_no_action": agent.reward_map.get("skip") == agent.reward_map.get("no_action"),
        }

    # Fallback for agents not yet wired.
    if agent_name in ("BudgetAndDealAgent", "CartAndCheckoutPrepAgent"):
        return {"fixture_mode": "placeholder", "agent": agent_name}

    return {"fixture_mode": "unknown_agent", "agent": agent_name}


def _compute_metric_hints(result: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    """Compare result to expected and produce deterministic metric hints."""
    hints: Dict[str, Any] = {"matches": {}, "mismatches": {}}
    for key, exp_val in expected.items():
        # Pattern: foo_any — check if result["foo"] is in the list.
        if key.endswith("_any"):
            base_key = key[:-4]
            actual = result.get(base_key)
            if isinstance(exp_val, list) and actual in exp_val:
                hints["matches"][key] = True
            elif isinstance(exp_val, list) and isinstance(actual, list) and any(v in actual for v in exp_val):
                hints["matches"][key] = True
            else:
                hints["mismatches"][key] = {"expected_any": exp_val, "actual": actual}
        # Pattern: required_keys — all keys must exist in result.
        elif key == "required_keys":
            missing = [k for k in exp_val if k not in result]
            if missing:
                hints["mismatches"][key] = {"missing": missing}
            else:
                hints["matches"][key] = True
        # Pattern: foo_contains — result["foo"] list must include all items.
        elif key.endswith("_contains"):
            base_key = key[:-9]
            actual = result.get(base_key, [])
            if isinstance(actual, list) and isinstance(exp_val, list) and all(v in actual for v in exp_val):
                hints["matches"][key] = True
            else:
                hints["mismatches"][key] = {"expected_contains": exp_val, "actual": actual}
        # Pattern: foo_excludes — result["foo"] list must not include items.
        elif key.endswith("_excludes"):
            base_key = key[:-9]
            actual = result.get(base_key, [])
            if isinstance(actual, list) and isinstance(exp_val, list) and not any(v in actual for v in exp_val):
                hints["matches"][key] = True
            else:
                hints["mismatches"][key] = {"expected_excludes": exp_val, "actual": actual}
        # Pattern: foo_mentions — string result["foo"] contains substring.
        elif key.endswith("_mentions"):
            base_key = key[:-9]
            actual = str(result.get(base_key, "")).lower()
            if isinstance(exp_val, str) and exp_val.lower() in actual:
                hints["matches"][key] = True
            else:
                hints["mismatches"][key] = {"expected_mentions": exp_val, "actual": actual}
        # Pattern: has_foo — check if result["foo"] is truthy.
        elif key.startswith("has_"):
            base_key = key[4:]
            actual_in_result = result.get(key)
            if actual_in_result == exp_val:
                hints["matches"][key] = True
            elif base_key in result and bool(result[base_key]) == exp_val:
                hints["matches"][key] = True
            else:
                hints["mismatches"][key] = {"expected": exp_val, "actual": result.get(key, result.get(base_key))}
        # Pattern: excludes_foo or no_foo — check boolean flag.
        elif key.startswith("excludes_") or key.startswith("no_"):
            actual = result.get(key)
            if actual == exp_val:
                hints["matches"][key] = True
            else:
                hints["mismatches"][key] = {"expected": exp_val, "actual": actual}
        # Pattern: foo.bar — dotted path into nested result.
        elif "." in key:
            parts = key.split(".")
            actual = result
            for part in parts:
                if isinstance(actual, dict):
                    actual = actual.get(part)
                else:
                    actual = None
                    break
            if actual == exp_val:
                hints["matches"][key] = True
            else:
                hints["mismatches"][key] = {"expected": exp_val, "actual": actual}
        # Direct equality.
        else:
            actual = result.get(key)
            if actual == exp_val:
                hints["matches"][key] = True
            else:
                hints["mismatches"][key] = {"expected": exp_val, "actual": actual}
    return hints


# ---------------------------------------------------------------------------
# Scoring and gate enforcement
# ---------------------------------------------------------------------------

def score_suite(suite: Dict[str, Any], case_outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Score a suite's outputs and determine gate status."""
    thresholds = suite.get("thresholds", {})
    pass_thresholds = thresholds.get("pass", {})
    warning_thresholds = thresholds.get("warning", {})
    fail_condition = thresholds.get("fail_condition", "")

    total = len(case_outputs)
    successes = sum(1 for o in case_outputs if o.get("success"))
    failures = total - successes

    # Count match rate from metric hints.
    total_checks = 0
    matched_checks = 0
    for o in case_outputs:
        hints = o.get("metric_hints", {})
        matches = hints.get("matches", {})
        mismatches = hints.get("mismatches", {})
        total_checks += len(matches) + len(mismatches)
        matched_checks += len(matches)

    match_rate = matched_checks / total_checks if total_checks > 0 else 1.0
    success_rate = successes / total if total > 0 else 0.0

    # Determine gate.
    gate = GATE_PASS

    # Check for integrity failures (execution errors).
    if failures > 0:
        gate = worse_gate(gate, GATE_FAIL_INTEGRITY)

    # Check match rate against thresholds.
    if match_rate < 1.0:
        # Use first pass threshold as proxy.
        first_pass = list(pass_thresholds.values())[0] if pass_thresholds else 0.95
        first_warn = list(warning_thresholds.values())[0] if warning_thresholds else 0.90
        if match_rate < first_warn:
            gate = worse_gate(gate, GATE_FAIL)
        elif match_rate < first_pass:
            gate = worse_gate(gate, GATE_WARNING)

    metrics = {
        "total_cases": total,
        "successes": successes,
        "failures": failures,
        "total_checks": total_checks,
        "matched_checks": matched_checks,
        "match_rate": round(match_rate, 4),
        "success_rate": round(success_rate, 4),
    }

    return {
        "suite_id": suite.get("suite_id", ""),
        "agent": suite.get("agent", ""),
        "gate": gate,
        "metrics": metrics,
        "pass_thresholds": pass_thresholds,
        "warning_thresholds": warning_thresholds,
        "fail_condition": fail_condition,
    }


def aggregate_results(suite_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate all suite results into a single summary."""
    overall_gate = GATE_PASS
    agent_gates: Dict[str, str] = {}
    total_cases = 0
    total_successes = 0

    for sr in suite_results:
        overall_gate = worse_gate(overall_gate, sr["gate"])
        agent_gates[sr["agent"]] = sr["gate"]
        total_cases += sr["metrics"]["total_cases"]
        total_successes += sr["metrics"]["successes"]

    return {
        "overall_gate": overall_gate,
        "agent_gates": agent_gates,
        "total_suites": len(suite_results),
        "total_cases": total_cases,
        "total_successes": total_successes,
        "total_failures": total_cases - total_successes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Artifact writing
# ---------------------------------------------------------------------------

def write_artifacts(
    out_dir: Path,
    suite_results: List[Dict[str, Any]],
    all_case_inputs: List[Dict[str, Any]],
    all_case_outputs: List[Dict[str, Any]],
    all_case_scores: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> Dict[str, Any]:
    """Write the full artifact contract to out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "runner": "run_agent_evals.py",
        "timestamp": summary["timestamp"],
        "overall_gate": summary["overall_gate"],
        "total_suites": summary["total_suites"],
        "total_cases": summary["total_cases"],
    }
    _write_json(out_dir / "run_manifest.json", manifest)
    _write_jsonl(out_dir / "case_inputs.jsonl", all_case_inputs)
    _write_jsonl(out_dir / "case_outputs.jsonl", all_case_outputs)
    _write_jsonl(out_dir / "case_scores.jsonl", all_case_scores)
    _write_csv(out_dir / "case_scores.csv", all_case_scores)
    _write_json(out_dir / "summary.json", summary)
    _write_summary_md(out_dir / "summary.md", summary, suite_results)

    integrity = _compute_integrity(out_dir)
    _write_json(out_dir / "artifact_integrity.json", integrity)

    return integrity


def _write_json(path: Path, data: Any) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row, default=str) + "\n")


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in row.items()})


def _write_summary_md(path: Path, summary: Dict[str, Any], suite_results: List[Dict[str, Any]]) -> None:
    lines = [
        "# Agent Eval Summary",
        "",
        f"**Overall Gate:** `{summary['overall_gate']}`",
        f"**Timestamp:** {summary['timestamp']}",
        f"**Suites:** {summary['total_suites']} | **Cases:** {summary['total_cases']} | "
        f"**Successes:** {summary['total_successes']} | **Failures:** {summary['total_failures']}",
        "",
        "## Per-Agent Results",
        "",
        "| Agent | Suite | Gate | Cases | Match Rate |",
        "|---|---|---|---:|---:|",
    ]
    for sr in suite_results:
        m = sr["metrics"]
        lines.append(
            f"| {sr['agent']} | {sr['suite_id']} | `{sr['gate']}` | {m['total_cases']} | {m['match_rate']:.2%} |"
        )
    lines.append("")
    path.write_text("\n".join(lines))


def _compute_integrity(out_dir: Path) -> Dict[str, Any]:
    required_files = [
        "run_manifest.json",
        "case_inputs.jsonl",
        "case_outputs.jsonl",
        "case_scores.jsonl",
        "case_scores.csv",
        "summary.json",
        "summary.md",
    ]
    file_hashes: Dict[str, str] = {}
    missing: List[str] = []
    for fname in required_files:
        fpath = out_dir / fname
        if fpath.exists():
            content = fpath.read_bytes()
            file_hashes[fname] = hashlib.sha256(content).hexdigest()
        else:
            missing.append(fname)
    return {
        "all_present": len(missing) == 0,
        "missing": missing,
        "file_hashes": file_hashes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(
    suite_paths: List[Path],
    out_dir: Path,
    fail_on_gate: bool = False,
    max_cases: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute all suites and produce artifacts."""
    suite_results: List[Dict[str, Any]] = []
    all_case_inputs: List[Dict[str, Any]] = []
    all_case_outputs: List[Dict[str, Any]] = []
    all_case_scores: List[Dict[str, Any]] = []

    for suite_path in suite_paths:
        suite = load_suite(suite_path)
        suite_id = suite.get("suite_id", suite_path.stem)
        cases = suite.get("cases", [])
        if max_cases is not None:
            cases = cases[:max_cases]

        case_outputs: List[Dict[str, Any]] = []
        for case in cases:
            case_input = {
                "suite_id": suite_id,
                "case_id": case.get("id", ""),
                "agent": suite.get("agent", ""),
                "input": case.get("input", {}),
                "expected": case.get("expected", {}),
                "tags": case.get("tags", []),
            }
            all_case_inputs.append(case_input)

            output = execute_case(suite, case)
            output["suite_id"] = suite_id
            case_outputs.append(output)
            all_case_outputs.append(output)

        result = score_suite(suite, case_outputs)
        suite_results.append(result)

        for output in case_outputs:
            score_entry = {
                "suite_id": suite_id,
                "case_id": output["case_id"],
                "agent": output["agent"],
                "success": output["success"],
                "gate": result["gate"],
                "match_rate": result["metrics"]["match_rate"],
            }
            all_case_scores.append(score_entry)

    summary = aggregate_results(suite_results)
    integrity = write_artifacts(out_dir, suite_results, all_case_inputs, all_case_outputs, all_case_scores, summary)

    print(f"\nAgent Eval Complete: {summary['overall_gate'].upper()}")
    print(f"  Suites: {summary['total_suites']}")
    print(f"  Cases:  {summary['total_cases']} ({summary['total_successes']} passed, {summary['total_failures']} failed)")
    print(f"  Output: {out_dir}")
    for sr in suite_results:
        print(f"    {sr['agent']:.<40s} {sr['gate']}")
    print(f"  Artifacts: {'COMPLETE' if integrity.get('all_present') else 'INCOMPLETE'}")

    if fail_on_gate and summary["overall_gate"] in (GATE_FAIL, GATE_FAIL_INTEGRITY):
        print(f"\nFAIL: overall gate is {summary['overall_gate']}")
        sys.exit(1)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run per-agent eval suites")
    parser.add_argument("--suite-dir", type=str, default="ops/evals/agents", help="Directory containing agent suite JSON files")
    parser.add_argument("--suite", type=str, default=None, help="Single suite JSON file to run")
    parser.add_argument("--out-dir", type=str, default="data/logs/agent_evals", help="Output directory for artifacts")
    parser.add_argument("--fail-on-gate", action="store_true", help="Exit with code 1 if any fail gate triggers")
    parser.add_argument("--max-cases", type=int, default=None, help="Limit cases per suite")
    args = parser.parse_args()

    if args.suite:
        suite_paths = [Path(args.suite)]
    else:
        suite_paths = discover_suites(Path(args.suite_dir))

    if not suite_paths:
        print(f"No suites found in {args.suite_dir}")
        sys.exit(1)

    run(
        suite_paths=suite_paths,
        out_dir=Path(args.out_dir),
        fail_on_gate=args.fail_on_gate,
        max_cases=args.max_cases,
    )


if __name__ == "__main__":
    main()
