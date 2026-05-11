#!/usr/bin/env python3
"""Phase 2 Wave A ontology-surgery audit.

Produces the data each Wave A surgical PR needs:

1. **Redundancy correlations** — for each "claimed-redundant" axis pair
   (e.g., FitEase vs FitType), how strongly co-occur the values across
   the 14,242 enriched rows? High correlation supports removal.
2. **Confidence + null-rate** distribution per candidate-for-removal
   axis (StretchLevel, OccasionFit, OccasionSignal). Confirms or
   refutes the vision-extractability claim.
3. **Consumer audit** — every PR-affecting reference (Python + YAML +
   SQL) to each candidate axis, so the surgery's scope is visible
   before any cut.

Output: a single markdown file (default: `docs/phase2_wave_a_audit.md`)
that each Wave A surgical PR can link as its evidence.

Usage:
    APP_ENV=staging python3 ops/scripts/phase2_wave_a_audit.py \\
        --output docs/phase2_wave_a_audit.md
"""
import argparse
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
for p in ["modules/platform_core/src", "modules/catalog/src", "modules/user_profiler/src"]:
    sys.path.insert(0, str(ROOT / p))

from platform_core.config import load_config
from platform_core.supabase_rest import SupabaseRestClient


# ─────────────────────────────────────────────────────────────────────────
# What we're auditing
# ─────────────────────────────────────────────────────────────────────────

# Redundancy claims from OPEN_TASKS Phase 2 Wave A. Each tuple is
# (candidate_for_removal, claimed_redundant_with). The audit reports
# co-occurrence — high overlap supports removal, low overlap means the
# claim is wrong and the axis carries independent signal.
REDUNDANCY_PAIRS: List[Tuple[str, str]] = [
    ("FitEase", "FitType"),
    ("SilhouetteContour", "SilhouetteType"),
    ("VolumeProfile", "VolumePlacement"),
    ("HipDefinition", "WaistDefinition"),
]

# Axes whose extractability the audit verifies via confidence + null
# rate. Per OPEN_TASKS: StretchLevel "vision can't reliably extract",
# OccasionFit / OccasionSignal "subjective; derive downstream".
EXTRACTABILITY_AXES: List[str] = [
    "StretchLevel",
    "OccasionFit",
    "OccasionSignal",
]

# Every axis the audit touches — needed for the consumer grep.
ALL_AXES_AUDITED: List[str] = sorted(
    set(a for pair in REDUNDANCY_PAIRS for a in pair) | set(EXTRACTABILITY_AXES)
)

# Where to look for consumers. Limited to source dirs so generated
# files / virtualenvs / build artifacts don't pollute the report.
GREP_PATHS: List[str] = [
    "modules",
    "knowledge/style_graph",
    "supabase/migrations",
    "tests",
    "ops/scripts",
]


# ─────────────────────────────────────────────────────────────────────────
# Catalog fetch
# ─────────────────────────────────────────────────────────────────────────


_PAGE_SIZE = 1000


def _page_catalog_rows(client: SupabaseRestClient, columns: str) -> Iterable[dict]:
    offset = 0
    while True:
        batch = client.select_many(
            "catalog_enriched",
            columns=columns,
            order="product_id.asc",
            limit=_PAGE_SIZE,
            offset=offset,
        )
        if not batch:
            break
        for row in batch:
            yield row
        if len(batch) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE


def _fetch_redundancy_data(client: SupabaseRestClient) -> List[dict]:
    """Pull just the columns the redundancy correlations need — keeps
    the payload small (14K rows × 8 columns vs the full enrichment)."""
    needed = sorted({a for pair in REDUNDANCY_PAIRS for a in pair})
    columns = "product_id," + ",".join(needed)
    return list(_page_catalog_rows(client, columns))


def _fetch_extractability_data(client: SupabaseRestClient) -> List[dict]:
    needed = []
    for axis in EXTRACTABILITY_AXES:
        needed.append(axis)
        needed.append(f"{axis}_confidence")
    columns = "product_id," + ",".join(needed)
    return list(_page_catalog_rows(client, columns))


# ─────────────────────────────────────────────────────────────────────────
# Analyses
# ─────────────────────────────────────────────────────────────────────────


def _redundancy_report(rows: List[dict]) -> List[dict]:
    """For each pair, compute:
      - non_null_count: rows where BOTH axes are populated (the basis
        for correlation)
      - distinct_co_occurrence_count: number of distinct (a, b) value
        pairs observed
      - top_pairs: 10 most common (a, b) value pairs
      - dominant_pair_ratio: fraction of non_null_rows covered by the
        single most-common pair (a near-1 ratio is the strongest
        redundancy signal — one value of A nearly always implies one
        value of B)
      - entropy_ratio: H(B|A) / H(B) — how much A's value reduces
        uncertainty about B. Low ratio = strong dependence = high
        redundancy.
    """
    import math

    results = []
    for cand, kept in REDUNDANCY_PAIRS:
        non_null = [(r.get(cand), r.get(kept)) for r in rows if r.get(cand) and r.get(kept)]
        n = len(non_null)
        pair_counts = Counter(non_null)
        most_common = pair_counts.most_common(10)
        dominant_ratio = (most_common[0][1] / n) if n else 0.0

        # Conditional entropy: how predictable is `kept` given `cand`?
        b_counts: Counter = Counter()
        ab_counts: Dict[str, Counter] = defaultdict(Counter)
        for a, b in non_null:
            b_counts[b] += 1
            ab_counts[a][b] += 1

        def _entropy(counts: Counter, total: int) -> float:
            if total == 0:
                return 0.0
            h = 0.0
            for c in counts.values():
                p = c / total
                if p > 0:
                    h -= p * math.log2(p)
            return h

        h_b = _entropy(b_counts, n)
        h_b_given_a = 0.0
        for a, bs in ab_counts.items():
            a_total = sum(bs.values())
            h_b_given_a += (a_total / n) * _entropy(bs, a_total)
        entropy_ratio = (h_b_given_a / h_b) if h_b > 0 else 1.0

        results.append({
            "candidate": cand,
            "kept": kept,
            "non_null_count": n,
            "distinct_pairs": len(pair_counts),
            "dominant_pair_ratio": dominant_ratio,
            "entropy_ratio": entropy_ratio,
            "top_pairs": most_common,
        })
    return results


def _extractability_report(rows: List[dict]) -> List[dict]:
    """For each axis: null rate, mean / median / p10 confidence on
    non-null values, and distribution of values seen."""
    import statistics

    results = []
    total = len(rows)
    for axis in EXTRACTABILITY_AXES:
        null_count = sum(1 for r in rows if not r.get(axis))
        confidences = []
        value_counts: Counter = Counter()
        for r in rows:
            v = r.get(axis)
            if not v:
                continue
            value_counts[v] += 1
            c = r.get(f"{axis}_confidence")
            if c is not None:
                try:
                    confidences.append(float(c))
                except (TypeError, ValueError):
                    pass
        confidences.sort()
        mean_c = statistics.mean(confidences) if confidences else 0.0
        median_c = statistics.median(confidences) if confidences else 0.0
        p10 = confidences[max(0, len(confidences) // 10 - 1)] if confidences else 0.0
        results.append({
            "axis": axis,
            "total": total,
            "null_count": null_count,
            "null_rate": (null_count / total) if total else 0.0,
            "confidence_mean": mean_c,
            "confidence_median": median_c,
            "confidence_p10": p10,
            "value_counts_top": value_counts.most_common(10),
            "distinct_values": len(value_counts),
        })
    return results


def _consumer_audit(axes: List[str]) -> Dict[str, List[str]]:
    """Run `git grep` for each axis name in the source paths. Returns
    a dict of axis → list of file:line refs."""
    results: Dict[str, List[str]] = {}
    for axis in axes:
        # `git grep -n` keeps the output bounded to tracked files and
        # avoids walking ignored dirs. Limit each axis to 80 refs so
        # the report stays readable.
        try:
            out = subprocess.run(
                ["git", "grep", "-n", axis, "--"] + GREP_PATHS,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
            lines = (out.stdout or "").strip().splitlines()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            lines = []
        results[axis] = lines[:80]
    return results


# ─────────────────────────────────────────────────────────────────────────
# Markdown rendering
# ─────────────────────────────────────────────────────────────────────────


def _fmt_ratio(x: float) -> str:
    return f"{x:.3f}"


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _render_markdown(
    redundancy: List[dict],
    extractability: List[dict],
    consumers: Dict[str, List[str]],
    total_rows: int,
    generated_at: str,
) -> str:
    out: List[str] = []
    out.append("# Phase 2 Wave A — Ontology-Surgery Audit\n")
    out.append(
        f"Generated: `{generated_at}` against `catalog_enriched` "
        f"(N = {total_rows:,} rows).\n"
    )
    out.append(
        "Each Wave A surgical PR should link this report as its evidence — "
        "no cut ships unless the data here supports the OPEN_TASKS claim "
        "for that axis. Wave B (4 deferred ShapeArchitecture axes) is "
        "gated separately on Phase 4.6 eval data, not this report.\n"
    )

    # 1. Redundancy
    out.append("\n## 1. Redundancy correlations\n")
    out.append(
        "For each `(candidate_for_removal, claimed_redundant_with)` pair, "
        "we compute the conditional-entropy ratio H(B|A) / H(B): how much "
        "knowing A's value reduces uncertainty about B. **Lower = more "
        "redundant**. `dominant_pair_ratio` is the share of populated "
        "rows covered by the single most-common (A, B) value combination — "
        "near 1 means A nearly determines B.\n"
    )
    out.append(
        "**Surgical-decision rule of thumb**: entropy_ratio < 0.35 OR "
        "dominant_pair_ratio > 0.70 → strong support for removing the "
        "candidate. Between those bounds → review the top_pairs to see "
        "whether the residual signal is meaningful.\n"
    )
    out.append("| Candidate | Kept | non-null N | distinct pairs | dominant pair ratio | entropy ratio H(B\\|A)/H(B) | Surgical-decision |")
    out.append("|---|---|---:|---:|---:|---:|---|")
    for r in redundancy:
        verdict = (
            "✅ Remove" if r["entropy_ratio"] < 0.35 or r["dominant_pair_ratio"] > 0.70
            else ("⚠️ Review" if r["entropy_ratio"] < 0.55 else "❌ Keep")
        )
        out.append(
            f"| `{r['candidate']}` | `{r['kept']}` | {r['non_null_count']:,} | "
            f"{r['distinct_pairs']:,} | {_fmt_ratio(r['dominant_pair_ratio'])} | "
            f"{_fmt_ratio(r['entropy_ratio'])} | {verdict} |"
        )
    out.append("")

    out.append("### Top value-pairs per redundancy candidate\n")
    for r in redundancy:
        out.append(f"#### `{r['candidate']}` × `{r['kept']}`\n")
        out.append("| Pair | Count | Share |")
        out.append("|---|---:|---:|")
        for (a, b), c in r["top_pairs"]:
            share = (c / r["non_null_count"]) if r["non_null_count"] else 0
            out.append(f"| `{a}` → `{b}` | {c:,} | {_fmt_pct(share)} |")
        out.append("")

    # 2. Extractability
    out.append("\n## 2. Vision-extractability per candidate axis\n")
    out.append(
        "For each axis OPEN_TASKS proposes removing on extractability "
        "grounds, the null rate and the confidence distribution on "
        "non-null values. **High null rate (>30%) AND/OR low p10 "
        "confidence (<0.55) supports removal**: the vision model wasn't "
        "able to commit to an answer for many rows, suggesting the "
        "signal isn't reliably visible.\n"
    )
    out.append("| Axis | null rate | confidence mean | median | p10 | distinct values | Surgical-decision |")
    out.append("|---|---:|---:|---:|---:|---:|---|")
    for r in extractability:
        verdict = (
            "✅ Remove" if r["null_rate"] > 0.30 or r["confidence_p10"] < 0.55
            else ("⚠️ Review" if r["null_rate"] > 0.15 or r["confidence_p10"] < 0.70 else "❌ Keep")
        )
        out.append(
            f"| `{r['axis']}` | {_fmt_pct(r['null_rate'])} | "
            f"{_fmt_ratio(r['confidence_mean'])} | "
            f"{_fmt_ratio(r['confidence_median'])} | "
            f"{_fmt_ratio(r['confidence_p10'])} | "
            f"{r['distinct_values']} | {verdict} |"
        )
    out.append("")

    out.append("### Top values per extractability candidate\n")
    for r in extractability:
        non_null = r["total"] - r["null_count"]
        out.append(f"#### `{r['axis']}` (top values across {non_null:,} non-null rows)\n")
        out.append("| Value | Count | Share of populated |")
        out.append("|---|---:|---:|")
        for v, c in r["value_counts_top"]:
            share = (c / non_null) if non_null else 0
            out.append(f"| `{v}` | {c:,} | {_fmt_pct(share)} |")
        out.append("")

    # 3. Consumer audit
    out.append("\n## 3. Code / YAML / SQL consumers per axis\n")
    out.append(
        "Each candidate axis's downstream consumers (first 80 hits from "
        "`git grep`). Before any surgical PR, every reference must be "
        "either removed (drop site) or migrated to the kept axis "
        "(derive-from site). A short consumer list = a safer cut; a "
        "long one signals that the cleanup PR will be wider than it "
        "looks.\n"
    )
    for axis in ALL_AXES_AUDITED:
        hits = consumers.get(axis, [])
        out.append(f"\n### `{axis}` ({len(hits)} hits)\n")
        if not hits:
            out.append("_No references found._\n")
            continue
        out.append("```")
        for line in hits:
            out.append(line)
        out.append("```")

    out.append("")
    return "\n".join(out)


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--output",
        default="docs/phase2_wave_a_audit.md",
        help="Path to write the audit report.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    client = SupabaseRestClient(
        rest_url=config.supabase_rest_url,
        service_role_key=config.supabase_service_role_key,
    )

    print("[1/4] Fetching redundancy data from catalog_enriched...", flush=True)
    red_rows = _fetch_redundancy_data(client)
    print(f"      {len(red_rows):,} rows", flush=True)

    print("[2/4] Fetching extractability data...", flush=True)
    ext_rows = _fetch_extractability_data(client)
    print(f"      {len(ext_rows):,} rows", flush=True)

    print("[3/4] Computing redundancy + extractability + consumer audit...", flush=True)
    redundancy = _redundancy_report(red_rows)
    extractability = _extractability_report(ext_rows)
    consumers = _consumer_audit(ALL_AXES_AUDITED)

    print(f"[4/4] Writing report → {args.output}", flush=True)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out_path = ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md = _render_markdown(
        redundancy=redundancy,
        extractability=extractability,
        consumers=consumers,
        total_rows=len(red_rows),
        generated_at=generated_at,
    )
    out_path.write_text(md, encoding="utf-8")
    print("Done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
