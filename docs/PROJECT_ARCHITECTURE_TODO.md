# Project Architecture TODO

Last updated: March 12, 2026

## Target Bounded Contexts

### 1. User
Owns the full profile lifecycle:
- onboarding input
- profile analysis
- deterministic interpretations
- style preference
- persistent user context snapshots

### 2. Agentic Application
Owns the interactive recommendation system:
- accepts user need / occasion / refinement input
- enriches requests with saved user context
- orchestrates the agent community
- retrieves and evaluates outfits
- communicates results back to the user

### 3. Catalog
Owns asynchronous admin-managed supply:
- CSV upload
- row validation and normalization
- catalog row sync into Supabase
- enrichment
- embedding generation
- partial-run controls for `N` rows or all rows

## Current Mapping

### User
- active implementation lives in `modules/onboarding`
- compatibility facade added in `modules/user`

### Agentic Application
- active implementation lives in `modules/conversation_platform`
- compatibility facade added in `modules/agentic_application`

### Catalog
- active implementation lives across `modules/catalog_enrichment` and `modules/catalog_retrieval`
- orchestration facade and admin surface added in `modules/catalog`

## Phase Plan

### Phase 1: Boundaries
- [x] Define `user`, `agentic_application`, and `catalog` as the canonical module boundaries.
- [x] Add compatibility facades so the new structure exists immediately.
- [x] Add a first admin catalog API surface for upload, row sync, and embedding sync.

### Phase 2: User Consolidation
- [ ] Move onboarding runtime imports from `onboarding.*` to `user.*`.
- [ ] Move analysis and interpretation code under `modules/user/src/user/analysis`.
- [ ] Move style preference code under `modules/user/src/user/style_preference`.
- [ ] Keep old `modules/onboarding` only as temporary compatibility wrappers, then remove.

### Phase 3: Agentic Application Expansion
- [ ] Move conversation runtime imports from `conversation_platform.*` to `agentic_application.*`.
- [ ] Split the orchestrator into explicit agent modules:
  - `occasion_analyst`
  - `outfit_architect`
  - `catalog_search_agent`
  - `outfit_assembler`
  - `outfit_evaluator`
  - `presentation_agent`
- [ ] Replace simple retrieval-response flow with full multi-agent community flow described in `docs/fashion-ai-architecture.jsx`.
- [ ] Update the architecture document to match the current single-embedding catalog reality, with room for future expansion.

### Phase 4: Catalog Operations
- [x] Add `catalog_items` and `catalog_item_embeddings` Supabase persistence.
- [x] Make row sync idempotent via upsert.
- [x] Make embedding writes idempotent via upsert.
- [x] Support limited-row processing via `max_rows`.
- [ ] Add admin job tables:
  - `catalog_upload_jobs`
  - `catalog_enrichment_jobs`
  - `catalog_embedding_jobs`
- [ ] Add admin UI for upload and run-status management.
- [ ] Add selective rerun by uploaded file and by row range.

### Phase 5: Cleanup
- [ ] Replace old runtime imports in scripts and run entrypoints with the new module roots.
- [ ] Remove temporary compatibility facades once all callers are migrated.
- [ ] Remove legacy module names from docs and developer workflows.

## Active Implementation Rules
- `user` produces context
- `catalog` produces searchable supply
- `agentic_application` consumes both and reasons

That rule is the architectural baseline for all new work.
