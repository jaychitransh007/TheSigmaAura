# Conversation Agent Platform

Last updated: February 28, 2026

Context sync note:
- Conversation module unchanged by latest work; update is in catalog enrichment auto-chunk resume/checkpoint behavior.

## Goal
Build a conversation-first styling platform where users upload an image, express needs in natural language, iterate across turns, and receive ranked fashion recommendations.

Companion implementation blueprint:
- `docs/context/CONVERSATION_SERVICE_BLUEPRINT.md`

## Core Principles
- Keep recommendation selection deterministic (`style_engine`) for reliability.
- Use OpenAI models for interpretation/inference and conversational reasoning.
- Persist all turn-state and telemetry in local Supabase tables.
- Keep catalog enrichment offline batch; keep user interaction online real-time.

## Modules
- `catalog_enrichment`: offline catalog attribute extraction (batch).
- `style_engine`: Tier 1 hard filter + Tier 2 ranking.
- `user_profiler`: real-time visual/text profile inference.
- `conversation_platform` (new): session orchestration, agents, APIs, persistence.

## API Surface (v1)
- `GET /` (browser chat interface)
- `POST /v1/conversations`
- `GET /v1/conversations/{conversation_id}`
- `POST /v1/conversations/{conversation_id}/turns`
- `POST /v1/conversations/{conversation_id}/turns/start`
- `GET /v1/conversations/{conversation_id}/turns/{job_id}/status`
- `GET /v1/recommendations/{run_id}`
- `POST /v1/feedback`

Service entrypoint:
- `run_conversation_platform.py`

## Local Supabase
- Use local Supabase Postgres + PostgREST only.
- Persist conversations, turns, profiles, contexts, recommendation runs/items, model logs, tool traces, feedback.

## Agent Roles
- `SupervisorAgent`: turn routing and tool sequence.
- `ProfileAgent`: visual profile extraction from image.
- `IntentAgent`: textual context extraction (`occasion`, `archetype`) from turn text.
- `RecommendationAgent`: calls Tier 1 + Tier 2 and outfit assembly to produce ranked single-garment and combo-outfit candidates.
- `StylistAgent`: user-facing recommendation response and clarifications.
- `MemoryAgent`: reads/writes state snapshots.
- `TelemetryAgent`: logs all model/tool/recommendation events.

## Turn Lifecycle
1. Receive user message (+ optional image URL/path).
2. Resolve session context and latest profile.
3. If image present, run visual profile inference.
4. Run textual context inference for current intent.
5. Merge state and execute deterministic recommendation engine.
6. Persist outputs and telemetry.
7. Return ranked items + explanation + resolved context.

If context is missing or unclear, the agent returns:
- `needs_clarification = true`
- `clarifying_question` with specific next input needed
- no recommendation run until required detail is provided

Recommendation mode behavior:
- If user text explicitly asks for a garment category/subtype (e.g., shirt, dress, jeans), recommendation mode resolves to garment-only.
- Otherwise, mode resolves to outfit: complete garments and top+bottom combos compete in one ranked list.

## Processing Stages (Async)
When the UI uses async turn execution, backend stages are streamed via polling:
- `validate_request`
- `load_conversation_state`
- `visual_profile_inference`
- `text_intent_inference`
- `merge_context_memory`
- `tier1_tier2_recommendation`
- `persist_results`
- `build_response`
- `clarification_required` (conditional)

## Feedback Capture in UI
- Recommendation cards render `Dislike`, `Like`, `Share`, and `Buy Now`.
- Layout is two rows per card:
  - row 1: full-width `Buy Now`
  - row 2: `Dislike | Like | Share`
- Each action logs an outcome event through `POST /v1/feedback`.

## Security and Privacy
- Never expose service role key to client.
- Store only required PII.
- Record model logs for observability; redact sensitive fields when needed.
