# Product Overview

Last updated: May 3, 2026

> **What is live today vs. aspirational:** This document describes the
> **target** product, including personas and surfaces that are not yet
> built. The currently live surfaces are **web** (onboarding, discovery
> surface with PDP carousels, intent-organized outfit history, wardrobe,
> profile, admin catalog) only. WhatsApp inbound is *not* in
> the live system — the runtime was deliberately removed and is being
> rebuilt as a separate workstream. Treat every mention of WhatsApp
> below as roadmap, not production. For the authoritative "what
> actually works right now" view, see `docs/APPLICATION_SPECS.md` § Live System Reference.

## Purpose

Sigma Aura is a personal fashion copilot.

For a user, it is meant to become a repeat-use assistant for real clothing decisions:
- what should I wear
- what goes with this piece
- should I buy this
- how would this look on me
- how do I plan from what I already own
- what collar, color, pattern, or style direction suits me

The product is not meant to behave like a one-time recommendation demo.
It is meant to behave like a memory-backed style assistant that gets more useful as the user completes onboarding, adds wardrobe items, gives feedback, and returns through chat.

## Product Definition

> A mandatory-onboarding, memory-backed personal fashion copilot that helps the user make better shopping and dressing decisions over time through intent-routed chat.

Core product principles:
- onboarding is required before first chat
- wardrobe is optional to provide, but fully supported by the system
- web handles onboarding and richer tasks
- WhatsApp handles lightweight repeat usage and retention
- every major answer should be explainable
- confidence should be visible
- safety guardrails should fail closed where needed

## User Value

For the user, the product should deliver:
- better shopping decisions before spending money
- better dressing decisions before real occasions
- wardrobe-first help instead of defaulting to new purchases
- more personalized guidance than generic styling content
- explanations grounded in the user's own profile and history
- continuity across web and WhatsApp

## Primary Personas

### 1. Practical Repeat Buyer

Needs:
- quick buy / skip guidance
- pairing suggestions before buying
- low-friction repeat use

Typical prompts:
- "Should I buy this?"
- "What would I wear this with?"
- "Show me a safer option."

### 2. Wardrobe Optimizer

Needs:
- better use of existing clothes
- occasion planning from owned items
- help filling real wardrobe gaps

Typical prompts:
- "What goes with this blazer?"
- "What should I wear tomorrow?"
- "Plan a mini capsule for my trip."
- "Build an outfit around this shirt from my wardrobe."

### 3. Style Learner

Needs:
- to understand what suits them
- transparency into why recommendations fit
- a guided path to better choices over time

Typical prompts:
- "What style suits me?"
- "Why did you recommend this?"
- "What should I avoid?"
- "What collar works best on me?"

### 4. Low-Friction Return User

Needs:
- to come back through WhatsApp without repeating context
- short answers and quick loops
- deep links to web only when necessary

Typical prompts:
- "Office dinner tomorrow"
- "Should I buy this?" + link
- "Save this to my wardrobe"

## User Journey

### Stage 1: Discovery

The user first encounters the website.

Goals:
- understand what the product helps with
- decide whether onboarding is worth the effort
- start onboarding

Expected surface:
- stylist-led landing language
- visible jobs to be done
- immediate clarity that Aura helps with dressing, pairing, checking, learning, and planning

### Stage 2: Onboarding

The user verifies identity by OTP and completes the required pre-chat contract:
- baseline profile
- required images
- style preference selection
- profile analysis

Optional:
- initial wardrobe upload

User outcome:
- the system has enough evidence to personalize future chat

### Stage 3: Processing and Unlock

The system analyzes the user's images and builds derived interpretations.
Chat remains blocked until the required onboarding state is complete.

User outcome:
- the user sees that the system is preparing a profile before giving advice

Unlock requirement:
- once analysis is complete, the user lands in the discovery surface with prompt suggestions rather than an empty input

### Stage 4: First Successful Styling Request

The user asks a first real question on web.

Examples:
- "What should I wear to an office dinner?"
- "What colors should I prioritise?"
- "What style suits me?"

User outcome:
- the product demonstrates profile-aware value quickly

Ideal first-session entry points:
- `Dress Me` for occasion outfits
- `Style This` for pairing
- `Check Me` for outfit critique
- `Know Me` for style advice
- `Trips` for capsule planning

### Stage 5: Memory Growth

The user saves wardrobe items, gives feedback, asks follow-up questions, and starts relying on the system for repeat decisions.

User outcome:
- the system becomes more useful with accumulated memory

### Stage 6: Repeat Usage Through WhatsApp

After onboarding, the user returns through WhatsApp for lightweight day-to-day use.

Examples:
- "Should I buy this?" + product link
- "What goes with this?" + image
- "What should I wear tomorrow?"

User outcome:
- repeat usage becomes habit-like, not novelty-like

### Stage 7: Web Return From WhatsApp

The user returns from WhatsApp through a deep link when the task needs richer visuals or more editing control.

Expected behavior:
- the same task context is visible on web
- the user lands in the relevant section, not a generic home state
- the stylist tone and source clarity remain consistent across channels

## Canonical Journey Loop

The full operating loop should be:

1. discovery on web
2. onboarding and processing
3. first value on web
4. wardrobe growth and saved-look accumulation
5. repeat day-to-day usage in chat and WhatsApp
6. return to web for richer review, wardrobe management, outfit check, or trip planning

This loop is the product’s intended habit system.

## First-Run Experience Contract

Immediately after onboarding and analysis completion, the user should land in:
- the discovery surface with the italic headline and prompt suggestions
- not an empty text field
- not a processing residue state

The first-run page should answer:
- what can Aura do for me right now
- what should I ask first
- what has Aura already learned about me
- how do I use my wardrobe with it

## Ideal First-Session Paths

### Occasion Outfit
- entry: `Dress Me`
- success condition: user receives a source-labeled occasion answer and can refine it quickly

### Pairing
- entry: `Style This` or image upload
- success condition: Aura builds around an anchor piece instead of echoing it

### Outfit Check
- entry: `Check Me` or outfit photo
- success condition: user receives a critique plus wardrobe-first swaps

### Shopping Decision
- entry: pasted product URL
- success condition: user gets buy / skip guidance plus a natural next step

### Style Advice
- entry: `Know Me`
- success condition: user understands one concrete profile-grounded styling principle

### Trip Planning
- entry: `Trips`
- success condition: user gets a duration-aware plan, not a generic short list

## Operating Surfaces

### Website

Responsibilities:
- onboarding and identity verification
- profile completion
- image upload and processing
- wardrobe management
- first successful chat
- richer visual and explanatory experiences

### WhatsApp

Responsibilities:
- repeat usage
- low-friction natural-language entry
- image / link intake
- quick answer loops
- re-engagement
- handoff back to web for heavier tasks

## Main User Stories

### US-01: Mandatory onboarding before chat

As a new user, I want onboarding to happen before chat so the advice is grounded in real evidence instead of generic guesses.

### US-02: Occasion recommendation

As an onboarded user, I want to ask what to wear for an occasion and get a useful answer based on my profile and, when available, my wardrobe first.

Expected behavior:
- wardrobe-first should work when the user wants an outfit from owned items
- catalog-only should work when the user explicitly wants options from the catalog
- the response should make the source mode explicit: wardrobe-first, catalog-only, or hybrid
- when no outfit clears the confidence threshold, the response should be honest about that and offer paths forward (refine the request, see closest matches, shop the catalog) rather than shipping a low-confidence pick

### US-03: Pairing request

As an onboarded user, I want to ask what goes with a piece I own or want to buy.

Expected behavior:
- uploading a wardrobe garment image should let the user ask for the best pairing for an occasion
- uploading a catalog garment image should let the user ask for the best pairing for an occasion
- the product should pair around the garment, not repeat the garment back as the only answer
- the system should distinguish wardrobe-image vs catalog-image anchors automatically or from explicit user phrasing

### US-04: Shopping decision

As an onboarded user, I want buy / skip help before spending money on clothing.

### US-05: Wardrobe ingestion

As an onboarded user, I want to save items into my wardrobe during onboarding or later through chat.

### US-06: Style discovery

As an onboarded user, I want to understand what suits me and why.

Expected behavior:
- the user can ask broad style questions ("what style suits me?")
- the user can ask specific styling questions ("what collar / color / pattern suits me?")

### US-07: Explanation request

As an onboarded user, I want the system to explain recommendations using my actual profile, memory, wardrobe, and confidence state.

### US-08: Virtual try-on

As an onboarded user, I want to request a try-on when it is safe and the output quality passes guardrails.

### US-09: Cross-channel continuity

As a repeat user, I want the same memory and identity to carry from web to WhatsApp.

### US-10: Outfit check with wardrobe follow-up

As an onboarded user, I want to rate or check my current outfit and get suggestions for what would work better from my wardrobe.

Expected behavior:
- the critique should suggest wardrobe swaps first
- catalog follow-up should stay optional, not forced
- a later `Show me options to buy` (catalog upsell CTA) should pivot with the same outfit context

### US-11: Trip / capsule planning

As an onboarded user, I want a trip-duration-aware capsule or outfit list that combines my wardrobe first and catalog gap-fillers when needed.

Expected behavior:
- trip duration should expand the number of looks up to a bounded multi-day plan
- the plan should cover multiple contexts or dayparts, not repeated undifferentiated looks
- catalog-supported hybrid looks should appear when wardrobe depth alone cannot cover the trip

## What Success Looks Like For The User

User success is not:
- receiving one interesting answer

User success is:
- completing onboarding
- trusting the system enough to ask real questions
- coming back before real buy / wear decisions
- feeling remembered across channels
- seeing explanations and confidence when needed
- experiencing wardrobe-first value, not only catalog upsell
- never being shown a low-confidence outfit dressed up as a recommendation — when the system can't match the request, it says so and offers a way forward

## First-50 Product Success

The first-50 rollout is about dependency, not generic engagement.

The product succeeds in this phase if users:
- complete onboarding
- return through WhatsApp
- use the product before real clothing decisions
- show recurring intent patterns
- build memory through wardrobe, feedback, and repeated usage

## Relationship To Other Docs

- [`docs/APPLICATION_SPECS.md`](APPLICATION_SPECS.md) § Live System Reference: **source of truth** — implementation state, runtime behavior, module layout, persistence contract.
- [`docs/WORKFLOW_REFERENCE.md`](WORKFLOW_REFERENCE.md) § Phase History: parked architectural decisions, decision log, color-system overhaul, cleanup plans.
- [`docs/RELEASE_READINESS.md`](RELEASE_READINESS.md) § Recently Shipped: per-PR record of completed work.
- [`docs/DESIGN.md`](DESIGN.md): design system, visual language, component rules
- [`docs/RELEASE_READINESS.md`](RELEASE_READINESS.md): 4-gate release checklist
- [`docs/OPERATIONS.md`](OPERATIONS.md): dashboards and SQL for the first-50 rollout
- [`docs/DESIGN_SYSTEM_VALIDATION.md`](DESIGN_SYSTEM_VALIDATION.md): manual design QA checklist
- [`docs/APPLICATION_SPECS.md`](APPLICATION_SPECS.md): runtime contract (⚠️ *partially deprecated*)
- [`docs/INTENT_COPILOT_ARCHITECTURE.md`](INTENT_COPILOT_ARCHITECTURE.md): target system design (pre-planner-inlining era)
- [`docs/WORKFLOW_REFERENCE.md`](WORKFLOW_REFERENCE.md): human-facing per-intent execution flows (not loaded at runtime)

---

# Strategy + Gap Reference (migrated May 3, 2026)

_Migrated from `CURRENT_STATE.md`. Strategic direction, first-50 validation criteria, and the live gap-versus-target analysis previously lived in CURRENT_STATE.md and are consolidated here so PRODUCT.md is the single home for product framing._

## Product Positioning

> **For** people who want to dress better every day, **Aura is** a personal fashion copilot **that** knows your body, your style, and your wardrobe — so you always know what to wear and what's worth buying.

Strategy: **stylist for retention, shopping for revenue.** The product should feel like a personal stylist that users make part of their daily routine. Shopping is the natural outcome when the stylist identifies a wardrobe gap — not the default answer to every question.

## Executive Status

Project status (as of 2026-05-11):
- user layer: implemented and usable
- catalog layer: implemented and usable (14,242 garment-only items, all enriched on the v3 + ShapeArchitecture axis set, all embedded; catalog is now frozen — no further bulk re-enrichment)
- application layer: end-to-end recommendation pipeline with copilot planner, wardrobe ingestion, image moderation, and confidence engines
- **composition engine SHIPPED (Phase 4.7, behind `AURA_COMPOSITION_ENGINE_ENABLED` flag).** YAML-driven deterministic outfit-direction planning replaces the architect LLM on engine-accepted turns. Architect stage 19s → ~0ms; engine-friendly follow-up intents (decrease_formality, increase_formality, more_options, similar_to_previous, change_color, full_alternative, increase_boldness) all route to engine. Per-axis YAML-gap weights with confidence threshold 0.50. LLM falls back on confidence misses, anchor turns, or YAML gaps.
- **composer engine SHIPPED behind flag (Phase 5, `AURA_COMPOSER_ENGINE_ENABLED`).** Deterministic tuple scoring replaces LLM composer. Flag-on validation gated on Phase 4.6 eval-set + 4.2 stylist YAML review (both blocked on human work).
- **cache layer SHIPPED (Phase 2).** Architect + composer cache, profile-cluster keying. Hit rate started ticking up once Phase 4.7 + canonicalization (4.11) made engine inputs deterministic.
- **prompt compression SHIPPED (Phase 3, May 8 2026).** Architect 8343 → 7412 tokens, composer 1715 → 1441; episodic memory cap 30 → 20; new `ops/scripts/audit_prompt_tokens.py` regression guard.
- **rater parallelization SHIPPED (Phase 1).** Per-outfit fan-out via ThreadPoolExecutor (was a single batched call); rater stage 13.4s → ~2-3s.
- wardrobe: ingestion, enrichment, retrieval, wardrobe-first occasion response, full CRUD UI (add/edit/delete), enhanced filters (search, category, color), and completeness scoring implemented
- WhatsApp: removed from current codebase (previously had formatting and deep linking; runtime was never built)
- safety: dual-layer image moderation (heuristic + vision), restricted category exclusion, try-on quality gate implemented; try-on rendering itself flag-gated via `AURA_TRYON_ENABLED` (default false to save cost in dev loops)
- web UI: Confident Luxe design system (Phase 14) + intent-organized discovery surface (Phase 15 — complete).
  - **Visuals.** Ivory / oxblood / champagne palette, Fraunces + Inter + JetBrains Mono, hairline borders, full dark mode.
  - **Navigation.** 5-tab nav (Home / Outfits / Checks / Wardrobe / Saved) with 56px header. Tab page headers removed (May 12 2026); the tab nav is the breadcrumb and each tab opens straight onto content.
  - **Home.** Discovery input + PDP carousel with CSS slide transitions, swipe/keyboard nav, iteration stacking.
  - **Outfits.** Occasion-driven theme buckets (Beach & Vacation / Date Night / Office & Professional / Party & Night Out / Wedding & Engagement / Festival / Weekend & Everyday / Travel) + formality fallback (Smart Looks / Easy Everyday / Off-Duty) for sessions with no occasion signal — driven server-side from the planner's occasion + the rater's `formality_pct`. Each theme renders a single flattened carousel of every look in that bucket (no nested per-session carousels). Single source filter (All / From Wardrobe / Hybrid / Shop).
  - **Checks.** Outfit-check cards.
  - **Outfit card** (PRs #306, #317, #318, #323). 3-column body (thumbnails | hero | context-sync'd detail panel). Header is title + Hide (X) only — Like moved into outfit-mode CTA row. Try-on active → outfit mode (outfit title, reasoning, per-garment marked-up price + XS-XL size chips, CTA row of disabled Buy Outfit + Like heart). Garment active → garment mode (garment title, ×1.2 marked-up price, composer-authored 2-3 sentence description, XS-XL size chips, CTA row of Buy Now + Save heart). Pairing-card anchor (wardrobe item in a `pairing_request`) routes its thumbnail to outfit mode and is filtered out of the per-garment listing — only the recommended pairings show. Panel uses `min-height` + 2/4-line clamps so the CTA row stays anchored across cards. User-facing rater radar retired; rater still runs server-side for ranking/filtering.
  - **Removed surfaces.** No chat bubbles, no conversation sidebar, no Trial Room tab, no Looks page.
  - **Feedback.** Contextual strip on the outfit card (heart + Hide opening a feedback modal with reaction chips + textarea).
  - **Modals.** Native browser `alert` / `confirm` replaced with in-app `auraPrompt` helper (ESC-dismissable; scoped to the top-most overlay when modals stack).
- profile: style dossier with display-xl name hero, italic adjective list, champagne signal rule on palette card, theme toggle, underline-only edit inputs
- wardrobe: borderless 5-column closet grid with right-edge Add Item drawer — photo-only upload with auto-enrichment (46 attributes via vision API); edit modal with underline inputs; hover-reveal edit/delete text buttons
- wardrobe filters: hairline-underline search, uppercase tracked label category chips (7), color filter row (11 colors), localStorage persistence. **Shoes category dropped** (PR #330) — the system doesn't style around footwear yet, so the filter chip + shoe wardrobe items are hidden from the view. Shoe items still in the DB are filtered globally at `process_turn` entry (PR #332) so they never reach the planner. Shoe-anchor uploads to chat get an honest *"Styling around shoes isn't supported yet — try a top, bottom, dress, or outerwear instead."* response (PR #330) rather than the system silently building wrong outfits.
- chat management: conversation rename (inline edit) and delete (archive) with hover-reveal sidebar actions; `title` column on conversations table
- virtual try-on: persistent storage with cache reuse — images saved to disk + `virtual_tryon_images` table, mapped by user + garment IDs + source; same garment combination returns cached result without re-generation
- chat composer: `+` button popover with "Upload image" and "Select from wardrobe" options; drag-drop and paste support
- wishlist: wishlisted catalog garments with product images, title, price, Buy Now — data from `catalog_interaction_history` hydrated with `catalog_enriched`
- trial room: virtual try-on render gallery (2:3 aspect ratio, gradient timestamp overlay) — data from `virtual_tryon_images`
- catalog admin: pipeline with upload, enrichment sync, embedding generation, URL backfill, include-incomplete toggle, skip-already-embedded optimization, **resync-from-DB endpoint** (`POST /v1/admin/catalog/embeddings/resync`) for re-embedding enriched items with product_id_prefix filter and paginated fetch
- catalog health: **14,242 garment-only items** — all enriched on the v3 + ShapeArchitecture axis set (Step 2b re-enrichment shipped May 11, 2026; 54 rows with broken Shopify-CDN image URLs dropped, 14,242/14,296 ok = 99.62%), all embedded, zero null filter columns. **Catalog is frozen** — no further bulk re-enrichment (no-re-enrichment policy 2026-05-11)
- retrieval performance: **batched embeddings** (single OpenAI call for all query documents) + **parallel search+hydrate** (ThreadPoolExecutor, 4 workers) — ~4x speedup vs sequential
- query document coverage: **all enrichment attributes** in architect query template (55 enum + 2 text canonical attrs as of Step 2a + Path B); includes EMBELLISHMENT (EmbellishmentLevel/Type/Zone), VISUAL_DIRECTION (VerticalWeightBias, VisualWeightPlacement, StructuralFocus, BodyFocusZone, LineDirection), and the ShapeArchitecture quad (VolumePlacement, AsymmetryType, AttachmentStructure, MotionBehavior) + v3 axes (FabricTransparency, SurfaceFinish, LayeringVisibility, BlouseLength, ShoulderExposure, SleeveVolume, BorderContrast) shipped 2026-05-11

The system is a working recommendation engine with supporting infrastructure, now with deterministic engine paths replacing LLM hops on the common case (composition + composer). Wardrobe-first is live across the recommendation flow. Open work tracked in `docs/OPEN_TASKS.md`: Phase 6 streaming delivery (perceived-latency UX win), Phase 4.6 eval-set curation (gates several follow-on validations), Phase 4.2 stylist YAML review (paid consultant pass), and Phase 7 distillation (gated on 10K+ traces).


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
- onboarding flow (OTP, profile, images, analysis, style prefs) — draping removed
- catalog enrichment and embedding retrieval pipeline
- copilot planner with intent classification and action routing (12 intents recognized)
- recommendation pipeline (architect → search → composer → rater → try-on → format) — used for both occasion and pairing requests (pairing always runs full pipeline including try-on). As of 2026-05-07, the architect stage is wrapped by a deterministic composition router (`composition/router.py`, PRs #149-#155) that tries a YAML-driven engine first when `AURA_COMPOSITION_ENGINE_ENABLED=true`; engine accepts → architect LLM never runs (~19s saved per turn). See `docs/composition_semantics.md`.
- wardrobe ingestion with vision-API enrichment and image moderation
- wardrobe retrieval and wardrobe-first occasion response
- virtual try-on via Gemini with quality gate
- 3-column PDP outfit cards (thumbnails | hero | context-sync'd detail panel, PR #306):
  - **Detail panel mode** follows the active thumbnail.
  - **Outfit mode** (try-on active): outfit title, reasoning, per-garment rows with marked-up price + size chips, disabled Buy Outfit (multi-item checkout not wired).
  - **Garment mode** (garment active): garment title, composer-authored `description`, ×1.2 price markup applied at render, size chips, Buy Now, Save.
  - **Per-item description.** LLM composer (`outfit_composer.md`) writes **2-3 sentences (30-55 words, stylist voice)** per garment into `item_descriptions: [{item_id, description}]` — an array, not a dict (OpenAI Structured Outputs forbids dynamic-key dicts; the array reshape shipped as hotfix #313). Orchestrator folds it back into `Dict[str, str]` keyed by `item_id`. Threaded ComposedOutfit → orchestrator → response_formatter into `OutfitItem.description`. **Composer-engine path** (the deterministic Python composer that doesn't emit `item_descriptions`) now also ships descriptions — PR #333 added `synthesize_item_description`, a 12-25-word stylist-flavored template built from catalog attributes (color, fit, pattern, silhouette, formality, occasion). LLM descriptions still win when present; engine-path turns no longer ship empty description panels. Phonetic article exceptions (PRs #335, #337, #340, #342) ensure copy like *"A slim olive utility jacket"* / *"An uninsulated shell"* / *"Slim indigo cargo pants"* reads grammatically.
  - **Rater visibility.** User-facing radar retired May 12 2026. Rater still runs server-side for ranking / filtering (`fashion_score_pct`, `formality_pct`, etc. populate on `EvaluatedRecommendation` but are not displayed).
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

### Recently Completed Roadmap Items:

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

