#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from catalog_enrichment.styling_filters import (  # noqa: E402
    UserContext,
    filter_catalog_rows,
    load_tier_a_rules,
    parse_relaxed_filters,
    read_csv_rows,
    write_csv_rows,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tier A hard-filtered outfit selection from enriched CSV.")
    parser.add_argument("--input", default="out/enriched.csv", help="Input enriched CSV path.")
    parser.add_argument("--occasion", required=True, help="Occasion context (e.g. 'Work Mode').")
    parser.add_argument("--archetype", required=True, help="Archetype context (e.g. 'Classic').")
    parser.add_argument("--gender", required=True, help="User gender.")
    parser.add_argument("--age", required=True, help="Age band: 18-24, 25-30, or 30-35.")
    parser.add_argument("--output", default="out/filtered_outfits.csv", help="Output CSV path for passing items.")
    parser.add_argument("--fail-log", default="out/filtered_outfits_failures.json", help="Failure reason log path.")
    parser.add_argument("--limit", type=int, default=0, help="Optional max rows to keep (0 means no limit).")
    parser.add_argument(
        "--relax",
        action="append",
        default=[],
        help=(
            "Relax hard filters: price, age, archetype, occasion_archetype. "
            "Repeat or comma-separate (e.g. --relax age --relax price,archetype)."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = read_csv_rows(args.input)
    rules = load_tier_a_rules()
    ctx = UserContext(
        occasion=args.occasion,
        archetype=args.archetype,
        gender=args.gender,
        age=args.age,
    )
    relaxed = parse_relaxed_filters(args.relax)

    passed, failed = filter_catalog_rows(rows=rows, ctx=ctx, rules=rules, relaxed_filters=relaxed)
    if args.limit > 0:
        passed = passed[: args.limit]

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.fail_log).parent.mkdir(parents=True, exist_ok=True)

    write_csv_rows(args.output, passed)
    with open(args.fail_log, "w", encoding="utf-8") as f:
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

    print(f"total_rows={len(rows)}")
    print(f"passed_rows={len(passed)}")
    print(f"failed_rows={len(failed)}")
    print(f"relaxed_filters={','.join(sorted(relaxed)) if relaxed else '(none)'}")
    print(f"output_csv={args.output}")
    print(f"failure_log={args.fail_log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
