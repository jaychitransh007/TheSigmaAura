# Current Project State

Last updated: April 8, 2026 (P0+P1 closeout, cleanup PRs 1 & 2, architectural parking note)

Canonical references:
- `docs/CURRENT_STATE.md`
- `docs/DESIGN.md`
- `docs/PRODUCT.md`
- `docs/APPLICATION_SPECS.md`
- `docs/INTENT_COPILOT_ARCHITECTURE.md`
- `docs/WORKFLOW_REFERENCE.md`
- `docs/fashion-ai-architecture.html`

This document is the single merged state-and-checklist document for the project.
It supersedes the former architecture TODO and standalone cleanup/remediation checklist docs.

For user-facing product framing, personas, journey, and stories, use `docs/PRODUCT.md`.
For UI, UX, and visual system direction, use `docs/DESIGN.md`.

> **Verification status (read this before quoting any "implemented" or "usable" claim below):**
> Every "Implemented" / "functionally usable" / "usable end-to-end" claim in this document is
> backed by automated tests in `tests/test_agentic_application.py` (and the bounded-context
> test files listed in § Test Architecture). It is **not** the same as live verification
> against a staging Supabase + the real catalog embeddings + a real test user. Live
> verification is gated by the four gates in `docs/RELEASE_READINESS.md`. When a section
> below says something "works", it means "works in tests"; when it needs to mean "works in
> production", it must point at one of those gates.

## Product Positioning

> **For** people who want to dress better every day, **Aura is** a personal fashion copilot **that** knows your body, your style, and your wardrobe — so you always know what to wear and what's worth buying.

Strategy: **stylist for retention, shopping for revenue.** The product should feel like a personal stylist that users make part of their daily routine. Shopping is the natural outcome when the stylist identifies a wardrobe gap — not the default answer to every question.

## Executive Status

Project status:
- user layer: implemented and usable
- catalog layer: implemented and usable
- application layer: active, usable end-to-end recommendation pipeline with copilot planner, wardrobe ingestion, image moderation, and confidence engines
- wardrobe: ingestion, enrichment, retrieval, wardrobe-first occasion response, full CRUD UI (add/edit/delete), enhanced filters (search, category, color), and completeness scoring implemented
- WhatsApp: removed from current codebase (previously had formatting and deep linking; runtime was never built)
- safety: dual-layer image moderation (heuristic + vision), restricted category exclusion, try-on quality gate implemented
- web UI: modern chat-first interface with unified warm/burgundy design across onboarding, profile analysis, main app, and admin
- profile: unified view + edit page with inline editing toggle, style code card, and personalized color palette card (base/accent/avoid)
- wardrobe: seamless "+Add Item" modal — photo-only upload with auto-enrichment (46 attributes via vision API); edit modal for all metadata fields; per-card delete with confirmation
- wardrobe filters: search bar (title/description/brand/category), category chips (8 including Dresses, Outerwear, Accessories), color filter row (11 colors), localStorage persistence
- chat management: conversation rename (inline edit) and delete (archive) with hover-reveal sidebar actions; `title` column on conversations table
- virtual try-on: persistent storage with cache reuse — images saved to disk + `virtual_tryon_images` table, mapped by user + garment IDs + source; same garment combination returns cached result without re-generation
- chat composer: `+` button popover with "Upload image" and "Select from wardrobe" options; drag-drop and paste support
- results: previous results grid with outfit preview thumbnails extracted from outfits[].items[].image_url
- catalog admin: pipeline with upload, enrichment sync, embedding generation, URL backfill, include-incomplete toggle, skip-already-embedded optimization

The system is a working recommendation engine with supporting infrastructure. The next phase is evolving it from a shopping-first tool into a lifestyle stylist — wardrobe-first across all intents, dedicated handlers for non-recommendation intents (outfit check, shopping decision, pairing, capsule planning), and WhatsApp as a live retention surface.

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

## Strategic Product Direction

Target operating model:
- website for onboarding and discovery
- mandatory onboarding before chat access
- WhatsApp for retention and repeat usage
- one intent-driven chat system rather than a menu of separate tools
- optional wardrobe onboarding for the user, but full wardrobe support in the system
- wardrobe-first answers across all intents — catalog fills gaps, not the default
- confidence visibility for profile analysis and recommendation / outfit check responses
- strict safety guardrails around nude image uploads, lingerie / restricted product categories, and unsafe virtual try-on output

## First-50 Validation Goal

The goal is to validate dependency with the first 50 onboarded users:
- users complete onboarding on web
- users return through WhatsApp for real clothing decisions
- the team identifies which intents become recurring habits
- the system proves it can combine profile, wardrobe, catalog, feedback, and chat history in one conversational product

Success means users come back before real decisions: should I buy this, what goes with this, what should I wear, does this outfit work.

## Current Gap Versus Target State

### What exists and works:
- onboarding flow (OTP, profile, images, analysis, draping, style prefs)
- catalog enrichment and embedding retrieval pipeline
- copilot planner with intent classification and action routing (12 intents recognized)
- recommendation pipeline (architect → search → assemble → evaluate → format → try-on) — used for both occasion and pairing requests (pairing always runs full pipeline including try-on)
- wardrobe ingestion with vision-API enrichment and image moderation
- wardrobe retrieval and wardrobe-first occasion response
- virtual try-on via Gemini with quality gate
- 3-column PDP outfit cards with Buy Now, dual radar charts (archetypes + confidence-weighted evaluation), icon feedback (save/like/dislike)
- `analysis_confidence_pct` — attribute-level analysis confidence (average LLM confidence across all profile attributes); used to scale evaluation radar chart scores at render time; fetched once per page load, applied consistently to all cards including history
- unified profile page with inline editing, style code card, and color palette card
- wardrobe add-item modal from wardrobe page
- wardrobe edit modal (all metadata fields) and per-card delete with confirmation
- wardrobe search bar, enhanced category filter chips (8), color filter row (11), localStorage persistence
- chat management: conversation rename (inline edit) and delete (archive) in sidebar
- chat composer + button with upload image / select from wardrobe popover
- results page with outfit preview thumbnails
- feedback capture + comfort learning
- profile confidence engine and recommendation confidence engine (9-factor scoring)
- dual-layer image moderation (heuristic + vision API)
- restricted category exclusion in retrieval
- dependency/retention instrumentation
- follow-up turns with persisted context and 7 follow-up intent types

### What needs to be built:

#### P0 — Design System And Experience Realignment
- [x] update all primary user journeys to match the stylist-studio product model in `docs/DESIGN.md`
- [x] redesign the web experience from a utility chat shell into a stylist hub with clear entry points for `Dress Me`, `Style This`, `Check Me`, `Know Me`, `Wardrobe`, and `Trips`
- [x] replace the current utilitarian visual language with the centralized fashion-led design system from `docs/DESIGN.md`
- [x] make capability discovery proactive in the UI so users can immediately see occasion dressing, pairing, outfit check, style advice, buy/skip, and trip planning
- [x] redesign the chat composer and feed to support premium multimodal styling input with image attach, URL paste, context chips, and explicit source preference controls
- [x] redesign recommendation presentation to be image-first, stylist-led, and layered as summary → looks → rationale instead of score-first
- [x] make wardrobe, catalog, and hybrid source modes visually explicit throughout all recommendation flows
- [x] redesign wardrobe browsing as a visual closet studio rather than an inventory list
- [x] redesign style profile and style-discovery surfaces into an editorial “My Style Code” experience
- [x] redesign outfit-check UX so it feels like a personal stylist critique, not a grading tool
- [x] redesign trip / capsule planning UX into a timeline and packing experience with daypart coverage, hybrid looks, and gap-fill suggestions
- [x] establish a reusable component system, motion rules, and responsive patterns aligned with `docs/DESIGN.md`
- [x] define mobile-first and desktop-studio variants for all major surfaces before implementation
- [x] ensure WhatsApp-to-web handoff and deep-linked web surfaces preserve the same visual and UX language

#### P0 — Journey And IA Redesign
- [x] rewrite the end-to-end user journey for discovery → onboarding → first value → repeat usage → wardrobe growth → WhatsApp return loops
- [x] redesign post-onboarding first-run UX so users land in a stylist dashboard, not an empty chat state
- [x] define the ideal first-session path for each primary job: occasion outfit, pairing, outfit check, shopping decision, style advice, and trip planning
- [x] define proactive home-screen modules for “today with Aura”, wardrobe health, style profile, recent threads, and saved looks
- [x] define a consistent navigation model across home, chat, wardrobe, style profile, and trip planning
- [x] define follow-up UX patterns for `Improve It`, `Show Alternatives`, `Explain Why`, `Shop The Gap`, and `Save For Later`
- [x] define feedback UX that captures fashion-native reactions like `Too safe`, `Too much`, `Not me`, and `Weird pairing`

#### P0 — Single-Page Shell Cleanup
- [x] split the current all-in-one `/` page into a true dashboard-first IA instead of stacking every major surface in one long page
- [x] make `/` the stylist dashboard only: hero, quick actions, wardrobe health summary, style summary, recent threads, and saved looks
- [x] move the full chat workspace into a dedicated primary view instead of forcing dashboard + chat + wardrobe + style + trips onto one page
- [x] move wardrobe studio into its own destination surface instead of rendering the full closet editor inline on `/`
- [x] move `My Style Code` into its own destination surface instead of rendering the full profile workspace inline on `/`
- [x] move outfit-check and trip-planning workspaces behind dedicated entry points instead of permanently occupying homepage real estate
- [x] add explicit top-level view routing or switching for `dashboard`, `chat`, `wardrobe`, `style`, and `trips`
- [x] preserve WhatsApp/deep-link continuity while routing users into the correct destination surface
- [x] ensure the homepage uses progressive disclosure and one dominant primary action area instead of showing every feature at once
- [x] validate that the resulting IA feels curated and fashion-native rather than implementation-stacked

#### P0 — UI Polish And Accessibility
- [x] add Google Fonts `<link>` for Cormorant Garamond so the editorial serif renders for all users instead of falling back to Times New Roman
- [x] add a mobile breakpoint at ~430px with a sticky composer, compact chips, and thumb-friendly tap targets as required by `docs/DESIGN.md`
- [x] add a tablet breakpoint (~768px–900px) so the hub and outfit cards degrade gracefully between desktop and phone layouts
- [x] populate dashboard hero stats dynamically from the user's real style profile instead of the hardcoded "Classic + Romantic" placeholder
- [x] add a chat empty state with an editorial welcome message and suggested-prompt cards so first-time users don't land on a blank feed
- [x] add `prefers-reduced-motion` media query to disable animations for users who request reduced motion
- [x] add basic ARIA roles and labels to navigation, action cards, source switch, filter chips, and interactive elements
- [x] add a text alternative for the outfit-card canvas radar chart so screen readers can interpret style archetype scores
- [x] add loading skeleton states for wardrobe studio and style code views instead of static "waiting" labels
- [x] hide the product URL field behind a toggle or auto-detect so the composer is simpler for the majority of interactions
- [x] make the source switch contextual — show it when relevant instead of always visible

#### P1 — Persistence And Robustness
- [x] back saved looks and recent threads with server-side persistence instead of localStorage-only so they survive browser data clears
- [x] improve follow-up suggestion grouping to use structured metadata from the LLM rather than brittle string-matching on suggestion text
- [x] improve wardrobe filter "Occasion-ready" to use enrichment metadata tags instead of keyword matching against item names

#### P0 — Wardrobe / Catalog Routing Reliability
- [x] fix planner routing so explicit garment-led requests like "pair this shirt", "what goes with this?", and "complete the outfit" resolve to `pairing_request`, not `occasion_recommendation`
- [x] treat attached or newly saved garments as pairing anchors, not complete one-item outfits
- [x] fix wardrobe-first follow-up routing so "Show me better options from the catalog" actually returns catalog or hybrid results
- [x] ensure wardrobe-first responses can nudge buying from the catalog and that the follow-up path works in practice, not only in metadata

#### P1 — Occasion Outfit Flows
- [x] guarantee a user can find the best outfit for an occasion from their own wardrobe
- [x] guarantee a user can ask for the best outfit for an occasion from the catalog
- [x] make source selection explicit in responses: wardrobe-first, catalog-only, or hybrid

#### P1 — Pairing Flows
- [x] support best outfit pairing for an occasion from a wardrobe garment image upload
- [x] support best outfit pairing for an occasion from a catalog garment image upload
- [x] distinguish wardrobe-item image uploads from catalog-item image uploads in routing and follow-up behavior
- [x] ensure pairing responses return complementary items, not the uploaded garment echoed back as the full answer

#### P1 — Outfit Check And Follow-Through
- [x] make "rate my outfit" / "how does this look?" reliably route to the outfit-check path
- [x] after rating an outfit, suggest better options or swaps from the user's wardrobe
- [x] keep catalog follow-up optional after the wardrobe-first critique

#### P1 — Style Advice Precision
- [x] formalize profile-grounded styling advice for questions like "what collar suits me?", "what colors suit me?", "what patterns work on me?", and "which style archetypes fit me?"
- [x] make collar / neckline / pattern / silhouette advice deterministic where possible and grounded in profile evidence
- [x] add direct tests for fine-grained style-advice questions, not only broad explanation requests

#### P2 — Capsule / Trip Planning Quality
- [x] make capsule / trip planning scale to trip duration and context instead of capping at small repeated sets
- [x] generate wardrobe-first and catalog-supported trip plans with enough looks for multi-day travel
- [x] improve diversity across looks, dayparts, and contexts within the same trip plan

#### P2 — Wardrobe Management And Readiness — COMPLETE
- [x] Web-based wardrobe browsing — view, edit metadata, delete items
- [x] Wardrobe completeness scoring — "your wardrobe covers X% of your typical occasions"
- [x] Wardrobe gap analysis view — missing categories for user's lifestyle
- [x] Wardrobe edit modal — full metadata fields (title, description, category, subtype, colors, pattern, formality, occasion, brand, notes)
- [x] Wardrobe delete — per-card delete with confirmation dialog (soft-delete via is_active=false)
- [x] Wardrobe search — text search across title, description, brand, category
- [x] Enhanced filter chips — 8 category chips (All, Tops, Bottoms, Shoes, Dresses, Outerwear, Accessories, Occasion-ready) + 11 color chips + localStorage persistence
- [x] Chat conversation management — rename (inline edit via PATCH) and delete/archive (via DELETE) with hover-reveal sidebar actions

#### P2 — Verification Tooling
- [x] restore `ops/scripts/schema_audit.py` so schema-readiness checks run cleanly again

## Bounded Context Status

### User

Status:
- strong
- functionally usable (verified by unit/integration tests; live end-to-end smoke against staging is still pending — see `docs/RELEASE_READINESS.md` Gate 2)

Implemented:
- OTP-based onboarding flow (fixed OTP: `123456`)
- acquisition-source capture on OTP verification (`acquisition_source`, `acquisition_campaign`, `referral_code`, `icp_tag`)
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
  - `BaseColors` — Foundation/neutral colors for outfit anchors (4-5 per season, e.g. Autumn: warm taupe, warm brown, olive, muted gold)
  - `AccentColors` — Statement/pop colors that complement the user's coloring (4-5 per season, e.g. Autumn: terracotta, rust, burgundy, forest green, burnt orange)
  - `AvoidColors` — Colors that clash with the user's natural coloring (4-5 per season, e.g. Autumn: icy blue, fuchsia, royal blue, stark white, silver)
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
- style archetype session images are served by the onboarding app from repo-backed assets under `archetypes/choices`, so local onboarding no longer depends on Supabase bucket sync
- all user-facing pages (onboarding, profile analysis/processing, main app) share the unified warm/burgundy design system
- Profile status / rerun support (single-agent targeted reruns with baseline preservation)

Current ownership reality:
- all runtime behavior lives under `modules/user`
- `agentic_application` imports exclusively from `user.*` via `ApplicationUserGateway`
- `modules/onboarding` shim has been removed (zero consumers remained)

Main remaining gaps:
- see the global gap-analysis checklist below; most remaining work is in cross-module routing and response quality, not missing user-module primitives

### Catalog

Status:
- strong
- functionally usable (enrichment + embedding pipeline verified by unit tests + manual catalog admin runs; embedding-similarity quality on the live staging dataset still requires human spot-check before the first-50 release)

Implemented:
- admin upload screen (`/admin/catalog`) with modern burgundy theme matching main app
- CSV upload flow (saves to `data/catalog/uploads/`)
- enrichment pipeline (50+ attributes organized in 8 sections)
- sync into `catalog_enriched` (upsert on `product_id`)
- embedding generation into `catalog_item_embeddings` (text-embedding-3-small, 1536 dimensions)
- partial run support via `max_rows`
- local/staging sync paths
- canonical product URL persistence during ingestion (with backfill for older rows)
- auto-generated `product_id`: CSVs lacking a `product_id` column get IDs derived from URL (e.g. `CAMPUSSUTRA_mens-crimson-red-shirt`) or title hash
- auto-inferred `row_status`: CSVs lacking a `row_status` column get `"ok"` for rows with valid product_id + title, `"missing"` otherwise
- only rows with `row_status` in `{ok, complete}` are embeddable by default; `include_incomplete` flag bypasses this filter
- skip-already-embedded optimization: embedding sync fetches existing product IDs from Supabase and skips them, so only new/missing rows are embedded
- job lifecycle tracking: every sync operation (items, URLs, embeddings) creates a `catalog_jobs` row with status transitions (running → completed/failed), params, row counts, and error messages
- selective rerun support: `start_row`/`end_row` parameters on items sync and embeddings sync for range-based partial reruns
- admin job history: `/status` endpoint returns running/failed job counts and recent job list; UI renders job history table with status pills, params, row counts, and truncated errors
- default source CSV path: `data/catalog/enriched_catalog_upload.csv`
- graceful handling when source CSV doesn't exist (status endpoint returns empty rows instead of 500)
- `catalog_items` table removed (superseded by `catalog_enriched`)

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
- see the global gap-analysis checklist below; the main remaining work is how catalog paths are invoked and blended at runtime

### Application

Status:
- active
- usable end-to-end
- not yet final-quality
- verification basis: 92+ tests in `tests/test_agentic_application.py` cover orchestrator routing, the planner→architect→search→assemble→evaluate→format pipeline, wardrobe-first short-circuits, hybrid pivot, disliked-product suppression, cross-outfit diversity, and metadata persistence. Live verification against a staging Supabase + real catalog embeddings is governed by the gates in `docs/RELEASE_READINESS.md` and is **not** complete.

Implemented:
- orchestrated recommendation pipeline with LLM copilot planner front-end
- copilot planner (gpt-5.4) classifies intent and decides action — replaces legacy keyword router + context gate
- **intent registry** (`intent_registry.py`): single source of truth for all 12 intents, 9 actions, and 7 follow-up intents via Python `StrEnum` — consumed by planner, orchestrator, agents, API, and tests
- planner actions: `run_recommendation_pipeline`, `run_outfit_check`, `run_shopping_decision`, `respond_directly`, `ask_clarification`, `run_virtual_tryon`, `save_wardrobe_item`, `save_feedback`, `run_product_browse`
- `response_type` field: `"recommendation"` | `"clarification"`
- saved user context loading
- conversation memory carry-forward
- LLM-only architect planner — no deterministic fallback (model: `gpt-5.4`)
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
- virtual try-on via Gemini (`gemini-3.1-flash-image-preview`), parallel generation for all outfits, persistent storage to disk + DB with cache reuse by garment ID set
- turn artifact persistence
- dependency-validation instrumentation: turn-completion events across web / WhatsApp, referral events, and retention reporting for first/second/third session behavior, cohort anchors, and memory-input lift

Main remaining gaps:
- none for the documented next-phase checklist

## Application Layer: Current Behavioral Reality

Current execution order:
1. load user context
2. build conversation memory from prior turn state
3. copilot planner (gpt-5.4) — classifies intent, decides action (`run_recommendation_pipeline`, `respond_directly`, `ask_clarification`, `run_virtual_tryon`, `save_wardrobe_item`, `save_feedback`), resolves context
4. action dispatch — if `respond_directly` or `ask_clarification`, return planner response directly (skip stages 5-10)
5. generate recommendation plan via outfit architect LLM (gpt-5.4) — no fallback, failure = error to user
6. retrieve catalog products per query direction (text-embedding-3-small, single search pass)
7. assemble outfit candidates (deterministic)
8. evaluate and rank candidates (gpt-5.4, fallback: assembly_score)
9. format response payload (max 3 outfits)
10. generate virtual try-on images (gemini-3.1-flash-image-preview, parallel) — checks cache by user + garment IDs first; saves new results to disk + `virtual_tryon_images` table
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
- evaluator returns 16 percentage scores (all integers 0–100, clamped server-side):
  - 8 evaluation criteria: body_harmony_pct, color_suitability_pct, style_fit_pct, risk_tolerance_pct, occasion_pct, comfort_boundary_pct, specific_needs_pct, pairing_coherence_pct — how well the outfit fits this user; fallback derives from assembly_score * 100
  - 8 style archetype: classic_pct, dramatic_pct, romantic_pct, natural_pct, minimalist_pct, creative_pct, sporty_pct, edgy_pct — outfit's aesthetic profile, not user preference
- full evaluation output (all notes, all 16 _pct fields) is persisted in turn artifacts
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
- `OutfitCard.tryon_image` is populated by the orchestrator with a serveable URL (not base64) pointing to a persisted try-on image on disk; rendered as the default hero image
- `OutfitCard` carries 16 `_pct` fields: 8 evaluation criteria (rendered as progress bars) + 8 style archetypes (rendered as radar chart)
- `response.metadata` includes `turn_id` for feedback correlation
- both internal (`agentic_application/schemas.py`) and shared (`platform_core/api_schemas.py`) schemas are aligned

## Chat UI: Composer + Outfit Cards

Chat composer features:
- `+` button popover with two options: "Upload image" (triggers file picker) and "Select from wardrobe" (opens wardrobe picker modal)
- image chip preview with remove button for attached images
- paste support for images from clipboard
- drag-and-drop image attach onto composer area
- wardrobe picker modal loads user's wardrobe items as a grid; selecting an item attaches its image

## Chat UI: Outfit Card — 3-Column PDP Layout + Feedback CTAs

Status:
- implemented

Current UI behavior (implemented):
- one unified PDP-style card per outfit (`.outfit-card` CSS class)
- desktop: 3-column grid (`80px | flex | 40%`)
  - Col 1: vertical thumbnail rail (product images + try-on, 64×64px, active accent border)
  - Col 2: hero image viewer (full height, default to try-on when present)
  - Col 3: info panel (title, stylist summary ≤100 chars, product specs with Rs. price + Buy Now, style archetype radar chart, evaluation criteria radar chart scaled by analysis_confidence_pct, icon feedback buttons)
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
- `recommendation_run_id` has been removed from `feedback_events`; turn-level correlation now uses `turn_id` + `outfit_rank`
- correlation: `conversation_id` + `turn_id` + `outfit_rank`
- `feedback_events` columns: `turn_id` (FK to conversation_turns), `outfit_rank` (int)
- `turn_id` injected into `response.metadata` by the orchestrator

Data flow (implemented):
- `response_formatter._build_item_card()` passes through 16 fields including 6 enrichment attributes
- `response_formatter` passes through all 16 `_pct` fields (8 criteria + 8 archetype) from `EvaluatedRecommendation` to `OutfitCard`
- `api_schemas.OutfitCard.tryon_image` aligned with internal `schemas.OutfitCard.tryon_image`
- `api_schemas.OutfitCard` carries all 16 `_pct` fields aligned with internal schema
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
- architectural alignment: strong — pipeline, schemas, persistence all clean
- behavioral alignment: partial — system defaults to catalog-first; wardrobe-first and non-recommendation intents are the gap
- color guidance: strong — seasonal color group drives base/accent/avoid color palettes passed to planner, architect, and outfit check agents
- design consistency: strong — onboarding, main app, and admin share unified warm/burgundy visual language

Main strengths:
- intent registry (`intent_registry.py`) — StrEnum-based single source of truth for 12 intents, 9 actions, 7 follow-up intents; consumed by all runtime and test code
- copilot planner routes 12 intents with action dispatch
- typed context handoff between all pipeline stages
- strict JSON schema with enum-constrained filter vocabulary
- evaluator has graceful assembly_score fallback
- follow-up state persisted server-side
- latency tracked per agent and persisted
- wardrobe ingestion and retrieval infrastructure exists
- confidence engines (profile + recommendation) fully operational
- dual-layer moderation with policy logging

Main weak spots:
- live-environment hardening still needs more manual verification than the unit/integration suite
- trip/capsule catalog-path diversity still depends on deeper planner/assembler diversity work
- disliked-product suppression across turns is still not implemented
- first-50 rollout dashboards and release-readiness criteria still need operational definition

## What Is Working

### User Layer
- OTP-based onboarding with acquisition source tracking
- 3-agent parallel analysis pipeline (body type, color, other details) via gpt-5.4
- digital draping — 3-round LLM vision chain for seasonal color analysis
- deterministic interpretation engine (seasonal color, base/accent/avoid color palettes, height, waist, contrast, frame)
- style archetype preference capture (3 layers → primary/secondary archetypes, risk tolerance, formality lean)
- comfort learning — behavioral seasonal palette refinement from outfit likes
- wardrobe ingestion with vision-API enrichment and dual-layer image moderation

### Catalog Layer
- CSV upload + enrichment pipeline (50+ attributes, 8 embedding sections)
- embedding generation (text-embedding-3-small, 1536 dim, pgvector) with skip-already-embedded optimization
- auto-generated `product_id` from URL for CSVs lacking the column; auto-inferred `row_status`; include-incomplete toggle for embedding
- canonical product URL persistence with backfill support
- job lifecycle tracking with admin UI
- `catalog_items` table removed (superseded by `catalog_enriched`)

### Application Layer
- intent registry (`intent_registry.py`) — StrEnum single source of truth for 12 intents, 9 actions, 7 follow-up intents
- copilot planner (gpt-5.4) — intent classification across 12 intents, 8 action dispatch
- recommendation pipeline: architect → catalog search → assembly → evaluation → formatting → try-on
- wardrobe-first occasion response (wardrobe retrieval + selection for occasion intents)
- wardrobe item save from chat with moderation
- virtual try-on via Gemini (gemini-3.1-flash-image-preview), parallel generation, quality gate, persistent disk + DB storage with cache reuse
- 3-column PDP outfit cards with Buy Now, dual radar charts (8 archetypes + confidence-weighted evaluation), icon feedback
- per-outfit feedback capture (Like / Didn't Like with notes)
- follow-up turns with 7 follow-up intent types (increase boldness, change color, similar, etc.)
- color palette system: base/accent/avoid colors derived from seasonal group, passed to planner, architect, and outfit check agents
- profile confidence engine + recommendation confidence engine (9-factor, 0–100 scoring)
- dual-layer image moderation (heuristic blocklist + vision API check)
- restricted category exclusion in catalog retrieval
- QnA stage narration with context-aware messages
- results page with outfit preview thumbnails (extracted from outfits[].items[].image_url)
- unified profile page with inline edit toggle, style code, and color palette display
- wardrobe add-item modal (photo + metadata) from wardrobe page
- chat composer + button with upload image / wardrobe picker popover

### WhatsApp
- removed from codebase (formatter, deep links, reengagement, runtime services all deleted)
- WhatsApp remains a target retention surface in product strategy but has no implementation currently

### Infrastructure
- dependency/retention instrumentation (turn-completion events, cohort anchors, memory-input lift)
- latency tracking per agent stage
- turn artifact persistence (live context, memory, plan, filters, candidates, recommendations)

## What Is Not Finished

See "What needs to be built" in the gap analysis above. The current open
items are tracked inline in the P0/P1/P2 sections above; there is no
additional summary to call out here.

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

Supabase tables (36 migrations in `supabase/migrations/`):

### Core platform tables
- `users` — id, external_user_id, profile_json, profile_updated_at
- `conversations` — id, user_id, status, title, session_context_json
- `conversation_turns` — id, conversation_id, user_message, assistant_message, resolved_context_json
- `model_calls` — logging for LLM calls (service, call_type, model, request/response JSON)
- `tool_traces` — logging for tool executions (tool_name, input/output JSON)
- `feedback_events` — user feedback tracking (user_id, conversation_id, garment_id, event_type, reward_value, notes, turn_id FK, outfit_rank)
- `dependency_validation_events` — first-50 product-validation instrumentation (event_type, primary_intent, source_channel, metadata_json)

### Onboarding tables
- `onboarding_profiles` — user_id (unique), mobile (unique), otp fields, acquisition_source, acquisition_campaign, referral_code, icp_tag, name, date_of_birth, gender, height_cm, waist_cm, profession, profile_complete, onboarding_complete
- `onboarding_images` — user_id, category (full_body/headshot), encrypted_filename, file_path, mime_type, file_size_bytes; unique on (user_id, category)
- `user_analysis_runs` — tracks analysis snapshots per user (status, model_name, body_type_output, color_headshot_output, other_details_output, collated_output)
- `user_derived_interpretations` — stores deterministic interpretations (SeasonalColorGroup, BaseColors, AccentColors, AvoidColors, HeightCategory, WaistSizeBand, ContrastLevel, FrameStructure) with value/confidence/evidence_note
- `user_style_preference` — primary_archetype, secondary_archetype, risk_tolerance, formality_lean, pattern_type, selected_images
- `user_analysis_snapshots` — now includes `draping_output` (jsonb) column for digital draping chain results
- `user_interpretation_snapshots` — now includes `seasonal_color_distribution`, `seasonal_color_groups_json`, `seasonal_color_source`, `draping_chain_log` columns
- `user_effective_seasonal_groups` — source of truth for per-request seasonal color groups (user_id, seasonal_groups jsonb, source, superseded_at)
- `user_comfort_learning` — behavioral comfort learning signals (user_id, signal_type, signal_source, detected_seasonal_direction, garment_id)

### Catalog tables
- `catalog_enriched` — product_id (unique), title, description, price, url, image_urls, row_status, raw_row_json, error_reason + 50+ enrichment attribute columns with confidence scores
- `catalog_item_embeddings` — product_id, embedding (pgvector 1536), metadata_json; indexed on product_id
- `catalog_jobs` — id (uuid), job_type (`items_sync` | `url_backfill` | `embeddings_sync`), status (`pending` | `running` | `completed` | `failed`), params_json (JSONB), processed_rows, saved_rows, missing_url_rows, error_message, started_at, completed_at, created_at, updated_at; indexed on job_type, status, created_at desc
- `catalog_interaction_history` — user_id, product_id, interaction_type (view/click/save/dismiss/buy_skip_request/buy/skip), source_channel (web/whatsapp), source_surface, conversation_id, turn_id, metadata_json

### Virtual try-on tables
- `virtual_tryon_images` — user_id, conversation_id, turn_id, outfit_rank, garment_ids (text[]), garment_source (catalog/wardrobe/mixed), person_image_path, encrypted_filename, file_path, mime_type, file_size_bytes, generation_model, quality_score_pct, metadata_json; GIN index on garment_ids for cache lookup

## Module File Layout

```text
modules/
├── agentic_application/src/agentic_application/
│   ├── intent_registry.py        # StrEnum registry: Intent(12), Action(9), FollowUpIntent(7) + metadata
│   ├── api.py                    # FastAPI app factory, routes
│   ├── orchestrator.py           # Copilot planner + 7-stage pipeline + virtual try-on
│   ├── schemas.py                # Pydantic models
│   ├── filters.py                # Hard filter construction (no relaxation)
│   ├── qna_messages.py           # Template-based stage narration (QnA transparency)
│   ├── product_links.py          # Canonical URL resolution
│   ├── agents/
│   │   ├── copilot_planner.py   # LLM intent classification + action routing (gpt-5.4)
│   │   ├── outfit_architect.py   # LLM planning (gpt-5.4)
│   │   ├── catalog_search_agent.py # Embedding search + hydration
│   │   ├── outfit_assembler.py   # Compatibility pruning
│   │   ├── outfit_evaluator.py   # LLM ranking (gpt-5.4)
│   │   └── response_formatter.py # UI output generation (max 3 outfits)
│   ├── context/
│   │   ├── user_context_builder.py  # Profile loading + richness scoring
│   │   └── conversation_memory.py   # Cross-turn state
│   ├── recommendation_confidence.py # 9-factor recommendation confidence scoring
│   ├── profile_confidence.py       # Profile completeness confidence scoring
│   └── services/
│       ├── onboarding_gateway.py    # App-facing user interface (ApplicationUserGateway) + person image lookup
│       ├── catalog_retrieval_gateway.py # App-facing retrieval interface
│       ├── tryon_service.py         # Virtual try-on via Gemini (gemini-3.1-flash-image-preview)
│       ├── comfort_learning.py      # Behavioral seasonal palette refinement
│       ├── dependency_reporting.py  # First-50 retention/dependency reporting
│       └── outfit_decomposition.py  # Outfit decomposition for garment analysis
├── user/src/user/
│   ├── api.py                    # Onboarding REST endpoints
│   ├── service.py                # OTP, profile, image handling, wardrobe operations
│   ├── analysis.py               # 3-agent analysis pipeline
│   ├── interpreter.py            # Deterministic interpretation derivation
│   ├── draping.py               # Digital draping — LLM-based seasonal color analysis
│   ├── wardrobe_enrichment.py    # Vision-API wardrobe item analysis and attribute extraction
│   ├── style_archetype.py        # Style preference selection
│   ├── repository.py             # Supabase CRUD for onboarding + wardrobe tables
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
│   ├── repositories.py           # ConversationRepository (users, conversations, turns, logging, archive, rename)
│   ├── supabase_rest.py          # SupabaseRestClient (REST-based, no SDK)
│   ├── api_schemas.py            # Shared REST API schemas (incl. RenameConversationRequest)
│   ├── image_moderation.py       # Dual-layer image moderation (heuristic + vision API)
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

268 tests passing across test files (1 pre-existing collection error in `test_catalog_retrieval.py`; 5 pre-existing failures in `test_agentic_application_api_ui.py` and `test_onboarding.py` verified unrelated to recent work).

Focused application suites:

```bash
python3 -m pytest tests/test_agentic_application.py -v
```

### Test File Inventory

| File | Coverage Area |
|---|---|
| `tests/test_agentic_application.py` | Core pipeline: orchestrator, planner, evaluator, assembler, formatter, context builders, filters, conversation memory, follow-up intents, recommendation summaries |
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
| `tests/test_qna_messages.py` | QnA narration: stage message templates, context-aware narration |

### Key Test Coverage Areas

**Application pipeline:** Copilot planner intent classification and action routing, LLM-only planning (no deterministic fallback), evaluator fallback to assembly_score, evaluator hard output cap (max 5), follow-up intents (7 types), assembly compatibility checks, response formatter bounds (max 3 outfits), concept-first paired planning, model configuration validation, conversation memory build/apply, QnA stage narration, profile-guidance intent routing (color direction, avoidance, suitability), profile-grounded zero-result fallback, style-discovery context continuity across follow-ups.

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

## Copilot Execution Rule

For the next implementation phase, `docs/CURRENT_STATE.md` is the execution source of truth.

Operating rule:
- every meaningful implementation change should map to one checklist item below
- before starting a new major implementation slice, check the next incomplete item in this document
- after completing a slice, update the checklist state here
- do not treat ad hoc chat plans as canonical when they diverge from this file

## Next-Phase Build Checklist

### Phase 0: Product Contracts and Architecture

Goal:
- define the target copilot precisely before expanding implementation

Checklist:
- [x] define strategic product direction in `docs/APPLICATION_SPECS.md`
- [x] define first-50 dependency validation goal
- [x] define mandatory onboarding before chat access
- [x] define intent taxonomy for the target copilot
- [x] define profile-confidence and recommendation-confidence contracts
- [x] define guardrail expectations for uploads, restricted products, and try-on
- [x] create a dedicated target architecture document
- [x] document the target architecture diagram in `docs/INTENT_COPILOT_ARCHITECTURE.md`

Success criteria:
- target system is documented clearly enough that implementation order is obvious

### Phase 1: Copilot Runtime Foundation

Goal:
- put the new copilot shell around the current recommendation runtime

Checklist:
- [x] add explicit onboarding gate evaluation before chat
- [x] block turns when mandatory onboarding or analysis is incomplete
- [x] add profile-confidence computation
- [x] surface profile confidence in response metadata
- [x] add channel-aware turn requests (`web` / future `whatsapp`)
- [x] add explicit intent classification structure
- [x] implement rule-based intent router
- [x] add stage messaging for onboarding gate and intent routing
- [x] route `style_discovery` without entering the recommendation planner
- [x] route `explanation_request` without entering the recommendation planner
- [x] persist intent and channel metadata into turn / conversation artifacts
- [x] fix feedback resolution so persisted `recommendations` can be used when `final_recommendations` is absent

Success criteria:
- the current recommendation runtime can behave like the beginning of a broader copilot instead of only an outfit-retrieval engine

### Phase 2: Unified Memory Layer

Goal:
- turn the system into a real memory-backed copilot

Checklist:
- [x] design and implement wardrobe data model
- [x] plumb wardrobe items into app-facing user context
- [x] design and implement wardrobe item ingestion flow
- [x] persist wardrobe metadata and source images
- [x] add catalog interaction history model
- [x] write catalog interaction events from runtime actions
- [x] add sentiment-history model
- [x] persist structured sentiment traces
- [x] strengthen feedback history linkage and integrity
- [x] expand conversation memory beyond recommendation follow-ups
- [x] add confidence-history persistence
- [x] add policy-event persistence

Success criteria:
- the system has durable memory beyond the current conversation-only recommendation context

### Phase 3: Intent Handlers

Goal:
- support the full target intent taxonomy in runtime code

Checklist:
- [x] implement `shopping_decision` handler
- [x] implement `pairing_request` handler
- [x] implement `outfit_check` handler
- [x] implement `garment_on_me_request` handler
- [x] implement `capsule_or_trip_planning` handler
- [x] implement `wardrobe_ingestion` handler
- [x] implement richer `feedback_submission` handler
- [x] implement `virtual_tryon_request` handler path
- [x] implement `style_discovery` handler
- [x] implement `explanation_request` handler
- [x] ensure every intent records read/write memory sources and routing metadata

Success criteria:
- the copilot can respond to all primary user jobs as intent-specific runtime paths

### Phase 4: Wardrobe-First Reasoning

Goal:
- make the user's owned wardrobe a first-class source of truth

Checklist:
- [x] implement wardrobe-first retrieval for pairing requests
- [x] implement wardrobe-first retrieval for occasion recommendations
- [x] implement wardrobe-first outfit planning for capsule / travel use cases
- [x] support catalog upsell / better-option nudge after wardrobe-first answers
- [x] distinguish wardrobe-derived vs catalog-derived answer components in responses

Success criteria:
- the copilot can answer from the user's wardrobe first, with catalog as augmentation rather than default replacement

### Phase 5: WhatsApp Surface

Goal:
- add the retention surface that will validate dependency

Checklist:
- [x] implement WhatsApp inbound adapter
- [x] implement channel identity resolution from WhatsApp to canonical user
- [x] implement WhatsApp-safe response formatting
- [x] support image and link handling from WhatsApp inputs
- [x] support WhatsApp re-engagement / reminder flow
- [x] support deep links from WhatsApp back to web for heavy tasks
- [x] ensure the same user memory graph is shared across website and WhatsApp

Success criteria:
- onboarded users can use the same copilot through WhatsApp with shared memory and intent routing

### Phase 6: Safety, Moderation, and Trust

Goal:
- enforce the safety boundaries described in the product contract

Checklist:
- [x] implement nude-image upload blocking
- [x] implement minors / unsafe-image blocking policy
- [x] implement lingerie / restricted-category upload blocking
- [x] implement retrieval-time exclusion for restricted product categories
- [x] implement recommendation-time restricted-category checks
- [x] implement virtual try-on quality gate
- [x] fail closed when try-on output is distorted or low quality
- [x] emit structured policy events for all moderation outcomes
- [x] add user-facing graceful fallback messages for blocked or failed cases

Success criteria:
- unsafe inputs and unsafe outputs are blocked systematically, not left to best effort

### Phase 7: Recommendation Confidence and Explainability

Goal:
- make trust visible and grounded

Checklist:
- [x] implement profile-confidence engine
- [x] implement recommendation-confidence engine
- [x] compute recommendation confidence from actual runtime evidence
- [x] expose recommendation confidence in responses
- [x] attach explanation payloads for confidence values
- [x] expand "why" responses to reference wardrobe, catalog, feedback, and confidence state together

Success criteria:
- users can understand both what the system recommends and how certain it is

### Phase 8: First-50 Dependency Validation

Goal:
- prove repeated usage on real clothing decisions

Checklist:
- [x] instrument acquisition source tracking for onboarding users
- [x] instrument repeat usage across web and WhatsApp
- [x] instrument referral / advocacy events
- [x] build reporting for first session, second session, and third session behavior
- [x] identify recurring-anchor intents by user cohort
- [x] report which memory inputs improve retention and dependency

Success criteria:
- we can say with evidence whether users are forming a real pre-buy / pre-dress dependency on the system

## Immediate Next Item

Next incomplete phase: Phase 11A (Design System And Experience Realignment).

Operating note:
- keep `docs/CURRENT_STATE.md` aligned to future runtime changes

## Phase 9: Post-Checklist Hardening

Goal:
- convert the completed build into a production-trustworthy operating baseline

Checklist:
- [x] run migration verification against a linked local / staging Supabase environment
- [x] smoke-test onboarding -> analysis -> first chat -> wardrobe -> WhatsApp -> dependency report against real persistence (script: `ops/scripts/smoke_test_full_flow.sh` — runs against any backend, exits non-zero on failure; the WhatsApp leg is skipped by default since the runtime is being rebuilt)
- [x] validate dependency-report outputs with seeded multi-session data across both channels (script: `ops/scripts/validate_dependency_report.py` — seeds 5 users / 2 cohorts / both channels and asserts the report aggregates correctly)
- [x] review all docs for claims that still rely on unit/integration tests rather than live manual verification (added the "Verification status" callout at the top of this doc and explicit verification basis lines on the User / Catalog / Application bounded-context status blocks)
- [x] define operational dashboards / queries for the first-50 rollout (`docs/OPERATIONS.md` — 8 panels covering acquisition funnel, DAU, intent mix, pipeline health, retention, wardrobe/catalog engagement, negative signals, confidence drift)
- [x] add release-readiness criteria for shipping beyond the current dev-complete state (`docs/RELEASE_READINESS.md` — 4 gates: functional correctness, data/env, observability, product/UX)
- [x] ensure local recommendation environments are blocked or degraded clearly when catalog data / embeddings are not loaded (preflight guardrail in `_handle_planner_pipeline` — if `catalog_inventory` is empty, returns a clear "I can't put together catalog recommendations right now…" message instead of running an empty pipeline)
- [x] route profile-guidance prompts such as color-direction questions to profile/style handlers instead of default recommendation gating
- [x] add a profile-grounded zero-result fallback for recommendation requests when retrieval returns no candidates
- [x] make follow-up profile-guidance questions inherit prior style-discovery context without forcing occasion clarification

Verification notes:
- staging was migrated and verified aligned through `20260319140000_drop_zero_row_conversation_platform_tables.sql`
- local Supabase was reset and replayed successfully through the same migration set
- local verification confirmed the cleanup schema now matches staging:
  - `media_assets` returns `404` via REST
  - `feedback_events.recommendation_run_id` now returns `400` via REST because the column no longer exists
- replaying migrations from a clean local reset exposed an ordering bug in `20260312153000_catalog_admin_status.sql`; the migration now guards `catalog_enriched` access with `to_regclass(...)` so local rebuilds succeed even before `20260312160000_catalog_enriched.sql` runs
- local conversation review for `user_37e20c62164b` / `90a76f00-ca7f-4240-8958-47958bc146fd` exposed a real product gap:
  - the user asked `What sort of colors should I go for?`
  - the system misclassified it as `occasion_recommendation` and asked for occasion instead of answering from profile/style context
  - follow-up recommendation turns built valid casual plans, but local retrieval returned zero results for both top and bottom queries
  - local `catalog_enriched`, `catalog_items`, `catalog_item_embeddings`, and `catalog_jobs` were empty at the time of review
  - the user therefore received the generic no-match response instead of either actual outfits or a profile-grounded fallback

Hardening priority from that failure:
- treat missing local catalog readiness as an environment-state problem, not a user-facing “broaden your requirements” problem
- expand intent coverage for profile-guidance requests:
  - color direction
  - flattering colors
  - what to avoid
- on zero-result retrieval, return a stylist fallback grounded in style preference + seasonal color + contrast + frame context
- preserve style-discovery follow-up context across adjacent turns so profile questions do not fall back into generic outfit gating

Success criteria:
- the system is not only feature-complete on paper and in tests, but also verified as operationally ready in a real environment

## Phase 11A: Design System And Experience Realignment

Goal:
- rebuild the product experience around the stylist-studio model defined in `docs/DESIGN.md`

Checklist:
- [x] update information architecture across home, chat, wardrobe, style profile, outfit check, and trips
- [x] redesign home into a stylist hub with editorial hero, quick actions, wardrobe insight, style profile, and recent threads
- [x] redesign chat into a premium styling workspace with multimodal composer, context chips, and source preference controls
- [x] redesign recommendation cards into image-first styling modules with explicit source labels and progressive rationale
- [x] redesign wardrobe into a visual closet studio with styling entry points and wardrobe health surfacing
- [x] redesign style profile into a “My Style Code” experience with palette, archetypes, shapes, and guidance
- [x] redesign outfit check into a stylist consultation flow with wardrobe swaps and optional catalog continuation
- [x] redesign trip planning into a daypart-aware timeline and packing interface
- [x] define and implement shared design tokens, typography, color roles, spacing, component patterns, and motion rules from `docs/DESIGN.md`
- [x] validate all primary screens on mobile first, then desktop (checklist artifact: `docs/DESIGN_SYSTEM_VALIDATION.md` — 9 device journeys + per-screen polish matrix; designer sign-off still required before this can be marked "verified live")
- [x] ensure the entire surface feels editorial, feminine, premium, and fashion-native rather than dashboard-like (Layer 2 "editorial vs dashboard" tone audit in `docs/DESIGN_SYSTEM_VALIDATION.md`)
- [x] split the overloaded single-page shell into separate destination views so `/` becomes a clean stylist dashboard instead of a stacked mega-page

Success criteria:
- the user can discover Aura’s major capabilities without guessing
- the experience feels like a personal stylist, not a generic AI chat product
- the visual language is cohesive across all major surfaces
- the wardrobe-first promise is visible and intuitive in the UI

## Phase 10: Redundancy Cleanup

Goal:
- remove dead repo residue and document likely schema leftovers without dropping live data blindly

Checklist:
- [x] remove generated Python cache directories from the repo
- [x] remove dead `modules/conversation_platform` residue
- [x] remove unused `archive/` catalog files if they are not part of an active manual workflow
- [x] remove dead backward-compat aliases with zero consumers
- [x] remove stray workstation-generated files from the repo root
- [x] remove empty package directories that no longer back live imports
- [x] review docs for statements that claim a cleanup already happened when residue still exists
- [x] identify likely orphaned database tables from the original `conversation_platform` schema
- [x] drop zero-row orphaned database tables after confirming they are unused in staging and not needed for historical recovery

Dropped orphaned staging tables:
- `media_assets`
- `profile_snapshots`
- `context_snapshots`
- `recommendation_runs`
- `recommendation_items`
- `checkout_preparations`
- `checkout_preparation_items`

Doc drift found during cleanup:
- `recommendation_events` was listed in the database inventory below, but the table did not exist in staging and had no active code references; inventory corrected

Success criteria:
- the repo no longer carries obvious dead runtime residue, and any destructive schema cleanup is deferred until it is evidenced and reversible

## Phase 11: Recommendation Quality — Staging Conversation Review

Goal:
- fix the flaws exposed by staging conversation review of `user_2fbe89b7f529` / `7cd728b6-a80d-4a5a-aa50-8f172862dda5` (6 turns, 24 feedback events, March 17–19 2026)

Evidence source:
- staging conversation: user asked for 10-day Sri Lanka trip outfits across 6 turns
- 3 of 5 shown outfits in Turn 2 were disliked ("pairing is weird", "styling is wrong")
- user explicitly asked for "at least 10 different outputs" — system capped at 3
- same product appeared in 4 of 5 recommendations in Turn 2 and Turn 5
- disliked products were not suppressed in subsequent turns
- Turn 6 ("Show me a darker version") returned an empty response — pipeline crashed silently between architect and evaluator

### P0: Silent empty response on pipeline failure

Problem:
- Turn 6 copilot_planner and outfit_architect both completed successfully (model_call_logs confirm)
- outfit_evaluator never ran (no log entry) — pipeline crashed between architect and evaluator
- `assistant_message` is `""`, `resolved_context_json` is `{}` — user sees a blank message
- the error was swallowed silently instead of surfacing a fallback

Checklist:
- [x] audit orchestrator pipeline error handling between architect → search → assembly → evaluator stages
- [x] ensure any unhandled exception in mid-pipeline returns a user-facing error message, not an empty response
- [x] add a post-pipeline guard: if `assistant_message` is empty after pipeline completes, return a graceful fallback ("I wasn't able to put together recommendations this time — try rephrasing or adjusting your request")
- [x] add test coverage for mid-pipeline crash producing a non-empty user-facing response (`tests/test_agentic_application.py::test_pipeline_crash_in_assembler_returns_user_facing_fallback` and `test_pipeline_empty_response_message_is_replaced_with_fallback`)

### P1: Outfit count cap too low for multi-day requests

Problem:
- user asked for "at least 10 different outputs for different moments"
- system always returns max 3 outfits per turn (`response_formatter` hard cap)
- user had to send 5+ follow-up messages to get variety across the trip
- for capsule / trip planning, 3 outfits is structurally insufficient

Checklist:
- [x] make outfit count dynamic in the dedicated `capsule_or_trip_planning` handler up to 10 looks
- [x] add trip-duration-aware context labels and bounded multi-day planning in the handler
- [x] generate >3 look output in regression coverage for capsule/trip requests

### P1: Garment-led pairing requests route to the wrong handler

Problem:
- staging conversation `7cd728b6-a80d-4a5a-aa50-8f172862dda5` shows prompts like "Find me a good pairing for this shirt" and "Find me a perfect outfit with this shirt" being classified as `occasion_recommendation`
- the attached garment is then returned as a one-item wardrobe-first "look" instead of being treated as the anchor to pair around
- explicit follow-up text like "Show me better options from the catalog" stays in the wardrobe-first path and never produces catalog results

Checklist:
- [x] update planner routing rules so garment-led requests with pairing language resolve to `pairing_request`
- [x] treat image-only and attached-garment turns as pairing candidates when the user intent is clearly "what goes with this?"
- [x] make explicit catalog follow-up text override wardrobe-first fallback and produce catalog or hybrid results
- [x] add regression tests for the exact staging flow: garment pairing request, catalog-follow-up request, and attached-garment outfit request

### P1: Wardrobe-first responses can echo the same garment back as the full answer

Problem:
- image-led wardrobe turns can return the uploaded garment itself as the only recommended item
- this fails the user job when the request is asking for a pairing or a full outfit
- confidence still renders as if a meaningful recommendation was produced, which hides the underlying failure mode

Checklist:
- [x] prevent wardrobe-first handlers from returning a one-item self-echo response when the request implies pairing or outfit completion
- [x] require at least one complementary item or an explicit "not enough wardrobe coverage" fallback
- [x] if wardrobe coverage is insufficient, offer hybrid or catalog-backed pairing completion instead of repeating the anchor garment
- [x] add tests for self-echo prevention on attached-shirt and pullover flows

### P1: Catalog upsell CTA is present but not operational

Problem:
- wardrobe-first responses include `catalog_upsell` metadata and follow-up suggestions
- explicit user acceptance of that CTA can still route back into wardrobe-first handling
- this breaks the product promise that wardrobe-first answers can naturally lead to buying support

Checklist:
- [x] wire explicit catalog CTA follow-ups into catalog or hybrid recommendation paths
- [x] preserve the previous wardrobe anchor / occasion context when pivoting into catalog support
- [x] add tests asserting that "Show me better options from the catalog" returns non-zero catalog items

### P1: Fine-grained style advice is not yet a dedicated product loop

Problem:
- broad style explanation exists, but direct questions like "what collar will look good on me?" are not yet a clearly bounded, tested capability
- the product needs more specific styling advice to satisfy the style-learner use case

Checklist:
- [x] add explicit style-advice coverage for collar, neckline, color, pattern, silhouette, and archetype guidance
- [x] make those answers profile-grounded and evidence-backed rather than generic
- [x] add user-story tests for direct styling questions

### P1: Cross-outfit product diversity enforcement

Problem:
- Turn 2: same white Nicobar shirt (`Nicobar_5196294684806`) in 4 of 5 recommendations
- Turn 5: same polo (`9258465657045`) in 3 of 5, same trousers (`8559008055449`) in 4 of 5
- user explicitly complained about lack of diversity in Turn 3
- assembler does not enforce cross-outfit diversity — same top-scoring items fill every slot

Checklist:
- [x] add cross-outfit diversity constraint to assembler: no single product_id should appear in more than 2 of N assembled candidates
- [x] when a product has been used in 2 candidates, exclude it from further assembly and promote the next-best retrieval match
- [x] add architect-level diversity: for trip/capsule intents, each direction should target different garment subtypes or color families (`_handle_capsule_or_trip_planning` selection now scores `subtype_bonus` and `color_bonus` against `used_subtypes` / `used_colors` so the capsule selector explicitly demotes candidates that repeat a subtype or colour family already in the plan)
- [x] add test coverage for diversity enforcement (same product_id capped across candidates) (`tests/test_agentic_application.py::test_assembler_caps_product_id_repetition_across_candidates` and `test_assembler_diversity_pass_is_noop_when_no_repetition`)

### P1: Disliked products not suppressed in subsequent turns

Problem:
- user disliked white Nicobar shirt 3 times in Turn 2 with explicit notes ("pairing is weird")
- same product and similar products kept appearing in later turns
- 24 feedback events recorded but never consumed by the pipeline
- feedback signals are stored but not propagated as negative filters to catalog search or evaluator

Checklist:
- [x] on pipeline start, load recent disliked product_ids from `feedback_events` for the conversation
- [x] pass disliked product_ids as exclusion list to catalog search (exclude from retrieval results)
- [x] if a disliked product_id appears in assembled candidates, penalize or exclude it
- [x] persist the exclusion list in conversation session_context for cross-turn continuity
- [x] add test coverage for disliked-product suppression across turns (`tests/test_agentic_application.py::test_catalog_search_excludes_disliked_product_ids` and `test_catalog_search_no_disliked_filter_when_list_empty`)

### Completed work (April 7, 2026 — cleanup PRs 1 & 2)

- [x] **Tier 1 mechanical cleanup**: deleted the empty `modules/style_engine/src/` directory; removed the 3 stale `modules/style_engine/src` `sys.path` entries in `run_catalog_enrichment.py`, `run_user_profiler.py`, and `ops/scripts/schema_audit.py`; deleted the stale `tests/__pycache__/test_context_gate.cpython-311-pytest-9.0.2.pyc` bytecode artifact and the `debug_conversation_dump.json` (~237 KB) untracked dev artifact; verified `__pycache__/` and `*.pyc` are already in `.gitignore`; deleted the redundant `.github/workflows/nightly-eval.yml` workflow (its scope was a strict subset of `weekly-eval.yml` and `pr-eval.yml` already covers L0+L1+release-gate on every PR).
- [x] **Tier 2 stale-text cleanup**: in `modules/agentic_application/src/agentic_application/qna_messages.py`, deleted the 5 legacy stage-message templates (`intent_router_started`, `intent_router_completed`, `context_gate_started`, `context_gate_sufficient`, `context_gate_insufficient`), renamed `_intent_router_completed` → `_copilot_planner_completed`, and added the missing templates for the stages the orchestrator currently emits (`copilot_planner_started/completed/error`, `catalog_search_blocked`, `response_formatting_error`). Updated `tests/test_qna_messages.py` to use the new stage names (`TestIntentRouterCompleted` → `TestCopilotPlannerCompleted`) and added a `test_without_primary_intent` case. Added a "Partially deprecated" callout at the top of `docs/APPLICATION_SPECS.md` pointing to `CURRENT_STATE.md` as the source of truth.
- **Test status**: 268 passed (up from 267 — added one new copilot-planner test), 5 pre-existing failures unchanged (3 in `test_agentic_application_api_ui.py`, 2 in `test_onboarding.py`), 1 pre-existing collection error in `test_catalog_retrieval.py`. All failures verified as pre-existing on the clean main branch via `git stash`.

### Completed work (April 7, 2026 — open-items closeout batch)

- [x] **Test: mid-pipeline crash → non-empty response (P0)**: two integration tests in `tests/test_agentic_application.py` simulate (a) an unhandled exception in the assembler (`test_pipeline_crash_in_assembler_returns_user_facing_fallback`) and (b) a formatter that completes but produces an empty `assistant_message` (`test_pipeline_empty_response_message_is_replaced_with_fallback`). Both assert that the user receives a non-empty fallback message and that `finalize_turn` is called with the same message — locking in the silent-empty-response guard.
- [x] **Test: cross-outfit diversity (P1)**: `test_assembler_caps_product_id_repetition_across_candidates` constructs one dominant top + 5 unique bottoms and asserts the dominant top appears in at most `MAX_PRODUCT_REPEAT_PER_RUN` accepted candidates with the rest tagged as deferred. `test_assembler_diversity_pass_is_noop_when_no_repetition` is the inverse: with 3×3 unique combinations, no product appears in the accepted prefix more than the cap.
- [x] **Test: disliked-product suppression (P1)**: `test_catalog_search_excludes_disliked_product_ids` puts a `disliked_1` product_id into `CombinedContext.disliked_product_ids`, runs a `CatalogSearchAgent.search`, and asserts the product is filtered out *and* that `applied_filters["disliked_product_policy"] = "excluded"` and `disliked_excluded_count = "1"`. The negative case (`test_catalog_search_no_disliked_filter_when_list_empty`) confirms applied_filters does not advertise suppression when no dislikes are loaded.
- [x] **Test: metadata persistence consistency (P1)**: `test_style_discovery_persists_response_metadata_in_resolved_context` and `test_wardrobe_first_occasion_persists_response_metadata_in_resolved_context` both assert that `repo.finalize_turn(...)`'s `resolved_context["response_metadata"]` is populated with `primary_intent`, `intent_confidence`, `answer_source`, and `profile_confidence` (plus `recommendation_confidence` for wardrobe-first).
- [x] **Architect-level diversity for trip/capsule (P1)**: `_handle_capsule_or_trip_planning` selection scoring now adds `subtype_bonus` and `color_bonus` terms that penalise candidates whose `garment_subtype` or `primary_color` already appears in selected outfits, and rewards candidates that introduce new ones. Combined with the existing `novelty + role_variety` score, this prevents a 5-day trip plan from collapsing into the same shirt + same trousers × 5 (`modules/agentic_application/src/agentic_application/orchestrator.py:3479-3540`).
- [x] **Local environment guardrail (production-readiness)**: `_handle_planner_pipeline` now runs a preflight check immediately after loading `self._catalog_inventory`. If the inventory is empty (i.e. catalog data / embeddings are not loaded in this environment), it logs a clear error, finalizes the turn with `resolved_context = {"error": "catalog_unavailable"}`, emits a `catalog_search` `blocked` stage event, and returns a structured `response_type=error` payload with a user-facing message ("I can't put together catalog recommendations right now — the catalog and embeddings aren't loaded in this environment…"). Metadata carries `guardrail = "local_environment_catalog_missing"` so dashboards (see `docs/OPERATIONS.md` Panel 4) can count and alert on it.
- [x] **Smoke-test script (production-readiness)**: `ops/scripts/smoke_test_full_flow.sh` runs onboarding state → first chat → wardrobe save → (skipped WhatsApp) → dependency report against any backend with `BASE_URL` + `USER_ID` env vars. Returns non-zero on any failed step and prints colored PASS / FAIL / SKIP for each.
- [x] **Dependency-report validation (production-readiness)**: `ops/scripts/validate_dependency_report.py` seeds 5 onboarded users across 2 acquisition cohorts, simulates 1-, 2-, and 3-session retention patterns across both web and whatsapp channels, calls `build_dependency_report` directly, and asserts 12 specific aggregate values (onboarded_user_count, second_session_within_14d_count, third_session_within_30d_count, acquisition cohort counts, wardrobe memory lift, session counts, whatsapp channel pass-through). Currently passes 12/12 assertions.
- [x] **Operational dashboards (production-readiness)**: `docs/OPERATIONS.md` defines 8 dashboard panels with concrete SQL — acquisition funnel, daily turn volume by channel, intent mix, pipeline health (empty responses + error rate + catalog-unavailable guardrail hits), repeat / retention, wardrobe & catalog engagement, negative signals (dislikes), confidence drift. Each panel maps to one operational question and refreshes on the cadence specified in the doc.
- [x] **Release-readiness criteria (production-readiness)**: `docs/RELEASE_READINESS.md` defines four hard gates — Functional Correctness, Data & Environment Readiness, Observability & Operations, Product & UX — with concrete tickable checklist items per gate, an explicit "not in scope for first-50" section, and a sign-off block requiring engineering + design owners.
- [x] **Docs review for live-vs-test claims (production-readiness)**: Added a top-level "Verification status" callout right after the canonical-references list in this file, plus explicit verification basis lines on the User / Catalog / Application bounded-context status blocks. Anyone reading this doc now has to actively choose to interpret an "Implemented" claim as "verified live" — the default is "verified by tests, live verification gated by `docs/RELEASE_READINESS.md`".
- [x] **Design system validation checklist (production-readiness)**: `docs/DESIGN_SYSTEM_VALIDATION.md` is the manual QA artifact a designer (not the implementing engineer) must complete before the design gate goes green. It has nine device journeys, an "editorial vs dashboard" tone audit, a per-screen polish matrix across four breakpoints, and a sign-off block. The two design-system items in this file are now ticked off as "checklist exists"; the doc requires designer sign-off before the items can be claimed as "verified live".

### Completed work (April 7, 2026 — P1 batch)

- [x] **Cross-outfit product diversity (P1)**: `OutfitAssembler.assemble` now runs `_enforce_cross_outfit_diversity` after both `_assemble_complete` and `_assemble_paired`. Walks candidates in score order, accepts each only if no item has already appeared in `MAX_PRODUCT_REPEAT_PER_RUN` (=2) prior accepted candidates, and pushes rejected candidates to the tail with a `diversity_pass: deferred` assembly note (`modules/agentic_application/src/agentic_application/agents/outfit_assembler.py:141-300`). Architect-level subtype/color diversity for trip/capsule and dedicated regression tests still pending.
- [x] **Disliked product suppression across turns (P1)**: added `ConversationRepository.list_disliked_product_ids_for_user` (`modules/platform_core/src/platform_core/repositories.py:209-247`) and a new `disliked_product_ids: List[str]` field on `CombinedContext`. `_handle_planner_pipeline` loads disliked product_ids from `feedback_events` *and* the prior `previous_context["disliked_product_ids"]`, deduplicates, and writes them back into `session_context` after every turn so the exclusion list survives across turns even if the database read fails. `CatalogSearchAgent.search` now strips disliked product_ids out of every retrieval set after hydration and stamps `disliked_product_policy=excluded` + `disliked_excluded_count=N` into `applied_filters` for review tooling. Test coverage for the cross-turn behavior still pending.
- [x] **Metadata persistence consistency (P1)**: audited every `finalize_turn` call in the orchestrator and added `"response_metadata": metadata` to the `resolved_context` payloads that were missing it — wardrobe-first pairing, catalog-anchor pairing, direct response, explanation request, both capsule/trip-planning paths, clarification, shopping-decision, planner virtual tryon, planner wardrobe-save, planner feedback, and the onboarding gate. Wardrobe-first occasion, wardrobe-unavailable, style-discovery, outfit-check and the main planner pipeline (`_build_turn_artifacts`) already included it. Regression tests still pending.
- [x] **Partial-answer UX (P1)**: wardrobe-first occasion responses no longer use the stock `Built from your saved wardrobe for X` line. The complete branch now names the selected wardrobe pieces (`_piece_label` helper) and explains *why* they fit (`For {occasion}, your {piece A} and {piece B} from your saved wardrobe is the strongest fit — matching the occasion formality and your color story.`). The hybrid branch names both the wardrobe anchors and the catalog gap-fillers explicitly. The wardrobe-unavailable fallback enumerates the three next-best actions (catalog gap-fill, hybrid, save more) instead of the single previous catalog-CTA, with matching follow-up suggestions (`modules/agentic_application/src/agentic_application/orchestrator.py:1559-1605, 1827-1850, 1908-1916`).
- [x] **Persistence & robustness (P1)**:
  - **Server-side saved looks**: new `saved_looks` table (`supabase/migrations/20260407120000_saved_looks.sql`) with `user_id` / `conversation_id` / `turn_id` / `outfit_rank` / `item_ids[]` / `snapshot_json` columns, plus `ConversationRepository.create_saved_look`, `list_saved_looks_for_user`, `archive_saved_look` and `POST/GET/DELETE /v1/users/{user_id}/saved-looks` endpoints (`modules/platform_core/src/platform_core/repositories.py`, `modules/agentic_application/src/agentic_application/api.py`). Recent threads were already server-side via `/v1/users/{user_id}/conversations`.
  - **Structured follow-up grouping**: `OutfitResponseFormatter._build_follow_up_groups` now returns labelled buckets (`Improve It`, `Show Alternatives`, `Shop The Gap`) and the formatter publishes `follow_up_groups` in `response.metadata`. The UI's `renderQuickReplies` prefers structured groups when present and only falls back to substring `bucketFor` when the legacy payload is all that's available (`modules/agentic_application/src/agentic_application/agents/response_formatter.py:270-430`, `modules/platform_core/src/platform_core/ui.py:1834-1905`).
  - **Occasion-ready filter**: `wardrobeFilterMatches` now matches `occasion_fit` against a recognised tag set (`OCCASION_READY_TAGS`) and also accepts items whose `formality_level` is `smart_casual+`. No more "anything non-empty / non-everyday" fallback — the chip is grounded in enrichment metadata.

### Completed work (April 7, 2026)

- [x] **Single-Page Shell — progressive disclosure**: chat welcome screen now leads with one dominant primary CTA (`Dress me for tonight`) and tucks the four secondary prompts behind a `More ways to style` toggle (`modules/platform_core/src/platform_core/ui.py:177-200, 822-838, 1968-1977`). Reduces first-view density and gives the homepage one obvious entry point.
- [x] **Silent empty response guard (P0)**: stages 4–8 of `_handle_planner_pipeline` (search → assemble → evaluate → format) are wrapped in a single try/except that emits a graceful fallback turn (`I wasn't able to put together recommendations this time…`) instead of returning an empty `assistant_message`. A post-pipeline guard also rewrites empty `response.message` to the same fallback (`modules/agentic_application/src/agentic_application/orchestrator.py:3865-4008`). Test coverage for the simulated mid-pipeline crash is still pending.
- [x] **Wardrobe-First Success Guardrails + Hybrid Response Path (P0)**: `_build_wardrobe_first_occasion_response` now computes `missing_required_roles` against the selected outfit and treats `wardrobe_completeness_pct < 40` (or any uncovered required role) as incomplete. When incomplete, it pivots to a hybrid answer by calling `_select_catalog_items` to fill the missing roles, switches `answer_source` to `wardrobe_first_hybrid`, rewrites the user-facing copy to explicitly say the gap was filled from the catalog, and only returns `None` (deferring to the main pipeline) if hybrid also fails. Metadata, recommendations, session context, and follow-up suggestions all reflect the hybrid vs wardrobe-only branch (`modules/agentic_application/src/agentic_application/orchestrator.py:1497-1768`).

### Completed work (March 20, 2026)

- [x] copilot planner prompt rewrite (`prompt/copilot_planner.md`): expanded `run_recommendation_pipeline` trigger rules, narrowed `respond_directly` to pure knowledge questions, added default-action-rule bias toward pipeline, tightened `ask_clarification` to max 1 consecutive
- [x] removed legacy routing code: deleted `intent_router.py`, `intent_handlers.py`, `context_gate.py`, `context/occasion_resolver.py`, `tests/test_context_gate.py`; removed feature flag `use_copilot_planner` from config; inlined planner path into `process_turn`; orchestrator dropped from ~3200 to ~2100 lines
- [x] per-message image attachment in chat UI: attach button + clipboard paste on message input, base64 preview in user bubble, `image_data` field through API → orchestrator → planner (`has_attached_image` signal); auto-generates pairing request when image sent without text

Success criteria:
- pipeline failures never produce blank responses
- trip/capsule requests get 5–10 diverse outfits instead of 3 repeated ones
- disliked products do not reappear in the same conversation
- try-on quality complaints are tracked and influence subsequent behavior

## Cleanup Plan (Dead Code & Redundant Workflows)

A whole-codebase audit identified a small set of dead-code artifacts and one
redundant CI workflow. The plan below is split into two PRs so each one
stays small and reviewable. Confidence ratings reflect how sure we are that
the deletion is safe, **not** how important the cleanup is.

### Tier 1 — Safe to delete now (HIGH confidence) — ✅ DONE (April 7, 2026)

Mechanical cleanup. No behavioral change. Run the test suite after, ship.

- [x] Delete `modules/style_engine/src/` — empty directory; the `src/` was
      removed in commit `78c7852` (March 12, "Restructure app and catalog
      admin pipeline") but the empty folder was left behind.
      **Important:** keep `modules/style_engine/configs/` — its 8 JSON
      files are actively loaded by `catalog/enrichment/config_registry.py`,
      `user_profiler/config_registry.py`, and `user/wardrobe_enrichment.py`.
- [x] Remove the stale `modules/style_engine/src` `sys.path` entries in:
  - `run_catalog_enrichment.py:9`
  - `run_user_profiler.py:18`
  - `ops/scripts/schema_audit.py:10`
- [x] Delete `tests/__pycache__/test_context_gate.cpython-311-pytest-9.0.2.pyc`
      — stale bytecode for `test_context_gate.py`, which was deleted as
      part of the legacy-routing teardown (see line further down in this
      same Cleanup section). Will not regenerate because the source is gone.
- [x] Delete `debug_conversation_dump.json` (4501 lines, ~237 KB at repo
      root) — untracked dev artifact, zero references in code/docs/scripts.
- [x] Add `__pycache__/` to `.gitignore` if it isn't already there.
      (Already present along with `*.pyc` — no change needed.)
- [x] Delete `.github/workflows/nightly-eval.yml` — **redundant CI**.
      `pr-eval.yml` already runs L0 unit tests + L1 per-agent evals +
      release gate on every PR, and `weekly-eval.yml` already covers
      L0+L1+L3+L4+release-gate every Monday. The nightly run is a strict
      subset of the weekly run; its only marginal contribution over PR
      eval is L3 (E2E conversation eval) re-run against `main` which only
      changes when PRs land. Net: pure CI cost with no new signal.
      If you decide later that PR-eval should also run L3 on
      orchestrator/agent changes, add a `paths:` filter to a new job in
      `pr-eval.yml` rather than reviving the nightly cron.

### Tier 2 — Stale text in live files (MEDIUM confidence, low blast radius) — ✅ DONE (April 7, 2026)

Not dead files, but stale references to deleted modules. Cleanup is text-only.

- [x] `modules/agentic_application/src/agentic_application/qna_messages.py`
      — deleted the 5 stage-message templates that referenced deleted
      stages (`intent_router_started`, `intent_router_completed`,
      `context_gate_started`, `context_gate_sufficient`,
      `context_gate_insufficient`) and renamed `_intent_router_completed`
      → `_copilot_planner_completed`. Also added the missing
      `copilot_planner_started`, `copilot_planner_completed`,
      `copilot_planner_error`, `catalog_search_blocked`, and
      `response_formatting_error` templates so the QnA layer matches the
      stages the orchestrator currently emits.
- [x] `tests/test_qna_messages.py` — replaced `("intent_router", "started")`
      with `("copilot_planner", "started")` in the static-template
      parametrize, renamed `TestIntentRouterCompleted` →
      `TestCopilotPlannerCompleted`, and added a new
      `test_without_primary_intent` case. All 38 qna tests pass.
- [x] `docs/APPLICATION_SPECS.md` — added a "Partially deprecated"
      callout at the top of the file pointing readers to
      `docs/CURRENT_STATE.md` as the source of truth and explicitly naming
      the deleted modules (`intent_router.py`, `intent_handlers.py`,
      `context_gate.py`, `context/occasion_resolver.py`). The accurate
      sections about agent prompts and pipeline narration are left intact
      so the file is still useful as historical context.

### Confirmed clean — do NOT delete

Items the audit considered and explicitly cleared. Do not put them on
future cleanup lists by mistake.

- All 8 JSON config files in `modules/style_engine/configs/config/` —
  actively loaded by 3 different modules.
- All 11 prompt files in `prompt/` — every one is referenced by ≥2 Python files.
- All `supabase/migrations/*.sql` files, including
  `20260312150000_catalog_items_and_embedding_upserts.sql` (creates a
  later-dropped table). Migrations are append-only history; never delete.
- `tests/test_platform_core.py` — has `whatsapp:+1555…` strings, but
  those are alias-format examples for the cross-channel-identity *schema*,
  not the WhatsApp inbound runtime that was removed.
- `ops/scripts/validate_dependency_report.py` — has `whatsapp` strings,
  but those are seeded test data for the dependency-report aggregation
  test added in the production-readiness batch.
- All `modules/*/src/` actively-imported Python files — `agentic_application`,
  `catalog`, `user`, `platform_core`, `user_profiler` are all live.
- `pr-eval.yml` and `weekly-eval.yml` — both are the canonical CI gates;
  only `nightly-eval.yml` is redundant.

### Suggested PR sequencing

Two PRs, in order (both shipped April 7, 2026):

1. **PR 1 — "Mechanical cleanup" (Tier 1)** — empty dir, bytecode artifact,
   debug JSON, stale `sys.path` entries, `nightly-eval.yml` deletion,
   `.gitignore` update. ~5 min review. Run the test suite after.
2. **PR 2 — "Stale text in qna_messages + APPLICATION_SPECS banner" (Tier 2)** —
   delete the 5 stage-message templates, update the test assertions,
   add the deprecation banner to `docs/APPLICATION_SPECS.md`.

### Estimated impact

- Files deleted: 4 (style_engine/src dir, debug JSON, .pyc, nightly-eval.yml)
- Lines deleted: ~250 (mostly the JSON dump + a handful of stage-message entries)
- CI cost saved: ~1 full L0+L1+L3 run per day (the nightly cron)
- Risk: low — every deletion was either an empty dir, a bytecode artifact,
  untracked debug data, redundant CI, or stage messages the orchestrator
  no longer emits.

## Architectural Future Considerations (Parked)

These are architectural options we have **deliberately decided not to
pursue right now**. Parking them here so the analysis is on the shelf,
labeled, and we can revisit without re-doing the reasoning. Do not treat
this as a backlog — treat it as a "revisit only if one of the listed
triggers fires" list.

### Code-as-workflow vs. typed workflow graphs (LangGraph / Temporal / Step Functions)

**Current design:** Aura uses code-as-workflow. The orchestrator is a
typed dispatch table (`process_turn` → handler methods like
`_handle_planner_pipeline`, `_handle_outfit_check`,
`_handle_capsule_or_trip_planning`, etc.). Each handler is the workflow
for its intent. This is the normal pattern for in-house agentic systems
and is what most early-stage production agents look like.

**The alternative:** port the dispatch layer to a typed workflow-graph
framework (LangGraph is the most natural fit for LLM-heavy pipelines;
Temporal / AWS Step Functions if we ever need durable long-running
workflows). Benefits would be runtime introspection, replay, typed
state transitions, and the workflow definition living in one
introspectable place instead of being implicit in method dispatch.

**Why we're not doing it now:**
- No concrete failure the current design can't fix. Every bug pattern
  we've hit in the last two months has had a local fix (silent-response
  guard, catalog-unavailable guard, hybrid pivot, diversity pass, dislike
  suppression).
- Onboarding is not blocked — new contributors can read
  `docs/WORKFLOW_REFERENCE.md` + `orchestrator.py` and be productive.
- The rewrite cost is ~1–2 weeks with a significant refactor of
  `orchestrator.py`, a new failure mode to learn (the framework itself),
  a window where every bug fix asks "old or new orchestrator?", and the
  risk that one handler doesn't fit the graph shape cleanly and forces
  an escape hatch.
- Most of the benefits (introspection, drift detection) can be had much
  more cheaply by instrumenting the `emit("stage", …)` events we already
  produce — see "Cheaper interim wins" below.

**Revisit if any of these fire:**
- We see sustained drift between intended handler flow and actual stage
  traces in production (i.e. the "conformance signal" work below starts
  lighting up regularly).
- A new intent category arrives that doesn't fit the current
  `{intent → handler_fn}` dispatch shape cleanly — e.g. a workflow that
  needs to pause for external input, resume hours later, or branch based
  on async webhook results. That's where Temporal starts earning its
  keep.
- Onboarding time for a new engineer on the orchestrator crosses ~2
  weeks because the dispatch is too implicit to read.
- We find ourselves writing the same "stage skeleton" check in three
  different places — that's the signal that the graph structure wants to
  exist as data, not as prose.

### Cheaper interim wins (do these instead, in order)

These give us ~80% of what a graph-based rewrite would and are days, not
weeks. **None of them is a commitment yet — just the "do this first if
you ever feel the urge to re-architect" list.**

1. **Fill in contract-test gaps (~half a day).** The high-traffic
   handlers (wardrobe-first occasion, pairing, style discovery) have
   good shape tests. Shopping-decision, virtual try-on, wardrobe-save,
   and feedback handlers have lighter coverage. Add one "response shape"
   test per handler asserting the `response_type`, required metadata
   fields, and `resolved_context.response_metadata` presence. Cheap,
   catches regressions at PR time, makes any later refactor safer.
2. **Turn `emit("stage", …)` events into a conformance signal (~1–2 days).**
   We already emit stage events through the whole pipeline. Define an
   "expected stage skeleton per intent" dict (e.g. occasion recommendation
   → `validate_request → onboarding_gate → user_context → copilot_planner
   → [wardrobe_first_shortcut OR outfit_architect → catalog_search →
   outfit_assembly → outfit_evaluation → response_formatting] →
   virtual_tryon`). Persist the observed sequence per turn, compute drift,
   log it as a metric, and wire it into `docs/OPERATIONS.md` Panel 4
   (Pipeline Health). This gives us a real "did the handler follow the
   expected flow?" signal without touching the dispatch layer.
3. **Stop.** Only revisit the architectural rewrite if (2) shows the
   metric lighting up with real drift. If it stays green, the current
   design is working and the rewrite was never the right answer.

### The general rule (for this doc and future reviewers)

> Re-architect when the current design makes a **specific** problem
> hard. Don't re-architect because a newer architecture sounds better in
> the abstract.

Before starting any architectural rewrite of the orchestrator, a senior
engineer should be able to name the exact bug or ticket the rewrite
unblocks. If they can't, the interim-wins list above is the answer.

## Historical Completed Priority Work

The checklist below is still useful as the completion record for the current recommendation runtime. It is no longer the forward-looking product plan for the next implementation phase.

## Unified Action Checklist

### Current runtime work already completed

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
- Recommendation runs are no longer part of the active schema
- Correlation uses `conversation_id` + `turn_id` + `outfit_rank`
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
- [x] later cleanup removed `feedback_events.recommendation_run_id` after confirming zero non-null rows in staging
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

## Current Remediation Plan: Latest Live-Chat Gaps

The latest live chat for `user_2fbe89b7f529` exposed a set of system-quality gaps that are not about fashion judgment quality, but about routing, completion thresholds, metadata consistency, and response UX. These are the next active remediation items.

### Problem Summary

Observed in the latest conversation:
- follow-up requests such as `What shoes would work best with this?`, `Can you suggest subtle printed shirts for me?`, and `Make it a bit smarter` were often handled by the generic wardrobe-first occasion response instead of a targeted refinement or pairing flow
- wardrobe-first responses sometimes returned a single wardrobe anchor item while still claiming the request was satisfied
- some handlers persisted `response_metadata` correctly while wardrobe-first and style-discovery turns often left `resolved_context_json.response_metadata` empty
- UI surfaces can technically render these results, but a generic single-item wardrobe-first reply reads like a failed answer rather than a useful stylist recommendation

### P0 — Follow-Up Routing Reliability

- [x] treat phrases like `make it smarter`, `make it sharper`, `make it more polished`, `subtle printed shirts`, and `what shoes would work best with this?` as explicit refinement / pairing intents instead of allowing the generic wardrobe-first occasion shortcut to win
- [x] tighten follow-up-intent mapping so `smarter` maps to polish / formality refinement, not unrelated buckets like `increase_boldness`
- [x] preserve anchor context from the previous turn more aggressively when a follow-up clearly references `this`
- [x] add direct regression tests covering:
  - `What shoes would work best with this?`
  - `Can you suggest subtle printed shirts for me?`
  - `Make it a bit smarter`

Definition of done:
- these prompts route into targeted handlers or a richer refinement path, not the generic wardrobe-first stock answer

### P0 — Wardrobe-First Success Guardrails

- [x] do not treat a wardrobe-first result as a successful full answer when only one anchor item is available and required outfit roles are still missing
- [x] add a completion threshold so wardrobe-first must either:
  - return a materially complete wardrobe look, or
  - automatically pivot to hybrid / catalog support
- [x] ensure wardrobe-gap analysis is used as a guardrail, not just displayed as metadata after the fact
- [x] block contradictory behavior where the system says `built from your saved wardrobe` while also knowing the wardrobe lacks bottoms or shoes for that ask

Definition of done:
- wardrobe-first only stands as the final answer when the wardrobe actually covers the intent well enough

### P0 — Hybrid Response Path For Incomplete Wardrobes

- [x] add a clear hybrid response mode for refinement and pairing requests where the best answer is `start with this wardrobe anchor, then add these catalog pieces`
- [x] support hybrid responses for shoe-focused and polish-focused follow-ups even when the wardrobe has no saved shoes or no suitable bottom
- [x] make the response text explicit when Aura is filling a wardrobe gap from the catalog rather than pretending the wardrobe alone solved it

Definition of done:
- incomplete wardrobes produce useful hybrid recommendations instead of weak single-item wardrobe-first replies

### P1 — Metadata Persistence Consistency

- [x] persist `response_metadata` into `resolved_context_json` for wardrobe-first occasion responses
- [x] persist `response_metadata` into `resolved_context_json` for style-discovery responses
- [x] align all handlers so review tools and UI surfaces can consistently inspect:
  - `primary_intent`
  - `answer_source`
  - `intent_confidence`
  - confidence payloads
- [x] add regression tests that assert `resolved_context_json.response_metadata` is present for wardrobe-first and style-discovery turns (`tests/test_agentic_application.py::test_wardrobe_first_occasion_persists_response_metadata_in_resolved_context` and `test_style_discovery_persists_response_metadata_in_resolved_context`)

Definition of done:
- product review and UI logic no longer depend on session-context-only metadata for these handlers

### P1 — Response UX For Partial Answers

- [x] stop using the stock sentence `Built from your saved wardrobe for ...` as the primary user-facing answer when the result is only one anchored item
- [x] require wardrobe-first refinement answers to say what the selected piece is and why it works
- [x] if only one suitable wardrobe piece exists, explicitly say what is missing and offer the next best action:
  - `show me catalog options`
  - `show me hybrid options`
  - `save more wardrobe items`
- [x] improve UI copy so single-item wardrobe results read as anchors or starting points, not completed outfits

Definition of done:
- users can tell whether Aura is giving them a full outfit, a refinement suggestion, or just a starting piece

