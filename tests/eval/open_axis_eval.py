"""Phase 5x.4b open-axis eval harness.

Tests the planner's ability to extract open-axis user preferences
(EmbellishmentLevel, ContrastLevel, NecklineType, FabricDrape, ...)
against a fixed set of natural-language inputs. The expected outputs
follow directly from the glossary in `prompt/copilot_planner.md`'s
Resolved Context section — this is a planner-prompt-fidelity test,
not a fashion-correctness test.

Pure-function helpers (``compare_extraction``, ``aggregate_results``)
are unit-tested in tests/test_open_axis_eval.py without an LLM call.
The integration runner (``run_eval``) requires real planner LLM
calls and is gated on RUN_EVAL=1 in the pytest variant. Cost per
run is ~$0.01 (12 queries × ~$0.001 per gpt-5-mini call).

CLI:

    RUN_EVAL=1 python tests/eval/open_axis_eval.py

Module API:

    from tests.eval.open_axis_eval import (
        load_eval_set, compare_extraction, aggregate_results, run_eval
    )
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

# sys.path setup — make the src-layout modules importable when the
# script is invoked directly (e.g., `python tests/eval/open_axis_eval.py`).
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _src in (
    _REPO_ROOT,
    *sorted((_REPO_ROOT / "modules").glob("*/src"), reverse=True),
):
    s = str(_src)
    if s not in sys.path:
        sys.path.insert(0, s)


DEFAULT_EVAL_SET = _REPO_ROOT / "tests" / "eval" / "eval_set_5x.jsonl"


# ─────────────────────────────────────────────────────────────────────
# Data shapes
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvalCase:
    """One row from eval_set_5x.jsonl."""
    id: str
    user_message: str
    expected_extracted_preferences: Dict[str, List[str]]
    notes: str = ""


@dataclass(frozen=True)
class CaseResult:
    """Outcome of evaluating one case.

    ``status``:
    - ``"pass"`` — exact match (or both empty for negatives)
    - ``"partial"`` — actual is a non-strict subset of expected
                      (under-extracted, didn't make anything up)
    - ``"fail"``  — actual contains keys/values not in expected
                    (over-extracted)
    """
    case_id: str
    user_message: str
    expected: Dict[str, List[str]]
    actual: Dict[str, List[str]]
    status: str  # "pass" | "partial" | "fail"
    extra_axes: List[str] = field(default_factory=list)  # axes in actual not in expected (key-level over-extraction)
    missing_axes: List[str] = field(default_factory=list)  # axes in expected not in actual (under-extraction)
    value_fail_axes: List[str] = field(default_factory=list)  # axes present in both, actual has values not in expected (value-level over-extraction)
    value_partial_axes: List[str] = field(default_factory=list)  # axes present in both, actual is a strict subset of expected values


@dataclass(frozen=True)
class AxisStats:
    attribute: str
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> Optional[float]:
        denom = self.true_positives + self.false_positives
        return None if denom == 0 else self.true_positives / denom

    @property
    def recall(self) -> Optional[float]:
        denom = self.true_positives + self.false_negatives
        return None if denom == 0 else self.true_positives / denom


@dataclass(frozen=True)
class Aggregate:
    total: int
    pass_: int
    partial: int
    fail: int
    by_axis: Dict[str, AxisStats]

    @property
    def pass_rate(self) -> float:
        return 0.0 if self.total == 0 else self.pass_ / self.total

    @property
    def fail_rate(self) -> float:
        return 0.0 if self.total == 0 else self.fail / self.total


# ─────────────────────────────────────────────────────────────────────
# Loaders
# ─────────────────────────────────────────────────────────────────────


def load_eval_set(path: Path = DEFAULT_EVAL_SET) -> List[EvalCase]:
    """Read JSONL eval cases. Skips blank lines and lines starting with '#'."""
    out: List[EvalCase] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            row = json.loads(line)
            out.append(
                EvalCase(
                    id=str(row.get("id") or "").strip(),
                    user_message=str(row.get("user_message") or "").strip(),
                    expected_extracted_preferences={
                        str(k): [str(v) for v in (vs or [])]
                        for k, vs in (row.get("expected_extracted_preferences") or {}).items()
                    },
                    notes=str(row.get("notes") or ""),
                )
            )
    return out


# ─────────────────────────────────────────────────────────────────────
# Comparison
# ─────────────────────────────────────────────────────────────────────


def compare_extraction(
    expected: Mapping[str, Sequence[str]],
    actual: Mapping[str, Sequence[str]],
    case_id: str = "",
    user_message: str = "",
) -> CaseResult:
    """Compare planner-emitted extracted_preferences against expected.

    Status semantics:
    - Both empty → pass.
    - Actual contains a key not in expected → fail (over-extraction).
    - Expected has a key missing from actual → partial (under-extraction).
    - All actual keys are in expected and values are a subset of expected
      values → pass (when key sets match) or partial (when actual is a
      strict subset of expected by keys or values).
    - Actual contains a value not in expected for a shared key → fail
      (made up a value the prompt said the user didn't ask for).
    """
    expected_keys = set(expected.keys())
    actual_keys = set(actual.keys())
    extra_axes = sorted(actual_keys - expected_keys)
    missing_axes = sorted(expected_keys - actual_keys)

    if extra_axes:
        return CaseResult(
            case_id=case_id, user_message=user_message,
            expected=dict(expected), actual=dict(actual),
            status="fail", extra_axes=extra_axes,
            missing_axes=missing_axes,
        )

    value_partial_axes: List[str] = []
    value_fail_axes: List[str] = []
    for k in expected_keys & actual_keys:
        e_set = set(expected[k] or [])
        a_set = set(actual[k] or [])
        if a_set - e_set:
            value_fail_axes.append(k)
        elif a_set != e_set:
            value_partial_axes.append(k)

    if value_fail_axes:
        return CaseResult(
            case_id=case_id, user_message=user_message,
            expected=dict(expected), actual=dict(actual),
            status="fail", extra_axes=[],
            missing_axes=missing_axes,
            value_fail_axes=sorted(value_fail_axes),
            value_partial_axes=sorted(value_partial_axes),
        )

    if missing_axes or value_partial_axes:
        return CaseResult(
            case_id=case_id, user_message=user_message,
            expected=dict(expected), actual=dict(actual),
            status="partial", extra_axes=[],
            missing_axes=missing_axes,
            value_partial_axes=sorted(value_partial_axes),
        )

    return CaseResult(
        case_id=case_id, user_message=user_message,
        expected=dict(expected), actual=dict(actual),
        status="pass",
    )


# ─────────────────────────────────────────────────────────────────────
# Aggregation
# ─────────────────────────────────────────────────────────────────────


def aggregate_results(results: Sequence[CaseResult]) -> Aggregate:
    """Collapse per-case results into pass/partial/fail counts plus
    per-axis precision/recall.

    Axis-level metrics treat each (case, axis) as one observation:
    - TP: axis present in both expected and actual (value-subset OK)
    - FP: axis present in actual but not expected
    - FN: axis present in expected but not actual
    """
    pass_ = sum(1 for r in results if r.status == "pass")
    partial = sum(1 for r in results if r.status == "partial")
    fail = sum(1 for r in results if r.status == "fail")

    tp: Dict[str, int] = {}
    fp: Dict[str, int] = {}
    fn: Dict[str, int] = {}
    for r in results:
        e_keys = set(r.expected.keys())
        a_keys = set(r.actual.keys())
        for k in e_keys & a_keys:
            tp[k] = tp.get(k, 0) + 1
        for k in a_keys - e_keys:
            fp[k] = fp.get(k, 0) + 1
        for k in e_keys - a_keys:
            fn[k] = fn.get(k, 0) + 1

    all_axes = sorted(set(tp) | set(fp) | set(fn))
    by_axis = {
        a: AxisStats(
            attribute=a,
            true_positives=tp.get(a, 0),
            false_positives=fp.get(a, 0),
            false_negatives=fn.get(a, 0),
        )
        for a in all_axes
    }
    return Aggregate(
        total=len(results),
        pass_=pass_,
        partial=partial,
        fail=fail,
        by_axis=by_axis,
    )


# ─────────────────────────────────────────────────────────────────────
# Runner — needs real planner LLM
# ─────────────────────────────────────────────────────────────────────


def _build_minimal_planner_input(message: str) -> Dict[str, Any]:
    """Minimal planner input shaped like build_planner_input but without
    a UserContext object. Stays neutral (no archetype, no wardrobe, no
    prior recommendations) so the user_message is the dominant signal
    and the eval measures EXTRACTION quality, not personalization."""
    return {
        "user_message": message.strip(),
        "conversation_history": [],
        "user_profile": {
            "gender": "feminine",
            "seasonal_color_group": None,
            "base_colors": [],
            "accent_colors": [],
            "avoid_colors": [],
            "contrast_level": None,
            "frame_structure": None,
            "height_category": None,
            "risk_tolerance": "balanced",
            "profile_richness": "minimal",
        },
        "wardrobe_summary": {"count": 0, "top_items": []},
        "previous_recommendations": None,
        "previous_occasion": None,
        "previous_intent": None,
        "profile_confidence_pct": 60,
        "has_person_image": False,
        "has_attached_image": False,
        "url_detected": None,
    }


def run_eval(
    cases: Sequence[EvalCase],
    *,
    planner: Optional[Any] = None,
    verbose: bool = True,
) -> List[CaseResult]:
    """Run each case through the planner and compare. Returns the list
    of CaseResults; the caller aggregates / formats.

    ``planner`` defaults to a fresh ``CopilotPlanner()`` — pass an
    instance to share across runs or to inject a mock. Real LLM calls
    require ``OPENAI_API_KEY`` in the environment and may incur cost
    (~$0.001/case at gpt-5-mini)."""
    if planner is None:
        from agentic_application.agents.copilot_planner import CopilotPlanner
        planner = CopilotPlanner()

    results: List[CaseResult] = []
    for case in cases:
        planner_input = _build_minimal_planner_input(case.user_message)
        try:
            plan_result = planner.plan(planner_input)
            actual = dict(plan_result.resolved_context.extracted_preferences or {})
        except Exception as exc:  # noqa: BLE001 — surface and keep going
            if verbose:
                print(f"  [{case.id}] ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
            results.append(CaseResult(
                case_id=case.id, user_message=case.user_message,
                expected=case.expected_extracted_preferences,
                actual={},
                status="fail",
                missing_axes=sorted(case.expected_extracted_preferences.keys()),
            ))
            continue

        cr = compare_extraction(
            case.expected_extracted_preferences,
            actual,
            case_id=case.id,
            user_message=case.user_message,
        )
        results.append(cr)
        if verbose:
            tag = {"pass": "✓", "partial": "~", "fail": "✗"}.get(cr.status, "?")
            print(f"  {tag} [{case.id:30s}] {cr.status}", file=sys.stderr)
    return results


# ─────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────


def format_report(agg: Aggregate, results: Sequence[CaseResult]) -> str:
    """Human-readable markdown summary."""
    lines = [
        f"# Open-axis extraction eval — {agg.total} cases",
        "",
        f"- pass:    {agg.pass_:>3} / {agg.total} ({100*agg.pass_rate:.0f}%)",
        f"- partial: {agg.partial:>3} / {agg.total}",
        f"- fail:    {agg.fail:>3} / {agg.total} ({100*agg.fail_rate:.0f}%)",
        "",
        "## Per-axis metrics",
        "",
        "| attribute | TP | FP | FN | precision | recall |",
        "|---|---|---|---|---|---|",
    ]
    for axis_name in sorted(agg.by_axis):
        s = agg.by_axis[axis_name]
        p = "—" if s.precision is None else f"{s.precision:.2f}"
        r = "—" if s.recall is None else f"{s.recall:.2f}"
        lines.append(
            f"| {axis_name} | {s.true_positives} | {s.false_positives} | {s.false_negatives} | {p} | {r} |"
        )
    if agg.fail or agg.partial:
        lines.extend(["", "## Non-pass cases", ""])
        for r in results:
            if r.status == "pass":
                continue
            lines.append(f"### [{r.case_id}] {r.status} — \"{r.user_message}\"")
            lines.append(f"- expected: `{r.expected}`")
            lines.append(f"- actual:   `{r.actual}`")
            if r.extra_axes:
                lines.append(f"- over-extracted axes: {r.extra_axes}")
            if r.value_fail_axes:
                lines.append(f"- axes with unexpected values: {r.value_fail_axes}")
            if r.missing_axes:
                lines.append(f"- missing: {r.missing_axes}")
            if r.value_partial_axes:
                lines.append(f"- value-subset: {r.value_partial_axes}")
            lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--cases", type=Path, default=DEFAULT_EVAL_SET,
        help=f"Path to eval JSONL (default: {DEFAULT_EVAL_SET.name})",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Run only the first N cases (0 = all)",
    )
    args = parser.parse_args(argv)

    if not os.getenv("RUN_EVAL"):
        print(
            "Refusing to run without RUN_EVAL=1 (real LLM calls cost money).",
            file=sys.stderr,
        )
        return 2

    cases = load_eval_set(args.cases)
    if args.limit > 0:
        cases = cases[: args.limit]
    print(f"Loaded {len(cases)} eval cases from {args.cases}", file=sys.stderr)
    print("Running planner against each…", file=sys.stderr)

    results = run_eval(cases)
    agg = aggregate_results(results)
    print(format_report(agg, results))
    # Exit 0 iff zero failures. Partial doesn't fail the run by default —
    # the prompt's allowed-value lists are deliberately loose ("flowy" → fluid OR
    # soft_structured) and the planner picking the inner subset is acceptable.
    return 1 if agg.fail else 0


if __name__ == "__main__":
    sys.exit(main())
