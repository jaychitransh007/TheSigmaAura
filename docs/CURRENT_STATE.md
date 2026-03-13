# Current Project State

Last updated: March 13, 2026

Canonical references:
- `docs/CURRENT_STATE.md`
- `docs/APPLICATION_SPECS.md`
- `docs/fashion-ai-architecture.jsx`

This document is the single merged state-and-checklist document for the project.
It supersedes the former architecture TODO and standalone cleanup/remediation checklist docs.

## Executive Status

Project status:
- user layer: implemented and usable
- catalog layer: implemented and usable
- application layer: active and usable end-to-end, but still in quality/consolidation phase

The project is no longer in a pure scaffolding state. A real recommendation pipeline is running through `modules/agentic_application`, and the main remaining work is quality, refinement, boundary cleanup, and catalog ingestion hardening.

## Active Runtime

Primary app runtime:
- `run_agentic_application.py`
- `modules/agentic_application/src/agentic_application/api.py`
- `modules/agentic_application/src/agentic_application/orchestrator.py`

Supporting runtime surface still present:
- `modules/platform_core`
- `modules/onboarding`
- `modules/user` thin facade
- `modules/catalog` thin admin facade

Important current rule:
- new recommendation work should treat `agentic_application` as the canonical application runtime

## Bounded Context Status

### User

Status:
- strong
- functionally usable

Implemented:
- OTP-based onboarding flow
- onboarding profile persistence
- image upload and crop flow
- 4-agent analysis pipeline
- deterministic interpretation pipeline
- style preference selection and persistence
- profile status / rerun support

Current ownership reality:
- active runtime behavior still lives mostly under `modules/onboarding`
- `modules/user` exists mainly as compatibility wrappers

Main remaining gap:
- move ownership fully to `modules/user`

### Catalog

Status:
- strong
- functionally usable

Implemented:
- admin upload screen
- CSV upload flow
- enrichment pipeline
- sync into `catalog_enriched`
- embedding generation into `catalog_item_embeddings`
- partial run support via `max_rows`
- local/staging sync paths

Current ownership reality:
- active ingestion and retrieval behavior still spans `modules/catalog_enrichment` and `modules/catalog_retrieval`
- `modules/catalog` is still more facade than true boundary

Main remaining gaps:
- job tables
- clearer rerun support
- stronger admin observability
- canonical product URL persistence during ingestion

### Application

Status:
- active
- usable end-to-end
- not yet final-quality

Implemented:
- orchestrated recommendation pipeline
- saved user context loading
- rule-based live context extraction
- conversation memory carry-forward
- planner with deterministic fallback
- vector retrieval with hard filters
- retrieval relaxation
- complete-outfit and paired top/bottom support
- assembly layer
- evaluator with graceful fallback
- response formatting and UI rendering support
- turn artifact persistence

Main remaining gaps:
- stronger planner/evaluator prompts and validation
- cleaner module boundaries
- dedicated eval harness / run artifact model

Concrete implementation gaps against `docs/APPLICATION_SPECS.md`:
- evaluator fallback behavior is still assembly-score based rather than the spec's "top retrieved candidates" degradation contract

## Application Layer: Current Behavioral Reality

Current execution order:
1. load user context
2. resolve live context from user message
3. merge prior turn memory if the request is a refinement
4. generate recommendation plan
5. retrieve catalog products per query direction
6. relax retrieval filters if necessary
7. assemble outfit candidates
8. evaluate and rank candidates
9. format response payload
10. persist turn artifacts and updated conversation context

Current supported plan modes:
- `complete_only`
- `paired_only`
- `mixed`

Current supported retrieval directions:
- complete outfit
- paired top
- paired bottom

Current follow-up support:
- `increase_boldness`
- `decrease_formality`
- `increase_formality`
- `change_color`
- `full_alternative`
- `more_options`
- `similar_to_previous`

Current nuance:
- follow-up intents are detected and persisted
- `change_color` now rewrites styling goal away from persisted prior colors when no explicit new color is supplied
- `similar_to_previous` now reuses persisted primary color, occasion, plan shape, and silhouette/pattern signals when conversation memory is sparse
- evaluator now receives candidate-by-candidate deltas against the previous recommendation and fallback reasoning uses that delta
- LLM evaluator outputs are normalized so sparse follow-up notes are backfilled from candidate deltas

## Retrieval Reality

Embedding stack:
- model: `text-embedding-3-small`
- dimensions: `1536`
- vector search: pgvector cosine similarity

Primary data sources:
- vectors from `catalog_item_embeddings`
- hydrated products from `catalog_enriched`

Current filter behavior:
- global hard filter includes `gender_expression`
- contextual filters include `occasion_fit` and `formality_level`
- direction filters enforce `styling_completeness`
- query-document filters are extracted server-side from planner output

Current relaxation order:
1. no relaxation
2. drop `occasion_fit`
3. drop `occasion_fit` and `formality_level`

Hard rule:
- never relax `gender_expression`

## Product Payload Reality

Current runtime product cards can carry:
- image
- title
- price
- product URL
- similarity

Current response behavior:
- UI renders `result.outfits`

Current catalog weakness:
- some source catalogs do not persist canonical absolute `url`
- some rows only provide `store` and `handle`

Current ingestion behavior:
- `catalog_enriched.url` and `catalog_enriched.product_url` are now canonicalized during ingestion
- if a row lacks an absolute URL but has known `store + handle`, ingestion synthesizes the canonical absolute product URL
- catalog admin and ops now expose an explicit URL backfill path for older stored rows missing canonical URLs

Current runtime behavior:
- runtime now trusts canonical persisted `url` values and only normalizes already-present URLs
- local and staging backfill checks returned zero rows needing repair at the time of cleanup

Correct long-term fix:
- keep catalog ingestion/backfill healthy so runtime can remain dependent on canonical persisted URLs only

## Persistence Reality

Turn-level artifacts currently persisted:
- raw user message
- resolved live context
- conversation memory
- planner output
- applied retrieval filters
- retrieved product IDs / summaries
- assembled candidate summaries
- final recommendations

Conversation-level state currently persisted:
- latest live context
- latest conversation memory
- latest recommendation plan
- latest recommendation summaries

## Architecture Review Snapshot

Current alignment level:
- architectural alignment: strong
- behavioral alignment: partial

Main strengths:
- the active runtime follows the intended 7-stage agentic pipeline
- typed context handoff exists between all major stages
- planner and evaluator both have graceful fallbacks
- follow-up state is persisted server-side instead of relying on client history

Main weak spots:
- `change_color` and `similar_to_previous` now affect deterministic planning, evaluator fallback, and LLM post-processing, but silhouette-level memory is still thin
- evaluator fallback behavior and spec wording are not yet fully synchronized

## What Is Working

Working now:
- onboarding flow
- profile analysis and interpretation
- style preference capture
- catalog enrichment and embeddings
- recommendation orchestration
- complete-outfit retrieval
- paired retrieval and assembly
- recommendation rendering with images
- title / price / product link rendering
- similarity rendering
- follow-up turns with persisted context

## What Is Not Finished

Not finished:
- robust silhouette-level color-change and similar-to-previous refinement
- catalog job model and admin observability
- canonical URL ingestion for all catalog sources
- removal of compatibility wrappers and stale placeholders
- fully consolidated module boundaries

## Repo Reality

The repo currently contains more than one generation of the architecture.

Active path:
- `modules/agentic_application`

Still transitional:
- `modules/onboarding`
- compatibility exports and wrappers in several modules

This means:
- the system works
- the architecture is directionally correct
- the repo still needs consolidation to match that architecture cleanly

## How To Run

Start the app:

```bash
APP_ENV=local python3 run_agentic_application.py --reload --port 8010
```

Run the smoke flow:

```bash
USER_ID=your_completed_user_id bash ops/scripts/smoke_test_agentic_application.sh
```

Run tests:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Focused application suites:

```bash
python3 -m unittest tests.test_agentic_application -v
python3 -m unittest tests.test_agentic_application_api_ui -v
```

## Immediate Priority Order

1. make evaluator and retrieval explicitly memory-aware for follow-up refinement
2. improve planner/evaluator quality and add stronger eval coverage
3. persist canonical product URLs during catalog ingestion
4. consolidate user ownership under `modules/user`
5. consolidate catalog ownership under `modules/catalog`
6. remove transitional wrappers and stale placeholder modules

## Unified Action Checklist

### Priority 1: Recommendation Safety

- [x] add `OccasionFit` compatibility checks to paired assembly in `agentic_application/agents/outfit_assembler.py`
- [x] add regression tests covering relaxed retrieval followed by mismatched-occasion pair candidates
- [ ] decide whether assembly should also explicitly validate `GenderExpression` or continue relying on retrieval-only enforcement

Success criteria:
- relaxed retrieval cannot produce paired candidates that violate intended occasion compatibility

### Priority 2: Follow-up Depth

- [x] make `change_color` update planning constraints from persisted prior recommendation attributes
- [x] make `similar_to_previous` preserve prior occasion / plan intent while requesting alternative candidates
- [x] expand persisted recommendation summaries with follow-up-safe attributes
- [x] pass richer prior recommendation context into architect input payloads
- [x] pass richer prior recommendation context into evaluator input payloads
- [x] add evaluator-side candidate delta summaries against the latest previous recommendation
- [x] make evaluator fallback explain similarity/color shifts for follow-up intents
- [x] strengthen the evaluator prompt so the LLM explicitly receives and is told to use prior recommendation deltas
- [x] normalize sparse evaluator LLM outputs with follow-up-aware defaults
- [x] make `similar_to_previous` preserve prior silhouette intent when those attributes are persisted
- [x] add tests for:
  - color-change follow-up
  - similar-to-previous follow-up
  - follow-up on paired recommendations

Success criteria:
- follow-up intents modify retrieval/evaluation in a demonstrably targeted way instead of only nudging heuristics

### Priority 3: Output Contract Quality

- [x] enforce hard output cap of 3-5 outfits in `response_formatter.py`
- [x] add tests that verify formatter never emits more than 5 outfits
- [x] confirm downstream UI assumptions still hold when output is capped

Success criteria:
- runtime consistently returns a bounded, spec-compliant outfit count

### Priority 4: Evaluator Alignment

- [x] decide whether evaluator fallback should remain assembly-score based or be replaced by a "top retrieved candidates" fallback
- [x] update implementation or spec so both say the same thing
- [x] add explicit tests for evaluator-failure behavior
- [x] review evaluator payload for missing spec criteria:
  - risk tolerance
  - comfort boundaries
  - pairing coherence
  - richer delta reasoning on persisted conversation memory

Success criteria:
- evaluator behavior and `docs/APPLICATION_SPECS.md` no longer diverge

### Priority 5: Module Boundary Cleanup

- [x] reduce direct `agentic_application` imports from `onboarding.*`
- [x] reduce direct `agentic_application` imports from `catalog_retrieval.*`
- [x] introduce narrower app-facing interfaces where useful
- [x] keep `platform_core` as shared infrastructure only

Success criteria:
- application layer depends on clean interfaces rather than cross-boundary internals

### Priority 6: Catalog Link Integrity

- [x] persist canonical absolute product URLs during ingestion into `catalog_enriched`
- [x] add a backfill path for older `catalog_enriched` rows missing canonical URLs
- [x] reduce or remove runtime `store + handle` URL synthesis once catalog rows are fixed
- [x] add ingestion validation for URL completeness

Success criteria:
- runtime no longer depends on temporary URL synthesis for core product navigation

### Priority 7: Cleanup and Verification

- [x] remove `conversation_platform` runtime
- [x] move shared infrastructure into `modules/platform_core`
- [x] remove obsolete query-builder runtime path
- [x] remove old launcher `run_conversation_platform.py`
- [x] remove legacy orchestrator aliasing
- [x] delete dead placeholder agents
- [x] remove old UI naming and flat legacy response fields
- [x] move human context docs under `docs/`
- [x] delete outdated `ops` eval/release-gate assets
- [x] remove empty project directories
- [x] clean stale test cache artifacts
- [x] remove stale module names from scripts, docs, and sys.path entries where any remain
- [x] reduce env-file surface to:
  - `.env.local`
  - `.env.staging`
  - `.env.example`
- [x] clean remaining stale config/docs from removed heuristic systems
- [x] formalize an application-layer eval harness for the current agentic runtime

Success criteria:
- repo reflects one architecture, not multiple overlapping generations

## Consolidation Plan

### User Boundary

- [ ] move runtime imports and ownership fully under `modules/user`
- [ ] move analysis code under `modules/user`
- [ ] move deterministic interpretation under `modules/user`
- [ ] move style preference flow under `modules/user`
- [ ] reduce `modules/onboarding` to compatibility wrappers, then remove

Definition of done:
- app runtime no longer depends on `onboarding.*` directly

### Catalog Boundary

- [ ] move active ingestion/orchestration imports from `catalog_enrichment.*` and `catalog_retrieval.*` to `catalog.*`
- [ ] add explicit job tables:
  - `catalog_upload_jobs`
  - `catalog_enrichment_jobs`
  - `catalog_embedding_jobs`
- [ ] add per-job admin status instead of aggregate-only counts
- [ ] add selective rerun support by file, `max_rows`, and row range
- [ ] ensure `catalog_enriched` remains the canonical enriched record table in both dev and staging

Definition of done:
- catalog operations are fully manageable from `modules/catalog`

### Application Quality

- [ ] strengthen planner prompts and server-side plan validation
- [ ] strengthen evaluator prompts and context payload quality
- [ ] add targeted regression coverage around:
  - relaxed retrieval behavior
  - follow-up refinement
  - evaluator fallback
  - formatter output bounds
- [ ] keep `docs/APPLICATION_SPECS.md` synchronized with actual implementation behavior and active tests

Definition of done:
- architecture docs remain trustworthy and the active runtime behaves as specified
