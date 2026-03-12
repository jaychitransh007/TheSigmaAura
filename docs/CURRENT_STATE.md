# Current Project State

Last updated: March 13, 2026

Canonical references:
- `docs/APPLICATION_SPECS.md`
- `docs/PROJECT_ARCHITECTURE_TODO.md`
- `docs/fashion-ai-architecture.jsx`

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

Compatibility and transitional runtime surface still present:
- `modules/conversation_platform`
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
- deeper follow-up constraint editing
- explicit evaluator conditioning on conversation memory
- stronger planner/evaluator prompts and validation
- cleaner module boundaries
- dedicated eval harness / run artifact model

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
- not all follow-up intents are equally deep in runtime effect yet
- `change_color` and `similar_to_previous` remain partial heuristic refinements

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

Current compatibility behavior:
- UI prefers `result.outfits`
- UI falls back to older `result.recommendations`

Current catalog weakness:
- some source catalogs do not persist canonical absolute `url`
- some rows only provide `store` and `handle`

Current temporary fix:
- runtime synthesizes product URLs from known `store + handle` mappings

Correct long-term fix:
- persist canonical absolute `url` during catalog ingestion into `catalog_enriched`

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
- fully memory-aware evaluator behavior
- robust color-change and similar-to-previous refinement
- catalog job model and admin observability
- canonical URL ingestion for all catalog sources
- removal of compatibility wrappers and stale placeholders
- fully consolidated module boundaries

## Repo Reality

The repo currently contains more than one generation of the architecture.

Active path:
- `modules/agentic_application`

Still transitional:
- `modules/conversation_platform`
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
python3 -m unittest tests.test_conversation_api_ui -v
```

## Immediate Priority Order

1. make evaluator and retrieval explicitly memory-aware for follow-up refinement
2. improve planner/evaluator quality and add stronger eval coverage
3. persist canonical product URLs during catalog ingestion
4. consolidate user ownership under `modules/user`
5. consolidate catalog ownership under `modules/catalog`
6. remove transitional wrappers and stale placeholder modules
