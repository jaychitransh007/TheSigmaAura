# Agentic Implementation Checklist

Last updated: February 28, 2026

## Status Legend
- `[ ]` pending
- `[-]` in progress
- `[x]` complete

## Action Plan + Status
- [x] Create architecture/context spec docs for conversation platform.
- [x] Define local Supabase schema migration for conversation tables.
- [x] Implement Supabase REST client and repositories for persistence.
- [x] Add `conversation_platform` module skeleton (config, schemas, agents, orchestrator, API).
- [x] Implement turn orchestration with continuous session memory.
- [x] Integrate `user_profiler` + `style_engine` in orchestrator.
- [x] Persist model call logs, tool traces, recommendation runs/items, feedback.
- [x] Add root runner for conversation API service.
- [x] Add tests for schemas, orchestration flow, and repository behavior (mocked).
- [x] Update all context files/runbooks with new module and commands.
- [x] Run full test suite and validate API boot path.
- [x] Add browser conversational interface (`GET /`) with iterative turn handling.
- [x] Add async processing stages (`turns/start` + status polling) for live agent progress.
- [x] Add clarification-first branch when context is insufficient.
- [x] Add recommendation card actions (`Dislike`, `Like`, `Share`, `Buy Now`) wired to feedback logging.
- [x] Expand feedback event enum/reward mapping (`dislike`, `like`, `share`, `buy`, `no_action`, `skip`).
- [x] Patch local Supabase feedback constraint for existing projects.
- [x] Implement catalog enrichment auto-chunk orchestration.
- [x] Add checkpoint/resume behavior for org-level limits (`enqueued token`, `billing_hard_limit_reached`).
- [x] Implement conversation eval system (prompt suite + rubric + runner + integrity checks).
- [x] Add conversation eval runbook and scorer unit tests.

## Outfit Assembly Action Plan + Status
- [x] Define outfit-candidate generation strategy in context docs and runbook.
- [x] Add centralized config for outfit assembly rules and pairing constraints.
- [x] Implement style-engine outfit candidate builder (single complete garment + multi-garment combos).
- [x] Integrate Tier 2 score composition for combo outfits and ensure combo-vs-single competition.
- [x] Add request mode handling (auto/outfit/garment) with query-driven fallback behavior.
- [x] Wire conversation recommendation agent to return outfit candidates with component metadata.
- [x] Extend explainability contract and logs for outfit candidate IDs/components.
- [x] Add/expand tests for outfit assembly, mode resolution, and conversation mapping.
- [x] Run full test suite and reconcile docs with shipped behavior.

## Constraints
- User-facing profile module uses standard real-time Responses API.
- Local Supabase only (no cloud dependency for this implementation).
- Deterministic recommendation layer remains source-of-truth ranking engine.

## Validation Notes
- Test command: `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- Latest full-suite result: `93 passed, 0 failed`.
- Eval runner command: `python3 ops/scripts/run_conversation_eval.py --help`
- API runner validation: `python3 run_conversation_platform.py --help`
