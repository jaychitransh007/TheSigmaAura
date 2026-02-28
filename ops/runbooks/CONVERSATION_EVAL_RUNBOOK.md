# Conversation Eval Runbook

Last updated: February 28, 2026

## Purpose
Run a repeatable conversation-quality evaluation and automatically persist:
- prompt inputs
- raw API outputs
- per-case rubric scores
- aggregate summary
- artifact integrity checks

All eval artifacts are written under `data/logs/evals/<run_id>/`.

## Prerequisites
- Local Supabase stack running (`supabase start`)
- Conversation API running (`python3 run_conversation_platform.py --host 127.0.0.1 --port 8010`)
- `.env` configured with:
  - `OPENAI_API_KEY`
  - `SUPABASE_SERVICE_ROLE_KEY`
  - `SUPABASE_URL` (defaults to `http://127.0.0.1:55321`)

## Prompt Suite + Rubric
- Prompt suite:
  - `ops/evals/conversation_prompt_suite_diverse_v1.json`
- Rubric:
  - `ops/evals/conversation_eval_rubric_v1.json`

## Run Full Eval (20 prompts)
```bash
python3 ops/scripts/run_conversation_eval.py \
  --base-url http://127.0.0.1:8010 \
  --suite ops/evals/conversation_prompt_suite_diverse_v1.json \
  --rubric ops/evals/conversation_eval_rubric_v1.json \
  --strictness balanced \
  --hard-filter-profile rl_ready_minimal \
  --max-results 3 \
  --result-filter complete_only \
  --initial-gender female \
  --initial-age 25_30 \
  --image-ref data/logs/user_profiler/input_09322a34663f.webp \
  --out-dir data/logs/evals \
  --fail-on-integrity
```

## Fast Smoke Run (first 3 prompts)
```bash
python3 ops/scripts/run_conversation_eval.py \
  --max-cases 3 \
  --max-results 3 \
  --result-filter complete_only \
  --image-ref data/logs/user_profiler/input_09322a34663f.webp
```

## Output Artifacts Per Run
- `run_manifest.json`
- `case_inputs.jsonl`
- `case_outputs.jsonl`
- `case_scores.jsonl`
- `case_scores.csv`
- `summary.json`
- `summary.md`
- `artifact_integrity.json`

## Quality Gates
- Case score status:
  - `pass`
  - `warning`
  - `fail`
  - `fail_integrity`
  - `error`
- Integrity requirements are rubric-driven:
  - non-empty `turn_id`
  - non-empty `recommendation_run_id`
  - successful fetch from `/v1/recommendations/{run_id}`
  - non-empty recommendation list
- Use `--fail-on-integrity` to force non-zero exit on any integrity failure.

## Troubleshooting
- `HTTP 500` on `/v1/conversations` or `/turns`:
  - verify Supabase local stack is up and reachable
  - verify `.env` keys are set
- frequent `clarification_requested` notes:
  - pass `--image-ref` or provide stronger initial context
- many `avoid_keyword_hits_detected` in work prompts:
  - inspect policy config and Tier 1/Tier 2 constraints for work-mode guardrails
