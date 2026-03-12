# Project Architecture TODO

Last updated: March 12, 2026

## Current Project Status

### User
Status: strong, functionally usable

Implemented:
- onboarding flow with OTP gate
- profile input persistence
- image upload and crop flow
- analysis pipeline
- deterministic interpretation pipeline
- style preference selection and persistence
- profile processing / rerun flows

Current implementation:
- active runtime still lives mainly in `modules/onboarding`
- compatibility facade exists in `modules/user`

Remaining structural work:
- move runtime imports and ownership fully under `modules/user`
- reduce `modules/onboarding` to compatibility wrappers, then remove

### Catalog
Status: strong, functionally usable

Implemented:
- admin catalog screen
- CSV upload flow
- sync into `catalog_enriched`
- embedding generation into `catalog_item_embeddings`
- local and staging Supabase sync
- partial-run support via `max_rows`
- storage-backed style archetype assets

Current implementation:
- admin/runtime facade in `modules/catalog`
- enrichment logic still split across `modules/catalog_enrichment` and `modules/catalog_retrieval`

Remaining structural work:
- add upload / enrichment / embedding job tables
- support file-based reruns and range-based reruns
- finish consolidating catalog runtime under `modules/catalog`

### Agentic Application
Status: partial, not yet aligned with target architecture

Implemented:
- user message intake in conversation UI
- profile-aware retrieval query generation
- vector retrieval against catalog embeddings
- hard retrieval filter for `styling_completeness = complete`

Current limitation:
- the system is still effectively:
  - context assembly
  - one LLM retrieval-query call
  - one vector search
  - simple response formatting

It is not yet the multi-agent application shown in `docs/fashion-ai-architecture.jsx`.

## Architecture Review Against `docs/fashion-ai-architecture.jsx`

### What is already aligned
- 3 bounded contexts:
  - user
  - application
  - catalog
- profile-first recommendation flow
- structured retrieval query generation
- embedding-based catalog retrieval
- complete-outfit filtering is now enforced in retrieval
- async catalog preparation pipeline exists

### What is not yet aligned
- application layer is missing explicit agent execution boundaries
- no real `occasion_analyst` agent yet
- no real `outfit_architect` output model beyond retrieval query text
- no distinct `catalog_search_agent` contract
- no `outfit_assembler` for outfit composition logic
- no `outfit_evaluator` reranking / reasoning stage over retrieved products
- no `presentation_agent` framing layer
- no conversation memory / refinement loop beyond minimal stored context
- architecture doc still contains stale assumptions:
  - `text-embedding-3-small` at `1024` dims
  - current code uses `1536`
  - catalog now uses `catalog_enriched`, not the older catalog-items-centric framing
  - current runtime forces `complete` outfits, so the application document should reflect that simplified retrieval scope

## Canonical Bounded Contexts

### 1. User
Owns:
- onboarding input
- profile analysis
- deterministic interpretation
- style preference
- stored user context snapshots

### 2. Agentic Application
Owns:
- user need intake
- context enrichment from saved profile
- agent orchestration
- retrieval strategy
- outfit reasoning
- presentation and follow-up refinement

### 3. Catalog
Owns:
- upload
- validation
- enrichment
- embeddings
- admin controls
- searchable supply state

## Completion Plan

### Phase 1: User Consolidation
Goal: finish moving profile ownership to `modules/user`

- [ ] Move runtime imports from `onboarding.*` to `user.*`
- [ ] Move analysis code under `modules/user/src/user/analysis`
- [ ] Move deterministic interpretation under `modules/user/src/user/interpretation`
- [ ] Move style preference flow under `modules/user/src/user/style_preference`
- [ ] Keep `modules/onboarding` only as temporary wrappers
- [ ] Remove `modules/onboarding` after callers are migrated

Definition of done:
- app runtime no longer depends on `onboarding.*` directly

### Phase 2: Catalog Consolidation
Goal: make `modules/catalog` the true catalog boundary

- [ ] Move active ingestion/orchestration imports from `catalog_enrichment.*` and `catalog_retrieval.*` to `catalog.*`
- [ ] Add explicit job tables:
  - `catalog_upload_jobs`
  - `catalog_enrichment_jobs`
  - `catalog_embedding_jobs`
- [ ] Add admin status per job, not only aggregate counts
- [ ] Add selective rerun by:
  - uploaded file
  - `max_rows`
  - row range
- [ ] Add clear admin status for:
  - current file totals
  - DB totals
  - last run processed rows
  - last run saved rows
- [ ] Ensure `catalog_enriched` is the canonical enriched record table in both dev and staging

Definition of done:
- catalog operations are fully manageable from `modules/catalog`
- admin screen is job-aware instead of count-only

### Phase 3: Application Layer Foundation
Goal: replace the thin retrieval loop with explicit application modules

- [ ] Move runtime imports from `conversation_platform.*` to `agentic_application.*`
- [ ] Make `agentic_application` the canonical app module
- [ ] Keep `conversation_platform` only as compatibility wrapper during migration
- [ ] Formalize these runtime components:
  - `user_context_builder`
  - `occasion_analyst`
  - `outfit_architect`
  - `catalog_search_agent`
  - `outfit_assembler`
  - `outfit_evaluator`
  - `presentation_agent`

Definition of done:
- application runtime imports no longer depend on `conversation_platform.*`

### Phase 4: Application Layer Agent Flow
Goal: implement the real multi-agent recommendation loop

- [ ] `occasion_analyst`
  - parse live user message
  - derive occasion, formality, time, constraints, specific goals
  - output normalized occasion context

- [ ] `user_context_builder`
  - load onboarding profile
  - load analysis attributes
  - load deterministic interpretations
  - load style preference
  - build one canonical application context object

- [ ] `outfit_architect`
  - consume user context + occasion context
  - produce one or more outfit directions
  - for current simplified scope:
    - only complete outfits
  - output structured retrieval specs, not only one raw text blob

- [ ] `catalog_search_agent`
  - convert architect output into retrieval queries
  - apply hard filters
  - retrieve top candidates from `catalog_item_embeddings`
  - return structured candidate sets

- [ ] `outfit_evaluator`
  - reason over retrieved candidates against:
    - body profile
    - color profile
    - style preference
    - occasion fit
  - rerank and reject weak candidates
  - return top outfits with reasoning

- [ ] `presentation_agent`
  - translate evaluated results into user-facing explanation
  - preserve recommendation structure for follow-up refinement

Definition of done:
- application runtime follows the architecture doc in actual execution order

### Phase 5: Conversation and Refinement
Goal: make the application conversational, not one-shot

- [ ] Add explicit follow-up refinement flow:
  - “show bolder”
  - “more formal”
  - “different color”
  - “less expensive”
- [ ] Add conversation memory model for constraints accumulated across turns
- [ ] Store resolved need/context snapshots per turn
- [ ] Allow the architect and evaluator to use prior turn constraints

Definition of done:
- follow-up requests modify retrieval/evaluation rather than restart from scratch

### Phase 6: Architecture Doc Sync
Goal: make `docs/fashion-ai-architecture.jsx` match reality exactly

- [ ] Update embedding details:
  - current code path uses `text-embedding-3-small`
  - current dimension is `1536`
- [ ] Update catalog storage naming:
  - `catalog_enriched`
  - `catalog_item_embeddings`
- [ ] Update application layer to show current and target agent flow clearly
- [ ] Reflect current simplified retrieval scope:
  - complete outfits only
- [ ] Mark future expansion areas explicitly instead of implying they already exist

Definition of done:
- the architecture doc is a truthful system diagram, not an aspirational mismatch

### Phase 7: Cleanup
Goal: remove transitional noise from the repo

- [ ] Remove compatibility facades once migrations are complete
- [ ] Remove stale module names from scripts and runbooks
- [ ] Reduce env-file surface to the intended set:
  - `.env.local`
  - `.env.staging`
  - `.env.example`
- [ ] Clean remaining stale config/docs from removed heuristic systems

Definition of done:
- repo reflects one architecture, not multiple overlapping generations

## Immediate Priority Order

1. User consolidation
2. Catalog consolidation
3. Application layer foundation
4. Application multi-agent flow
5. Conversation refinement
6. Architecture doc sync
7. Final cleanup

## Active Implementation Rules

- `user` produces context
- `catalog` produces searchable supply
- `agentic_application` consumes both and reasons

That rule remains the baseline for all new work.
