#!/usr/bin/env python3
"""Tuning harness for `_YAML_GAP_AXIS_WEIGHTS` (Phase 4 confidence
re-tune from telemetry).

Pulls recent architect distillation_traces, extracts the router
decision's `yaml_gaps` and `used_engine` flag, and computes per-axis
statistics that inform whether the current weight (from
`engine.py:_YAML_GAP_AXIS_WEIGHTS`) is right.

The tuning question per axis is: **does this axis appearing in the
gap list correlate with the engine being unable to produce a usable
plan?** If yes (gap → fallback dominates), weight UP. If no (axis
gap shows up in engine-accepted turns about as often as fallback
turns), the weight is too aggressive and should come down.

Usage:

    APP_ENV=staging python3 ops/scripts/tune_yaml_gap_weights.py
    APP_ENV=staging python3 ops/scripts/tune_yaml_gap_weights.py --limit 1000

Output: a markdown table per axis with:
- gap_count_total
- gap_in_engine_accepted (axis appeared in a turn that the engine still accepted)
- gap_in_llm_fallback (axis appeared in a turn that fell through)
- fallback_correlation = gap_in_llm_fallback / gap_count_total
- current_weight (read from engine.py)
- suggested_weight (heuristic: if correlation > 0.7 → UP; if < 0.3 → DOWN; otherwise keep)

The script does NOT modify code. It prints suggestions; the engineer
edits `_YAML_GAP_AXIS_WEIGHTS` in a follow-up PR.

**Sample-size guard:** any axis with fewer than `MIN_SAMPLE_FLOOR`
total occurrences gets a "data too sparse" note rather than a
suggestion. Avoids tuning on noise.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

# sys.path bootstrap so this script runs standalone.
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _src in (
    _REPO_ROOT,
    *sorted((_REPO_ROOT / "modules").glob("*/src"), reverse=True),
):
    s = str(_src)
    if s not in sys.path:
        sys.path.insert(0, s)


MIN_SAMPLE_FLOOR = 10  # below this, "data too sparse" instead of a suggestion
HIGH_CORRELATION_THRESHOLD = 0.7   # correlation above → weight up
LOW_CORRELATION_THRESHOLD = 0.3    # correlation below → weight down
WEIGHT_STEP = 0.2  # how much to nudge per direction


def _load_current_weights() -> dict[str, float]:
    """Read the current weight map from engine.py without importing
    the engine module (avoids pulling its YAML loader on a quick
    diagnostic run)."""
    from agentic_application.composition.engine import _YAML_GAP_AXIS_WEIGHTS
    return dict(_YAML_GAP_AXIS_WEIGHTS)


def _suggest_weight(
    current: float,
    correlation: float,
    sample_size: int,
) -> tuple[float | None, str]:
    """Return (suggested_weight, note). suggested_weight is None when
    the data is too sparse or no change is recommended."""
    if sample_size < MIN_SAMPLE_FLOOR:
        return None, f"data too sparse (n={sample_size} < floor {MIN_SAMPLE_FLOOR})"
    if correlation > HIGH_CORRELATION_THRESHOLD:
        return min(current + WEIGHT_STEP, 2.0), "high correlation with fallback → weight up"
    if correlation < LOW_CORRELATION_THRESHOLD:
        return max(current - WEIGHT_STEP, 0.3), "low correlation with fallback → weight down"
    return None, "correlation in middle band → keep current"


def _format_row(
    axis: str,
    total: int,
    in_engine: int,
    in_fallback: int,
    correlation: float,
    current_weight: float,
    suggested: float | None,
    note: str,
) -> str:
    sug = "—" if suggested is None else f"{suggested:.2f}"
    return (
        f"| {axis} | {total} | {in_engine} | {in_fallback} "
        f"| {correlation:.2f} | {current_weight:.2f} | {sug} | {note} |"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--limit", type=int, default=500,
        help="Max architect distillation_traces rows to pull (default: 500)",
    )
    args = parser.parse_args(argv)

    # Lazy imports so --help works without a Supabase config.
    from platform_core.config import load_config
    from platform_core.supabase_rest import SupabaseRestClient

    cfg = load_config()
    client = SupabaseRestClient(cfg.supabase_rest_url, cfg.supabase_service_role_key)

    print(f"Pulling up to {args.limit} architect distillation_traces …", file=sys.stderr)
    rows = client.select_many(
        "distillation_traces",
        columns="full_output,created_at",
        filters={"stage": "eq.outfit_architect"},
        order="created_at.desc",
        limit=args.limit,
    )
    print(f"  got {len(rows)} rows", file=sys.stderr)

    # Per-axis tallies: (total, in-engine-accepted, in-LLM-fallback)
    axis_total: Counter = Counter()
    axis_in_engine: Counter = Counter()
    axis_in_fallback: Counter = Counter()
    n_engine_total = 0
    n_fallback_total = 0
    fallback_reasons: Counter = Counter()

    for r in rows:
        fo = r.get("full_output") or {}
        rd = fo.get("router_decision") or {}
        used_engine = rd.get("used_engine")
        if used_engine is True:
            n_engine_total += 1
        elif used_engine is False:
            n_fallback_total += 1
        if rd.get("fallback_reason"):
            fallback_reasons[rd["fallback_reason"]] += 1
        for gap in rd.get("yaml_gaps") or []:
            if not isinstance(gap, str):
                continue
            axis = gap.split(":", 1)[0]
            axis_total[axis] += 1
            if used_engine is True:
                axis_in_engine[axis] += 1
            elif used_engine is False:
                axis_in_fallback[axis] += 1

    current_weights = _load_current_weights()

    # Header
    print()
    print(f"# YAML-gap weight tuning report")
    print()
    print(f"- rows scanned: **{len(rows)}**")
    print(f"- engine-accepted turns: {n_engine_total}")
    print(f"- LLM-fallback turns: {n_fallback_total}")
    if fallback_reasons:
        print()
        print("## Fallback reasons")
        print()
        for reason, n in fallback_reasons.most_common():
            print(f"- `{reason}`: {n}")
    print()

    # Per-axis table
    print("## Per-axis stats")
    print()
    print("| axis | total_gaps | in_engine_accepted | in_llm_fallback | fallback_correlation | current_weight | suggested_weight | note |")
    print("|---|---|---|---|---|---|---|---|")

    all_axes = sorted(set(axis_total) | set(current_weights))
    any_suggestion = False
    for axis in all_axes:
        total = axis_total.get(axis, 0)
        in_engine = axis_in_engine.get(axis, 0)
        in_fallback = axis_in_fallback.get(axis, 0)
        correlation = in_fallback / total if total else 0.0
        current_weight = current_weights.get(axis, 1.0)
        suggested, note = _suggest_weight(current_weight, correlation, total)
        if suggested is not None and abs(suggested - current_weight) > 1e-6:
            any_suggestion = True
        print(_format_row(
            axis, total, in_engine, in_fallback, correlation,
            current_weight, suggested, note,
        ))

    print()
    if not any_suggestion:
        print("**No suggestions.** Either the data is too sparse, or correlations are in the middle band. Re-run when more telemetry has accumulated.")
    else:
        print("**Suggestions present.** Edit `_YAML_GAP_AXIS_WEIGHTS` in")
        print("`modules/agentic_application/src/agentic_application/composition/engine.py`")
        print("with the suggested values, ship as a config-only PR.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
