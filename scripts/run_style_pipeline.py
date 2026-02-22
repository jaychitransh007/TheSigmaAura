#!/usr/bin/env python3
import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from catalog_enrichment.styling_filters import (  # noqa: E402
    UserContext,
    filter_catalog_rows,
    load_tier_a_rules,
    parse_relaxed_filters,
    read_csv_rows as read_filter_csv_rows,
    write_csv_rows,
)
from catalog_enrichment.tier2_ranker import (  # noqa: E402
    load_tier2_rules,
    rank_garments,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run full styling engine: Tier 1 filters + Tier 2 ranking + compact ranked summary."
    )
    parser.add_argument("--input", default="out/enriched.csv", help="Input enriched CSV.")
    parser.add_argument("--profile", required=True, help="User profile JSON path for Tier 2 ranking.")
    parser.add_argument("--occasion", required=True, help="Occasion context (e.g. 'Work Mode').")
    parser.add_argument("--archetype", required=True, help="Archetype context (e.g. 'Classic').")
    parser.add_argument("--gender", required=True, help="User gender.")
    parser.add_argument("--age", required=True, help="Age band: 18-24, 25-30, 30-35.")
    parser.add_argument(
        "--relax",
        action="append",
        default=[],
        help=(
            "Relax Tier 1 hard filters: price, age, archetype, occasion_archetype. "
            "Repeat or comma-separate."
        ),
    )
    parser.add_argument(
        "--tier2-strictness",
        default="balanced",
        choices=["safe", "balanced", "bold"],
        help="Tier 2 strictness profile.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Optional max ranked rows in final outputs (0 = all).")
    parser.add_argument("--out-dir", default="out", help="Output directory for all artifacts.")
    parser.add_argument("--prefix", default="style_pipeline", help="Artifact filename prefix.")
    return parser.parse_args()


def _write_ranked_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _build_summary_rows(ranked_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for i, row in enumerate(ranked_rows, start=1):
        out.append(
            {
                "rank": str(i),
                "id": str(row.get("id", "")),
                "title": str(row.get("title", "")),
                "images__0__src": str(row.get("images__0__src", "")),
                "images__1__src": str(row.get("images__1__src", "")),
                "tier2_final_score": str(row.get("tier2_final_score", "")),
                "tier2_raw_score": str(row.get("tier2_raw_score", "")),
                "tier2_confidence_multiplier": str(row.get("tier2_confidence_multiplier", "")),
                "tier2_flags": str(row.get("tier2_flags", "")),
            }
        )
    return out


def _write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    try:
        args = parse_args()
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        filtered_csv = out_dir / f"{args.prefix}_filtered.csv"
        filter_failures_json = out_dir / f"{args.prefix}_filter_failures.json"
        ranked_csv = out_dir / f"{args.prefix}_ranked.csv"
        explain_json = out_dir / f"{args.prefix}_ranked_explainability.json"
        summary_csv = out_dir / f"{args.prefix}_ranked_summary.csv"

        rows = read_filter_csv_rows(args.input)
        t1_rules = load_tier_a_rules()
        t2_rules = load_tier2_rules()
        relaxed = parse_relaxed_filters(args.relax)
        ctx = UserContext(
            occasion=args.occasion,
            archetype=args.archetype,
            gender=args.gender,
            age=args.age,
        )
        passed, failed = filter_catalog_rows(rows=rows, ctx=ctx, rules=t1_rules, relaxed_filters=relaxed)
        write_csv_rows(str(filtered_csv), passed)

        with filter_failures_json.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "total_rows": len(rows),
                    "passed_rows": len(passed),
                    "failed_rows": len(failed),
                    "context": {
                        "occasion": args.occasion,
                        "archetype": args.archetype,
                        "gender": args.gender,
                        "age": args.age,
                        "relaxed_filters": sorted(relaxed),
                    },
                    "failures": failed,
                },
                f,
                ensure_ascii=True,
                indent=2,
            )

        with open(args.profile, "r", encoding="utf-8") as f:
            profile = json.load(f)

        ranked = rank_garments(rows=passed, user_profile=profile, rules=t2_rules, strictness=args.tier2_strictness)
        if args.limit > 0:
            ranked = ranked[: args.limit]

        ranked_rows = [r.row for r in ranked]
        _write_ranked_csv(ranked_csv, ranked_rows)
        summary_rows = _build_summary_rows(ranked_rows)
        _write_csv(summary_csv, summary_rows)

        with explain_json.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "input_rows": len(rows),
                    "tier1_passed_rows": len(passed),
                    "tier1_failed_rows": len(failed),
                    "tier2_ranked_rows": len(ranked_rows),
                    "tier2_strictness": args.tier2_strictness,
                    "profile_path": args.profile,
                    "artifacts": {
                        "filtered_csv": str(filtered_csv),
                        "filter_failures_json": str(filter_failures_json),
                        "ranked_csv": str(ranked_csv),
                        "ranked_summary_csv": str(summary_csv),
                    },
                    "top_results": [
                        {
                            "rank": i + 1,
                            "id": r.row.get("id", ""),
                            "title": r.row.get("title", ""),
                            "image_1": r.row.get("images__0__src", ""),
                            "image_2": r.row.get("images__1__src", ""),
                            "tier2_final_score": r.final_score,
                            "tier2_raw_score": r.raw_score,
                            "tier2_confidence_multiplier": r.confidence_multiplier,
                            "tier2_flags": r.flags,
                        }
                        for i, r in enumerate(ranked[:25])
                    ],
                },
                f,
                ensure_ascii=True,
                indent=2,
            )

        print(f"input_rows={len(rows)}")
        print(f"tier1_passed={len(passed)}")
        print(f"tier1_failed={len(failed)}")
        print(f"tier2_ranked={len(ranked_rows)}")
        print(f"filtered_csv={filtered_csv}")
        print(f"filter_failures_json={filter_failures_json}")
        print(f"ranked_csv={ranked_csv}")
        print(f"ranked_summary_csv={summary_csv}")
        print(f"explain_json={explain_json}")
        return 0
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
