#!/usr/bin/env python3
"""Engine confidence analysis from ``composition_router_decision`` traces.

PR #207 began persisting every router decision to ``tool_traces`` —
``used_engine``, ``fallback_reason``, ``engine_confidence``,
``yaml_gaps``, ``per_axis_gap_impact``, ``provenance_summary``,
``engine_ms``. This script reads recent rows and surfaces:

  1. Acceptance rate (engine vs LLM fallback) and reason distribution.
  2. For ``low_confidence`` + ``yaml_gap`` rejections — the rejections
     we could actually fix via weight tuning — the median confidence,
     gap to the 0.50 threshold, and the top axes by cumulative
     impact.
  3. Provenance hot spots: most common omitted / hard_widened /
     soft_relaxed attributes on rejected turns.
  4. A ranked recommendation of which ``_YAML_GAP_AXIS_WEIGHTS`` keys
     would move the most rejected turns above threshold if their
     weight dropped to a tuning floor (NOT applied by this script —
     analysis only).

The script does NOT modify code or the engine. It produces a Markdown
report on stdout suitable for handing to the team that owns Phase 4.6
eval-set prioritization.

Usage:

    APP_ENV=staging python3 ops/scripts/analyze_engine_confidence.py
    APP_ENV=staging python3 ops/scripts/analyze_engine_confidence.py --limit 2000
    APP_ENV=staging python3 ops/scripts/analyze_engine_confidence.py --since 2026-05-08

The companion ``tune_yaml_gap_weights.py`` runs a different analysis
(per-axis fallback correlation from ``distillation_traces``) and
emits direct weight suggestions. This script is more focused on
**which rejected turns are recoverable** — the universe Phase 4.6
should prioritize curating eval queries for.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

# sys.path bootstrap so this script runs standalone.
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _src in (
    _REPO_ROOT,
    *sorted((_REPO_ROOT / "modules").glob("*/src"), reverse=True),
):
    s = str(_src)
    if s not in sys.path:
        sys.path.insert(0, s)


# Below this many low_confidence/yaml_gap rejections, we don't try to
# rank axes — distribution is too thin to read signal from noise.
MIN_REJECTIONS_FOR_RANKING = 20

# Tuning-floor weight used for the "what if we floored this axis's
# weight?" simulation. The current floor in tune_yaml_gap_weights.py
# is 0.3. Matches the project's existing convention.
TUNING_FLOOR_WEIGHT = 0.3

# Engine confidence threshold from composition/engine.py. Hardcoded to
# avoid an import chain just for one constant; re-check if the engine
# changes its threshold.
CONFIDENCE_THRESHOLD = 0.50


def _pull_router_decisions(client, since_iso: str | None, limit: int) -> list[dict]:
    """Fetch ``composition_router_decision`` rows from tool_traces."""
    filters: dict[str, str] = {"tool_name": "eq.composition_router_decision"}
    if since_iso:
        filters["created_at"] = f"gte.{since_iso}"
    rows = client.select_many(
        "tool_traces",
        columns="turn_id,input_json,output_json,latency_ms,created_at",
        filters=filters,
        order="created_at.desc",
        limit=limit,
    )
    return rows or []


def _is_recoverable_rejection(reason: str | None) -> bool:
    """``low_confidence`` and ``yaml_gap`` are the rejection reasons
    that confidence-math tuning can actually move. The other reasons
    (engine_disabled, anchor_*, has_previous_recommendations,
    followup_request, no_direction, excessive_widening,
    needs_disambiguation, engine_error) reflect input shape or
    non-tunable engine state."""
    return (reason or "").lower() in ("low_confidence", "yaml_gap")


def _analyze(rows: list[dict]) -> dict[str, Any]:
    """Pure analysis. Takes a list of rows, returns a structured dict
    of metrics. No I/O, easy to unit-test."""
    n_total = len(rows)
    n_engine = 0
    n_fallback = 0
    reason_counts: Counter = Counter()

    # Buckets for recoverable rejections (low_confidence + yaml_gap)
    rec_confidences: list[float] = []
    rec_axis_impact: defaultdict = defaultdict(float)  # axis → cumulative confidence loss
    rec_axis_count: Counter = Counter()                # axis → number of rejected turns it appeared in
    rec_omitted: Counter = Counter()
    rec_hard_widened: Counter = Counter()
    rec_soft_relaxed: Counter = Counter()
    n_recoverable = 0

    for r in rows:
        out = r.get("output_json") or {}
        if not isinstance(out, dict):
            continue
        used_engine = out.get("used_engine")
        reason = out.get("fallback_reason")
        if used_engine is True:
            n_engine += 1
            continue
        n_fallback += 1
        reason_counts[str(reason or "unknown")] += 1

        if _is_recoverable_rejection(reason):
            n_recoverable += 1
            conf = out.get("engine_confidence")
            if isinstance(conf, (int, float)):
                rec_confidences.append(float(conf))
            impact = out.get("per_axis_gap_impact") or {}
            if isinstance(impact, dict):
                for axis, contrib in impact.items():
                    if isinstance(contrib, (int, float)):
                        rec_axis_impact[axis] += float(contrib)
                        rec_axis_count[axis] += 1
            prov = out.get("provenance_summary") or {}
            if isinstance(prov, dict):
                for attr in (prov.get("omitted") or []):
                    rec_omitted[str(attr)] += 1
                for attr in (prov.get("hard_widened") or []):
                    rec_hard_widened[str(attr)] += 1
                for attr in (prov.get("soft_relaxed") or []):
                    rec_soft_relaxed[str(attr)] += 1

    return {
        "n_total": n_total,
        "n_engine": n_engine,
        "n_fallback": n_fallback,
        "reason_counts": reason_counts,
        "n_recoverable": n_recoverable,
        "rec_confidences": rec_confidences,
        "rec_axis_impact": dict(rec_axis_impact),
        "rec_axis_count": dict(rec_axis_count),
        "rec_omitted": rec_omitted,
        "rec_hard_widened": rec_hard_widened,
        "rec_soft_relaxed": rec_soft_relaxed,
    }


def _simulate_floor(
    rec_confidences: list[float],
    rec_axis_impact: dict[str, float],
    n_recoverable: int,
    floor: float,
) -> list[tuple[str, float, int]]:
    """For each axis, estimate how many rejected turns would clear
    ``CONFIDENCE_THRESHOLD`` if that axis's per-turn impact dropped
    to the floor weight. The simulation is approximate — it assumes
    each rejected turn would gain back a uniform per-axis delta — but
    it ranks axes by potential recovery impact, which is what Phase
    4.6 prioritization actually needs.

    Returns ``[(axis, recovered_turns_estimate, rejected_turn_count_for_axis)]``
    sorted by recovered_turns_estimate descending."""
    if n_recoverable == 0:
        return []
    # Per-axis average impact-per-turn-it-appeared-on.
    # rec_axis_impact[axis] is cumulative across all turns; if we
    # don't know how many turns each axis appeared on, fall back to
    # n_recoverable as denominator (under-estimates per-turn delta
    # but keeps the ranking direction-correct).
    out: list[tuple[str, float, int]] = []
    for axis, cumulative in rec_axis_impact.items():
        if cumulative <= 0:
            continue
        # Heuristic: assume floor halves the axis's contribution
        # (most current weights are 0.5-1.5; floor is 0.3). On rejections
        # at confidence ~0.20-0.30, recovering ~0.20 typically clears
        # the threshold. Estimate: (cumulative / n_recoverable) is the
        # average per-rejection contribution; if that contribution alone
        # exceeds the threshold gap, count the rejection as recoverable.
        avg_threshold_gap = 0.0
        if rec_confidences:
            avg_threshold_gap = max(
                0.0, CONFIDENCE_THRESHOLD - (sum(rec_confidences) / len(rec_confidences))
            )
        avg_axis_per_turn = cumulative / n_recoverable
        # Recoverable ≈ how many turns the axis's average contribution
        # would have closed the threshold gap. Capped at n_recoverable.
        recoverable_frac = (
            min(1.0, avg_axis_per_turn / max(avg_threshold_gap, 0.01))
            if avg_threshold_gap > 0 else 0.0
        )
        recovered_turns = int(recoverable_frac * n_recoverable)
        out.append((axis, recovered_turns, n_recoverable))
    out.sort(key=lambda t: t[1], reverse=True)
    return out


def _format_report(analysis: dict[str, Any], window_label: str) -> str:
    """Render the analysis as a Markdown report."""
    n_total = analysis["n_total"]
    n_engine = analysis["n_engine"]
    n_fallback = analysis["n_fallback"]
    reason_counts: Counter = analysis["reason_counts"]
    n_rec = analysis["n_recoverable"]
    rec_confidences: list[float] = analysis["rec_confidences"]
    rec_axis_impact: dict[str, float] = analysis["rec_axis_impact"]
    rec_axis_count: dict[str, int] = analysis["rec_axis_count"]

    out: list[str] = []
    out.append(f"# Engine confidence analysis — {window_label}")
    out.append("")
    if n_total == 0:
        out.append("No `composition_router_decision` rows found in the requested window.")
        out.append("")
        out.append("- Confirm `AURA_COMPOSITION_ENGINE_ENABLED=true` is set on the running service.")
        out.append("- Confirm at least one occasion or eligible-pairing turn ran post-PR-#207.")
        return "\n".join(out)

    accept_pct = 100.0 * n_engine / n_total
    out.append(f"**Total decisions:** {n_total}  ")
    out.append(f"**Engine accepted:** {n_engine} ({accept_pct:.1f}%)  ")
    out.append(f"**LLM fallback:** {n_fallback} ({100.0 - accept_pct:.1f}%)")
    out.append("")
    out.append("## Fallback reasons")
    out.append("")
    out.append("| reason | count | % of fallbacks | recoverable via weight tuning? |")
    out.append("|---|---:|---:|:---:|")
    for reason, cnt in reason_counts.most_common():
        pct = 100.0 * cnt / n_fallback if n_fallback else 0.0
        rec_marker = "✅" if _is_recoverable_rejection(reason) else "—"
        out.append(f"| `{reason}` | {cnt} | {pct:.1f}% | {rec_marker} |")
    out.append("")

    if n_rec == 0:
        out.append("## Recoverable rejections")
        out.append("")
        out.append("No `low_confidence` or `yaml_gap` rejections in the window. No weight-tuning leverage to find here.")
        return "\n".join(out)

    out.append(f"## Recoverable rejections ({n_rec} turns: low_confidence + yaml_gap)")
    out.append("")
    if rec_confidences:
        med = median(rec_confidences)
        gap = CONFIDENCE_THRESHOLD - med
        out.append(
            f"**Median engine_confidence:** {med:.3f}  "
            f"(threshold {CONFIDENCE_THRESHOLD}, gap {gap:+.3f})"
        )
    out.append("")

    if n_rec < MIN_REJECTIONS_FOR_RANKING:
        out.append(
            f"_Sample size {n_rec} is below floor {MIN_REJECTIONS_FOR_RANKING}; "
            "axis ranking suppressed (too noisy). Increase --limit or wait for more traffic._"
        )
        return "\n".join(out)

    out.append("### Top axes by cumulative confidence loss on rejected turns")
    out.append("")
    out.append("| axis | rejected turns it appeared on | cumulative confidence loss | avg per-turn |")
    out.append("|---|---:|---:|---:|")
    by_impact = sorted(rec_axis_impact.items(), key=lambda kv: kv[1], reverse=True)
    for axis, cumulative in by_impact[:10]:
        cnt = rec_axis_count.get(axis, 0)
        avg = cumulative / cnt if cnt else 0.0
        out.append(f"| `{axis}` | {cnt} | {cumulative:.2f} | {avg:.3f} |")
    out.append("")

    floor_sim = _simulate_floor(
        rec_confidences=rec_confidences,
        rec_axis_impact=rec_axis_impact,
        n_recoverable=n_rec,
        floor=TUNING_FLOOR_WEIGHT,
    )
    if floor_sim:
        out.append(f"### Heuristic recovery estimate at floor weight {TUNING_FLOOR_WEIGHT}")
        out.append("")
        out.append(
            "Approximate count of currently-rejected turns that would clear "
            f"the {CONFIDENCE_THRESHOLD} threshold if this axis's per-turn "
            f"impact dropped to the floor weight ({TUNING_FLOOR_WEIGHT}). The "
            "estimate assumes a uniform per-turn delta per axis — real "
            "tuning needs the Phase 4.6 eval set to validate quality, this "
            "ranks where to look first."
        )
        out.append("")
        out.append("| axis | est. turns recovered | of total rejected |")
        out.append("|---|---:|---:|")
        for axis, recovered, total in floor_sim[:10]:
            pct = 100.0 * recovered / total if total else 0.0
            out.append(f"| `{axis}` | {recovered} | {pct:.1f}% |")
        out.append("")

    out.append("### Provenance hot spots on rejected turns")
    out.append("")
    out.append("Frequency of attribute statuses on rejected turns. High counts here = the engine's reduction step is doing a lot of work that the user perceives as plan misses.")
    out.append("")
    for label, ctr in (
        ("Most-omitted attributes", analysis["rec_omitted"]),
        ("Most-hard-widened attributes", analysis["rec_hard_widened"]),
        ("Most-soft-relaxed attributes", analysis["rec_soft_relaxed"]),
    ):
        top = ctr.most_common(8)
        if not top:
            continue
        out.append(f"**{label}:** " + ", ".join(f"`{a}` ({c})" for a, c in top))
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--limit", type=int, default=2000,
        help="Max tool_traces rows to pull (default: 2000)",
    )
    parser.add_argument(
        "--days", type=int, default=7,
        help="Lookback window in days (default: 7). Ignored when --since is set.",
    )
    parser.add_argument(
        "--since", type=str, default="",
        help="ISO timestamp lower bound. Overrides --days when set. "
             "Example: 2026-05-08T00:00:00Z",
    )
    args = parser.parse_args(argv)

    # Lazy imports so --help works without a Supabase config.
    from platform_core.config import load_config
    from platform_core.supabase_rest import SupabaseRestClient

    cfg = load_config()
    client = SupabaseRestClient(cfg.supabase_rest_url, cfg.supabase_service_role_key)

    if args.since:
        since_iso = args.since
        window_label = f"since {args.since}"
    else:
        since = datetime.now(timezone.utc) - timedelta(days=args.days)
        since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        window_label = f"last {args.days} days (since {since_iso})"

    print(
        f"Pulling up to {args.limit} composition_router_decision rows {window_label} …",
        file=sys.stderr,
    )
    rows = _pull_router_decisions(client, since_iso, args.limit)
    print(f"  got {len(rows)} rows", file=sys.stderr)
    print("", file=sys.stderr)

    analysis = _analyze(rows)
    report = _format_report(analysis, window_label)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
