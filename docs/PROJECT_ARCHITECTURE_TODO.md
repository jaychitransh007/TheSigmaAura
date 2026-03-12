# Project Architecture TODO

Last updated: March 12, 2026

Canonical target spec: `docs/APPLICATION_SPECS.md`

## Current Project Status

### User
Status: strong, functionally usable

Implemented:
- onboarding flow with OTP gate (fixed OTP: 123456)
- profile input persistence (`onboarding_profiles`)
- image upload and crop flow (`onboarding_images`, SHA256 filenames, 3:2 ratio)
- analysis pipeline (4 agents: body_type, color_headshot, color_veins, other_details)
- deterministic interpretation pipeline (ContrastLevel, WaistSizeBand, FrameStructure, SeasonalColorGroup, HeightCategory)
- style preference selection and persistence (104-image pool, 3-layer selection)
- profile processing / rerun flows

Current implementation:
- active runtime lives in `modules/onboarding`
  - `onboarding/api.py` — routes: send-otp, verify-otp, profile, images, status, style
  - `onboarding/analysis.py` — UserAnalysisService (4-agent image analysis)
  - `onboarding/interpreter.py` — deterministic interpretation
  - `onboarding/style_archetype.py` — style preference selection + interpretation
  - `onboarding/repository.py` — Supabase persistence
  - `onboarding/ui.py` — 6-step onboarding wizard
- compatibility facade exists in `modules/user`
  - `user/api.py`, `user/service.py`, `user/context.py`, `user/repository.py`
  - thin wrappers, no independent logic

Remaining structural work:
- move runtime imports and ownership fully under `modules/user`
- reduce `modules/onboarding` to compatibility wrappers, then remove

### Catalog
Status: strong, functionally usable

Implemented:
- admin catalog screen (`catalog/admin_api.py`, `catalog/ui.py`)
- CSV upload flow
- LLM enrichment: 44 enum attributes + 2 text colors via gpt-4-vision (`catalog_enrichment/attributes.py`)
- sync into `catalog_enriched` (102 columns)
- embedding generation into `catalog_item_embeddings` (text-embedding-3-small, 1536 dims)
- local and staging Supabase sync
- partial-run support via `max_rows`
- storage-backed style archetype assets

Current implementation:
- admin facade in `modules/catalog` (routes + UI only)
- enrichment pipeline in `modules/catalog_enrichment` (batch_runner, batch_builder, response_parser, merge_writer)
- retrieval stack in `modules/catalog_retrieval` (query_builder, vector_store, embedder, document_builder)

Remaining structural work:
- add upload / enrichment / embedding job tables
- support file-based reruns and range-based reruns
- finish consolidating catalog runtime under `modules/catalog`

### Agentic Application
Status: active foundation implemented; usable end-to-end, still needs quality and consolidation work

Implemented (in `modules/agentic_application`):
- `AgenticOrchestrator` is now the active recommendation runtime behind `agentic_application/api.py`
- `user_context_builder.py` loads saved profile, analysis attributes, derived interpretations, style preference, computes `profile_richness`, and validates minimum profile completeness
- `occasion_resolver.py` performs rule-based phrase-priority extraction for occasion/formality/time, specific-needs detection, and follow-up intent detection
- `conversation_memory.py` carries prior occasion/formality/specific-needs/plan state across turns when a request is a refinement
- `outfit_architect.py` produces structured `RecommendationPlan` / `DirectionSpec` / `QuerySpec` output via LLM with deterministic fallback planning
- `catalog_search_agent.py` executes per-query retrieval against `catalog_item_embeddings`, hydrates `catalog_enriched`, applies direction-aware filters, extracts filterable fields from structured query documents, and supports relaxation of `occasion_fit` / `formality_level`
- `outfit_assembler.py` supports both complete-outfit candidates and paired top+bottom assembly with compatibility pruning
- `outfit_evaluator.py` ranks via LLM with graceful fallback to assembly-score ordering
- `response_formatter.py` produces `RecommendationResponse` with outfit cards, reasoning fields, and follow-up suggestions
- product-card serialization now preserves image, title, price, product URL, and similarity for both `outfits` and legacy `recommendations`
- missing canonical product URLs are synthesized at runtime from `store + handle` for known catalog sources
- turn artifacts are now persisted with live context, conversation memory, plan, applied filters, retrieved IDs, assembled candidates, and final recommendations

Transitional leftovers still present:
- `modules/conversation_platform` remains in the repo and is not yet reduced to a compatibility wrapper
- legacy placeholder files still exist:
  - `agents/occasion_analyst.py`
  - `agents/presentation_agent.py`

Current limitations vs APPLICATION_SPECS.md:
- architect and evaluator quality still depend heavily on prompt quality; deterministic fallback exists, but its query documents are intentionally conservative
- evaluator does not yet receive explicit conversation-memory payload beyond the merged live context
- follow-up handling is now real, but color-change and similarity refinement are still shallow heuristic steering rather than full constraint editing
- `agentic_application` still imports `onboarding.*`, `catalog_retrieval.*`, and `conversation_platform.*` internals instead of owning clean boundaries
- agent-stage observability exists via model/tool logs, but there is no dedicated application-run artifact model or eval harness yet
- naming cleanup is incomplete while old placeholder files remain on disk
- some catalog datasets still do not persist canonical absolute `url`, so runtime link synthesis remains a temporary compatibility layer instead of a real ingestion fix

## Architecture Review Against Target Spec

Reference documents:
- `docs/APPLICATION_SPECS.md` — canonical v1 implementation contract
- `docs/fashion-ai-architecture.jsx` — visual system diagram

### What is already aligned
- 3 bounded contexts: user, application, catalog
- profile-first recommendation flow
- explicit 7-stage application pipeline in `agentic_application`
- structured plan/query contracts (`RecommendationPlan`, `DirectionSpec`, `QuerySpec`)
- structured labeled retrieval query generation (section-based documents)
- embedding-based catalog retrieval (text-embedding-3-small, 1536 dims, cosine)
- retrieval from `catalog_item_embeddings`, hydration from `catalog_enriched`
- hard filter support (gender_expression, formality_level, occasion_fit, etc.)
- complete-outfit and paired-direction support
- conversation persistence with turn-level state and conversation-memory carry-forward
- graceful degradation for planning/evaluation and retrieval filter relaxation
- async catalog preparation pipeline

### What is not yet aligned
- evaluator is not yet explicitly conditioned on persisted conversation-memory state
- planner fallback is generic and should be replaced by stronger architect prompting plus tighter server-side validation
- no query-rewrite / retry strategy beyond relaxing `occasion_fit` then `formality_level`
- `agentic_application` is still coupled to legacy module imports and compatibility shims
- docs are materially closer to reality now, but they still need one more pass once module-boundary cleanup and catalog URL ingestion are finished

### Naming alignment needed
APPLICATION_SPECS.md names vs current stub names:
- Occasion Resolver (rule-based) → currently `occasion_analyst.py`
- Response Formatter → currently `presentation_agent.py`

These should be renamed during Phase 3 to match the canonical spec.

## Canonical Bounded Contexts

### 1. User
Owns:
- onboarding input
- profile analysis (4-agent pipeline)
- deterministic interpretation (5 derived attributes)
- style preference (archetype selection + interpretation)
- stored user context snapshots

### 2. Agentic Application
Owns:
- user need intake
- context enrichment from saved profile
- agent orchestration (7-component pipeline per APPLICATION_SPECS.md)
- retrieval strategy (multi-direction, multi-query)
- outfit assembly and evaluation
- presentation and follow-up refinement

### 3. Catalog
Owns:
- upload and validation
- LLM enrichment (44 attributes)
- embedding generation (1536-dim)
- admin controls and job management
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
Goal: establish `agentic_application` as the canonical module with properly named components

Reference: APPLICATION_SPECS.md §15, Steps 1-7

- [ ] Rename stubs to match APPLICATION_SPECS.md:
  - `occasion_analyst.py` → `occasion_resolver.py`
  - `presentation_agent.py` → `response_formatter.py`
- [x] Define Pydantic schemas in `agentic_application/schemas.py` matching APPLICATION_SPECS.md contracts:
  - `RecommendationRequest`
  - `UserContext` (with `profile_richness`)
  - `LiveContext` (with `is_followup`, `followup_intent`, `specific_needs`)
  - `CombinedContext`
  - `RecommendationPlan`, `DirectionSpec`, `QuerySpec`
  - `RetrievedSet`
  - `OutfitCandidate`
  - `EvaluatedRecommendation`
  - `RecommendationResponse`, `OutfitCard`
- [x] Build new orchestrator in `agentic_application/orchestrator.py` following APPLICATION_SPECS.md §5 flow
- [x] Make `agentic_application` the canonical app module for new recommendation work
- [ ] Keep `conversation_platform` only as compatibility wrapper during migration

Definition of done:
- all schema contracts exist
- orchestrator shell calls components in correct order
- application runtime imports no longer depend on `conversation_platform.*`

### Phase 4: Application Layer Agent Flow
Goal: implement the real multi-agent recommendation loop per APPLICATION_SPECS.md

Reference: APPLICATION_SPECS.md §2-10

Step 1 — Context loading:

- [x] `user_context_builder.py` (APPLICATION_SPECS.md §2)
  - load onboarding profile, analysis attributes, derived interpretations, style preference
  - compute `profile_richness` (full | moderate | basic | minimal)
  - output `UserContext` object

- [x] `occasion_resolver.py` (APPLICATION_SPECS.md §3)
  - rule-based only, no LLM
  - phrase-priority matching: "smart casual" before "casual", "work meeting" before "work"
  - extract: occasion_signal, formality_hint, time_hint, specific_needs
  - specific-needs mapping: "look taller" → elongation, "look slimmer" → slimming, etc.
  - detect follow-up intent when prior recommendations exist

Step 2 — Planning:

- [x] `outfit_architect.py` (APPLICATION_SPECS.md §6)
  - consume `CombinedContext`
  - return `RecommendationPlan` as strict JSON
  - support `plan_type`: complete_only, paired_only, mixed
  - each `DirectionSpec` contains `QuerySpec` entries with structured labeled `query_document`
  - query documents must use same section format as catalog embeddings (USER_NEED, PROFILE_AND_STYLE, GARMENT_REQUIREMENTS, FABRIC_AND_BUILD, PATTERN_AND_COLOR, OCCASION_AND_SIGNAL)
  - v1: one complete direction + optionally one paired direction
  - deterministic fallback exists when planner LLM fails

Step 3 — Retrieval:

- [x] `catalog_search_agent.py` (APPLICATION_SPECS.md §7)
  - for each `QuerySpec`: embed query_document, apply hard filters, search `catalog_item_embeddings`
  - hydrate matching rows from `catalog_enriched`
  - return `RetrievedSet` per query
  - hard filters from query spec + combined context (APPLICATION_SPECS.md §4)
  - direction-specific: complete uses `StylingCompleteness=complete`, paired uses `StylingCompleteness=needs_pairing`

Step 4 — Assembly:

- [x] `outfit_assembler.py` (APPLICATION_SPECS.md §8)
  - complete directions: each product is already an outfit candidate
  - paired directions: combine top-query + bottom-query results
  - deterministic compatibility pruning: same gender_expression, compatible formality, compatible color_temperature, compatible pattern_type/scale, no extreme volume conflict
  - prune to top 20-30 assembled pairs max
  - output `OutfitCandidate` list with `assembly_score` and `assembly_notes`

Step 5 — Evaluation:

- [x] `outfit_evaluator.py` (APPLICATION_SPECS.md §9)
  - LLM-based ranking against: body harmony, color suitability, occasion appropriateness, style-archetype fit, risk-tolerance alignment, comfort-boundary compliance, specific-needs support, pairing coherence
  - rank by actual user fit, not vector similarity score
  - return `EvaluatedRecommendation` list (top 3-5) with per-criterion reasoning
  - strict JSON output
  - graceful fallback exists if evaluator LLM fails

Step 6 — Formatting:

- [x] `response_formatter.py` (APPLICATION_SPECS.md §10)
  - convert evaluated results into `RecommendationResponse`
  - each `OutfitCard`: title, reasoning, body_note, color_note, style_note, occasion_note, product cards
  - generate `follow_up_suggestions`

Step 7 — Integration:

- [x] Wire all components into `agentic_application/orchestrator.py`
- [x] Add error handling per APPLICATION_SPECS.md §12:
  - graceful degradation: evaluator failure falls back to top retrieved candidates
  - filter relaxation order: OccasionFit → FormalityLevel (never relax GenderExpression)
  - profile validation: minimum required = gender + SeasonalColorGroup + primaryArchetype
- [x] Add turn persistence per APPLICATION_SPECS.md §11:
  - resolved live context, architect output, applied filters, retrieved IDs, assembled candidates, final recommendations
- [ ] Reduce `conversation_platform` to compatibility wrapper

Definition of done:
- application runtime follows APPLICATION_SPECS.md in actual execution order
- both complete-outfit and two-piece pairing are supported
- recommendations include per-criterion reasoning

### Phase 5: Conversation and Refinement
Goal: make the application conversational, not one-shot

Reference: APPLICATION_SPECS.md §11

- [x] Implement follow-up detection in occasion resolver
- [x] Support follow-up intents per APPLICATION_SPECS.md:
  - `increase_boldness`
  - `decrease_formality`
  - `increase_formality`
  - `change_color`
  - `full_alternative`
  - `more_options`
  - `similar_to_previous`
- [x] Add conversation memory model for constraints accumulated across turns
- [x] Store resolved need/context snapshots per turn
- [x] Follow-up requests operate on persisted prior recommendations, not only text history
- [ ] Allow the architect and evaluator to use prior turn constraints

Definition of done:
- follow-up requests modify retrieval/evaluation rather than restart from scratch

### Phase 6: Architecture Doc Sync
Goal: make `docs/fashion-ai-architecture.jsx` match reality exactly

- [x] Update application layer in diagram to show the 7-component pipeline
- [x] Reflect pairing support (complete + paired directions)
- [ ] Verify embedding details match (text-embedding-3-small, 1536 dims) — already correct in APPLICATION_SPECS.md
- [ ] Verify catalog storage naming matches (catalog_enriched, catalog_item_embeddings) — already correct in APPLICATION_SPECS.md
- [ ] Mark future expansion areas explicitly instead of implying they already exist
- [ ] Ensure diagram and APPLICATION_SPECS.md are fully consistent

Definition of done:
- the architecture doc is a truthful system diagram, not an aspirational mismatch

### Phase 7: Cleanup
Goal: remove transitional noise from the repo

- [ ] Remove compatibility facades once migrations are complete:
  - `modules/onboarding` wrappers (after Phase 1)
  - `modules/conversation_platform` wrappers (after Phase 4)
  - re-export shims in `agentic_application/api.py`, `orchestrator.py`, `schemas.py`
- [ ] Remove stale module names from scripts, runbooks, and sys.path entries
- [ ] Reduce env-file surface to the intended set:
  - `.env.local`
  - `.env.staging`
  - `.env.example`
- [ ] Clean remaining stale config/docs from removed heuristic systems
- [ ] Rename any remaining references to old component names (occasion_analyst, presentation_agent)

Definition of done:
- repo reflects one architecture, not multiple overlapping generations

## Immediate Priority Order

1. Application quality pass:
   close remaining planner/evaluator gaps, deepen follow-up constraint handling, and add eval coverage around the new runtime
2. Conversation refinement closure (Phase 5):
   make evaluator and retrieval explicitly memory-aware, especially for color-change and similarity follow-ups
3. Catalog ingestion quality pass:
   persist canonical absolute product URLs in `catalog_enriched` so runtime link synthesis can be removed
4. User consolidation (Phase 1)
5. Catalog consolidation (Phase 2)
6. Final cleanup (Phase 7)

## Active Implementation Rules

- `user` produces context
- `catalog` produces searchable supply
- `agentic_application` consumes both and reasons
- APPLICATION_SPECS.md is the canonical v1 contract for the application layer
- all component names follow APPLICATION_SPECS.md, not earlier naming

That rule set remains the baseline for all new work.
