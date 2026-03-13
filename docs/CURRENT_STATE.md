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
- OTP-based onboarding flow (fixed OTP: `123456`)
- onboarding profile persistence (name, DOB, gender, height_cm, waist_cm, profession)
- image upload with SHA256-encrypted filenames (user_id + category + timestamp), enforced 3:2 aspect ratio on frontend
- image categories: `full_body`, `headshot`, `veins`
- 4-agent analysis pipeline (model: `gpt-5.4`, reasoning effort: high, runs in parallel via ThreadPoolExecutor):
  1. `body_type_analysis` — uses full_body image → ShoulderToHipRatio, TorsoToLegRatio, BodyShape, VisualWeight, VerticalProportion, ArmVolume, MidsectionState, BustVolume
  2. `color_analysis_headshot` — uses headshot → SkinSurfaceColor, HairColor, HairColorTemperature, EyeColor, EyeClarity
  3. `color_analysis_veins` — uses veins image (+ enhanced version) → SkinUndertone
  4. `other_details_analysis` — uses headshot + full_body → FaceShape, NeckLength, HairLength, JawlineDefinition, ShoulderSlope
- Each agent returns JSON with `{value, confidence, evidence_note}` per attribute
- Deterministic interpretation pipeline (`interpreter.py`) derives:
  - `SeasonalColorGroup` — 12-season color analysis from undertone, surface color, hair, eye inputs
  - `HeightCategory` — Petite (<160cm) / Average (160-175cm) / Tall (>175cm)
  - `WaistSizeBand` — Very Small / Small / Medium / Large / Very Large
  - `ContrastLevel` — Low / Medium-Low / Medium / Medium-High / High (from depth spread across skin, hair, eyes)
  - `FrameStructure` — Light and Narrow / Light and Broad / Medium and Balanced / Solid and Narrow / Solid and Broad
- Style archetype preference: user selects 3-5 archetypes across 3 layers → produces primaryArchetype, secondaryArchetype, blending ratios, risk tolerance, formality lean, pattern type, comfort boundaries
- Profile status / rerun support (single-agent targeted reruns with baseline preservation)

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
- admin upload screen (`/admin/catalog`)
- CSV upload flow (saves to `data/catalog/uploads/`)
- enrichment pipeline (50+ attributes organized in 8 sections)
- sync into `catalog_enriched` (upsert on `product_id`)
- embedding generation into `catalog_item_embeddings` (text-embedding-3-small, 1536 dimensions)
- partial run support via `max_rows`
- local/staging sync paths
- canonical product URL persistence during ingestion (with backfill for older rows)
- only rows with `row_status` in `{ok, complete}` are embeddable

Catalog embedding document structure (8 labeled sections):
1. `GARMENT_IDENTITY` — GarmentCategory, GarmentSubtype, GarmentLength, StylingCompleteness, GenderExpression
2. `SILHOUETTE_AND_FIT` — SilhouetteContour, SilhouetteType, VolumeProfile, FitEase, FitType, ShoulderStructure, WaistDefinition, HipDefinition
3. `NECKLINE_SLEEVE_EXPOSURE` — NecklineType, NecklineDepth, SleeveLength, SkinExposureLevel
4. `FABRIC_AND_BUILD` — FabricDrape, FabricWeight, FabricTexture, StretchLevel, EdgeSharpness, ConstructionDetail
5. `EMBELLISHMENT` — EmbellishmentLevel, EmbellishmentType, EmbellishmentZone
6. `VISUAL_DIRECTION` — VerticalWeightBias, VisualWeightPlacement, StructuralFocus, BodyFocusZone, LineDirection
7. `PATTERN_AND_COLOR` — PatternType, PatternScale, PatternOrientation, ContrastLevel, ColorTemperature, ColorSaturation, ColorValue, ColorCount, PrimaryColor, SecondaryColor
8. `OCCASION_AND_SIGNAL` — FormalitySignalStrength, FormalityLevel, OccasionFit, OccasionSignal, TimeOfDay

Each attribute is stored with a confidence score and included in the embedding document as `- AttributeName: value [confidence=X.XX]`.

Embedding metadata (stored in `catalog_item_embeddings.metadata_json` for filtering):
- garment_category, garment_subtype, styling_completeness, gender_expression, formality_level, occasion_fit, time_of_day, primary_color, price

Current ownership reality:
- active ingestion and retrieval behavior still spans `modules/catalog_enrichment` and `modules/catalog_retrieval`
- `modules/catalog` is still more facade than true boundary

Main remaining gaps:
- job tables
- clearer rerun support
- stronger admin observability

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

## Database Table Inventory

Supabase tables (19 migrations in `supabase/migrations/`):

### Core platform tables
- `users` — id, external_user_id, profile_json, profile_updated_at
- `conversations` — id, user_id, status, session_context_json
- `conversation_turns` — id, conversation_id, user_message, assistant_message, resolved_context_json
- `model_calls` — logging for LLM calls (service, call_type, model, request/response JSON)
- `tool_traces` — logging for tool executions (tool_name, input/output JSON)
- `recommendation_events` — logging for recommendation pipeline events
- `feedback_events` — user feedback tracking

### Onboarding tables
- `onboarding_profiles` — user_id (unique), mobile (unique), otp fields, name, date_of_birth, gender, height_cm, waist_cm, profession, profile_complete, onboarding_complete
- `onboarding_images` — user_id, category (full_body/headshot/veins), encrypted_filename, file_path, mime_type, file_size_bytes; unique on (user_id, category)
- `user_analysis_runs` — tracks analysis snapshots per user (status, model_name, body_type_output, color_headshot_output, color_veins_output, other_details_output, collated_output)
- `user_derived_interpretations` — stores deterministic interpretations (SeasonalColorGroup, HeightCategory, WaistSizeBand, ContrastLevel, FrameStructure) with value/confidence/evidence_note
- `user_style_preference` — primary_archetype, secondary_archetype, risk_tolerance, formality_lean, pattern_type, selected_images

### Catalog tables
- `catalog_enriched` — product_id (unique), title, description, price, url, image_urls, row_status, raw_row_json, error_reason + 50+ enrichment attribute columns with confidence scores
- `catalog_item_embeddings` — product_id, embedding (pgvector 1536), metadata_json; indexed on product_id

## Module File Layout

```text
modules/
├── agentic_application/src/agentic_application/
│   ├── api.py                    # FastAPI app factory, routes
│   ├── orchestrator.py           # 7-stage pipeline
│   ├── schemas.py                # Pydantic models
│   ├── filters.py                # Hard filter construction and relaxation
│   ├── product_links.py          # Canonical URL resolution
│   ├── agents/
│   │   ├── outfit_architect.py   # LLM planning (gpt-5-mini)
│   │   ├── catalog_search_agent.py # Embedding search + hydration
│   │   ├── outfit_assembler.py   # Compatibility pruning
│   │   ├── outfit_evaluator.py   # LLM ranking (gpt-5-mini)
│   │   └── response_formatter.py # UI output generation
│   ├── context/
│   │   ├── user_context_builder.py  # Profile loading + richness scoring
│   │   ├── occasion_resolver.py     # Rule-based live context extraction
│   │   └── conversation_memory.py   # Cross-turn state
│   └── services/
│       ├── onboarding_gateway.py    # App-facing onboarding interface
│       └── catalog_retrieval_gateway.py # App-facing retrieval interface
├── onboarding/src/onboarding/
│   ├── api.py                    # Onboarding REST endpoints
│   ├── service.py                # OTP, profile, image handling
│   ├── analysis.py               # 4-agent analysis pipeline
│   ├── interpreter.py            # Deterministic interpretation derivation
│   ├── style_archetype.py        # Style preference selection
│   ├── repository.py             # Supabase CRUD for onboarding tables
│   └── schemas.py                # Request/response models
├── catalog/src/catalog/
│   ├── admin_api.py              # Catalog admin REST endpoints
│   ├── admin_service.py          # CSV processing, enrichment sync, embedding sync
│   └── ui.py                     # Admin UI HTML
├── catalog_enrichment/src/catalog_enrichment/
│   └── ...                       # Enrichment pipeline internals
├── catalog_retrieval/src/catalog_retrieval/
│   ├── vector_store.py           # pgvector similarity search
│   ├── document_builder.py       # Embedding document construction
│   ├── embedder.py               # text-embedding-3-small batch embedding
│   └── ...
├── platform_core/src/platform_core/
│   ├── config.py                 # AuraRuntimeConfig, env file resolution
│   ├── repositories.py           # ConversationRepository (users, conversations, turns, logging)
│   ├── supabase_rest.py          # SupabaseRestClient (REST-based, no SDK)
│   ├── api_schemas.py            # Shared REST API schemas
│   └── ui.py                     # Chat UI HTML
└── user_profiler/src/user_profiler/
    └── ...                       # User profiling utilities
```

## Ops Scripts

| Script | Purpose |
|---|---|
| `ops/scripts/run_agentic_eval.py` | Focused eval harness for agentic pipeline |
| `ops/scripts/check_supabase_sync.py` | Verify migration sync between local and staging |
| `ops/scripts/bootstrap_env_files.py` | Create .env.local and .env.staging from .env.example |
| `ops/scripts/backfill_catalog_urls.py` | Backfill missing canonical product URLs |
| `ops/scripts/schema_audit.py` | Audit database schema |

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
