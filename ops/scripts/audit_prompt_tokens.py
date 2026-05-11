#!/usr/bin/env python3
"""Prompt token audit (Phase 3.0).

Walks `prompt/*.md` and prints a per-file token estimate so we can
track prompt-size budget over time. Use it as a check before merging
prompt edits — Phase 3 set the architect's token target at ~5K (down
from ~14K) and the composer at <2K.

Token counts are estimated with `tiktoken` when available (gpt-4 /
gpt-5 family use the same `cl100k_base` BPE), and fall back to a
char-based approximation (chars / 4) when tiktoken isn't installed.
The approximation drifts a bit on heavy markdown/JSON, but the
relative trend across runs is what we care about for budget tracking.

Usage:

    python3 ops/scripts/audit_prompt_tokens.py
    python3 ops/scripts/audit_prompt_tokens.py --json     # machine-readable
    python3 ops/scripts/audit_prompt_tokens.py --budget   # exits 1 if any file exceeds its budget

Per-prompt budgets live in `_BUDGETS` below; bump them in this file
when a deliberate change crosses the line, so the budget walks
forward intentionally rather than drifting silently.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPT_DIR = _REPO_ROOT / "prompt"

# Per-prompt token budgets. Sized to be safe under both estimation
# methods: tiktoken's cl100k_base BPE (more accurate, ~10-15% lower)
# and the chars/4 fallback (deterministic, used when tiktoken isn't
# installed — e.g., CI). Set ~5% above the chars/4 reading of the
# post-Phase-3 prompt so a real regression flags reliably across
# environments. If a prompt creeps over its budget, the right move
# is usually to compress (not bump the number).
_BUDGETS: dict[str, int] = {
    "outfit_architect.md": 8300,
    "outfit_architect_anchor.md": 500,
    "outfit_architect_followup.md": 850,
    "outfit_composer.md": 1600,
    "outfit_rater.md": 2600,
    "outfit_decomposition.md": 800,
    "copilot_planner.md": 6000,  # +500 for anchor_garment field (PR #287 follow-up)
    "style_advisor.md": 3300,
    "virtual_tryon.md": 400,
    "body_type_analysis.md": 3000,
    "color_analysis_headshot.md": 1600,
    "other_details_analysis.md": 1550,
}


def _count_tokens(text: str) -> tuple[int, str]:
    """Return (token_count, method). Prefers tiktoken; falls back to
    char/4 when the package isn't installed."""
    try:
        import tiktoken  # type: ignore[import-not-found]
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text)), "tiktoken"
    except Exception:  # pragma: no cover — depends on env
        return len(text) // 4, "approx (chars/4)"


def _audit_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    tokens, method = _count_tokens(text)
    budget = _BUDGETS.get(path.name)
    over = budget is not None and tokens > budget
    return {
        "name": path.name,
        "lines": text.count("\n") + 1,
        "chars": len(text),
        "tokens": tokens,
        "method": method,
        "budget": budget,
        "over_budget": over,
    }


def _format_row(row: dict) -> str:
    budget = row["budget"]
    if budget is None:
        budget_str = "—"
        ratio_str = ""
    else:
        budget_str = f"{budget}"
        ratio = row["tokens"] / budget
        marker = " ⚠️" if row["over_budget"] else ""
        ratio_str = f" ({ratio:.0%}{marker})"
    return (
        f"| {row['name']:<35} | {row['lines']:>5} | {row['chars']:>6} "
        f"| {row['tokens']:>6} | {budget_str:>6}{ratio_str} |"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--json", action="store_true",
        help="Emit JSON instead of a markdown table",
    )
    parser.add_argument(
        "--budget", action="store_true",
        help="Exit 1 if any prompt exceeds its budget",
    )
    args = parser.parse_args(argv)

    if not _PROMPT_DIR.is_dir():
        print(f"prompt/ not found at {_PROMPT_DIR}", file=sys.stderr)
        return 2

    rows = [_audit_file(p) for p in sorted(_PROMPT_DIR.glob("*.md"))]

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        method = rows[0]["method"] if rows else "n/a"
        total = sum(r["tokens"] for r in rows)
        print(f"# Prompt token audit ({method})")
        print()
        print("| prompt | lines | chars | tokens | budget |")
        print("|---|---:|---:|---:|---:|")
        for r in rows:
            print(_format_row(r))
        print(f"| **total** | | | **{total}** | |")
        print()
        over = [r for r in rows if r["over_budget"]]
        if over:
            print(f"⚠️  {len(over)} prompt(s) over budget:")
            for r in over:
                print(f"  - {r['name']}: {r['tokens']} > {r['budget']}")

    if args.budget and any(r["over_budget"] for r in rows):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
