#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from catalog_enrichment.audit import PROMPT_PATH, run_schema_audit, write_audit_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit schema enums and prompt coverage.")
    parser.add_argument(
        "--prompt-path",
        default=str(PROMPT_PATH),
        help="Path to system prompt file.",
    )
    parser.add_argument(
        "--out",
        default="out/schema_audit.json",
        help="Path to write JSON audit report.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail (non-zero exit) if warnings are present.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_schema_audit(prompt_path=Path(args.prompt_path))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    write_audit_report(report, args.out)

    print(f"status: {report['status']}")
    if report["errors"]:
        print("errors:")
        for item in report["errors"]:
            print(f"- {item}")
    if report["warnings"]:
        print("warnings:")
        for item in report["warnings"]:
            print(f"- {item}")
    for item in report["info"]:
        print(item)
    print("pair_diffs:")
    print(json.dumps(report["pair_diffs"], indent=2))
    print(f"report_path: {args.out}")

    if report["status"] != "pass":
        return 1
    if args.strict and report["warnings"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
