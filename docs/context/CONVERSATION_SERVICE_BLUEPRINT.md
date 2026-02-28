# Conversation Service Blueprint (Local Supabase)

Last updated: February 28, 2026

Context sync note:
- Service blueprint remains valid with these additions:
  - intent-policy staging in recommendation flow for high-stakes work prompts
  - result filter contract (`complete_only` vs `complete_plus_combos`) in turn requests
  - offline conversation eval pipeline with rubric scoring + artifact integrity checks

## Scope
Blueprint for the conversation-agentic styling service that:
- accepts user image + natural-language turn input
- infers profile/context in real-time
- runs deterministic recommendation
- logs telemetry for future RL optimization

## Services
- `conversation_platform` API service
- `user_profiler` (visual + textual inference)
- `style_engine` (Tier 1 + Tier 2)
- Local Supabase (Postgres + PostgREST)

## API Contracts

### 1) Create Conversation
- `POST /v1/conversations`
- Request:
```json
{
  "user_id": "user_123",
  "initial_context": {
    "occasion": "work_mode",
    "archetype": "classic",
    "gender": "female",
    "age": "25_30"
  }
}
```
- Response:
```json
{
  "conversation_id": "uuid",
  "user_id": "user_123",
  "status": "active",
  "created_at": "2026-02-24T15:00:00.000000+00:00"
}
```

### 2) Create Turn
- `POST /v1/conversations/{conversation_id}/turns`
- Request:
```json
{
  "user_id": "user_123",
  "message": "Need work looks and one evening option.",
  "image_refs": ["/absolute/path/user.jpg"],
  "strictness": "balanced",
  "hard_filter_profile": "rl_ready_minimal",
  "max_results": 12,
  "result_filter": "complete_plus_combos"
}
```
- Response:
```json
{
  "conversation_id": "uuid",
  "turn_id": "uuid",
  "assistant_message": "Top recommendations are ready...",
  "resolved_context": {
    "occasion": "work_mode",
    "archetype": "classic",
    "gender": "female",
    "age": "25_30"
  },
  "profile_snapshot_id": "uuid",
  "recommendation_run_id": "uuid",
  "recommendations": [
    {
      "rank": 1,
      "garment_id": "combo::9259444797653|9259444764885",
      "title": "Estate White Cotton Twill Shirt + Cedar Green Cotton Oxford Shirt",
      "image_url": "https://...",
      "score": 0.91,
      "max_score": 1.1,
      "compatibility_confidence": 0.83,
      "reasons": "...",
      "recommendation_kind": "outfit_combo",
      "outfit_id": "combo::9259444797653|9259444764885",
      "component_count": 2,
      "component_ids": ["9259444797653", "9259444764885"],
      "component_titles": [
        "Estate White Cotton Twill Shirt",
        "Cedar Green Cotton Oxford Shirt"
      ],
      "component_image_urls": ["https://...", "https://..."]
    }
  ],
  "needs_clarification": false,
  "clarifying_question": ""
}
```

### 2A) Async Turn With Processing Stages
- `POST /v1/conversations/{conversation_id}/turns/start`
  - starts backend agent execution and returns `job_id`
- `GET /v1/conversations/{conversation_id}/turns/{job_id}/status`
  - returns live stage events:
    - `validate_request`
    - `load_conversation_state`
    - `visual_profile_inference`
    - `text_intent_inference`
    - `merge_context_memory`
    - `tier1_tier2_recommendation`
    - `persist_results`
    - `build_response`
    - `clarification_required` (conditional)
  - and final result when completed

### 3) Get Conversation State
- `GET /v1/conversations/{conversation_id}`
- Response includes latest context/profile/recommendation pointers.

### 4) Get Recommendation Run
- `GET /v1/recommendations/{run_id}`
- Returns ranked items + run metadata.

### 5) Feedback
- `POST /v1/feedback`
- Request:
```json
{
  "user_id": "user_123",
  "conversation_id": "uuid",
  "recommendation_run_id": "uuid",
  "garment_id": "9259444797653",
  "event_type": "buy",
  "notes": "Purchased"
}
```
- Reward map:
  - `dislike: -5`
  - `like: +2`
  - `share: +10`
  - `buy: +20`
  - `no_action: -1`
  - `skip: -1` (alias for no-action flows)

UI behavior:
- Recommendation cards expose `Dislike`, `Like`, `Share`, and `Buy Now` buttons.
- UI action layout is two-row: full-width `Buy Now`, then `Dislike | Like | Share`.
- Each action writes a feedback event to `/v1/feedback` with the current `recommendation_run_id`.

## Table Blueprint
Migrations:
- `supabase/migrations/20260224160000_conversation_platform.sql`
- `supabase/migrations/20260224170500_feedback_events_event_type_v2.sql`

- `users`
  - canonical user record (`external_user_id` unique)
- `conversations`
  - user sessions + merged context JSON
- `conversation_turns`
  - turn input/output and resolved context
- `media_assets`
  - stored user image artifacts
- `profile_snapshots`
  - inferred body-harmony + gender/age snapshots
- `context_snapshots`
  - inferred `occasion` + `archetype` from text
- `recommendation_runs`
  - run-level metadata and strictness/filter profile
- `recommendation_items`
  - ranked candidates per run
- `feedback_events`
  - outcome events and scalar reward
- `model_call_logs`
  - OpenAI request/response + reasoning notes
- `tool_traces`
  - non-LLM tool execution traces

## Message Schemas
- Source: `modules/conversation_platform/src/conversation_platform/schemas.py`
- Strict enums:
  - `strictness`: `safe|balanced|bold`
  - `hard_filter_profile`: `rl_ready_minimal|legacy`
  - `result_filter`: `complete_only|complete_plus_combos`
  - `event_type`: `dislike|like|share|buy|skip|no_action`
  - resolved context: canonical `occasion/archetype/gender/age` values

## Runtime Flow
1. Resolve/create user and conversation.
2. For first turn, require image (or existing profile snapshot).
3. Visual inference (`gpt-5.2`, reasoning high) when image is provided.
4. Text inference (`gpt-5-mini`) every turn.
5. Merge context memory.
6. Run recommendation (`style_engine`).
7. Persist turn, run, items, telemetry.
8. Return assistant response + ranked items.

Recommendation mode:
- Auto mode resolves to garment-only when message explicitly asks a garment category/subtype.
- Otherwise it resolves to outfit mode where complete singles and combo outfits compete.
- Result filtering:
  - `complete_only` disables combos and enforces stricter complete-single integrity.
  - `complete_plus_combos` keeps complete singles + combos.

Intent policy overlay:
- Configured at `modules/style_engine/configs/config/intent_policy_v1.json`.
- Current high-stakes path uses stage-based enforcement:
  1. `strict`
  2. `style_relaxed`
  3. `formality_relaxed`
  4. `smart_casual_limited`
- Tool traces expose policy metadata:
  - `intent_policy_id`
  - `intent_policy_keyword_hits`
  - `intent_policy_hard_filter_applied`
  - `intent_policy_hard_filter_relaxed`
  - `intent_policy_relaxation_stage`
  - `intent_policy_smart_casual_trimmed`

Clarification branch:
- If required context is incomplete (for example missing visual profile, or missing context fields),
  the turn returns `needs_clarification=true` with `clarifying_question` and no recommendation run.
- The UI shows this as a follow-up prompt so user can continue iterating in the same conversation.

## Eval Contract (Offline QA)
Runner:
- `ops/scripts/run_conversation_eval.py`

Inputs:
- prompt suite JSON (`ops/evals/conversation_prompt_suite_diverse_v1.json`)
- rubric JSON (`ops/evals/conversation_eval_rubric_v1.json`)
- runtime settings (`strictness`, `hard_filter_profile`, `max_results`, `result_filter`, optional `image_ref`)

Per-case verification:
- calls `POST /v1/conversations`
- calls `POST /v1/conversations/{conversation_id}/turns`
- validates retrievability via `GET /v1/recommendations/{run_id}`

Per-run artifacts:
- `data/logs/evals/<run_id>/run_manifest.json`
- `data/logs/evals/<run_id>/case_inputs.jsonl`
- `data/logs/evals/<run_id>/case_outputs.jsonl`
- `data/logs/evals/<run_id>/case_scores.jsonl`
- `data/logs/evals/<run_id>/case_scores.csv`
- `data/logs/evals/<run_id>/summary.json`
- `data/logs/evals/<run_id>/summary.md`
- `data/logs/evals/<run_id>/artifact_integrity.json`

Quality status model:
- `pass`
- `warning`
- `fail`
- `fail_integrity`
- `error`

## Action Plan (Implementation State)
- [x] Service schema and table migration
- [x] REST repository layer
- [x] Orchestration layer
- [x] FastAPI endpoints
- [x] Root runner command
- [x] Runbook and context docs
- [x] Tests (schemas + repository + orchestrator + agents)
- [x] Full local test run
- [x] Outfit assembly mode integration (auto/outfit/garment)
- [x] Recommendation metadata contract for combo outfits
- [x] Conversation eval framework (suite/rubric/runner/integrity report)
