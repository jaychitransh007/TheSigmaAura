"""Tests for the prompt-token audit script
(`ops/scripts/audit_prompt_tokens.py`).

Verifies:
- _audit_file returns the expected fields
- over_budget flag fires correctly when a file exceeds its declared budget
- every prompt currently shipped is under its declared budget
  (regression guard for Phase 3 — if this fails, the prompt grew
  beyond what we intentionally budgeted; either compress or bump
  the budget in audit_prompt_tokens.py with reasoning)
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (
    _ROOT,
    _ROOT / "ops" / "scripts",
):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import audit_prompt_tokens  # type: ignore[import-not-found]


class AuditFileTests(unittest.TestCase):

    def test_audit_file_returns_expected_fields(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("# Hello\n\nThis is a tiny prompt.\n")
            path = Path(f.name)
        try:
            row = audit_prompt_tokens._audit_file(path)
            self.assertEqual(row["name"], path.name)
            self.assertGreater(row["tokens"], 0)
            self.assertGreater(row["chars"], 0)
            self.assertGreater(row["lines"], 0)
            self.assertIsNone(row["budget"])  # no entry for temp file name
            self.assertFalse(row["over_budget"])
        finally:
            path.unlink()

    def test_over_budget_flag_fires(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("word " * 1000)  # ~1000 tokens
            path = Path(f.name)
        try:
            audit_prompt_tokens._BUDGETS[path.name] = 100
            row = audit_prompt_tokens._audit_file(path)
            self.assertTrue(row["over_budget"])
            self.assertEqual(row["budget"], 100)
        finally:
            audit_prompt_tokens._BUDGETS.pop(path.name, None)
            path.unlink()


class CurrentPromptsUnderBudgetTests(unittest.TestCase):
    """Regression guard: every prompt in `prompt/` must stay under
    its declared Phase 3 budget. If this fails, compress the prompt
    or bump the budget in audit_prompt_tokens.py with reasoning."""

    def test_all_shipped_prompts_under_budget(self):
        prompt_dir = _ROOT / "prompt"
        offenders = []
        for path in sorted(prompt_dir.glob("*.md")):
            row = audit_prompt_tokens._audit_file(path)
            if row["over_budget"]:
                offenders.append(
                    f"{row['name']}: {row['tokens']} > {row['budget']}"
                )
        self.assertEqual(
            offenders, [],
            f"Prompts over budget: {offenders}. "
            "Compress or bump the budget in ops/scripts/audit_prompt_tokens.py.",
        )


if __name__ == "__main__":
    unittest.main()
