# Eval sets

Hand-curated test suites that exercise specific pipeline behavior against natural-language inputs. Distinct from `tests/test_*.py` unit tests — eval cases here invoke real LLMs and are gated behind environment variables.

## Files

- **`eval_set_5x.jsonl`** — Phase 5x.4b open-axis user-preference extraction cases.
- **`open_axis_eval.py`** — harness for `eval_set_5x.jsonl`. Loads the JSONL, runs each query through `CopilotPlanner.plan()`, compares emitted `extracted_preferences` to expected, reports pass/partial/fail + per-axis precision/recall.

## Running

### CLI

```sh
RUN_EVAL=1 python tests/eval/open_axis_eval.py
RUN_EVAL=1 python tests/eval/open_axis_eval.py --limit 3
```

The harness refuses to run without `RUN_EVAL=1` (real LLM calls cost money). Cost ≈ $0.01 for the full set (12 queries × ~$0.001 per `gpt-5-mini` call).

Exit code: `0` if zero fails, `1` if any fails. Partials don't fail the run — see [`compare_extraction`](open_axis_eval.py) for status semantics.

### pytest

```sh
# Schema + pure-function tests only (always run, no LLM).
pytest tests/test_open_axis_eval.py

# Full integration run (real planner LLM, ~$0.01).
RUN_EVAL=1 pytest tests/test_open_axis_eval.py
```

## Eval-case shape

One JSON object per line:

```json
{
  "id": "embellish_high",
  "user_message": "I want something with more embellishment",
  "expected_extracted_preferences": {"EmbellishmentLevel": ["heavy", "statement"]},
  "notes": "single-axis: explicit 'more X' direction"
}
```

- **`id`** — short slug, must be unique within the file.
- **`user_message`** — exact text passed to the planner.
- **`expected_extracted_preferences`** — dict of `attribute_name → allowed_values_list`. Empty `{}` for negative cases (planner must NOT extract anything).
- **`notes`** — free-form; describes what the case is testing.

The expected outputs follow the glossary in [`prompt/copilot_planner.md`](../../prompt/copilot_planner.md) Resolved Context section. **This is a planner-prompt fidelity test, not a fashion-correctness test.** If you change the glossary, update this file.

## Status semantics

| status | meaning |
|---|---|
| **pass** | actual exactly matches expected (set-equality on values) |
| **partial** | actual is a non-strict subset of expected — fewer keys or narrower value sets, but no over-extraction |
| **fail** | actual contains a key or value NOT in expected — over-extraction, the cardinal sin |

Per-axis aggregate produces precision (TP / (TP+FP)) and recall (TP / (TP+FN)) per attribute. Useful for spotting axes that are silently dropped (low recall) vs axes the planner invents (low precision).

## When to update

| trigger | action |
|---|---|
| New axis added to `prompt/copilot_planner.md`'s glossary | Add ≥1 single-axis case + 1 multi-axis case combining it with an existing axis. |
| Allowed-value list for an axis changes | Update the `expected_extracted_preferences` for any case that referenced the old value set. |
| Production turn shows a regression you want to pin | Add the offending user_message + the correct expected output as a new case. |
| Fashion-correctness question raised (does "low contrast" really mean very_low+low?) | NOT in scope here — that's a stylist judgment and goes through prompt review, not the eval set. |

## CI integration

The pure-function tests (`CompareExtractionTests`, `EvalSetSchemaTests`) run in CI by default — they catch JSONL syntax errors and comparison-logic regressions without spending API credits. The integration test (`OpenAxisEvalIntegrationTests`) is `@unittest.skipUnless(RUN_EVAL=1)` so it's safe in CI.

For nightly extraction-quality monitoring, schedule the CLI form via cron / a CI job that exports `RUN_EVAL=1` (cost is bounded — ~$3/month at one run/day).
