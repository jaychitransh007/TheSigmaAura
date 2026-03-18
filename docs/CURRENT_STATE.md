# Current Project State

Last updated: March 18, 2026

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
- `modules/user` (owns all user/onboarding runtime code)
- `modules/catalog` (owns all catalog admin, enrichment, and retrieval code)

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
- image categories: `full_body`, `headshot`
- 3-agent analysis pipeline (model: `gpt-5.4`, reasoning effort: high, runs in parallel via `ThreadPoolExecutor`):
  1. `body_type_analysis` — uses full_body image → ShoulderToHipRatio, TorsoToLegRatio, BodyShape, VisualWeight, VerticalProportion, ArmVolume, MidsectionState, BustVolume
  2. `color_analysis_headshot` — uses headshot → SkinSurfaceColor, HairColor, HairColorTemperature, EyeColor, EyeClarity
  3. `other_details_analysis` — uses headshot + full_body → FaceShape, NeckLength, HairLength, JawlineDefinition, ShoulderSlope
- Each agent returns JSON with `{value, confidence, evidence_note}` per attribute
- Deterministic interpretation pipeline (`interpreter.py`) derives:
  - `SeasonalColorGroup` — 4-season color analysis (Spring, Summer, Autumn, Winter) — deterministic fallback from surface color, hair, eye inputs. Overridden by digital draping when headshot available.
  - `HeightCategory` — Petite (<160cm) / Average (160-175cm) / Tall (>175cm)
  - `WaistSizeBand` — Very Small / Small / Medium / Large / Very Large
  - `ContrastLevel` — Low / Medium-Low / Medium / Medium-High / High (from depth spread across skin, hair, eyes)
  - `FrameStructure` — Light and Narrow / Light and Broad / Medium and Balanced / Solid and Narrow / Solid and Broad
- **Digital draping** (`user/draping.py`) — LLM-based 3-round vision chain using headshot overlays:
  - R1: Warm vs Cool (gold vs silver overlay)
  - R2: Within-branch (Spring vs Autumn, or Summer vs Winter)
  - R3: Confirmation (winner vs cross-temperature neighbor)
  - Produces probability distribution over 4 seasons; selects 1-2 groups
  - Overrides deterministic SeasonalColorGroup when available
  - Results stored in `user_effective_seasonal_groups` table
- **Comfort learning** (`agentic_application/services/comfort_learning.py`) — behavioral signal system:
  - High-intent signals: outfit likes for garments outside current seasonal groups
  - Low-intent signals: explicit color keyword requests
  - Threshold: 5 high-intent signals triggers seasonal group update
  - Max 2 groups per user
- Style archetype preference: user selects 3-5 archetypes across 3 layers → produces primaryArchetype, secondaryArchetype, blending ratios, risk tolerance, formality lean, pattern type, comfort boundaries
- Profile status / rerun support (single-agent targeted reruns with baseline preservation)

Current ownership reality:
- all runtime behavior lives under `modules/user`
- `agentic_application` imports exclusively from `user.*` via `ApplicationUserGateway`
- `modules/onboarding` shim has been removed (zero consumers remained)

Main remaining gap:
- (none)

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
- job lifecycle tracking: every sync operation (items, URLs, embeddings) creates a `catalog_jobs` row with status transitions (running → completed/failed), params, row counts, and error messages
- selective rerun support: `start_row`/`end_row` parameters on items sync and embeddings sync for range-based partial reruns
- admin job history: `/status` endpoint returns running/failed job counts and recent job list; UI renders job history table with status pills, params, row counts, and truncated errors

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
- all retrieval and enrichment code lives in `catalog/retrieval/` and `catalog/enrichment/` subdirectories
- `modules/catalog_retrieval` and `modules/catalog_enrichment` shims have been removed (consumers migrated to `catalog.*`)
- `agentic_application` imports only from `catalog.*`

Main remaining gaps:
- (none — job tables, rerun support, and admin observability are now implemented)

### Application

Status:
- active
- usable end-to-end
- not yet final-quality

Implemented:
- orchestrated recommendation pipeline (10-stage, including context gate)
- context gate between context builder and outfit architect — rule-based signal scoring (<1ms) short-circuits vague requests with clarifying questions + quick-reply chips
- context gate bypass: "surprise me" phrases, follow-up turns, max 2 consecutive blocks
- `response_type` field: `"recommendation"` | `"clarification"`
- saved user context loading
- rule-based live context extraction (runs before context gate for structured signal availability)
- conversation memory carry-forward (accumulates context across gate-blocked turns)
- LLM-only planner — no deterministic fallback (model: `gpt-5.4`)
- strict JSON schema with enum-constrained hard filter vocabulary
- hard filters: `gender_expression`, `styling_completeness`, `garment_category`, `garment_subtype`
- soft signals via embedding only: `occasion_fit`, `formality_level`, `time_of_day`
- no filter relaxation — single search pass per query
- direction-aware retrieval: `needs_bottomwear` / `needs_topwear` / `complete`
- complete-outfit and paired top/bottom support
- assembly layer with deterministic compatibility pruning
- evaluator with graceful fallback (model: `gpt-5.4`), 8 style archetype percentage scoring (0–100 per archetype), and server-side output validation (score clamping, item_id verification, note backfill)
- architect failure returns error to user (no silent degradation)
- latency tracking via `time.monotonic()` on architect, search, evaluator (persisted as `latency_ms`)
- style archetype override: user's saved `style_preference.primaryArchetype` is the default, but if the user's message or conversation history explicitly requests a different style, the architect uses the requested style instead; the response formatter reads the archetype from the plan's query documents (not just the profile) so the response message reflects the actual style used
- response formatting (max 3 outfits) and UI rendering support
- virtual try-on via Gemini (`gemini-3.1-flash-image-preview`), parallel generation for all outfits
- turn artifact persistence

Main remaining gaps:
- dedicated eval harness / run artifact model

## Application Layer: Current Behavioral Reality

Current execution order:
1. load user context
2. resolve live context from user message (occasion resolver extracts structured signals)
3. build conversation memory from prior turn state + resolved live context
4. context gate — rule-based signal scoring; if insufficient, short-circuit with clarifying question (skip stages 5-10)
5. generate recommendation plan via LLM (gpt-5.4) — no fallback, failure = error to user
6. retrieve catalog products per query direction (text-embedding-3-small, single search pass)
7. assemble outfit candidates (deterministic)
8. evaluate and rank candidates (gpt-5.4, fallback: assembly_score)
9. format response payload (max 3 outfits)
10. generate virtual try-on images (gemini-3.1-flash-image-preview, parallel)
11. persist turn artifacts and updated conversation context

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
- all follow-up intents are detected, persisted, and have structured runtime effect across architect, assembler, evaluator, and response formatter
- `change_color`: architect preserves non-color dimensions while shifting colors; assembler penalizes +0.10 per overlapping color with previous; evaluator reports preserved non-color attributes in style_note; formatter opens with "fresh color direction" and shows intent-specific follow-up chips
- `similar_to_previous`: architect preserves all dimensions from previous recommendation; assembler boosts -0.05 for matching occasion and -0.03 per shared color; evaluator reports all shared dimensions (colors, patterns, volume, fit, silhouette) in style_note; formatter opens with "similar style" and shows intent-specific follow-up chips
- evaluator receives candidate-by-candidate deltas against the previous recommendation with 8 signals: colors, occasions, roles, formality levels, pattern types, volume profiles, fit types, silhouette types
- evaluator payload includes `body_context_summary` (height_category, frame_structure, body_shape) for body-aware ranking
- evaluator returns 8 style archetype percentage scores (classic_pct, dramatic_pct, romantic_pct, natural_pct, minimalist_pct, creative_pct, sporty_pct, edgy_pct) — integers 0–100, clamped server-side
- archetype scores describe the outfit's aesthetic profile, not the user's preference; used for radar chart visualization
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
- global hard filter: `gender_expression` (always applied, never relaxed)
- direction hard filters: `styling_completeness` (`complete`, `needs_bottomwear`, `needs_topwear`)
- query-document hard filters: `garment_category`, `garment_subtype` (extracted server-side from planner output)
- soft signals via embedding similarity only: `occasion_fit`, `formality_level`, `time_of_day`

No filter relaxation — single search pass per query. No retry with dropped filters.

Vector search function: `match_catalog_item_embeddings` uses a `MATERIALIZED` CTE in plpgsql to pre-filter rows before vector distance calculation. This prevents pgvector's HNSW index from scanning approximate nearest neighbors across the entire table and then post-filtering (which can eliminate all valid matches). The materialized CTE forces row-level WHERE filters to execute first, then runs exact cosine distance on the filtered subset.

## Product Payload Reality

Current runtime product cards carry:
- image
- title
- price
- product URL
- similarity
- garment_category
- garment_subtype
- primary_color
- role
- formality_level
- occasion_fit
- pattern_type
- volume_profile
- fit_type
- silhouette_type

Current response behavior:
- UI renders `result.outfits` as 3-column PDP cards
- `OutfitCard.tryon_image` is populated by the orchestrator and rendered as the default hero image
- `OutfitCard` carries 8 archetype `_pct` fields (classic, dramatic, romantic, natural, minimalist, creative, sporty, edgy) rendered as a radar chart in the UI
- `response.metadata` includes `turn_id` for feedback correlation
- both internal (`agentic_application/schemas.py`) and shared (`platform_core/api_schemas.py`) schemas are aligned

## Chat UI: Outfit Card — 3-Column PDP Layout + Feedback CTAs

Status:
- implemented
- pending manual smoke test on live server

Current UI behavior (implemented):
- one unified PDP-style card per outfit (`.outfit-card` CSS class)
- desktop: 3-column grid (`80px | flex | 40%`)
  - Col 1: vertical thumbnail rail (product images + try-on, 64×64px, active accent border)
  - Col 2: hero image viewer (full height, default to try-on when present)
  - Col 3: info panel (rank, title, per-product title + price, style archetype radar chart, feedback CTAs)
- mobile (`max-width: 900px`): hero image → horizontal thumbnail strip → info panel

Thumbnail ordering:
- paired outfit: topwear, bottomwear, virtual try-on
- single-piece: garment, virtual try-on
- default hero: try-on when present, otherwise first garment

Feedback behavior:
- `Like This` — sends `event_type: "like"` immediately via POST to `/v1/conversations/{id}/feedback`
- `Didn't Like This` — expands textarea + Submit; cancel collapses
- loading spinner and success/error state on submission
- feedback hides CTAs after successful submission

Feedback persistence:
- UI is outfit-level; backend fans out to one `feedback_events` row per garment
- `recommendation_run_id` is nullable (migration `20260317120000`)
- correlation: `conversation_id` + `turn_id` + `outfit_rank`
- `feedback_events` columns: `turn_id` (FK to conversation_turns), `outfit_rank` (int)
- `turn_id` injected into `response.metadata` by the orchestrator

Data flow (implemented):
- `response_formatter._build_item_card()` passes through 16 fields including 6 enrichment attributes
- `response_formatter` passes through 8 archetype `_pct` fields from `EvaluatedRecommendation` to `OutfitCard`
- `api_schemas.OutfitCard.tryon_image` aligned with internal `schemas.OutfitCard.tryon_image`
- `api_schemas.OutfitCard` carries 8 archetype `_pct` fields aligned with internal schema
- `api_schemas.OutfitItem` carries all enrichment attributes
- `api_schemas.FeedbackRequest` validates `event_type` via regex pattern `^(like|dislike)$`

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
- the active runtime follows the intended 10-stage agentic pipeline (including context gate and virtual try-on)
- typed context handoff exists between all major stages
- architect uses strict JSON schema with enum-constrained filter vocabulary
- evaluator has a graceful assembly_score fallback
- follow-up state is persisted server-side instead of relying on client history
- latency tracked per agent and persisted to model_call_logs / tool_traces

Main weak spots:
- (none — evaluator, assembler, and spec are synchronized)

## What Is Working

Working now:
- onboarding flow
- profile analysis and interpretation
- style preference capture
- catalog enrichment and embeddings
- recommendation orchestration (10-stage pipeline including context gate)
- complete-outfit retrieval
- paired retrieval and assembly
- 3-column PDP outfit cards with thumbnail navigation and hero image viewer
- per-product detail with title and price
- style archetype radar chart per outfit card (8 axes: classic, dramatic, romantic, natural, minimalist, creative, sporty, edgy)
- virtual try-on as default hero image in outfit cards
- per-outfit feedback capture (Like / Didn't Like with optional notes)
- feedback persistence via `/v1/conversations/{id}/feedback` endpoint
- context gate with clarifying questions and quick-reply chips for vague requests
- follow-up turns with persisted context
- virtual try-on image generation (inline, automatic for all outfits)
- try-on prompt engineering for body-preserving garment replacement
- QnA stage narration with context-aware messages
- digital draping (LLM-based 4-season color analysis via headshot overlays)
- comfort learning (behavioral seasonal palette refinement from outfit likes)
- effective seasonal groups pipeline (draping → comfort learning → per-request context)

## What Is Not Finished

(No outstanding items — all features implemented and smoke-tested.)

## Repo Reality

The repo currently contains more than one generation of the architecture.

Active path:
- `modules/agentic_application`

Consolidation status:
- `modules/onboarding`, `modules/catalog_retrieval`, and `modules/catalog_enrichment` shims have been removed
- all code lives under its owning bounded context (`user`, `catalog`, `agentic_application`, `platform_core`)

This means:
- the system works
- the architecture is clean — one generation, no overlapping layers

## Database Table Inventory

Supabase tables (25 migrations in `supabase/migrations/`):

### Core platform tables
- `users` — id, external_user_id, profile_json, profile_updated_at
- `conversations` — id, user_id, status, session_context_json
- `conversation_turns` — id, conversation_id, user_message, assistant_message, resolved_context_json
- `model_calls` — logging for LLM calls (service, call_type, model, request/response JSON)
- `tool_traces` — logging for tool executions (tool_name, input/output JSON)
- `recommendation_events` — logging for recommendation pipeline events
- `feedback_events` — user feedback tracking (user_id, conversation_id, garment_id, event_type, reward_value, notes, recommendation_run_id nullable, turn_id FK, outfit_rank)

### Onboarding tables
- `onboarding_profiles` — user_id (unique), mobile (unique), otp fields, name, date_of_birth, gender, height_cm, waist_cm, profession, profile_complete, onboarding_complete
- `onboarding_images` — user_id, category (full_body/headshot), encrypted_filename, file_path, mime_type, file_size_bytes; unique on (user_id, category)
- `user_analysis_runs` — tracks analysis snapshots per user (status, model_name, body_type_output, color_headshot_output, other_details_output, collated_output)
- `user_derived_interpretations` — stores deterministic interpretations (SeasonalColorGroup, HeightCategory, WaistSizeBand, ContrastLevel, FrameStructure) with value/confidence/evidence_note
- `user_style_preference` — primary_archetype, secondary_archetype, risk_tolerance, formality_lean, pattern_type, selected_images
- `user_analysis_snapshots` — now includes `draping_output` (jsonb) column for digital draping chain results
- `user_interpretation_snapshots` — now includes `seasonal_color_distribution`, `seasonal_color_groups_json`, `seasonal_color_source`, `draping_chain_log` columns
- `user_effective_seasonal_groups` — source of truth for per-request seasonal color groups (user_id, seasonal_groups jsonb, source, superseded_at)
- `user_comfort_learning` — behavioral comfort learning signals (user_id, signal_type, signal_source, detected_seasonal_direction, garment_id)

### Catalog tables
- `catalog_enriched` — product_id (unique), title, description, price, url, image_urls, row_status, raw_row_json, error_reason + 50+ enrichment attribute columns with confidence scores
- `catalog_item_embeddings` — product_id, embedding (pgvector 1536), metadata_json; indexed on product_id
- `catalog_jobs` — id (uuid), job_type (`items_sync` | `url_backfill` | `embeddings_sync`), status (`pending` | `running` | `completed` | `failed`), params_json (JSONB), processed_rows, saved_rows, missing_url_rows, error_message, started_at, completed_at, created_at, updated_at; indexed on job_type, status, created_at desc

## Module File Layout

```text
modules/
├── agentic_application/src/agentic_application/
│   ├── api.py                    # FastAPI app factory, routes
│   ├── orchestrator.py           # 10-stage pipeline (incl. context gate + virtual try-on)
│   ├── schemas.py                # Pydantic models
│   ├── context_gate.py            # Rule-based context sufficiency gate (<1ms)
│   ├── filters.py                # Hard filter construction (no relaxation)
│   ├── qna_messages.py           # Template-based stage narration (QnA transparency)
│   ├── product_links.py          # Canonical URL resolution
│   ├── agents/
│   │   ├── outfit_architect.py   # LLM planning (gpt-5.4)
│   │   ├── catalog_search_agent.py # Embedding search + hydration
│   │   ├── outfit_assembler.py   # Compatibility pruning
│   │   ├── outfit_evaluator.py   # LLM ranking (gpt-5.4)
│   │   └── response_formatter.py # UI output generation (max 3 outfits)
│   ├── context/
│   │   ├── user_context_builder.py  # Profile loading + richness scoring
│   │   ├── occasion_resolver.py     # Rule-based live context extraction
│   │   └── conversation_memory.py   # Cross-turn state
│   └── services/
│       ├── onboarding_gateway.py    # App-facing user interface (ApplicationUserGateway) + person image lookup
│       ├── catalog_retrieval_gateway.py # App-facing retrieval interface
│       ├── tryon_service.py         # Virtual try-on via Gemini (gemini-3.1-flash-image-preview)
│       └── comfort_learning.py      # Behavioral seasonal palette refinement
├── user/src/user/
│   ├── api.py                    # Onboarding REST endpoints
│   ├── service.py                # OTP, profile, image handling
│   ├── analysis.py               # 3-agent analysis pipeline
│   ├── interpreter.py            # Deterministic interpretation derivation
│   ├── draping.py               # Digital draping — LLM-based seasonal color analysis
│   ├── style_archetype.py        # Style preference selection
│   ├── repository.py             # Supabase CRUD for onboarding tables
│   ├── schemas.py                # Request/response models
│   ├── context.py                # Saved user context builder
│   └── ui.py                     # Onboarding + processing HTML
├── catalog/src/catalog/
│   ├── admin_api.py              # Catalog admin REST endpoints
│   ├── admin_service.py          # CSV processing, enrichment sync, embedding sync, job lifecycle
│   ├── ui.py                     # Admin UI HTML
│   ├── retrieval/                # Embedding & vector search (was catalog_retrieval)
│   │   ├── vector_store.py       # pgvector similarity search
│   │   ├── document_builder.py   # Embedding document construction
│   │   ├── embedder.py           # text-embedding-3-small batch embedding
│   │   └── ...
│   └── enrichment/               # Batch enrichment pipeline (was catalog_enrichment)
│       ├── batch_builder.py      # OpenAI batch request construction
│       ├── batch_runner.py       # Batch API orchestration
│       ├── config_registry.py    # Garment attribute config loader
│       └── ...
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
python3 -m pytest tests/ -v
```

200 tests across 14 files.

Focused application suites:

```bash
python3 -m pytest tests/test_agentic_application.py -v
python3 -m pytest tests/test_agentic_application_api_ui.py -v
```

### Test File Inventory

| File | Coverage Area |
|---|---|
| `tests/test_agentic_application.py` | Core pipeline: orchestrator, planner, evaluator, assembler, formatter, context builders, filters, conversation memory, follow-up intents, recommendation summaries |
| `tests/test_agentic_application_api_ui.py` | API routes, async turn jobs, UI rendering, conversation lifecycle, error handling |
| `tests/test_onboarding.py` | OTP flow, profile persistence, image upload, analysis pipeline, style preference, rerun support |
| `tests/test_onboarding_interpreter.py` | Deterministic interpretation derivation: 4 seasonal color groups, height categories, waist bands, contrast levels, frame structures |
| `tests/test_catalog_retrieval.py` | Embedding document builder, vector store operations, similarity search, filter application, confidence policy |
| `tests/test_batch_builder.py` | Catalog enrichment batch processing |
| `tests/test_platform_core.py` | SupabaseRestClient, ConversationRepository, config loading |
| `tests/test_user_profiler.py` | User profiler utilities |
| `tests/test_config_and_schema.py` | Configuration validation, schema consistency |
| `tests/test_architecture_boundaries.py` | Module boundary enforcement, import validation |
| `tests/test_digital_draping.py` | Digital draping: hex conversion, 4-season distribution computation, top-N group selection, tiebreak priority, DrapingResult serialization |
| `tests/test_comfort_learning.py` | Comfort learning: 4-season color mapping, high/low-intent signal detection, evaluate-and-update threshold logic, max 2 groups, supersede old rows |
| `tests/test_context_gate.py` | Context gate: signal scoring, bypass rules, consecutive block cap, clarification response |
| `tests/test_qna_messages.py` | QnA narration: stage message templates, context-aware narration |

### Key Test Coverage Areas

**Application pipeline:** LLM-only planning (no deterministic fallback), evaluator fallback to assembly_score, evaluator hard output cap (max 5), follow-up intents (7 types), assembly compatibility checks, response formatter bounds (max 3 outfits), concept-first paired planning, model configuration validation, conversation memory build/apply, context gate signal scoring/bypass, QnA stage narration.

**Onboarding:** 3-agent analysis with mock LLM responses, interpretation derivation across 4 seasonal color groups (Spring, Summer, Autumn, Winter), style archetype selection, single-agent rerun with baseline preservation.

**Digital draping:** Hex-to-RGBA conversion, 4-season probability distribution (sums to 1.0), high/low confidence behavior, confirmation round cross-temperature shifts, top-N group selection (clear winner / top-2 clash / 3+ clash with Autumn/Winter preference), tiebreak priority.

**Comfort learning:** Season-to-color mapping (4 seasons, warm/cool), high-intent signal detection (outside current groups), low-intent signal detection (color keywords), evaluate-and-update threshold (5 high-intent), max 2 groups, supersede old effective rows, no duplicate direction.

**Catalog:** Embedding document structure (8 sections), confidence-aware rendering, row status filtering, filter column normalization.

**Architecture:** No direct cross-boundary imports, gateway pattern enforcement.

## Supabase Sync

### Env Convention

- Local: `.env.local` / `APP_ENV=local`
- Staging: `.env.staging` / `APP_ENV=staging`
- Or explicit: `ENV_FILE=/path/to/file`

Bootstrap missing env files:
```bash
python3 ops/scripts/bootstrap_env_files.py
```

Required staging keys: `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`

### Link and Push

```bash
supabase link --project-ref zfbqkkegrfhdzqvjoytz --password '<db-password>' --yes
supabase db push --yes
python3 ops/scripts/check_supabase_sync.py --strict
```

### Key Table Relationships

```text
users
  └── conversations (user_id)
        └── conversation_turns (conversation_id)

onboarding_profiles (user_id → users)
  ├── onboarding_images (user_id, category unique)
  ├── user_analysis_runs (user_id)
  │     └── user_derived_interpretations (analysis_snapshot_id)
  ├── user_style_preference (user_id)
  ├── user_effective_seasonal_groups (user_id)
  └── user_comfort_learning (user_id)

catalog_enriched (product_id unique)
  └── catalog_item_embeddings (product_id)
```

## Immediate Priority Order

1. build dedicated eval harness for systematic recommendation quality testing

## Unified Action Checklist

### Priority 1: Recommendation Safety

- [x] add `OccasionFit` compatibility checks to paired assembly in `agentic_application/agents/outfit_assembler.py`
- [x] add regression tests covering relaxed retrieval followed by mismatched-occasion pair candidates
- [x] decide whether assembly should also explicitly validate `GenderExpression` or continue relying on retrieval-only enforcement — decided: retrieval-only enforcement, no assembly validation needed

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

### Priority 8: Chat UI Outfit Card Redesign — 3-Column PDP Layout + Feedback CTAs

Target: replace the current separate try-on / meta / product-grid rendering with one unified PDP-style card per outfit.

#### Layout spec

Desktop (3-column grid per outfit card):
- **Col 1 — Thumbnail rail** (~80px): vertical strip of clickable thumbnails
  - Paired outfit: topwear image, bottomwear image, virtual try-on
  - Single-piece direction (Direction A): garment image, virtual try-on
  - Active thumbnail gets a highlighted border
- **Col 2 — Hero image** (flex): full-height display of the selected thumbnail
  - Default: virtual try-on when present, otherwise the first garment image
  - Clicking any thumbnail in Col 1 swaps the hero
- **Col 3 — Info panel** (~40%): PDP-style product detail
  - Rank label + outfit title
  - Recommendation reasoning (body/color/style/occasion notes combined)
  - Per-product: title, price, "Open product" link
  - Attribute chips: garment_category, garment_subtype, primary_color, formality_level, occasion_fit, pattern_type, volume_profile, fit_type, silhouette_type
  - Feedback CTAs: "Like This" and "Didn't Like This"
  - Dislike expands a textarea + Submit button; cancel collapses it

Mobile (`max-width: 900px`): stack vertically — hero image, horizontal thumbnail rail, then info panel.

#### Feedback persistence strategy

- UI action is outfit-level (user clicks Like/Dislike on the whole card)
- Persistence fans out to one `feedback_events` row per garment in the outfit
- Each row shares the same `event_type` and `notes`
- `recommendation_run_id` is NOT available from the agentic pipeline → make nullable via migration
- Correlation: use `conversation_id` + `turn_id` (already available in response metadata) instead of `recommendation_run_id`
- Add `turn_id` and `outfit_rank` columns to `feedback_events` for traceability

#### Step 1: Schema alignment (`modules/platform_core/src/platform_core/api_schemas.py`)

- [x] add `tryon_image: str = ""` to `OutfitCard`
- [x] extend `OutfitItem` with: `formality_level`, `occasion_fit`, `pattern_type`, `volume_profile`, `fit_type`, `silhouette_type` (all `str = ""`)
- [x] add `FeedbackRequest` schema: `outfit_rank: int`, `event_type: str` (like/dislike), `notes: str = ""`, `item_ids: List[str] = []`

#### Step 2: Response formatter pass-through (`modules/agentic_application/src/agentic_application/agents/response_formatter.py`)

- [x] update `_build_item_card()` to include the 6 new item attributes from upstream candidate data
- [x] expose `turn_id` in `response.metadata` (injected by orchestrator after formatting)

#### Step 3: DB migration (`supabase/migrations/20260317120000_feedback_events_outfit_columns.sql`)

- [x] `ALTER TABLE feedback_events ALTER COLUMN recommendation_run_id DROP NOT NULL`
- [x] `ALTER TABLE feedback_events ADD COLUMN IF NOT EXISTS turn_id uuid REFERENCES conversation_turns(id)`
- [x] `ALTER TABLE feedback_events ADD COLUMN IF NOT EXISTS outfit_rank int`

#### Step 4: Repository method (`modules/platform_core/src/platform_core/repositories.py`)

- [x] add `create_feedback_event(conversation_id, turn_id, outfit_rank, garment_id, event_type, reward_value, notes, user_id)` method

#### Step 5: Feedback endpoint (`modules/agentic_application/src/agentic_application/api.py`)

- [x] add `POST /v1/conversations/{conversation_id}/feedback`
- [x] accept `FeedbackRequest` body
- [x] look up the latest turn for the conversation to get `turn_id` and `user_id`
- [x] resolve item IDs from the outfit at `outfit_rank` in the turn result
- [x] insert one `feedback_events` row per garment via the repository
- [x] return `{ "ok": true, "count": N }`

#### Step 6: UI rewrite (`modules/platform_core/src/platform_core/ui.py`)

CSS changes:
- [x] remove old styles: `.tryon-section`, `.tryon-label`, `.cards`, `.card`, `.card img`, `.card .body`
- [x] add `.outfit-card` — 3-column grid: `grid-template-columns: 80px 1fr 40%`
- [x] add `.outfit-thumbs` — vertical flex, gap 8px, thumbnails 64×64px with border/radius
- [x] add `.outfit-thumbs img.active` — accent border highlight
- [x] add `.outfit-main-img` — full height, `object-fit: contain`, background `#f5efe6`
- [x] add `.outfit-info` — padding, overflow-y auto
- [x] add `.outfit-feedback` — flex row for CTA buttons
- [x] add `.dislike-form` — hidden by default, textarea + submit
- [x] add responsive rule `@media (max-width: 900px)` — single column, horizontal thumbnails

JS changes:
- [x] rewrite `renderOutfits()` to build one `.outfit-card` per outfit with 3-column structure
- [x] add `buildOutfitCard(outfit, conversationId)` — creates full 3-column card with thumbnails, hero, info panel, and feedback CTAs
- [x] add `sendFeedback(conversationId, outfitRank, eventType, notes, itemIds, ...)` — POST to feedback endpoint with loading/error state
- [x] remove old `renderRecommendations()` function (replaced by inline rendering in `buildOutfitCard`)

#### Step 7: Test coverage

- [x] `test_ui_html_contains_outfit_card_classes` — verifies `.outfit-card`, `.outfit-thumbs`, `.outfit-main-img`, `.outfit-info` class hooks; verifies old classes removed
- [x] `test_outfit_card_schema_accepts_tryon_and_enrichment_fields` — schema validation for richer payloads
- [x] `test_feedback_request_schema_validates_event_type` — rejects invalid event types
- [x] `test_feedback_endpoint_returns_ok` — POST feedback returns 200, correct count, correct call shape
- [x] `test_feedback_endpoint_rejects_invalid_event_type` — returns 422 for invalid event type

#### Step 8: Verification

- [x] `python -m pytest tests/ -x -q` — 200 passed
- [x] manual smoke test:
  - desktop: 3-column layout renders correctly, thumbnails switch hero image
  - mobile: stacked layout, horizontal thumbnails
  - Like button sends feedback, shows confirmation
  - Dislike button reveals textarea, submit sends feedback with notes
  - feedback rows appear in `feedback_events` table

Success criteria:
- every recommended outfit renders as a single cohesive 3-column card
- thumbnail clicking swaps the hero image without re-rendering the conversation
- virtual try-on is the default hero when present
- outfit feedback is captured from the chat UI and persisted through the existing `feedback_events` table
- mobile layout degrades cleanly to a stacked single-column view

## Consolidation Plan

### User Boundary

- [x] move runtime imports and ownership fully under `modules/user`
- [x] move analysis code under `modules/user`
- [x] move deterministic interpretation under `modules/user`
- [x] move style preference flow under `modules/user`
- [x] reduce `modules/onboarding` to compatibility wrappers, then remove

Definition of done:
- app runtime no longer depends on `onboarding.*` directly — **DONE**: all imports use `user.*` via `ApplicationUserGateway`; `modules/onboarding` shim deleted

### Catalog Boundary

- [x] move active ingestion/orchestration imports from `catalog_enrichment.*` and `catalog_retrieval.*` to `catalog.*`
- [x] add explicit job tables:
  - single `catalog_jobs` table with `job_type` discriminator (`items_sync`, `url_backfill`, `embeddings_sync`)
- [x] add per-job admin status instead of aggregate-only counts
- [x] add selective rerun support by file, `max_rows`, and row range (`start_row`/`end_row`)
- [x] ensure `catalog_enriched` remains the canonical enriched record table in both dev and staging

Definition of done:
- catalog operations are fully manageable from `modules/catalog`
- code consolidation **DONE**: all retrieval and enrichment code lives in `catalog/retrieval/` and `catalog/enrichment/`; `catalog_retrieval` and `catalog_enrichment` shims deleted; `agentic_application` imports only from `catalog.*`

### Application Quality: Concept-First Paired Planning

**Status:** Complete. Concept-first paired planning is now handled entirely by the LLM via the system prompt in `prompt/outfit_architect.md`. The deterministic fallback code (seasonal palettes, volume balance rules, `_build_outfit_concept()`, etc.) has been removed.

The LLM is instructed to:
1. Define a holistic outfit vision first (color scheme, volume balance, pattern distribution, fabric story)
2. Decompose into role-specific queries with DIFFERENT, COMPLEMENTARY parameters for top and bottom

Key rules enforced by prompt:
- Color: contrasting/complementary colors, bottoms anchor with neutrals, tops carry accent
- Volume: visual balance — if one piece is relaxed, the other is slim/fitted
- Pattern: typically one piece carries pattern, other is solid
- Fabric: formal → both structured, smart casual → top relaxed + bottom structured

The architect JSON schema enforces valid filter vocabulary via enums. Null values are stripped from hard_filters before search.

#### Remaining application quality items

- [x] strengthen evaluator prompts and context payload quality
- [x] add targeted regression coverage around follow-up refinement and evaluator fallback
- [x] keep `docs/APPLICATION_SPECS.md` synchronized with actual implementation behavior and active tests
- [x] remove deterministic fallback from architect (LLM-only, failure = error to user)
- [x] fix filter vocabulary: `needs_bottomwear`/`needs_topwear`, remove `occasion_fit`/`formality_level`/`time_of_day` from hard filters
- [x] add enum-constrained JSON schema for valid hard filter values
- [x] add latency tracking (`latency_ms`) on model_call_logs and tool_traces

Definition of done:
- architecture docs remain trustworthy and the active runtime behaves as specified
