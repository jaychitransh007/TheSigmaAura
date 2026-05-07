"""Composer engine quality validator (Phase 5e).

Runs the composer engine and the LLM ``OutfitComposer`` side-by-side on
each row of an eval JSONL and emits a markdown divergence report.
Mirrors ``composition_quality_eval.py`` (architect) but with the wider
input shape: composer needs ``RecommendationPlan`` and
``List[RetrievedSet]`` per cell, not just user + live context.

Eval JSONL row schema (one cell per line):

    {
      "cell_id": "c_00001",                          # required
      "user_context":  {<UserContext fields>},       # required
      "live_context":  {<LiveContext fields>},       # required
      "recommendation_plan": {<RecommendationPlan>}, # required
      "retrieved_sets": [<RetrievedSet>, ...],       # required
      "expected": { ... }                            # optional
    }

Usage:

    APP_ENV=staging PYTHONPATH=modules/agentic_application/src:modules/catalog/src:modules/platform_core/src:modules/style_engine/src:modules/user/src:modules/user_profiler/src \\
        python ops/scripts/composer_quality_eval.py \\
            --eval-set tests/eval/composer_eval_set.jsonl \\
            --report ops/reports/composer_quality_$(date +%Y%m%d).md \\
            [--limit 50]

The script only depends on:
- agentic_application.composition.* (engine + router + quality)
- agentic_application.agents.outfit_composer (LLM path)

Best-effort against the OpenAI API: per-row failures are logged and
the cell is recorded with status=error in the report; the script
keeps going so one bad row doesn't poison the whole eval.
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from agentic_application.composition.quality import ComposerComparison


_log = logging.getLogger("composer_quality_eval")


def _parse_inputs(row: Dict[str, Any]):
    from agentic_application.schemas import (
        CombinedContext,
        LiveContext,
        RecommendationPlan,
        RetrievedSet,
        UserContext,
    )

    user = UserContext(**row["user_context"])
    live = LiveContext(**row["live_context"])
    ctx = CombinedContext(user=user, live=live)
    plan = RecommendationPlan(**row["recommendation_plan"])
    retrieved_sets = [RetrievedSet(**rs) for rs in row.get("retrieved_sets", [])]
    return ctx, plan, retrieved_sets


def _run_one_cell(
    *,
    composer,
    graph,
    row: Dict[str, Any],
) -> Dict[str, Any]:
    """Run engine + LLM against a single eval cell. Mirrors the
    architect eval's single-cell shape."""
    cell_id = row.get("cell_id") or "unknown"
    try:
        ctx, plan, retrieved_sets = _parse_inputs(row)
    except Exception as exc:
        return {"cell_id": cell_id, "status": "parse_error", "error": str(exc)}

    from agentic_application.composition.composer_engine import compose_outfits
    from agentic_application.composition.composer_router import (
        extract_tuple_context,
        is_engine_eligible,
    )

    eligible, ineligibility = is_engine_eligible(ctx, plan)
    if not eligible:
        return {
            "cell_id": cell_id,
            "status": "engine_skipped",
            "reason": ineligibility,
        }

    tuple_ctx = extract_tuple_context(ctx)
    t_engine_0 = time.monotonic()
    engine_result = compose_outfits(
        plan=plan, retrieved_sets=retrieved_sets, ctx=tuple_ctx, graph=graph,
    )
    engine_ms = int((time.monotonic() - t_engine_0) * 1000)

    accepted = engine_result.composer_result is not None

    try:
        t_llm_0 = time.monotonic()
        llm_result = composer.compose(ctx, retrieved_sets)
        llm_ms = int((time.monotonic() - t_llm_0) * 1000)
    except Exception as exc:
        _log.exception("LLM composer failed on cell %s", cell_id)
        return {
            "cell_id": cell_id,
            "status": "llm_error",
            "error": str(exc),
            "engine_accepted": accepted,
            "engine_reject_reason": engine_result.fallback_reason,
            "engine_confidence": engine_result.confidence,
            "engine_ms": engine_ms,
        }

    out: Dict[str, Any] = {
        "cell_id": cell_id,
        "status": "ok",
        "engine_accepted": accepted,
        "engine_reject_reason": engine_result.fallback_reason,
        "engine_confidence": engine_result.confidence,
        "engine_yaml_gaps": list(engine_result.yaml_gaps),
        "engine_ms": engine_ms,
        "llm_ms": llm_ms,
        "engine_outfit_count": (
            len(engine_result.composer_result.outfits)
            if accepted else 0
        ),
        "llm_outfit_count": len(llm_result.outfits),
    }
    if accepted:
        from agentic_application.composition.quality import compare_composer_outputs

        out["comparison"] = compare_composer_outputs(
            engine_result.composer_result, llm_result
        )
    return out


def _emit_markdown(rows: List[Dict[str, Any]], report_path: Path) -> None:
    from agentic_application.composition.quality import aggregate_composer_eval

    comparisons = [r["comparison"] for r in rows if r.get("comparison") is not None]
    summary = aggregate_composer_eval(comparisons)

    fallback_reasons = Counter(
        r.get("engine_reject_reason") for r in rows if not r.get("engine_accepted")
    )
    fallback_reasons.pop(None, None)

    engine_ms = [r["engine_ms"] for r in rows if "engine_ms" in r]
    llm_ms = [r["llm_ms"] for r in rows if "llm_ms" in r]

    lines: List[str] = []
    lines.append("# Composer engine quality eval")
    lines.append("")
    lines.append(f"- cells: {len(rows)}")
    lines.append(f"- engine accepted: {sum(1 for r in rows if r.get('engine_accepted'))}")
    lines.append(f"- engine rejected: {sum(1 for r in rows if r.get('engine_accepted') is False)}")
    lines.append(f"- median engine ms: {statistics.median(engine_ms) if engine_ms else 'n/a'}")
    lines.append(f"- median LLM ms: {statistics.median(llm_ms) if llm_ms else 'n/a'}")
    lines.append("")
    lines.append("## Aggregate divergence (engine-accepted cells only)")
    lines.append("")
    lines.append(f"- cells compared: {summary.cell_count}")
    lines.append(
        f"- median item_ids Jaccard: {summary.median_item_ids_jaccard:.3f}"
    )
    lines.append(
        f"- direction_type match rate: {summary.direction_type_match_rate:.3f}"
    )
    lines.append(
        f"- overall_assessment match rate: {summary.overall_assessment_match_rate:.3f}"
    )
    lines.append("")
    lines.append("## Engine fallback reasons")
    lines.append("")
    if fallback_reasons:
        for reason, count in fallback_reasons.most_common():
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Per-cell rows")
    lines.append("")
    lines.append(
        "| cell_id | status | engine_accepted | confidence | reject_reason | "
        "item_jaccard | engine_outfits | llm_outfits |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        cmp = r.get("comparison")
        ij = f"{cmp.aggregate_item_ids_jaccard:.3f}" if cmp else "—"
        conf = (
            f"{r['engine_confidence']:.3f}"
            if r.get("engine_confidence") is not None
            else "—"
        )
        lines.append(
            f"| {r.get('cell_id')} | {r.get('status')} | "
            f"{r.get('engine_accepted', '—')} | {conf} | "
            f"{r.get('engine_reject_reason') or '—'} | {ij} | "
            f"{r.get('engine_outfit_count', '—')} | "
            f"{r.get('llm_outfit_count', '—')} |"
        )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Stop after this many cells (0 = all).",
    )
    args = parser.parse_args(argv)

    if not args.eval_set.exists():
        print(f"eval set not found: {args.eval_set}", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    from agentic_application.agents.outfit_composer import OutfitComposer
    from agentic_application.composition.yaml_loader import load_style_graph

    composer = OutfitComposer()
    graph = load_style_graph()

    rows: List[Dict[str, Any]] = []
    with open(args.eval_set, "r", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            if args.limit and len(rows) >= args.limit:
                break
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                _log.error("line %d JSON parse failed: %s", i + 1, exc)
                rows.append(
                    {"cell_id": f"line_{i+1}", "status": "json_error", "error": str(exc)}
                )
                continue
            rows.append(_run_one_cell(composer=composer, graph=graph, row=row))

    _emit_markdown(rows, args.report)
    print(f"wrote {args.report}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
