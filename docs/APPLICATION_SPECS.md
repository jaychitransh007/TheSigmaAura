# Application Layer — Implementation Specification

Last updated: May 3, 2026 (Model migration to gpt-5.5/gpt-5-mini; architect prompt modular assembly; confidence threshold 0.75; parallel try-on renders; Lever 3 split-architect deprecated and removed)

> **⚠️ Header sections are partially deprecated; § Live System Reference (bottom) is authoritative.** The opening "Implementation Spec" sections of this document still describe the *legacy* routing layer (`intent_router.py`, `intent_handlers.py`, `context_gate.py`, `context/occasion_resolver.py`) which has been **deleted** from the codebase and replaced by the LLM copilot planner inlined into `process_turn`.
>
> **The authoritative "what is running right now" view lives at the bottom of this file in § Live System Reference (May 3, 2026)** — migrated from the now-deleted `CURRENT_STATE.md`. When the legacy header sections disagree with § Live System Reference, the latter wins.
>
> Other docs that delegate to this one:
> - `docs/PRODUCT.md` — product framing, personas, gap-versus-target
> - `docs/WORKFLOW_REFERENCE.md` — per-intent execution flows + full Phase History decision log
> - `docs/RELEASE_READINESS.md` — release gates + Recently Shipped (May 1) record
> - `docs/OPERATIONS.md` — dashboards, on-call runbook, ops scripts, Supabase sync, run instructions

## Product Positioning

> **For** people who want to dress better every day, **Aura is** a personal fashion copilot **that** knows your body, your style, and your wardrobe — so you always know what to wear and what's worth buying.

Strategy: **stylist for retention, shopping for revenue.** Users make Aura part of their lifestyle — checking outfits, getting pairing advice, planning what to wear. They can also shop from it: complete outfit recommendations, gap-filling for pieces they already own, or buy/skip verdicts on items they're considering. Dependency keeps them on the platform; shopping generates revenue.

## Current Implementation Status

This document serves two purposes:
- the implementation specification and contract for the fashion copilot runtime in `modules/agentic_application`
- the prioritized build plan for closing the gap between current state (shopping-first recommendation engine) and target state (lifestyle stylist with shopping)

For the user-facing product summary, personas, journeys, and stories, see `docs/PRODUCT.md`.
For the current project state, gap analysis, and file layout, see § Live System Reference at the bottom of this file.
For detailed step-by-step execution flows, see `docs/WORKFLOW_REFERENCE.md`.

Implemented now:
- **intent registry** (`intent_registry.py`): StrEnum-based single source of truth for the post-Phase 12A taxonomy — 7 advisory intents + silent `wardrobe_ingestion` (8 total `Intent` members), 7 actions (`Action`), and 7 follow-up intents (`FollowUpIntent`) — with metadata registries and JSON schema helpers; consumed by planner, orchestrator, agents, API, and tests. Phase 12A folded `shopping_decision` / `garment_on_me_request` / `virtual_tryon_request` into `garment_evaluation`, `product_browse` into `occasion_recommendation` (via `target_product_type`), and deferred `capsule_or_trip_planning`.
- copilot planner (gpt-5-mini) — intent classification across the 7 advisory intents + feedback, 7-action dispatch (JSON schema enums generated from registry)
- active runtime entrypoint in `agentic_application/api.py` with `AgenticOrchestrator`
- saved user-context loading from onboarding/profile-analysis/style-preference persistence
- server-side conversation-memory carry-forward across follow-up turns
- planner-driven runtime with deterministic handler overrides for pairing, outfit check, source preference, and catalog CTA follow-up
- strict JSON schema with enum-constrained hard filter vocabulary
- **tiered hard filter / soft signal system** (April 9 2026): `gender_expression` always hard; `garment_subtype` conditional (hard for specific requests, null for broad); `garment_category` and `styling_completeness` are soft signals in query document text only — never hard filters
- soft signals via embedding similarity only: `garment_category`, `styling_completeness`, `occasion_fit`, `formality_level`, `time_of_day`
- no filter relaxation — single search pass per query
- **batched embedding** (all query documents in one OpenAI API call) + **parallel search+hydrate** (ThreadPoolExecutor, 4 workers) — ~4x retrieval speedup
- embedding retrieval from `catalog_item_embeddings` with hydration from `catalog_enriched`
- direction-aware retrieval: `needs_bottomwear` for top (all direction types), `needs_topwear` for bottom, `["needs_innerwear"]` for outerwear, `complete` for complete directions. Outerwear exclusively in outerwear role.
- **direction-aware reranker**: round-robin picks one candidate per direction before filling by score — guarantees outfit variety across architect's concepts
- previous recommendation exclusion: follow-up turns exclude prior product IDs from retrieval
- deterministic assembly and LLM evaluation with graceful evaluator fallback
- architect failure returns error to user (no silent degradation)
- latency tracking via `time.monotonic()` per agent stage
- persisted turn artifacts: live context, memory, plan, applied filters, retrieved IDs, assembled candidates, final recommendations
- response formatting for recommendation-pipeline turns (max 3 outfits) with 16-field item cards; dedicated handlers can return bounded multi-look outputs beyond that
- virtual try-on via Gemini (`gemini-3.1-flash-image-preview`) with parallel generation, quality gate, persistent disk + DB storage (`virtual_tryon_images` table), and cache reuse by user + garment ID set
- 2-column PDP outfit cards (hero 3:4 aspect `object-fit: cover` + 36% info panel) with click-to-cycle hero + `1/N` counter badge, split polar bar chart (Nightingale-style: top semicircle = 8-axis style archetype profile in champagne `--signal`, bottom semicircle = dynamic 5-9 axis fit/evaluation profile in oxblood `--accent`, colours read from CSS custom properties via `getComputedStyle` so they flip for dark mode), feedback strip at bottom (heart SVG icon for like + "What would you change?" inline textarea with reaction chips for constructive dislike feedback)
- `analysis_confidence_pct` — attribute-level analysis confidence reported in metadata. Surfaced for downstream consumers; the PDP polar chart shows raw evaluator scores, not scaled.
- per-outfit feedback capture with turn-level correlation
- wardrobe ingestion from chat with vision-API enrichment and dual-layer image moderation
- wardrobe-first occasion, pairing, outfit-check follow-through, and capsule/trip support
- pairing request image gate: asks user for garment image when message references "this shirt" but no image attached
- anchor_garment on LiveContext: uploaded garment passed to architect with full enrichment attributes; architect skips anchor's role; anchor injected as sole item for its role before assembly
- **P0 open: pairing pipeline end-to-end fix still needed** — anchor injection + role stripping code exists but deployment issues prevent validation; see § Live System Reference below for details
- explicit source selection metadata: wardrobe-first, catalog-only, or hybrid
- deterministic 12-sub-season color analysis (draping removed — deterministic interpreter is sole authority)
- color palette system: base/accent/avoid colors derived from seasonal group, passed to copilot planner, outfit architect, and outfit check agents
- comfort learning: behavioral seasonal palette refinement from outfit likes
- profile confidence engine and recommendation confidence engine (9-factor, 0–100 scoring)
- **Outfit confidence threshold** (May 2026): catalog-pipeline outfits with `fashion_score < 75` (LLM Rater 0–100 scale, see `_RECOMMENDATION_FASHION_THRESHOLD` in `orchestrator.py`) are dropped before they reach the user; if zero candidates clear, `_build_low_confidence_catalog_response` returns `outfits=[]` with an honest "I couldn't find a strong match" message + refine / show-closest / shop CTAs. Wardrobe-first selection uses the equivalent 0.75 floor on its normalized item score (`_RECOMMENDATION_CONFIDENCE_THRESHOLD`; empty `occasion_fit` no longer counts as a participation point). User-facing copy never references the threshold or raw scores.
- **LLM ranker** (May 3 2026, PRs #29 / #30): the deterministic OutfitAssembler (combinatorial pairing + heuristic compatibility scoring) and Reranker (cosine sort + bias tie-break) were replaced with two gpt-5-mini calls — OutfitComposer constructs up to 10 outfits from the retrieved item pool; OutfitRater scores each on a four-dimension rubric (`occasion_fit`, `body_harmony`, `color_harmony`, `archetype_match`) and emits a blended `fashion_score`. Cosine similarity is now a retrieval primitive only.
- **parallel try-on renders** (May 2026): top-N candidate Gemini renders run in a `ThreadPoolExecutor` batch (`max_workers=N`), with per-batch INFO log lines (`tryon parallel batch: N/N succeeded (cold=K, cache_hit=M) in Xms wallclock`). Cache hits short-circuit inside the thread before the Gemini call. Quality-gate failures recover via a second parallel batch from the over-generation pool, not sequential retry.
- **architect prompt modular assembly** (May 2026): system prompt is built per-request from a 4.8K-token base + optional anchor module (when `anchor_garment` is set) + optional follow-up module (when `is_followup`). Saves ~6,850 input tokens on plain turns vs the pre-trim 11.6K monolithic prompt.
- dual-layer image moderation (heuristic blocklist + vision API)
- restricted category exclusion in catalog retrieval
- conversation management: rename (PATCH) and delete/archive (DELETE) endpoints with sidebar UI
- wardrobe edit modal (all metadata fields) and per-card delete with confirmation
- wardrobe: borderless 5-column closet grid, uppercase tracked label filter chips, hairline-underline search, right-edge Add Item drawer, per-card edit/delete as hover-reveal text buttons, localStorage filter persistence
- dependency/retention instrumentation (turn-completion events, cohort anchors, memory-input lift)
- follow-up turns with 7 follow-up intent types
- `response_type` field: `"recommendation"` | `"clarification"`
- quick-reply suggestion chips for clarification responses
- profile as style dossier: display-xl Fraunces name hero, italic adjective list, champagne signal rule on palette card, underline-only edit inputs, theme toggle, flat analysis badges
- chat: italic Fraunces welcome headline, borderless stylist bubbles (2px ink left rule on agent copy), ⌘K history rail toggle, follow-up uppercase bucket headers, stylist-voice stage messages (one-per-poll advance), 960px feed width
- header nav: 56px, uppercase tracked label links with ink underline active state, Home · Outfits · Checks · Wardrobe · Saved (Phase 15: intent-organized, no chat tab)
- wardrobe add-item drawer (right-edge slide) — photo-only upload with auto-enrichment (46 attributes via vision API)
- catalog pipeline: auto-generated product_id from URL for CSVs lacking the column
- Outfits tab (Phase 15 — replaces Looks + Trial Room): intent-grouped history with PDP carousels per occasion/intent section. Each section = Fraunces italic title + relative time + swipeable PDP cards. Try-on images embedded in PDP cards. Liked outfits persist with filled heart; hidden outfits filtered from history via (turn_id, outfit_rank) keys in feedback_events. Read-time hydration for historical turns missing outfits.
- Checks tab (Phase 15): outfit check history — each check as a card with user message + stylist assessment
- Home tab (Phase 15 — replaces Chat): discovery surface with centered input + PDP carousel for active request + recent intent group previews. No chat bubbles, no conversation sidebar.
- Intent-history endpoint: `GET /v1/users/{id}/intent-history` groups turns by (intent, occasion), embeds try-on images, supports `?types=` filter, filters disliked outfits, tags liked outfits
- Confident Luxe design system across onboarding, processing, main app, and admin — ivory `#F7F3EC` canvas, oxblood `#5C1A1B` accent, champagne `#C6A15B` signal (personal cues only), Fraunces (display) + Inter (body) + JetBrains Mono (labels), hairline borders replacing shadows on static cards, full dark mode parity via `[data-theme="dark"]`, motion system (single easing curve, 120/240/480ms durations, view-enter fade+rise, runway label track-in, staggered Looks grid entrance, `prefers-reduced-motion` override)

Remaining work is now concentrated in hardening and live-environment validation rather than core intent/runtime capability gaps. See `docs/RELEASE_READINESS.md` for the execution checklist.

## Strategic Product Direction

This section defines the target product state. The current runtime implements the recommendation pipeline and supporting infrastructure. The remaining build work is closing the gap to a full lifestyle copilot.

### Product Definition

> A mandatory-onboarding, memory-backed personal fashion copilot that helps the user make better shopping and dressing decisions over time through an intent-organized discovery surface with PDP carousels.

Core principles:
- onboarding is required before chat access
- wardrobe onboarding is optional for the user, but wardrobe support is mandatory in the system
- wardrobe-first answers across all intents — catalog fills gaps, not the default
- dependency is the product metric; shopping is the business model
- chat is the primary operating surface after onboarding

### First-50 Validation Goal

The next implementation phase is not trying to validate generic "AI engagement."

It is trying to validate **dependency** for the first 50 onboarded users.

Dependency means the user returns to the system before or during real clothing decisions such as:
- whether to buy an item
- what to pair with an item
- what to wear for an occasion
- how to plan a workweek, travel set, or mini capsule

The first-50 validation goal is:
- acquire 50 fully onboarded users
- observe repeated use through WhatsApp after onboarding
- determine which intents become recurring anchors in the user's life
- learn whether the product becomes a pre-buy / pre-dress habit rather than a one-time novelty

### Operating Surfaces

#### 1. Website — onboarding and discovery

Website responsibilities:
- capture acquisition source and ICP hypothesis
- enforce pre-chat onboarding gate
- collect mandatory profile data
- collect required images and run analysis
- collect required saved preferences
- optionally collect wardrobe items
- show profile confidence and how to improve it
- provide the first successful chat session

#### 2. WhatsApp — retention and repeat usage

WhatsApp responsibilities:
- serve as the lightweight repeat-use surface after onboarding
- accept new user intents in natural language or images/links
- support quick conversational loops with low friction
- drive return usage for shopping, pairing, occasion, and wardrobe-first requests
- send re-engagement nudges and reminders
- deep-link back to web only for heavy tasks:
  - image re-capture
  - wardrobe management
  - confidence detail
  - profile edits

### Mandatory Pre-Chat Onboarding Contract

Chat access is blocked until the user completes required onboarding.

Required before first chat:
- identity/contact record
- consent + safety acknowledgement
- baseline profile:
  - name
  - date of birth
  - gender / gender expression mapping policy
  - height
  - waist
  - profession
- required images:
  - full-body
  - headshot
- profile analysis run
- deterministic interpretations
- saved preferences / style preference completion

Optional during onboarding:
- wardrobe upload / wardrobe seeding

Rationale:
- the system depends on profile-aware reasoning
- confidence reporting must be grounded in actual evidence
- the user must see why the system is confident or not confident
- optional wardrobe memory should increase value, but should not block first access if the mandatory onboarding contract is satisfied

### Data Contract for the Copilot

#### Required pre-chat state

The system must have these records before chat unlocks:
- `user_profile`
- `onboarding_images`
- `analysis_attributes`
- `derived_interpretations`
- `style_preferences`
- `profile_confidence_state`
- `consent_and_guardrail_state`

#### Optional user-supplied state

The user may provide these at onboarding or later:
- `wardrobe_items`
- `wardrobe_item_images`
- `favorite_brands`
- `budget_bounds`
- `occasion_preferences`

#### System-generated memory

These are not onboarding inputs for a first-time user, but they are mandatory for the long-term intelligence of the system:
- `user_queries`
- `conversation_turns`
- `feedback_history`
- `catalog_interaction_history`
- `wardrobe_usage_history`
- `recommendation_history`
- `confidence_history`
- `policy_events`

### Intent Taxonomy

The system routes every incoming message into one primary intent and optional follow-up intents.

Primary intent taxonomy (post-Phase 12A: 7 advisory + silent wardrobe_ingestion):

| Intent ID | User job | Typical inputs | Core data sources | Core outputs |
|---|---|---|---|---|
| `occasion_recommendation` | "What should I wear for this occasion?" / "Show me items matching X" (when `target_product_type` is set) | occasion, formality, weather/trip/work context, optional product type | wardrobe, profile, catalog, history | wardrobe-first outfit(s), optional catalog upsell, or single-product cards |
| `pairing_request` | "What goes with this piece?" | wardrobe item image, product link, text | wardrobe, catalog, preferences, history | pairings from wardrobe first, then catalog; uploaded garment becomes the anchor in every paired candidate |
| `garment_evaluation` | "Should I buy this?" / "How will this look on me?" / "Try this on me." | garment image / product link + user image context | profile, body/color interpretation, catalog, try-on, visual evaluator | tryon-grounded verdict, fit/proportion critique, optional buy/skip |
| `outfit_check` | "How does what I'm wearing look?" | current outfit image(s) | profile, analysis, preferences, past feedback | outfit assessment, improvement suggestions, confidence |
| `style_discovery` | "What style suits me?" | text question, profile, images | analysis, interpretations, preferences | style explanation, archetype rationale, next actions |
| `explanation_request` | "Why did you recommend this?" | reference to prior answer | prior chats, recommendation history, confidence state | transparent explanation |
| `feedback_submission` | "I liked / disliked this." | explicit feedback | recommendation history, wardrobe, comfort learning | stored feedback + learning update |
| `wardrobe_ingestion` | (silent) "Save this into my wardrobe." | item image(s), link, text | profile, moderation, wardrobe store | wardrobe item saved + 46-attribute enrichment. **Not** classified by the planner from user messages — programmatic / bulk-upload path only. |

Removed in Phase 12A (do not extend):
- `shopping_decision`, `garment_on_me_request`, `virtual_tryon_request` → folded into `garment_evaluation` (visually-grounded evaluator pipeline)
- `product_browse` → folded into `occasion_recommendation` via `target_product_type`
- `capsule_or_trip_planning` → deferred (will return as a multi-day intent in a later phase)

Intent routing requirements:
- each turn must have exactly one primary intent
- the router may attach secondary intents
- every routed intent must record:
  - routing confidence
  - data sources read
  - memory written
  - policies triggered

### Confidence Model

The UI should show confidence, but the confidence must be decomposable and explainable.

#### 1. Profile confidence

Profile confidence answers:
- how complete is the user's style/body/color profile?
- how reliable is the personalization basis behind future recommendations?

Profile confidence should be computed from weighted factors:
- profile completeness
- image quality
- image coverage
- analysis confidence
- interpretation confidence
- style preference completion
- wardrobe coverage, if present
- consistency of explicit feedback over time

Profile confidence UX contract:
- show a percentage
- show the top missing evidence
- show which onboarding actions improve the score

Example:
- `Profile confidence: 68%`
- `Improve to 82% by uploading a clearer full-body photo`
- `Improve to 89% by saving 5 wardrobe staples`

#### 2. Recommendation confidence

Recommendation confidence answers:
- how strongly does the system believe this answer fits the user and the request?

Recommendation confidence should consider:
- clarity of detected intent
- clarity of occasion/context
- profile confidence
- wardrobe coverage for wardrobe-first requests
- catalog metadata completeness
- retrieval depth / candidate quality
- prior positive signals on similar items or styles
- virtual try-on quality gate status if try-on is involved

The system must never show a recommendation confidence percentage without an internal explanation payload.

### Safety and Guardrail Contract

The next-phase product must enforce the following guardrails:

#### Image upload guardrails
- reject nude or sexually explicit user images
- reject images of minors
- reject lingerie / underwear product uploads if outside allowed scope
- reject non-garment wardrobe uploads when the user is trying to save wardrobe items

#### Recommendation guardrails
- exclude lingerie / underwear from:
  - catalog retrieval
  - wardrobe pairing
  - outfit check recommendations
  - virtual try-on request fulfillment
- prevent unsafe or distorted outputs from reaching the user

#### Virtual try-on guardrails
- try-on must fail closed
- if composition quality is poor, body distortion is visible, or garment fidelity is broken, the result must not be shown
- the user should receive a safe fallback explanation instead of a bad image

#### Auditability

Every moderation / policy decision should emit a structured event:
- `policy_event_type`
- input class
- reason code
- blocked / allowed / escalated
- model or rule source

### Suggested Architecture Diagram

```mermaid
flowchart TD
    A[Website Acquisition + Onboarding] --> B[Mandatory Onboarding Gate]
    B --> C[Profile Store]
    B --> D[Image Store]
    D --> E[Profile Analysis + Interpretation]
    E --> F[Profile Confidence Engine]
    B --> G[Saved Preferences]
    B --> H[Optional Wardrobe Seeding]

    I[Web Chat] --> J[Intent Router]
    K[WhatsApp Chat] --> J

    J --> L[Policy + Moderation Layer]
    L --> M[Context Compiler]

    C --> M
    E --> M
    F --> M
    G --> M
    H --> M
    N[Conversation Memory] --> M
    O[Feedback History] --> M
    P[Catalog Interaction History] --> M
    R[Catalog Retrieval + Ranking] --> M

    M --> S{Intent Handler}
    S --> S1[Shopping Decision]
    S --> S2[Capsule / Trip Planning]
    S --> S3[Outfit Check]
    S --> S4[Garment on Me]
    S --> S5[Pairing Request]
    S --> S6[Wardrobe Ingestion]
    S --> S7[Occasion Recommendation]
    S --> S8[Style Discovery]
    S --> S9[Explanation]
    S --> S10[Feedback]
    S --> S11[Virtual Try-on]

    S1 --> T[Response Composer]
    S2 --> T
    S3 --> T
    S4 --> T
    S5 --> T
    S6 --> T
    S7 --> T
    S8 --> T
    S9 --> T
    S10 --> T
    S11 --> T

    T --> U[Recommendation Confidence Engine]
    U --> V[Chat Response]

    V --> W[Memory Writer]
    W --> N
    W --> O
    W --> P

    X[Telemetry + Outcome Tracking] --- A
    X --- I
    X --- K
    X --- J
    X --- T
    X --- W
```

### High-Level Implementation Plan

Implementation is organized in phases. Phases 0–3 and Phase 6 are substantially complete. The remaining work focuses on closing the gap between the current shopping-first engine and the target lifestyle stylist.

#### Phase 0 — contracts, analytics, and truth model — COMPLETE

Status: done.
- formal intent taxonomy defined (8 intents post-Phase 12A consolidation)
- event schema for turn-completion, feedback, and dependency validation
- confidence formula documented for profile and recommendation engines
- first-50 success metrics defined

#### Phase 1 — onboarding gate and confidence foundation — COMPLETE

Status: done.
- onboarding gate enforced before chat access
- profile confidence engine operational
- optional wardrobe onboarding entry point available
- acquisition source tracking on OTP verification

#### Phase 2 — unified memory model — COMPLETE

Status: done.
- conversation memory carry-forward across turns
- feedback history with turn-level correlation
- wardrobe item persistence with enrichment metadata
- comfort learning (behavioral seasonal palette refinement)
- turn artifact persistence (live context, memory, plan, filters, candidates, recommendations)

#### Phase 3 — intent router and handler contracts — COMPLETE

Status: router and dedicated handler set are implemented in runtime.

Done:
- copilot planner classifies 8 intents with action dispatch (post-Phase 12A)
- `run_recommendation_pipeline` handler fully operational (occasion recommendation)
- `run_outfit_check` handler implemented with structured scoring, critique, and improvement suggestions
- `run_shopping_decision` handler implemented with product parsing, verdicting, wardrobe overlap checks, and pairing follow-up
- `pairing_request` handler implemented with deterministic garment-led routing overrides, wardrobe-image pairing, and catalog-image pairing
- `style_discovery` handler implemented with profile-grounded explanation and deterministic attribute-level advice for color, collar, neckline, pattern, silhouette, and archetype questions
- `explanation_request` handler implemented with recommendation-evidence explanations from prior turn context
- `capsule_or_trip_planning` handler implemented with trip-duration-aware multi-look planning, daypart/context labeling, and catalog-supported gap coverage
- `respond_directly` and `ask_clarification` actions for non-recommendation turns
- `save_wardrobe_item` and `save_feedback` actions implemented
- `run_virtual_tryon` action implemented
- wardrobe-first occasion response implemented

#### Phase 4 — wardrobe + catalog blend — COMPLETE

Status: wardrobe-first and catalog-follow-through contract implemented across occasion, pairing, outfit-check follow-up, and capsule planning.

Done:
- wardrobe ingestion from chat with vision-API enrichment and moderation
- wardrobe retrieval and count
- wardrobe-first occasion response in orchestrator
- wardrobe source labeling in WhatsApp formatter
- explicit source preference routing (`from my wardrobe`, `from the catalog`) with `source_selection` metadata
- catalog upsell follow-through after wardrobe-first occasion and outfit-check answers
- wardrobe-image vs catalog-image pairing distinction at intake and runtime

#### Phase 5 — WhatsApp retention surface — REMOVED

Status: code removed from codebase as of April 2026. WhatsApp services (formatter, deep links, reengagement, runtime) were deleted. WhatsApp remains a target retention surface in product strategy but will need to be rebuilt when ready.

Previously implemented (now removed):
- WhatsApp message formatting (outfits, suggestions, source labeling)
- deep linking with task routing (onboarding, wardrobe, tryon review, chat)
- WhatsApp Business API integration — inbound webhook, outbound delivery
- cross-channel identity resolver — phone number → user_id mapping
- input normalizer for WhatsApp message format (text, images, product links)
- re-engagement trigger logic (when to nudge, what to say)
- onboarding gate enforcement for WhatsApp inbound

#### Phase 6 — safety, try-on, and trust layer — COMPLETE

Status: done.
- dual-layer image moderation (heuristic blocklist + vision API check)
- restricted category exclusion in catalog retrieval
- virtual try-on quality gate (fails closed)
- virtual try-on persistence: images saved to `data/tryon/images/` with metadata in `virtual_tryon_images` table; cache reuse by user + garment IDs avoids re-generation for same outfit
- policy event logging for all moderation decisions
- wardrobe upload moderation (rejects non-garment, explicit, minor images)

#### Phase 7 — first-50 dependency validation — PARTIAL

Status: instrumentation done, rollout pending.

Done:
- dependency validation event schema
- turn-completion events across web / WhatsApp
- cohort anchors and retention reporting
- memory-input lift measurement

Not done:
- [ ] first-50 user recruitment
- [ ] recurring-intent analysis from live data
- [ ] dependency and referral reporting from real cohorts

### Implementation Priority (Build Order)

This is the prioritized build sequence for closing the remaining gaps.

#### P0 — WhatsApp Runtime + Cross-Channel Identity — REMOVED / PENDING REBUILD
Why: no repeat usage without this. WhatsApp is the retention surface.
Status: code was removed from the codebase. Will need to be rebuilt when ready for first-50 rollout.
- WhatsApp Business API integration (inbound webhook + outbound delivery)
- cross-channel identity resolver (phone → user_id)
- input normalizer (text, images, product links from WhatsApp format)
- onboarding gate enforcement for WhatsApp
- re-engagement trigger logic

#### P1 — Outfit Check Pipeline — COMPLETE
Why: highest daily-use intent. "Does this work?" before leaving the house drives habit.
- dedicated handler: user uploads outfit photo → evaluate against profile
- scoring: body harmony, color suitability, style fit, occasion appropriateness
- improvement suggestions: wardrobe-first swaps, then catalog
- confidence-aware critique

#### P1 — Shopping Decision Agent — COMPLETE
Why: clearest revenue path. "Should I buy this?" = purchase intent.
- product link/screenshot parser
- buy/skip verdict against user profile
- wardrobe dedup check
- pairing follow-up from wardrobe then catalog

#### P1 — Wardrobe-First Routing Across All Intents — COMPLETE
Why: makes the product feel like a stylist, not a shopping app.
- extend wardrobe-first beyond occasion to: pairing, capsule, outfit check suggestions
- wardrobe gap detection → catalog nudge
- source labeling in every response (wardrobe vs catalog)

#### P2 — Pairing Agent (Wardrobe-First Mode) — COMPLETE
Why: bridges retention and revenue naturally.
- wardrobe-first pairing search
- hybrid response: wardrobe pairs + catalog alternatives
- source labeling

#### P2 — Wardrobe Management UI — COMPLETE
Why: users need to see and trust their wardrobe data.
- web-based wardrobe browsing (view, edit, delete)
- wardrobe completeness scoring
- gap analysis view
- edit modal with all metadata fields (title, description, category, subtype, colors, pattern, formality, occasion, brand, notes)
- per-card delete with confirmation dialog
- search bar, enhanced category filter chips (8), color filter row (11), localStorage filter persistence
- conversation rename (inline edit) and delete (archive) in sidebar

#### P2 — Style Discovery + Explanation Handlers — COMPLETE
Why: builds trust and keeps users engaged.
- profile-grounded style explanation using actual analysis data
- recommendation explanation using evaluator scores + profile evidence
- confidence rationale in user-facing language

#### P3 — Capsule / Trip Planning — COMPLETE
Why: high value but lower frequency.
- multi-outfit planning (wardrobe first, catalog for gaps)
- packing list (deduplicated items across outfits)
- gap shopping list → catalog

### User Stories and Clear Outcome Measures

The implementation should be judged against the following user stories and acceptance outcomes.

#### US-01 — Mandatory onboarding before chat

As a new user, I must complete onboarding before I can access chat so that the system has enough evidence to personalize safely.

Acceptance outcomes:
- chat is inaccessible until onboarding is complete
- onboarding explicitly shows what is required vs optional
- the user sees profile confidence and how to improve it

#### US-02 — Shopping decision

As an onboarded user, I can share a product link, screenshot, or garment image and ask whether I should buy it.

Acceptance outcomes:
- response includes buy / skip
- response explains why
- response includes pairing guidance
- response stores the request and later outcomes for learning

#### US-03 — Daily-use or travel capsule request

As an onboarded user, I can ask for a set of outfits for daily use or a particular trip.

Acceptance outcomes:
- response is bounded to the requested context
- wardrobe is used first if available
- missing wardrobe / catalog gaps are made explicit
- trip duration expands the look count up to a bounded multi-day plan
- response can mix wardrobe and catalog fillers when wardrobe depth is insufficient

#### US-04 — Outfit check for what I am wearing

As an onboarded user, I can send my current outfit and ask how it looks.

Acceptance outcomes:
- the system evaluates the look against my profile and request context
- confidence is shown
- suggestions improve the current look, not just replace it

#### US-05 — Garment-on-me request

As an onboarded user, I can send a garment and ask how it would look on me.

Acceptance outcomes:
- the system returns qualitative assessment even if try-on is unavailable
- if try-on is safe and high-quality, the system may attach it
- if try-on quality is poor, the system fails safely

#### US-06 — Pairing request

As an onboarded user, I can share one item and ask what pairs well with it.

Acceptance outcomes:
- system can return pairings from wardrobe
- system can return pairings from catalog
- response identifies whether each pairing came from wardrobe or catalog
- uploaded wardrobe garments and uploaded catalog garments are treated as anchors, not echoed back as one-item answers

#### US-07 — Wardrobe ingestion

As an onboarded user, I can add wardrobe items during onboarding or later through chat.

Acceptance outcomes:
- item is moderated
- item metadata is captured
- item becomes available for future wardrobe-first requests

#### US-08 — Occasion recommendation from wardrobe first

As an onboarded user, I can ask what to wear for an occasion and get an answer based on my wardrobe first.

Acceptance outcomes:
- wardrobe-first outfit recommendation is supported
- the system can nudge better catalog options without replacing the wardrobe-first answer
- the answer explains why the wardrobe option works

#### US-09 — Product and outfit feedback

As an onboarded user, I can give feedback on overall product quality and on specific outfits/items.

Acceptance outcomes:
- explicit feedback is stored with correct linkage to the relevant recommendation or item
- feedback updates future reasoning
- negative feedback suppresses repetition of similar bad outcomes

#### US-10 — Style suitability

As an onboarded user, I can ask what style would look good on me.

Acceptance outcomes:
- the answer references my profile analysis and saved preferences
- the answer is not generic fashion prose
- the answer tells me what additional evidence would improve the result

#### US-11 — Explanation request

As an onboarded user, I can ask why the recommendations are what they are.

Acceptance outcomes:
- the system explains using actual profile, wardrobe, catalog, and past-signal evidence
- explanation is traceable to stored reasoning inputs
- confidence rationale is available internally and summarized externally

#### US-12 — Confidence visibility

As an onboarded user, I can see confidence for my profile analysis and for recommendations.

Acceptance outcomes:
- profile confidence is shown with improvement actions
- recommendation confidence is shown with an interpretable rationale
- confidence never appears without a supporting explanation payload

#### US-13 — Upload guardrails

As the system, I must reject unsafe user images and restricted product categories.

Acceptance outcomes:
- nude images are blocked
- lingerie / restricted items are blocked according to policy
- blocked actions create auditable policy events

#### US-14 — Virtual try-on quality fail-safe

As the system, I must refuse to show try-on output when generation quality is poor or distorted.

Acceptance outcomes:
- bad try-on output is suppressed
- user receives a graceful fallback message
- quality-gate decision is logged

### First-50 Success Measures

The first-50 rollout should be evaluated against the following thresholds.

Activation:
- at least 70% of recruited users complete mandatory onboarding
- median time from onboarding start to first useful answer is under 15 minutes including required analysis wait

Repeat usage:
- at least 40% of onboarded users start a second distinct chat session within 14 days
- at least 25% of onboarded users use the copilot in 3 or more separate sessions within 30 days
- at least 50% of repeat sessions happen through WhatsApp

Behavioral depth:
- at least 30% of onboarded users submit at least one wardrobe item
- at least 40% of onboarded users provide explicit feedback on at least one response
- at least 30% of onboarded users use more than one intent family:
  - shopping
  - dressing
  - wardrobe
  - style / explanation

Trust and safety:
- zero confirmed cases of nude images being accepted
- zero confirmed cases of lingerie / restricted products being recommended where policy says they must be blocked
- zero confirmed cases of visibly distorted try-on output being shown to users

Advocacy:
- at least 10% of onboarded users generate one measurable referral or invitation event

### Definition of Implementation Success

This next phase should be considered successful only if all of the following are true:
- onboarding is mandatory and explainable
- intent-driven chat works on web and WhatsApp
- wardrobe is optional to provide but fully supported by the system
- every major recommendation can explain itself
- confidence is visible and grounded
- policy guardrails are enforced and audited
- first-50 data tells us which intents drive dependency

## Overview

The Application Layer handles every user recommendation request.

It receives a natural language message from the user, loads the saved user profile, resolves live context from the message, generates one or more catalog-optimized retrieval queries, retrieves matching products, assembles outfit candidates when pairing is needed, evaluates them against the user's specific context, and returns ranked recommendations.

No external knowledge documents are injected into prompts in the active runtime. The LLM is relied upon for its inherent fashion knowledge plus the structured user context supplied by the system.

This specification now describes the active runtime closely enough to use as the canonical application reference.

## V1 Scope

Supported in v1:
- complete outfit retrieval
- two-piece pairing retrieval
- follow-up refinement within a conversation
- profile-aware ranking

Not supported in v1:
- three-piece outfit assembly
- open-ended wardrobe planning
- knowledge-module injection
- checkout/cart preparation

## Core Principles

- Use saved user profile as first-class recommendation context.
- Use rule-based live context resolution for speed and determinism.
- Use structured JSON outputs from LLMs, not regex-parsed text.
- Use structured labeled retrieval documents that mirror catalog embedding documents.
- Use the same embedding model and dimensions at query time and catalog time.
- Retrieve from `catalog_item_embeddings` and hydrate product rows from `catalog_enriched`.
- Support both complete outfits and pairing in v1.

## LLM and Model Configuration

Active models used by application agents:

| Agent | Model | Provider | Output Mode |
|---|---|---|---|
| Copilot Planner | `gpt-5.5` | OpenAI | JSON schema (strict) |
| Outfit Architect | `gpt-5.5` | OpenAI | JSON schema (strict). System prompt assembled at request time: 4.8K-token base + optional anchor module + optional follow-up module. |
| Visual Evaluator | `gpt-5-mini` | OpenAI | JSON schema (strict), vision input |
| Style Advisor | `gpt-5.4` (May 5, 2026 — was `gpt-5.5`; reasoning_effort=low) | OpenAI | JSON schema (strict) |
| User Profiler (visual) | `gpt-5.5` | OpenAI | JSON schema (strict), reasoning effort: high |
| User Profiler (textual) | `gpt-5.5` | OpenAI | JSON schema (strict) |
| User Analysis (onboarding) | `gpt-5.5` | OpenAI | JSON schema (strict), reasoning effort: high |
| Catalog Enrichment | `gpt-5-mini` | OpenAI | JSON schema |
| Outfit Decomposition | `gpt-5-mini` | OpenAI | JSON schema, vision input |
| Image Moderation | `gpt-5-mini` | OpenAI | JSON schema, vision input |
| Query Embedding | `text-embedding-3-small` | OpenAI | 1536-dimensional vector |
| Virtual Try-on | `gemini-3.1-flash-image-preview` | Google | Image generation |

May 1, 2026: model migration consolidated reasoning paths on `gpt-5.5` and vision/transformation paths on `gpt-5-mini`. The architect has no fallback — failure returns an error to the user. The visual evaluator ranks by `fashion_score` when its LLM call fails. Try-on uses Google Gemini with direct API key authentication (not Vertex AI / service accounts).

## Active Catalog Reality

The current catalog search stack is:
- embedding model: `text-embedding-3-small`
- embedding dimensions: `1536`
- enriched catalog table: `catalog_enriched`
- vector table: `catalog_item_embeddings`
- distance metric: cosine similarity via pgvector

Any application implementation must match that reality.

## System Components

```text
User Message
    |
    v
Orchestrator (agentic_application/orchestrator.py)
    |
    +--> 1. User Context Builder ----> Onboarding Gateway ----> onboarding_profiles, user_derived_interpretations, user_style_preference
    |
    +--> 2. Context Builder (occasion resolver + conversation memory)
    |         +--> rule-based signal extraction via occasion_resolver
    |         +--> conversation memory build from session_context_json
    |
    +--> 3. Context Gate (rule-based, <1ms)
    |         +--> signal scoring: occasion (2.0), formality (1.0), category (1.0), season (0.5), style (0.5), follow-up bonus (1.0)
    |         +--> threshold: 3.0 points
    |         +--> insufficient: short-circuit with clarifying question + quick-reply chips
    |         +--> bypass: "surprise me", follow-up turns, max 2 consecutive blocks
    |
    v
4. Outfit Architect (gpt-5.5, JSON schema; conditional anchor/followup prompt modules)
    |
    v
5. Catalog Search Agent (batched embed + parallel search)
    |    +--> Step 1: batch embed all query documents (1 OpenAI call)
    |    +--> Step 2: parallel search+hydrate (ThreadPoolExecutor, 4 workers)
    |    |    +--> text-embedding-3-small (1536 dim)
    |    |    +--> catalog_item_embeddings (pgvector cosine)
    |    |    +--> catalog_enriched (hydration)
    |    +--> Hard filters: gender_expression (always), garment_subtype (conditional), styling_completeness (directional)
    |    +--> No filter relaxation — single search pass per query
    |
    v
6. Outfit Assembler (deterministic compatibility pruning)
    |
    v
7. Visual Evaluator (gpt-5-mini, JSON schema, fallback: fashion_score ranking; runs after parallel try-on render batch)
    |
    v
8. Response Formatter (max 3 outfits)
    |
    v
9. Virtual Try-on (gemini-3.1-flash-image-preview, parallel generation)
    |    +--> person image from onboarding full_body upload
    |    +--> product image from first item in each outfit
    |    +--> prompt from prompt/virtual_tryon.md
    |
    v
User Response + Turn Persistence + Conversation Memory Update
```

## 1. Request Contract

Use server-side conversation state, not client-supplied raw history.

```python
class RecommendationRequest:
    user_id: str
    conversation_id: str
    message: str
```

Why:
- the application already has persistence
- prior turns should be loaded from storage
- raw client-supplied history is easy to drift or spoof

## 2. User Context Builder

### Purpose

Load and normalize all saved user state into one application-facing object.

### Inputs

- onboarding profile
- analysis snapshots
- deterministic interpretations
- style preference snapshot

### Output

```python
class UserContext:
    user_id: str
    gender: str
    date_of_birth: str | None
    profession: str | None
    height_cm: float | None
    waist_cm: float | None

    analysis_attributes: dict
    derived_interpretations: dict
    style_preference: dict

    profile_richness: str   # full | moderate | basic | minimal
```

### Notes

- Use the actual current profile naming, not hypothetical alternate names.
- `HeightCategory` and `WaistSizeBand` should come from deterministic interpretations.
- Style preference should be loaded exactly as stored, including blend ratio, risk tolerance, formality lean, pattern type, and comfort boundaries.
- Current runtime enforces a minimum usable profile before recommendations: `gender`, `SeasonalColorGroup`, and primary archetype/style preference signal.
- `SeasonalColorGroup` is derived deterministically from weighted warmth (SkinUndertone + HairColorTemperature + EyeColor), depth, and chroma → 4-season → 12 sub-season. Digital draping was removed due to systematic LLM cool-bias.
- `SubSeason` (e.g., "Deep Autumn", "Clear Winter") provides finer-grained classification within the primary season.

## 3. Occasion Resolver

### Purpose

Extract structured live context from the incoming message.

### Output

```python
class LiveContext:
    user_need: str
    occasion_signal: str | None
    formality_hint: str | None
    time_hint: str | None
    specific_needs: list[str]
    is_followup: bool
    followup_intent: str | None
```

### Rules

- Rule-based only
- Longest or most specific phrase must match first
- Do not treat a request as a follow-up unless prior assistant recommendations exist in the current conversation

### Important precedence requirement

Phrase ordering must prefer:
- `smart casual` before `casual`
- `work meeting` before `work`
- `black tie` before `formal`

### Specific-needs examples

- `look taller` -> `elongation`
- `look slimmer` -> `slimming`
- `comfortable` -> `comfort_priority`
- `professional` -> `authority`
- `approachable` -> `approachability`

## 4. Conversation Memory

### Purpose

Preserve cross-turn state so follow-up requests carry forward prior context.

### Schema

```python
class ConversationMemory:
    occasion_signal: str | None
    formality_hint: str | None
    time_hint: str | None
    specific_needs: list[str]
    # plan_type removed — direction_type is per-direction
    followup_count: int
    last_recommendation_ids: list[str]
```

### Build and Apply

- `build_conversation_memory()` reads `session_context_json` from the conversation row and constructs the memory state.
- `apply_conversation_memory()` merges the memory into the current `LiveContext`, carrying forward occasion, formality, time, and specific needs from prior turns when the current message omits them.
- For `increase_formality` / `decrease_formality` intents, formality shifting is applied deterministically.
- Deduplication and order preservation are enforced on specific needs.

### Conversation-level state persisted on `session_context_json`

After each turn, the orchestrator writes:
- `memory` — serialized `ConversationMemory`
- `last_direction_types` — list of direction types from last plan (e.g. `["complete", "paired", "three_piece"]`)
- `last_recommendations` — enriched recommendation summaries (colors, garment categories, subtypes, roles, occasion fits, formality levels, pattern types, volume profiles, fit types, silhouette types)
- `last_occasion` — resolved occasion signal
- `last_live_context` — full live context snapshot
- `last_response_metadata` — response metadata dict
- `consecutive_gate_blocks` — number of consecutive turns blocked by context gate (reset to 0 on successful pipeline run)

## 4.5. Context Gate

### Purpose

Fast rule-based check (<1ms) that determines whether the conversation has enough styling context to produce meaningful recommendations. Runs between context building (stage 2) and the outfit architect (stage 4). If context is insufficient, short-circuits the pipeline with a single clarifying question and quick-reply chips.

### Module

`agentic_application/context_gate.py`

### Signal Scoring

| Signal | Points | Source |
|---|---|---|
| Occasion identified | 2.0 | `live_context.occasion_signal`, `conversation_memory.occasion_signal`, or keyword match in message + conversation history |
| Formality level set | 1.0 | `live_context.formality_hint`, `conversation_memory.formality_hint`, or keyword match |
| Specific need/category stated | 1.0 | `live_context.specific_needs`, `conversation_memory.specific_needs`, or category keyword in message |
| Time/season context | 0.5 | `live_context.time_hint`, `conversation_memory.time_hint`, or season keyword |
| Style preference expressed | 0.5 | style keyword in message, or `conversation_memory.specific_needs` |
| Follow-up turn bonus | 1.0 | `conversation_memory` has occasion_signal, formality_hint, or followup_count > 0 |

**Threshold: 3.0 points.**

Text scanning covers the current user message plus all prior user messages from `conversation_history`, ensuring accumulated context from prior turns is visible to the gate.

### Bypass Rules (Gate Always Passes)

- User explicitly says "just show me" / "surprise me" / "anything works" / "you pick" / etc.
- Turn is a follow-up refinement (`live_context.is_followup == True`)
- Max consecutive blocks reached (2) — force-passes to avoid frustrating the user
- Score ≥ 3.0

### Question Selection

Picks the **single highest-value missing signal** (never stacks multiple questions):

| Priority | Missing Signal | Question |
|---|---|---|
| 1 | Occasion | "What's the occasion? (e.g., date night, office meeting, casual weekend)" |
| 2 | Category/Need | "What kind of piece are you looking for? (e.g., complete outfit, a top to pair with jeans)" |
| 3 | Formality | "How dressed up do you want to be? (casual, smart casual, formal)" |
| 4 | Style direction | "Any style direction? (minimalist, bold colors, streetwear, classic)" |

Each question includes 4 quick-reply chips returned as `follow_up_suggestions`.

### Response

When the gate blocks, the orchestrator returns:
- `response_type: "clarification"` (vs. `"recommendation"` for normal pipeline)
- `assistant_message`: the clarifying question
- `follow_up_suggestions`: quick-reply chip labels
- `outfits: []`
- `metadata: {"gate_blocked": true}`

### Multi-turn Accumulation

Context accumulates across gate-blocked turns via conversation memory. When the gate asks about occasion and the user replies "date night":
1. The occasion resolver extracts `occasion_signal="date_night"` from the reply
2. `build_conversation_memory()` merges it into the memory
3. The memory is persisted to `session_context_json`
4. Next turn's gate sees the accumulated signal and scores it

This prevents the gate from re-asking the same question.

## 5. Combined Context

The orchestrator merges saved user context, live context, and conversation memory into one payload.

```python
class CombinedContext:
    user: UserContext
    live: LiveContext
    hard_filters: dict
    previous_recommendations: list[dict] | None
    conversation_memory: ConversationMemory | None
```

### Hard filters vs soft signals (April 9-10 2026 tiering)

**Tiered filter system** — hard filters are binary gates that exclude products. Use sparingly. The embedding similarity search ranks relevance via soft signals in the query document text.

Global hard filters (always applied):
- `gender_expression` (derived from user gender: male → masculine, female → feminine)

Direction-specific filters (applied by `build_directional_filters` in the catalog search agent):
- complete outfit directions use `styling_completeness = "complete"`
- top directions use `styling_completeness = "needs_bottomwear"` (all direction types — outerwear is exclusively in its own role)
- bottom directions use `styling_completeness = "needs_topwear"`
- outerwear directions use `styling_completeness = ["needs_innerwear"]` (blazers, nehru jackets, jackets)

Architect explicit hard filters (set in `query.hard_filters`):
- `garment_subtype` — **conditional**: set only when the user names a specific garment type ("show me kurtas"); null for broad requests ("something traditional for a wedding")

**NOT hard filters** (soft signals in query document text via embedding similarity only):
- `garment_category` — hard-filtering `top` excludes `set` (kurta_set), `one_piece`, `outerwear`; the #1 cause of zero results
- `styling_completeness` — hard-filtering `needs_bottomwear` excludes complete sets; the search agent handles completeness via direction structure
- `occasion_fit`
- `formality_level`
- `time_of_day`

No query-document-extracted hard filters — `_QUERY_FILTER_MAPPING` is empty. All query document lines are soft signals for embedding similarity only. The architect sets hard_filters explicitly when needed.

No filter relaxation — single search pass per query. If a query returns insufficient results, it is not retried with dropped filters. Previous recommendation product IDs are excluded from follow-up retrieval.

Valid filter vocabulary (enforced in architect JSON schema):

| Filter key | Role | Valid values |
|---|---|---|
| `garment_subtype` | Conditional hard filter (specific requests only) | `shirt`, `tshirt`, `blouse`, `sweater`, `sweatshirt`, `hoodie`, `cardigan`, `tunic`, `kurta`, `kurta_set`, `kurti`, `trouser`, `pants`, `jeans`, `track_pants`, `shorts`, `skirt`, `dress`, `gown`, `saree`, `anarkali`, `kaftan`, `playsuit`, `salwar_set`, `salwar_suit`, `co_ord_set`, `blazer`, `jacket`, `coat`, `shacket`, `palazzo`, `lehenga_set`, `jumpsuit`, `nehru_jacket`, `suit_set` |
| `gender_expression` | Always hard filter | `masculine`, `feminine`, `unisex` |
| `styling_completeness` | Direction-level only (not architect) | `complete`, `needs_bottomwear`, `needs_topwear`, `needs_innerwear`, `dual_dependency` |

Important:
- for v1, do not globally force complete outfits
- pairing must be supported in v1

## 6. Orchestrator

### Purpose

Entry point for every recommendation request.

### Responsibilities

- load user context
- resolve live message context (rule-based occasion extraction + memory build)
- evaluate context gate — short-circuit with clarifying question if insufficient context
- load previous recommendation state from the conversation
- call the Outfit Architect
- call the Catalog Search Agent
- call the Outfit Assembler
- call the Outfit Evaluator
- call the Response Formatter
- persist turn artifacts
- persist updated conversation memory back onto the conversation

### Main flow

```python
async def handle_recommendation_request(request: RecommendationRequest) -> dict:
    user_context = await load_user_context(request.user_id)
    live_context = resolve_context(request.message, request.conversation_id)
    combined = assemble_context(user_context, live_context, request.conversation_id)

    plan = await outfit_architect(combined)
    retrieved = await catalog_search_agent(plan, combined)
    candidates = assemble_outfits(retrieved, plan, combined)
    evaluated = await visual_evaluator(candidates, combined, plan)  # sole evaluator (legacy OutfitEvaluator removed April 9, 2026)
    response = format_response(evaluated, combined, plan)

    await persist_turn_state(request, combined, plan, retrieved, evaluated, response)
    return response
```

### Active runtime notes

- Context gate runs before the architect. If insufficient context, returns a clarification response with quick-reply chips and skips stages 4-9.
- Context gate tracks consecutive blocks in `session_context_json.consecutive_gate_blocks`; resets to 0 on successful pipeline run.
- Occasion resolver now runs during context building (before the gate), not just for memory bridging, so structured signals are available for gate scoring and memory persistence.
- No filter relaxation — single search pass per query.
- `gender_expression` is always applied and never relaxed.
- Architect has no fallback — LLM failure returns an error to the user.
- Evaluator has a graceful fallback: ranks by `fashion_score` if LLM fails.
- Latency is tracked per agent via `time.monotonic()` and persisted as `latency_ms` on `model_call_logs` and `tool_traces`.

## 7. Outfit Architect

> Updated: April 10, 2026 (Phase 13/13B remediation — prompt hardening, live_context wiring, occasion-driven structures, retrieval quality improvements)
>
> **2026-05-07 update — composition router (PR #149) sits in front of this stage when `AURA_COMPOSITION_ENGINE_ENABLED=true`.** The architect's `plan()` method is unchanged; the router (`composition/router.py:route_recommendation_plan`) wraps it. On every cache-miss architect turn the router tries the deterministic composition engine first; on accept (~0ms compute, ~150ms canonicalize embed when needed), the LLM call below never happens and `plan_source="engine"`. On fall-through (`yaml_gap` / `low_confidence` / `needs_disambiguation` / `excessive_widening` / ineligibility), the LLM architect runs as documented below and `plan_source="llm"`. The "Output schema" table is unchanged regardless of source — `plan_source` is the source-of-truth field.

### Purpose

Translate user context into retrieval directions. The architect is the planning brain: it reads the user's profile, occasion, and request, then produces structured query documents that drive embedding similarity search against the catalog.

### Output schema

```python
class RecommendationPlan:
    retrieval_count: int           # default 12; varies by request type
    directions: list[DirectionSpec]
    plan_source: str               # "engine" | "llm" | "cache" (engine added by Phase 4.7, PR #149)
    resolved_context: ResolvedContextBlock

class DirectionSpec:
    direction_id: str              # A | B | C
    direction_type: str            # complete | paired | three_piece
    label: str
    queries: list[QuerySpec]

class QuerySpec:
    query_id: str
    role: str                      # complete | top | bottom | outerwear
    hard_filters: dict             # only gender_expression (always) + garment_subtype (when user names a type)
    query_document: str            # structured labeled retrieval doc

class ResolvedContextBlock:
    occasion_signal: str | None
    formality_hint: str | None
    time_hint: str | None
    specific_needs: list[str]
    is_followup: bool
    followup_intent: str | None
    ```

### Direction types

- **complete** — one query with `role: "complete"`. Finds standalone outfit items (kurta_set, co_ord_set, suit_set, dress, jumpsuit).
- **paired** — two queries: `role: "top"` + `role: "bottom"`. Finds a top + bottom combination.
- **three_piece** — three queries: `role: "top"` + `role: "bottom"` + `role: "outerwear"`. Finds a top + bottom + layering piece.

### Occasion-driven structure selection

The architect creates **2–3 directions** using **only the structures appropriate for the specific occasion**. It does NOT mechanically produce one of each type. Examples: office → paired + three_piece (no complete sets); beach → paired only; wedding ceremony → all three can work. The architect consults a per-occasion structure table in the prompt to decide.

### Style-stretch direction

For broad occasion requests with 3 directions, the third direction pushes the user's style one notch beyond their comfort zone — blending in an adjacent archetype's vocabulary. Scaled by `riskTolerance`. The stretch MUST still satisfy all occasion calibration constraints (fabric, formality, embellishment, AvoidColors are not relaxable).

### Retrieval count guidance

| Request type | retrieval_count |
|---|---|
| Broad occasion (2–3 directions) | 12 |
| Specific single-garment | 6 |
| Anchor garment | 8–10 |
| Follow-up: more_options | 10–15 |
| Follow-up: change_color / similar / full_alternative | 12 |

The architect does not inflate retrieval_count to compensate for low inventory.

### live_context wiring (Phase 13)

`_build_user_payload()` sends a `live_context` block to the LLM containing:
- `weather_context` — free-form weather signal from the planner ("rainy", "humid", "cold")
- `time_of_day` — free-form time signal ("morning", "evening", "late night")
- `target_product_type` — when set, single-garment mode ("show me shirts")

These fields are added to `LiveContext` in `schemas.py` and wired from `CopilotResolvedContext` via `_build_effective_live_context()` in the orchestrator.

### Ranking bias (Phase 13B)

_The `ranking_bias` field was removed in May 3 2026 (PR #30) along with the Reranker. The LLM ranker (Composer + Rater) reads user context directly._

### Catalog inventory awareness

The architect receives a `catalog_inventory` snapshot. **Occasion fit takes priority over inventory depth** — if the occasion calls for a specific garment type and the catalog has at least 1 item, the architect includes it. When the ideal subtype has < 3 items, a fallback direction with a higher-inventory alternative is added (replacing the lowest-confidence direction if that would exceed 3 total). **Hard constraint:** subtypes with zero items in inventory must never be used — the search will return zero results, wasting a direction. This is reinforced in both the Catalog Awareness rules and the subtype diversification rule.

### Search timeout resilience (Post-13B)

The catalog search agent (`catalog_search_agent.py`) runs parallel vector similarity RPCs via ThreadPoolExecutor. Staging validation revealed intermittent Supabase statement timeouts (error 57014) when 7 concurrent queries hit the DB. Fix: `_MAX_SEARCH_WORKERS` reduced from 4 to 2, and `_search_one` retries once on timeout (0.5s delay) before returning empty. Without this, timed-out queries silently return 0 products, cascading into 1-outfit responses.

### Occasion calibration — formality, fabric, embellishment

A single reference table in the prompt governs formality level, fabric vocabulary, and embellishment level/type/zone per sub-occasion (wedding ceremony vs engagement vs sangeet vs cocktail vs **formal office** vs **daily office** vs casual). "Office / business" is split: formal office (meetings, presentations → paired + three_piece with blazer) vs daily office (everyday/routine → paired only, no blazer). Default is daily_office when the context is generic. Key rules:
- Occasion overrides style preference for fabric
- Weather overrides occasion for fabric weight/breathability (hot wedding → silk/crepe, NOT velvet)
- Semantic fabric clusters used in query documents (multi-term phrases for broader embedding match)
- Embellishment level is the key differentiator between "too much" and "not festive enough"

### Concept-first planning

For `paired` and `three_piece` directions, the architect defines the outfit vision (color scheme, volume balance, pattern distribution, fabric story) as one coherent concept BEFORE decomposing into role-specific queries. **Each direction must be a genuinely different outfit concept** — different garment subtypes, different color families, or different silhouette approaches — because the downstream diversity pass (`_enforce_cross_outfit_diversity`, `MAX_PRODUCT_REPEAT_PER_RUN=1`) eliminates outfits that share products. Similar query documents → overlapping retrieval → only 1 surviving outfit. **Role-level subtype diversification:** when multiple directions share a role (e.g., all need a top), vary `GarmentSubtype` across directions using only subtypes present in `catalog_inventory` (e.g., shirt/tshirt/sweater for daily office). Key rules:
- **Color:** BaseColors → anchors (bottoms, outerwear); AccentColors → statement (tops). AvoidColors are never used. **Color synonym expansion** in PrimaryColor/SecondaryColor fields (e.g., "terracotta, rust, burnt orange, warm brick").
- **Volume:** top and bottom create visual balance using FrameStructure data.
- **Pattern:** typically one patterned piece + one solid.
- **Fabric:** governed by occasion calibration; all pieces in premium fabrics for ceremonial occasions.

### Color analysis — 12 sub-season architecture (Phase: Color Overhaul)

The color analysis pipeline produces a dimension-first profile:

**Step 1 — LLM extraction (7 attributes from headshot, zero added latency):** SkinSurfaceColor, HairColor, HairColorTemperature, EyeColor, EyeChroma (renamed from EyeClarity), SkinUndertone (Warm/Cool/Neutral-Warm/Neutral-Cool/Olive), SkinChroma (Muted/Moderate/Clear).

**Step 2 — Dimension-first interpreter (deterministic, zero API calls):**
- Weighted warmth score: SkinUndertone(×3) + HairColorTemperature(×2) + EyeColor(×1), normalized to ±2. Replaces single-attribute binary branch. Ambiguous flag when |warmth| < 0.5.
- Depth score: average of skin/hair/eye depth (0-10 scale).
- SkinHairContrast: abs(skin_depth - hair_depth) → Low/Medium/High. First-class dimension for pattern/contrast decisions.
- Chroma score: average of SkinChroma + EyeChroma (0-1 scale).
- Primary season derived from warmth branch + depth band (same logic, better inputs).
- ColorDimensionProfile: raw warmth, depth, contrast, chroma stored as derived interpretation.

**Step 3 — 12 sub-season assignment (deterministic):**
- Each primary season splits into 3 sub-seasons by dominant dimension: Warm/Deep/Soft Autumn, Warm/Light/Clear Spring, Cool/Light/Soft Summer, Cool/Deep/Clear Winter.
- Adjacency rules: Warm Autumn ↔ Warm Spring, Soft Autumn ↔ Soft Summer, etc.
- 12 curated sub-season palettes (168 color values) with boundary blending: accents from adjacent sub-season, avoid list narrowed to intersection for boundary users.

### Anchor garment handling

When the user wants to build around an existing piece (`anchor_garment`), the architect:
1. Skips the anchor's garment_category role
2. Uses anchor attributes to guide complementary searches
3. Chooses direction structure based on what the anchor fills (top anchor → paired bottom or three_piece; outerwear anchor → paired top+bottom, no three_piece)
4. If anchor formality conflicts with occasion, shifts supporting garments UP in formality to compensate

### Query document format

7 sections mirroring the catalog embedding vocabulary: `USER_NEED`, `PROFILE_AND_STYLE`, `GARMENT_REQUIREMENTS`, `EMBELLISHMENT`, `VISUAL_DIRECTION`, `FABRIC_AND_BUILD`, `PATTERN_AND_COLOR`, `OCCASION_AND_SIGNAL`. Values are concise (single terms or comma-separated lists, not prose). Inapplicable fields are omitted (not filled with "not_applicable") for cleaner embedding signal. Per-role omission: bottom queries omit NecklineType, NecklineDepth, ShoulderStructure, SleeveLength.

### Style archetype override

The user's saved style_preference is the default. If the user's live message mentions a different style, the architect uses the requested style instead. Enforced in `prompt/outfit_architect.md`.

### Thinking directions

The architect reasons along four axes (physical+color, user comfort, occasion appropriateness, weather/time) and identifies which 1–2 dominate for each request. This section sits in the prompt after resolved_context rules, before direction rules, so it frames all downstream decisions.

### Follow-up intent handling

The architect receives `previous_recommendations` with structured fields: `primary_colors`, `garment_categories`, `garment_subtypes`, `roles`, `occasion_fits`, `formality_levels`, `pattern_types`, `volume_profiles`, `fit_types`, `silhouette_types`.

Follow-up intent effects:
- `change_color` — different colors, preserves `occasion_fits`, `formality_levels`, `garment_subtypes`, `silhouette_types`, `volume_profiles`, `fit_types`
- `similar_to_previous` — preserves all dimensions including `primary_colors`; variation from different products
- `increase_boldness` / `decrease_formality` / `increase_formality` — adjusts target parameters
- `full_alternative` — entirely different direction
- `more_options` — additional candidates in same direction

**Tiebreaker:** When the message matches multiple intents, priority: change_color > increase/decrease_formality > increase_boldness > full_alternative > similar_to_previous > more_options.

## 8. Catalog Search Agent

### Purpose

Run embedding search for each architect query and return hydrated candidate products.

### Input

- `RecommendationPlan`
- `CombinedContext`

### Retrieval source of truth

Search:
- `catalog_item_embeddings`

Hydrate from:
- `catalog_enriched`

### Embedding configuration

```python
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
```

### Search logic

For each `QuerySpec`:
- embed `query_document`
- apply hard filters from:
  - query spec
  - combined context
- search embeddings via `match_catalog_item_embeddings` RPC
- fetch matching `catalog_enriched` rows by `product_id`

### Vector search implementation

The `match_catalog_item_embeddings` function uses a `MATERIALIZED` CTE in plpgsql to pre-filter rows before vector distance calculation. This is critical because pgvector's HNSW index scans approximate nearest neighbors from the entire table first, then applies WHERE filters as a post-filter — which can eliminate all valid matches when the filter selectivity is high. The materialized CTE forces row-level WHERE filters (gender_expression, styling_completeness, garment_category, garment_subtype, etc.) to execute first, then runs exact cosine distance on the filtered subset. This is performant for catalogs under ~50K rows.

### Filter columns

Hard filter fields used in WHERE clauses:
- `gender_expression` — always applied (global)
- `styling_completeness` — direction-specific (`complete`, `needs_bottomwear`, `needs_topwear`)
- `garment_category` — extracted from architect query document
- `garment_subtype` — extracted from architect query document

Soft signal fields (NOT used as hard filters, influence via embedding similarity only):
- `formality_level`
- `occasion_fit`
- `time_of_day`

### Retrieval output

```python
class RetrievedSet:
    direction_id: str
    query_id: str
    role: str
    applied_filters: dict
    products: list[dict]
```

## 9. Outfit Assembler

### Purpose

Convert retrieved product sets into complete evaluable outfit candidates.

### Why this exists

If pairing is part of v1, the system needs an explicit assembly layer before evaluation. Retrieval alone is not enough.

### Pairing scope

Supported direction types:
- `complete` — single garment (kurta_set, suit_set, dress, co_ord_set)
- `paired` — `top + bottom` (kurta + trouser, shirt + trouser)
- `three_piece` — `top + bottom + outerwear` (shirt + trouser + blazer, kurta + trouser + nehru_jacket)

Role-category validation in assembler: top→top only, bottom→bottom only, outerwear→outerwear only, complete→set/one_piece only. Accessories (pocket squares, dupattas, jewelry) rejected from all roles.

Not in scope:
- accessory pairing (scarves, jewelry, shoes as add-ons)
- four-piece or layered combos beyond top+bottom+outerwear

### Assembly behavior

For `complete` directions:
- each retrieved product is already an outfit candidate

For `paired` directions:
- combine top-query results with bottom-query results
- run deterministic compatibility pruning before LLM evaluation

### Deterministic pairing rules

All compatibility checks are implemented and enforced:

**Formality compatibility matrix** (rejects if not compatible):

| Level | Compatible with |
|---|---|
| `casual` | casual, smart_casual |
| `smart_casual` | casual, smart_casual, business_casual |
| `business_casual` | smart_casual, business_casual, semi_formal |
| `semi_formal` | business_casual, semi_formal, formal |
| `formal` | semi_formal, formal, ultra_formal |
| `ultra_formal` | formal, ultra_formal |

**Color temperature compatibility** (penalty if incompatible, not hard reject):

| Temperature | Compatible with |
|---|---|
| `warm` | warm, neutral |
| `cool` | cool, neutral |
| `neutral` | warm, cool, neutral |

**Occasion compatibility**: requires exact match when both values present; rejects on mismatch.

**Pattern compatibility**: both patterned items incur a small penalty (0.05) but are not rejected. Solid + any pattern always passes.

**Volume compatibility**: rejects if both items are `oversized` (extreme volume conflict).

Pair score = average of top and bottom similarity scores, minus accumulated penalties. Score of 0.0 means rejection.

### Output

```python
class OutfitCandidate:
    candidate_id: str
    direction_id: str
    candidate_type: str          # complete | paired
    items: list[dict]            # each item carries: product_id, similarity, title, image_url, price, product_url, garment_category, garment_subtype, styling_completeness, primary_color, formality_level, occasion_fit, pattern_type, volume_profile, fit_type, silhouette_type, role (for paired)
    fashion_score: int  # 0–100, replaces assembly_score (May 3 2026, PR #30)
    assembly_notes: list[str]
```

### Candidate control

Limit paired combinations aggressively before evaluation.

Current implementation:
- retrieve per query (configurable, default `retrieval_count=12`)
- cap tops and bottoms each to 15 before cross-product
- keep top 30 assembled pairs max (`MAX_PAIRED_CANDIDATES = 30`)
- turn artifacts cap candidate summaries to 20 for persistence

## 10. Outfit Evaluator

### Purpose

Rank complete and paired outfit candidates against the user's body, color, style, and occasion needs.

### Input

- assembled outfit candidates
- combined context
- recommendation plan

### Evaluation payload

The evaluator builds a JSON payload for the LLM containing:
- `user_profile`: gender, height, waist, analysis_attributes, derived_interpretations, style_preference
- `live_context`: occasion, formality, specific_needs, followup_intent
- `conversation_memory`: persisted prior occasion, formality, follow-up count
- `previous_recommendations`: persisted summaries of prior recommendation candidates
- `previous_recommendation_focus`: the latest prior recommendation to compare against
- direction types: complete, paired, three_piece (per-direction, not plan-level)
- `candidates`: list of outfit candidates with full item metadata
- `candidate_deltas`: per-candidate comparison to the latest prior recommendation across 8 signals:
  - colors: `shared_colors`, `new_colors`
  - occasions: `preserves_occasion`, `occasion_shift`
  - roles: `preserves_roles`
  - formality: `formality_shift` (e.g. "casual→formal")
  - patterns: `shared_patterns`, `new_patterns`
  - volumes: `shared_volumes`, `new_volumes`
  - fits: `shared_fits`, `new_fits`
  - silhouettes: `shared_silhouettes`, `new_silhouettes`
- `body_context_summary`: extracted `height_category`, `frame_structure`, and `body_shape` for body-aware ranking

### Evaluation criteria

- body harmony (informed by `body_context_summary`)
- color suitability
- occasion appropriateness
- style-archetype fit
- risk-tolerance alignment
- comfort-boundary compliance
- specific-needs support
- pairing coherence for two-piece outfits

### Output

Return strict JSON.

```python
class EvaluatedRecommendation:
    candidate_id: str
    rank: int
    match_score: float
    title: str
    reasoning: str
    body_note: str
    color_note: str
    style_note: str
    occasion_note: str
    body_harmony_pct: int      # 0–100, evaluation criteria scores
    color_suitability_pct: int # 0–100
    style_fit_pct: int         # 0–100
    risk_tolerance_pct: int    # 0–100
    occasion_pct: int          # 0–100
    comfort_boundary_pct: int  # 0–100
    specific_needs_pct: int    # 0–100
    pairing_coherence_pct: int # 0–100
    classic_pct: int           # 0–100, style archetype scores
    dramatic_pct: int          # 0–100
    romantic_pct: int          # 0–100
    natural_pct: int           # 0–100
    minimalist_pct: int        # 0–100
    creative_pct: int          # 0–100
    sporty_pct: int            # 0–100
    edgy_pct: int              # 0–100
    item_ids: list[str]
```

The evaluator outputs two sets of percentage scores (all integers 0–100):
- **9 evaluation criteria scores** — how well the outfit fits this specific user. 5 always-evaluated (body harmony, color suitability, style fit, risk tolerance, comfort boundary) + 4 context-gated (pairing coherence, occasion, weather/time, specific needs) per the Phase 12B follow-ups (April 9 2026). Stored as raw scores (0-100) in the database; the 4 context-gated dimensions are stored as `null` when their gating condition is not met. Displayed in the **bottom semicircle** of the split polar bar chart as **raw evaluator scores** (no `analysis_confidence_pct` scaling — the chart reads what the evaluator actually output). Null/zero context-gated values are dropped from the chart entirely. Fallback path derives these from `fashion_score`.
- **8 style archetype scores** — how strongly the outfit expresses each archetype's aesthetic, based on garment characteristics not user preference (classic, dramatic, romantic, natural, minimalist, creative, sporty, edgy). Displayed in the **top semicircle** of the same split polar bar chart (not confidence-weighted).

Full evaluation output (all notes, all 16 `_pct` fields) is persisted in turn artifacts.

### Important rule

Rank by actual fit for this user, not by vector similarity score.

Similarity is retrieval input, not recommendation truth.

### Fallback behavior

If the LLM evaluator fails, the fallback ranks candidates by `fashion_score` (the LLM Rater's blended score). The fallback also generates synthetic reasoning notes. For follow-up intents, the fallback uses candidate-by-candidate deltas against the previous recommendation to explain color/silhouette shifts.

### Output normalization and validation

Server-side validation in `_normalize_evaluations()`:
- `match_score` is clamped to `[0.0, 1.0]`
- `item_ids` are validated against the actual product IDs in the candidate; invalid IDs are dropped, and if all are invalid the full candidate item set is substituted
- `rank` is re-assigned sequentially (1, 2, 3, ...) regardless of LLM output ordering
- Duplicate `candidate_id` entries are deduplicated (first occurrence wins)
- Invalid `candidate_id` values (not in the original candidate set) are silently dropped
- Empty note fields (`body_note`, `color_note`, `style_note`, `occasion_note`) are backfilled with generic defaults or, for follow-up turns, with contextual reasoning derived from candidate deltas against the previous recommendation

### Hard output cap

The evaluator returns a maximum of 5 evaluated recommendations, regardless of candidate pool size.

## 11. Response Formatter

### Purpose

Convert evaluated results into user-facing response structure.

### Output

```python
class RecommendationResponse:
    success: bool
    message: str
    response_type: str   # "recommendation" | "clarification"
    outfits: list[OutfitCard]
    follow_up_suggestions: list[str]
    metadata: dict
```

### Hard output cap

The response formatter caps output to a maximum of 3 outfits (`MAX_FORMATTED_OUTFITS = 3`).

### Outfit card rules

Each outfit card should contain:
- recommendation title
- per-product title, price, and "Buy Now" button (links to product URL when available)
- single split polar bar chart (Nightingale-style):
  - top semicircle: 8 archetype axes (classic, dramatic, romantic, natural, minimalist, creative, sporty, edgy) in purple
  - bottom semicircle: 5-9 fit/evaluation axes (dynamic per context-gating rules) in burgundy, raw evaluator scores
  - dashed horizontal divider through the centre
  - shared 0-100 grid rings + color-coded legend below the canvas
- one or more product cards
- virtual try-on image (optional, generated by the try-on stage)

### Chat UI: unified outfit PDP card (3-column layout)

This section describes the current chat UI outfit rendering, implemented in `modules/platform_core/src/platform_core/ui.py`.

#### Layout

**Recommendation cards** — 3-column body grid (`grid-template-columns: 100px 1fr 44%`):

| Section | Content | Behavior |
|---|---|---|
| **Header** (full width, `grid-column: 1/-1`) | Outfit title (left) + Like/Hide icons (right) + full stylist reasoning (no truncation) | Spans all columns above the 3-column body |
| **Thumbnail rail** (100px) | Vertical stack of clickable thumbnails | Click swaps hero; active thumb gets accent border |
| **Hero image** (flex) | Full-height display of selected thumbnail (`object-fit: contain`) | Default: virtual try-on when present, else first garment |
| **Info panel** (~44%) | Products + split polar bar chart | Scrollable if content overflows |

**Outfit check / garment evaluation cards** — 2-column layout (`grid-template-columns: 1fr 44%`):
- No thumbnail rail (hidden entirely, not appended to DOM)
- Hero shows the user's uploaded outfit photo (`tryon_image`)
- Info panel shows item names only (no price, no Buy Now — user's own clothes)
- Detected via `responseMetadata.primary_intent === "outfit_check" || "garment_evaluation"`

Mobile (`max-width: 900px`) — single column: header → hero image → info panel.

#### Info panel content (right column)

Per-product block (3-row layout per garment):
- Row 1: product title + source label (`YOURS` / `SHOP`)
- Row 2: `Rs. X` price in JetBrains Mono (hidden for wardrobe items)
- Row 3: `Buy Now` text-link + `Save` button (hidden for wardrobe items)
- Per-product wishlist: `POST /v1/products/{product_id}/wishlist` → persists to `catalog_interaction_history` with `interaction_type="save"`, heart fills on click

Split polar bar chart — top semicircle (archetypes, champagne `--signal`):
- Classic, Dramatic, Romantic, Natural, Minimalist, Creative, Sporty, Edgy

Split polar bar chart — bottom semicircle (evaluation criteria, oxblood `--accent`):
- Body, Color, Risk, Comfort (always) + Pairing, Occasion, Needs, Weather (context-gated)
- Raw evaluator scores — no profile confidence multiplication

#### Feedback behavior

- **Like** (heart icon, top-right header) — one-tap, sends `event_type: "like"` immediately, heart fills with `--accent`
- **Hide** (X icon, top-right header) — opens a feedback modal with reaction chips ("Too safe", "Not me", "Wrong color", "Weird pairing", "Too much") + freeform textarea + Submit/Cancel. On Submit: sends `event_type: "dislike"` with notes, removes the outfit from the carousel and advances to next card. If all outfits hidden, section is removed.
- When no `item_ids` exist (e.g. outfit check), feedback is recorded with a synthetic `outfit:{conversation_id}:{rank}` placeholder

#### Virtual try-on images

- Generated via Gemini `gemini-3.1-flash-image-preview` with `aspect_ratio="2:3"` (`ImageConfig`)
- Hero container: `max-height: 520px; object-fit: contain` — no stretching

#### Feedback persistence strategy

- UI action is outfit-level (one click per card)
- Backend fans out to one `feedback_events` row per garment in the outfit
- `recommendation_run_id` is nullable (agentic pipeline does not generate run IDs)
- Correlation via `conversation_id` + `turn_id` + `outfit_rank`
- `turn_id` and `outfit_rank` columns added to `feedback_events` via migration

#### Shared response contract (implemented)

- `platform_core.api_schemas.OutfitCard.tryon_image: str = ""`
- `platform_core.api_schemas.OutfitCard.body_harmony_pct: int = 0` *(always-evaluated)*
- `platform_core.api_schemas.OutfitCard.color_suitability_pct: int = 0` *(always-evaluated)*
- `platform_core.api_schemas.OutfitCard.style_fit_pct: int = 0` *(always-evaluated)*
- `platform_core.api_schemas.OutfitCard.risk_tolerance_pct: int = 0` *(always-evaluated)*
- `platform_core.api_schemas.OutfitCard.comfort_boundary_pct: int = 0` *(always-evaluated)*
- `platform_core.api_schemas.OutfitCard.occasion_pct: Optional[int] = None` *(context-gated on `live_context.occasion_signal`; Phase 12B follow-up April 9 2026)*
- `platform_core.api_schemas.OutfitCard.weather_time_pct: Optional[int] = None` *(context-gated on `weather_context` / `time_of_day`)*
- `platform_core.api_schemas.OutfitCard.specific_needs_pct: Optional[int] = None` *(context-gated on `specific_needs`)*
- `platform_core.api_schemas.OutfitCard.pairing_coherence_pct: Optional[int] = None` *(intent-gated: null for `garment_evaluation` / `style_discovery` / `explanation_request`)*
- `platform_core.api_schemas.OutfitCard.classic_pct: int = 0`
- `platform_core.api_schemas.OutfitCard.dramatic_pct: int = 0`
- `platform_core.api_schemas.OutfitCard.romantic_pct: int = 0`
- `platform_core.api_schemas.OutfitCard.natural_pct: int = 0`
- `platform_core.api_schemas.OutfitCard.minimalist_pct: int = 0`
- `platform_core.api_schemas.OutfitCard.creative_pct: int = 0`
- `platform_core.api_schemas.OutfitCard.sporty_pct: int = 0`
- `platform_core.api_schemas.OutfitCard.edgy_pct: int = 0`
- `platform_core.api_schemas.OutfitItem.formality_level: str = ""`
- `platform_core.api_schemas.OutfitItem.occasion_fit: str = ""`
- `platform_core.api_schemas.OutfitItem.pattern_type: str = ""`
- `platform_core.api_schemas.OutfitItem.volume_profile: str = ""`
- `platform_core.api_schemas.OutfitItem.fit_type: str = ""`
- `platform_core.api_schemas.OutfitItem.silhouette_type: str = ""`
- `platform_core.api_schemas.FeedbackRequest` — `outfit_rank: int`, `event_type: str` (regex `^(like|dislike)$`), `notes: str = ""`, `item_ids: List[str] = []`

#### Response formatter (implemented)

- `_build_item_card()` passes through all 16 fields including the 6 enrichment attributes
- `response.metadata["turn_id"]` is injected by the orchestrator after formatting
- `_build_message()` reads the style archetype from the plan's query documents via `_extract_plan_archetype()` (regex on `style_archetype_primary`), falling back to the user profile's `primaryArchetype` only if the plan does not specify one — this ensures the response message reflects the actual style used in the plan, not the saved profile default

## 11.5. Virtual Try-on

### Purpose

Generate photorealistic virtual try-on images showing the user wearing recommended garments.

### Model

`gemini-3.1-flash-image-preview` via Google Gemini API (direct API key, not Vertex AI).

### Flow

1. Load user's `full_body` image from onboarding uploads via `OnboardingGateway.get_person_image_path()`
2. For each outfit (max 3), extract the first product image URL
3. Send both images with a structured prompt to Gemini (parallel execution via `ThreadPoolExecutor`, max 3 workers)
4. Attach returned try-on image as base64 `data_url` on the `OutfitCard.tryon_image` field
5. UI renders try-on image as the default hero in the 3-column outfit PDP card

### Prompt

The try-on prompt is maintained in `prompt/virtual_tryon.md`. Key principles:
- Person's body is treated as immutable geometry — body shape, proportions, and silhouette must not change
- Only the clothing is replaced with the target garment
- Preserves pose, camera perspective, background, and lighting
- Garment adapts to the body, not the other way around

### Image handling

- Images are resized to max 1024px on longest side before sending (Pillow/LANCZOS)
- Each image is explicitly labeled in the content array ("This is the PERSON photo" / "This is the TARGET GARMENT")
- Response modalities are set to `["IMAGE"]` only (no text fallback)

### Current presentation

The UI uses `OutfitCard.tryon_image` as the default hero image inside the unified 3-column outfit PDP card. It is the last thumbnail in the rail and selected by default when present. Clicking any thumbnail swaps the hero image without re-rendering the conversation.

### Configuration

- `GEMINI_API_KEY` environment variable required (from Google AI Studio)
- Client is lazy-initialized — missing key does not break app startup, only fails on actual try-on call
- Graceful degradation: if try-on fails for an outfit, the outfit is still returned without a try-on image

## 12. Conversation State

### Persist per turn

- raw user message
- resolved live context
- architect output
- applied hard filters
- retrieved product ids
- assembled outfit candidates
- final recommendations

### Follow-up handling

Supported intents in v1:
- `increase_boldness`
- `decrease_formality`
- `increase_formality`
- `change_color`
- `full_alternative`
- `more_options`
- `similar_to_previous`

Current implementation note:
- all intents are detected, persisted, and have structured runtime effect across architect, assembler, evaluator, and response formatter
- `change_color` preserves non-color dimensions (occasion, formality, garment subtypes, silhouette, volume, fit) while shifting colors; assembler penalizes color overlap with previous recommendation; evaluator and formatter provide intent-specific notes and messaging
- `similar_to_previous` preserves all dimensions from previous recommendation; assembler boosts occasion and color matches; evaluator reports all shared dimensions; formatter provides similarity-aware messaging
- persisted recommendation summaries carry all 8 signal dimensions for follow-up delta computation

## Runtime Testing

Start the active app runtime:

```bash
APP_ENV=local python3 run_agentic_application.py --reload --port 8010
```

Run the targeted smoke flow:

```bash
USER_ID=your_completed_user_id bash ops/scripts/smoke_test_agentic_application.sh
```

Run automated tests:

```bash
python3 -m pytest tests/ -v
```

Focused suites used for the application layer:

```bash
python3 -m pytest tests/test_agentic_application.py -v
python3 -m pytest tests/test_agentic_application_api_ui.py -v
```

### Follow-up rule

Follow-up requests should operate on persisted prior recommendations, not only on text history.

## 13. Error Handling

### Error categories

- profile missing
- profile incomplete
- architect failed
- embedding failed
- retrieval failed
- no results
- evaluator failed

### Graceful degradation

If architect fails:
- return an error to the user ("I'm having trouble processing your request right now. Please try again.")
- log the error with `latency_ms` and `status="error"` to `model_call_logs`
- do NOT silently fall back to a deterministic plan

If evaluator fails:
- return a simpler deterministic ranking using `fashion_score`
- generate synthetic reasoning notes from candidate deltas

If no results:
- return with empty outfits — no filter relaxation is performed

### Filter policy

No filter relaxation in v1. Each query executes a single search pass with the merged hard filters. If a query returns insufficient results, it is not retried.

Hard rule:
- never relax `gender_expression`
- `styling_completeness` is direction-defining and remains stable

## 14. Profile Validation

Minimum required profile for recommendation:
- `gender`
- `SeasonalColorGroup`
- `SeasonalColorGroup` includes `dimension_profile` (warmth/depth/contrast/chroma scores) and `SubSeason` for 12-sub-season classification
- `BaseColors`, `AccentColors`, `AvoidColors` are derived from the sub-season palette with boundary blending when confidence is low
- `style_preference.primaryArchetype`

The system should degrade gracefully with partial body or detail attributes.

## 15. Performance Targets

Target latency:

```text
Profile load              < 50ms
Context resolution        < 10ms
Context gate              < 1ms   (rule-based, no LLM)
Outfit Architect          < 3000ms
Query embedding           < 200ms
Vector retrieval          < 150ms
Assembly                  < 50ms
Outfit Evaluator          < 5000ms
Formatting                < 10ms
Virtual Try-on (parallel) < 8000ms  (3 outfits in parallel)

Target total              < 17000ms (with try-on)
Target total              < 9000ms  (without try-on)
```

## 16. Implementation Sequence

### Step 1

Build:
- `user_context_builder.py`
- `occasion_resolver.py`

### Step 2

Build:
- `outfit_architect.py`

Return strict JSON with:
- complete directions
- paired directions
- structured query documents

### Step 3

Build:
- `catalog_search_agent.py`

Use:
- `catalog_item_embeddings`
- `catalog_enriched`
- `1536`-dim query embeddings

### Step 4

Build:
- `outfit_composer.py`, `outfit_rater.py` (LLM ranker; replaced `outfit_assembler.py` + `reranker.py` in May 3 2026 PR #30)

Support:
- complete outfit passthrough
- top+bottom pairing

### Step 5

Build:
- ~~`outfit_evaluator.py`~~ *(removed April 9, 2026 — VisualEvaluatorAgent is the sole evaluator)*

Return:
- ranked recommendations
- reasoning notes

### Step 6

Build:
- `formatter.py`

### Step 7

Integrate into:
- `agentic_application`

Then remove any remaining migration wrappers and keep shared runtime infrastructure in `platform_core`.

## 17. Async Turn Processing

The API supports two modes of turn processing:

### Synchronous

`POST /v1/conversations/{id}/turns` — blocks until the full pipeline completes, returns the result inline.

### Asynchronous (job-based)

`POST /v1/conversations/{id}/turns/start` — returns a `job_id` immediately, runs the pipeline in a background thread.

`GET /v1/conversations/{id}/turns/{job_id}/status` — polls for job completion with stage-by-stage progress events.

Stages emitted during async processing:
1. `validate_request`
2. `user_context`
3. `context_builder`
4. `context_gate` — may short-circuit here with `insufficient` (returns clarification response)
5. `outfit_architect`
6. `catalog_search`
7. `outfit_composer` (LLM ranker — replaced `outfit_assembly` May 3 2026)
8. `outfit_rater` (LLM ranker — replaces the deterministic reranker)
9. `visual_evaluation` (replaced `outfit_evaluation` May 3 2026; `confidence_gate` may emit `blocked` here)
10. `response_formatting`
11. `virtual_tryon`

Each stage emits `started` and `completed` (or `failed` / `insufficient` / `sufficient`) events with timestamps.

## 18. API Endpoint Inventory

### Application endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Smart home — routes to onboarding, processing, or chat UI based on user state |
| GET | `/onboard` | Onboarding wizard UI |
| GET | `/onboard/processing` | Analysis processing UI |
| GET | `/admin/catalog` | Catalog admin UI |
| GET | `/healthz` | Health check |
| POST | `/v1/conversations` | Create a new conversation |
| GET | `/v1/conversations/{id}` | Get conversation state |
| POST | `/v1/conversations/{id}/turns` | Synchronous turn processing |
| POST | `/v1/conversations/{id}/turns/start` | Async turn job start |
| GET | `/v1/conversations/{id}/turns/{job_id}/status` | Async turn job status |
| POST | `/v1/tryon` | Standalone virtual try-on (fallback endpoint) |
| POST | `/v1/conversations/{id}/feedback` | Outfit feedback (like/dislike with optional notes) |

#### Feedback endpoint detail

`POST /v1/conversations/{id}/feedback`
- accepts `FeedbackRequest`: `outfit_rank: int`, `event_type: str` (like/dislike, regex-validated), `notes: str = ""`, `item_ids: List[str] = []`
- looks up latest turn for the conversation to resolve `turn_id` and `user_id`
- if `item_ids` not provided, resolves garment IDs from the outfit at the given rank in the turn's `final_recommendations`
- inserts one `feedback_events` row per garment (same event_type/notes for all, reward +1 for like, -1 for dislike)
- `recommendation_run_id` is NULL (agentic pipeline doesn't use run IDs)
- returns `{ "ok": true, "count": N }`

### Onboarding endpoints (mounted via onboarding gateway)

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/onboarding/send-otp` | Send OTP to mobile |
| POST | `/v1/onboarding/verify-otp` | Verify OTP, create user if new |
| POST | `/v1/onboarding/profile` | Save profile (name, DOB, gender, height, waist, profession) |
| POST | `/v1/onboarding/images/normalize` | Normalize image for 3:2 crop |
| POST | `/v1/onboarding/images/{category}` | Upload image (full_body, headshot) |
| GET | `/v1/onboarding/style-archetype-session` | Load style archetype selection UI |
| POST | `/v1/onboarding/style-preference-complete` | Save style preference |
| POST | `/v1/onboarding/analysis/start` | Launch 3-agent analysis + deterministic interpretation |
| POST | `/v1/onboarding/analysis/status` | Check analysis completion |
| POST | `/v1/onboarding/analysis/rerun` | Rerun specific analysis agent |

### Catalog admin endpoints (mounted via catalog admin router)

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/admin/catalog/upload` | Upload CSV file |
| GET | `/v1/admin/catalog/status` | Catalog sync status + job counts + recent job history |
| POST | `/v1/admin/catalog/items/sync` | Sync enriched catalog rows (supports `start_row`/`end_row` for selective rerun) |
| POST | `/v1/admin/catalog/items/backfill-urls` | Backfill missing product URLs |
| POST | `/v1/admin/catalog/embeddings/sync` | Generate and sync embeddings (supports `start_row`/`end_row` for selective rerun) |

All sync operations (`items/sync`, `backfill-urls`, `embeddings/sync`) create a `catalog_jobs` row with lifecycle tracking (running → completed/failed). The `/status` endpoint returns `total_jobs`, `running_jobs`, `failed_jobs` counts and a `recent_jobs` list. The admin UI renders a job history table with status pills, params, row counts, and truncated error messages.

## 19. Final v1 Definition of Done

The Application Layer is considered complete for v1 when:

- user message intake is active
- saved profile context is loaded correctly
- live context is resolved deterministically
- architect returns structured JSON directions
- retrieval supports both complete outfits and pairing
- assembler builds top+bottom combinations
- evaluator ranks complete and paired candidates
- formatter returns up to 3 outfit recommendations
- virtual try-on generates inline try-on images for each outfit
- follow-up requests refine prior recommendations
- runtime is owned by `modules/agentic_application`
- `platform_core` holds shared runtime infrastructure; `agentic_application` is the canonical application module

All features complete — no outstanding blockers.

---

# Live System Reference (May 6, 2026)

_Migrated from `CURRENT_STATE.md` on May 3, 2026. Refreshed May 6, 2026 to reflect the post-PR-#101 system (6-dim 1/2/3 rater, episodic memory at the architect, source_preference→catalog default, composer-emitted card names). This is the authoritative "what is running right now" view that other docs delegate to. The historical decision-log (Phase 9–15) lives at the bottom of `docs/WORKFLOW_REFERENCE.md`._

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


## Performance Optimization (May 3, 2026)

A trace audit on May 3, 2026 of the date-night turn for `user_03026279ecd6` measured 141.7 s end-to-end at $0.30 per turn. Three optimization levers were tried; two landed and shipped as the new default; the third was deprecated and removed.

### Shipped (default-on)

- **Lever 1 — Parallel Gemini try-on renders.** [orchestrator.py:_render_candidates_for_visual_eval](../modules/agentic_application/src/agentic_application/orchestrator.py) now runs the top-N candidate renders in a `ThreadPoolExecutor` batch instead of sequentially. The cache lookup and quality gate continue to work per-candidate inside each thread; over-generation pool fallback runs the next batch in parallel too. INFO logs surface batch-start / batch-end wallclocks so parallelism is provable from server stdout. **Saves time only when there are 2+ cold renders in a turn**; on cache-heavy repeat turns the visible win is smaller.
- **Lever 2 — Architect prompt trim + conditional assembly.** [prompt/outfit_architect.md](../prompt/outfit_architect.md) trimmed from 11.6K → 4.8K tokens. Anchor-garment rules and follow-up-intent rules moved to separate modules ([outfit_architect_anchor.md](../prompt/outfit_architect_anchor.md), [outfit_architect_followup.md](../prompt/outfit_architect_followup.md)) loaded at request time only when the turn actually needs them. **Reproducible: −5,574 input tokens, −3 s architect latency, −$0.04 architect cost per turn.**

### Deprecated and removed

- **Lever 3 — Architect split (Plan + parallel Query Builder).** Premise: parallel per-direction LLM calls would beat monolithic on wallclock by sending each call less input. Empirically wrong — output streaming time, not input size, dominates Stage B wallclock. Each call must emit 2–3 multi-section `query_document` strings totaling 2–3K tokens; at gpt-5-mini's ~100 tok/s that's 20–30 s per parallel call regardless of input size. Three iterations of `max_output_tokens` tightening produced either truncation crashes or no latency win. Removed from the codebase in PR #10 (May 3, 2026). See git history for the full series (`git log --grep "architect-split"`).

### Honest measured impact (Levers 1 + 2 only)

Same query, same user, same anchor garment, comparing the pre-opt baseline against a 3-outfit response with all renders cold (apples-to-apples — no cache benefit folded in):

| | Baseline | Post Levers 1+2 | Δ |
|---|---:|---:|---:|
| End-to-end latency | 141.7 s | ~118 s | −24 s (−17%) |
| Architect input tokens | 15,264 | 9,690 | −37% |
| Architect cost | $0.145 | $0.105 | −$0.040 (−28%) |
| Total cost (cold renders) | ~$0.30 | ~$0.26 | −$0.04 (−13%) |

A repeat-turn run (2 of 3 garment combos already in the per-user tryon image cache) measured 100.8 s / $0.15 — but that further reduction is the **pre-existing tryon cache**, not a benefit from this work.

### Lever 1 doesn't always show

Lever 1's win is conditional on **2+ cold renders in the same turn**. With heavy cache hits, it saves nothing extra over what the cache already gave you. The parallel-batch logging makes this directly visible — look for `tryon parallel batch: N/N succeeded (cold=K, cache_hit=M) in Xms wallclock` in the server logs. Sequential would show a wallclock ≈ sum of individual render times; parallel shows wallclock ≈ max.

### Lessons

1. **Output-volume scaling can dominate input-volume scaling for LLM latency.** Parallelizing across calls doesn't help when each one is output-bound. The Lever 3 design assumed the wrong constraint was binding.
2. **Prompt-level output budgets aren't enforceable.** "≤350 tokens per query_document" in the prompt didn't constrain output. Only `max_output_tokens` does — and that brings truncation risk that has to be handled.
3. **Cost-attribution telemetry must be per-model-call, not per-step.** Logging `outfit_architect` as one row at gpt-5.5 prices for tokens that mostly ran on gpt-5-mini overstated cost by ~10×.
4. **Cache compounds.** The per-user tryon image cache delivered the biggest single-turn cost saving in steady-state runs — without any new code.
5. **Ship behind a flag when uncertain.** Lever 3 looked good on paper, failed in practice, and was easy to roll back because it shipped behind `OUTFIT_ARCHITECT_MODE` and was always default-off.
6. **Honest measurement > stubborn projection.** When the math says X and measurement says ¬X, believe the measurement and document why the model was wrong.

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
- 3-agent analysis pipeline (model: `gpt-5.5` since May 1, 2026 — was `gpt-5.4` before; reasoning effort: high, runs in parallel via `ThreadPoolExecutor`):
  1. `body_type_analysis` — uses full_body image → ShoulderToHipRatio, TorsoToLegRatio, BodyShape, VisualWeight, VerticalProportion, ArmVolume, MidsectionState, BustVolume
  2. `color_analysis_headshot` — uses headshot → SkinSurfaceColor, HairColor, HairColorTemperature, EyeColor, EyeClarity
  3. `other_details_analysis` — uses headshot + full_body → FaceShape, NeckLength, HairLength, JawlineDefinition, ShoulderSlope
- Each agent returns JSON with `{value, confidence, evidence_note}` per attribute
- Deterministic interpretation pipeline (`interpreter.py`) derives:
  - `SeasonalColorGroup` — 4-season → 12 sub-season color analysis (deterministic from weighted warmth, depth, chroma). Digital draping removed.
  - `BaseColors` — Foundation/neutral colors for outfit anchors (4-5 per season, e.g. Autumn: warm taupe, warm brown, olive, muted gold)
  - `AccentColors` — Statement/pop colors that complement the user's coloring (4-5 per season, e.g. Autumn: terracotta, rust, burgundy, forest green, burnt orange)
  - `AvoidColors` — Colors that clash with the user's natural coloring (4-5 per season, e.g. Autumn: icy blue, fuchsia, royal blue, stark white, silver)
  - `HeightCategory` — Petite (<160cm) / Average (160-175cm) / Tall (>175cm)
  - `WaistSizeBand` — Very Small / Small / Medium / Large / Very Large
  - `ContrastLevel` — Low / Medium-Low / Medium / Medium-High / High (from depth spread across skin, hair, eyes)
  - `FrameStructure` — Light and Narrow / Light and Broad / Medium and Balanced / Solid and Narrow / Solid and Broad
- ~~**Digital draping**~~ (`user/draping.py` deleted) — was LLM-based 3-round vision chain, removed due to systematic cool-bias:
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
- verification basis: **458 L0 tests** in `tests/` (May 6, 2026 post-PR-#101) cover orchestrator routing, the planner→architect→search→composer→rater→tryon→format pipeline, wardrobe-first short-circuits with the ≥2-per-role coverage gate, hybrid pivot, disliked-product suppression, cross-outfit diversity, episodic memory hydration, the R7 6-dim 1/2/3 rater contract, and metadata persistence. Live verification against a staging Supabase + real catalog embeddings is governed by the gates in `docs/RELEASE_READINESS.md`.

Implemented:
- orchestrated recommendation pipeline with LLM copilot planner front-end
- **copilot planner** (`gpt-5-mini`) classifies intent and decides action — replaces legacy keyword router + context gate
- **intent registry** (`intent_registry.py`): 6 intents (`occasion_recommendation`, `pairing_request`, `style_discovery`, `explanation_request`, `feedback_submission`, `wardrobe_ingestion`) and 5 actions (`run_recommendation_pipeline`, `respond_directly`, `ask_clarification`, `save_wardrobe_item`, `save_feedback`) via Python `StrEnum` — consumed by planner, orchestrator, agents, API, and tests. The Phase 12A consolidation collapsed the previous 12-intent + 9-action taxonomy.
- **source_preference routing** (PR #82, May 5 2026): planner sets `resolved_context.source_preference` to one of `"auto"` (default — routes to catalog), `"wardrobe"` (explicit), or `"catalog"` (explicit). Wardrobe-first only fires on `"wardrobe"`; auto and catalog both run the full catalog pipeline. When wardrobe-first IS requested, the orchestrator gates on a strict-AND minimum-coverage check: ≥2 tops AND ≥2 bottoms AND ≥2 one-pieces. Below that, falls through to a `wardrobe_unavailable` answer-source with the actual counts surfaced ("you have 2 tops, 2 bottoms, 0 dresses"). Metadata exposes a `wardrobe_coverage` block.
- **outfit architect** — LLM-only, no deterministic fallback (model: `gpt-5.4`, `reasoning_effort=medium`)
- strict JSON schema with enum-constrained hard filter vocabulary
- hard filters: `gender_expression` (always), `garment_subtype` (conditional — only when user names a specific garment type); `garment_category` and `styling_completeness` are **soft signals** in the query document text only
- soft signals via embedding only: `occasion_fit`, `formality_level`, `time_of_day`
- direction-aware retrieval: `complete` / `paired` (top + bottom) / `three_piece` (top + bottom + outerwear)
- **episodic memory** (PR #90 / #92 / #93, May 5 2026): the architect's input includes `recent_user_actions` — a chronological 30-day timeline of like/dislike events. Each row carries the `user_query` that produced the outfit and the garment's full attribute set. The architect prompt instructs the LLM to find context-dependent patterns (different occasions can take the same attribute differently) and bias retrieval queries — never as blanket exclusions. Loaded via `ConversationRepository.list_recent_user_actions(user_id, lookback_days=30)`.
- **outfit composer** (PR #30 May 3 + PR #81 + PR #88, model: `gpt-5.4`, `reasoning_effort=low`): builds up to 10 coherent outfits from the retrieved pool, each one-shot with one item per role. Emits a per-outfit stylist-flavored `name` (e.g. *"Camel Sand Refined"*, *"Sharp Navy Boardroom"*) that surfaces directly as the user-facing card title (PR #88). Schema enforces `direction_id` is one of the architect's letters (PR #80 dynamic enum); per-attempt logging via `on_attempt` callback puts one `model_call_logs` row per LLM call (PR #80) with real `latency_ms` (PR #95).
- **outfit rater** (PR #30 + R7 in PR #101, May 5 2026, model: `gpt-5-mini`, `reasoning_effort=minimal`): scores each composed outfit on **six dimensions** — `occasion_fit`, `body_harmony`, `color_harmony`, `pairing` (fit + fabric only, post-R7), `formality` (request match + inter-item consistency, new in R7), `statement` (pattern density + embellishment intensity, new in R7) — each on a **1/2/3 scale** (1=clear miss, 2=works, 3=clear win). Schema enforces the enum. `unsuitable=True` is a hard veto; the archetypal-preferences veto was removed in PR #89. Past likes/dislikes are applied upstream by the Architect (retrieval bias) and Composer (item-selection bias); the Rater scores what's in front of it on its own merits.
- **fashion_score blend** in Python via `compute_fashion_score`: `raw = Σ subscore × weight` (1.0..3.0), then `score = ((raw − 1) / 2) × 100` (0..100). Five weight profiles — `default`, `ceremonial`, `slimming`, `bold`, `comfortable` — picked by `select_weight_profile()` from planner-resolved context. All sum to 1.0. For `complete` (single-item) outfits the `pairing` dim drops and the remaining five weights renormalize.
- **threshold gate** at `_RECOMMENDATION_FASHION_THRESHOLD = 50` (PR #101, was 60 pre-R7, 75 pre-#81): outfits below the floor or flagged `unsuitable=True` never reach the user. An outfit at 2 across the board lands at exactly 50 (every dim at least neutral barely clears).
- response formatting (max 3 outfits) and UI rendering support
- **virtual try-on** via Gemini (`gemini-3.1-flash-image-preview`), top-3 candidates rendered in parallel via `ThreadPoolExecutor`, persistent storage to disk + DB with cache reuse by garment-ID set
- turn artifact persistence: full Composer + Rater raw responses to `model_call_logs.response_json`; per-outfit sub-scores to `tool_traces.rater_decision.output_json.ranked_outfits`
- dependency-validation instrumentation: turn-completion events on `dependency_validation_events`, referral events, retention reporting for first/second/third session behavior

Main remaining gaps:
- see `docs/OPEN_TASKS.md` for the running list


## Application Layer: Current Behavioral Reality

Current execution order:
1. load user context (profile, derived interpretations, wardrobe items)
2. build conversation memory from prior turn state
3. **copilot planner** (gpt-5-mini) — classifies intent + action; resolves `source_preference` (`auto` | `wardrobe` | `catalog`)
4. action dispatch — if `respond_directly` or `ask_clarification`, return planner response directly (skip stages 5–11)
5. **wardrobe-first short-circuit** — only fires when `source_preference == "wardrobe"` AND wardrobe meets the ≥2-per-role coverage gate (PR #82). Below the gate falls through to `wardrobe_unavailable` fallback with counts surfaced.
6. **outfit architect** (gpt-5.4, reasoning_effort=medium) — generates the recommendation plan; reads `recent_user_actions` (30-day episodic timeline, PR #90) to bias retrieval queries by context-dependent patterns. No deterministic fallback; failure = error to user.
7. retrieve catalog products per query direction (text-embedding-3-small + pgvector cosine, single search pass)
8. **outfit composer** (gpt-5.4, reasoning_effort=low) — constructs up to 10 coherent outfits from the retrieved pool; emits per-outfit `name` (PR #88) as the user-facing card title. One LLM call; on hallucinated item_ids the composer retries once with a stricter suffix (PR #80 smart retry).
9. **outfit rater** (gpt-5-mini, reasoning_effort=minimal) — scores each composed outfit on the six 1/2/3 dimensions. Computes `fashion_score` (0–100) in Python via `compute_fashion_score` with the planner-selected weight profile. Hard veto via `unsuitable=True` (rare); no archetypal-preferences veto post-PR-#89.
10. **threshold gate** at fashion_score ≥ 50 — pre-render filter so we don't burn Gemini renders on outfits the gate would drop.
11. **virtual try-on** (gemini-3.1-flash-image-preview, parallel) — top-3 by fashion_score; checks cache by user + garment IDs first; saves new results to disk + `virtual_tryon_images` table
12. format response payload (max 3 outfits with rater dims rescaled 1/2/3 → 0/50/100 for the radar `_pct` fields)
13. persist turn artifacts and updated conversation context

Current supported direction types (architect output):
- `complete` — single query, role=complete (kurta_set, suit_set, dress, jumpsuit)
- `paired` — two queries: role=top + role=bottom
- `three_piece` — three queries: role=top + role=bottom + role=outerwear (blazer, nehru_jacket, jacket)

Current follow-up support (planner-detected, persisted, structurally honored):
- `increase_boldness` · `decrease_formality` · `increase_formality` · `change_color` · `full_alternative` · `more_options` · `similar_to_previous`

Current nuance:
- All follow-up intents are detected, persisted, and have structured runtime effect across architect + composer + response formatter.
- `change_color`: architect preserves non-color dimensions while shifting colors; formatter opens with "fresh color direction" and shows intent-specific follow-up chips.
- `similar_to_previous`: architect preserves all dimensions from previous recommendation; formatter opens with "similar style".
- **Rater output (R7, PR #101)**: per-outfit row carries `composer_id`, `rank`, computed `fashion_score` (0–100), six 1/2/3 sub-scores (`occasion_fit`, `body_harmony`, `color_harmony`, `pairing`, `formality`, `statement`), `rationale` (two short sentences, stylist-to-stylist register), `unsuitable` flag.
- **OutfitCard radar dims** (post-R7): six `_pct` fields rescaled from 1/2/3 sub-scores via `((value − 1) / 2) × 100` → values land at 0, 50, or 100. UI renders a 6-axis hexagon (5-axis pentagon for `complete` outfits where `pairing_pct=None`). The legacy 8-axis archetype + 8-axis evaluation radar (visual_evaluator output) was removed in V2.
- Full Composer + Rater raw response is persisted in `model_call_logs.response_json`; distilled per-outfit decision in `tool_traces.{composer_decision, rater_decision}.output_json` for offline replay + ops queries.


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
- direction hard filters: `styling_completeness` — role-specific values: `complete` for complete directions, `needs_bottomwear` for top role (all direction types), `needs_topwear` for bottom role, `["needs_innerwear"]` for outerwear role. Outerwear items are exclusively discoverable via the outerwear role — never in top or bottom.
- architect explicit hard_filters: `garment_subtype` (conditional — set for specific requests, null for broad)
- query-document lines are **soft signals for embedding similarity only** — `_QUERY_FILTER_MAPPING` is empty; no hard filters extracted from query document text (April 9 2026)
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
- `OutfitCard.title` = the composer-emitted per-outfit `name` (PR #88, e.g. *"Camel Sand Refined"*); falls back to `f"Outfit {rank}"` only if the LLM somehow omitted the field
- `OutfitCard` carries **six rater `_pct` fields** (post-R7 PR #101): `occasion_pct`, `body_harmony_pct`, `color_suitability_pct`, `pairing_pct`, `formality_pct`, `statement_pct` — each rescaled from the 1/2/3 rater sub-score (1→0, 2→50, 3→100). Plus `fashion_score_pct` (0–100, blended in code via `compute_fashion_score`). Rendered as a 6-axis hexagon radar; `pairing_pct=None` for `complete` (single-item) outfits drops the axis → 5-axis pentagon.
- `response.metadata` includes `turn_id` for feedback correlation
- both internal (`agentic_application/schemas.py`) and shared (`platform_core/api_schemas.py`) schemas are aligned on the six-dim contract


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
- evaluator has graceful fashion_score fallback
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
- 3-agent parallel analysis pipeline (body type, color, other details) via gpt-5.5
- ~~digital draping~~ — removed (was 3-round LLM vision chain, replaced by deterministic 12-sub-season interpreter)
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
- intent registry (`intent_registry.py`) — StrEnum single source of truth for **8 Intent members** (7 advisory + 1 silent `wardrobe_ingestion`), **7 Actions**, **7 FollowUpIntents**. Phase 12A consolidated the prior 12-intent / 9-action taxonomy: `shopping_decision` / `garment_on_me_request` / `virtual_tryon_request` folded into `garment_evaluation`; `product_browse` folded into `occasion_recommendation` (via `target_product_type`); `capsule_or_trip_planning` deferred.
- copilot planner (gpt-5-mini) — intent classification across the 7 advisory intents (`wardrobe_ingestion` is silent / not exposed in the planner prompt), 7-action dispatch
- recommendation pipeline: architect → catalog search → assembly → evaluation → formatting → try-on
- wardrobe-first occasion response (wardrobe retrieval + selection for occasion intents)
- wardrobe item save from chat with moderation
- virtual try-on via Gemini (gemini-3.1-flash-image-preview), parallel generation, quality gate, persistent disk + DB storage with cache reuse
- 3-column PDP outfit cards with Buy Now, single split polar bar chart (8 archetypes top + dynamic 4-7 fit dimensions bottom), icon feedback
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

See "Recently Completed Roadmap Items" in the gap analysis in `docs/PRODUCT.md`. Current open items are tracked in `docs/OPEN_TASKS.md`. The legacy P0/P1/P2 sections earlier in this file are historical and all marked complete or removed; there is no additional summary to call out here.


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
- `user_analysis_snapshots` — `draping_output` column exists but no longer written (draping removed)
- `user_interpretation_snapshots` — draping columns (`seasonal_color_distribution`, `seasonal_color_groups_json`, `seasonal_color_source`, `draping_chain_log`) exist but no longer written. New columns: `sub_season_*`, `skin_hair_contrast_*`, `color_dimension_profile_*`, `confidence_margin`
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
│   │   ├── copilot_planner.py   # LLM intent classification + action routing (gpt-5-mini)
│   │   ├── outfit_architect.py   # LLM planning (gpt-5.5)
│   │   ├── catalog_search_agent.py # Embedding search + hydration
│   │   ├── outfit_composer.py    # LLM outfit constructor (replaced outfit_assembler.py in PR #30)
│   │   ├── outfit_rater.py       # LLM outfit scorer (replaced reranker.py in PR #30)
│   │   ├── visual_evaluator_agent.py # Visual ranking (gpt-5-mini, vision input)
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
│   ├── (draping.py deleted)      # Was digital draping — removed
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


## Copilot Execution Rule

For the next implementation phase, `docs/PRODUCT.md` § "Current Gap Versus Target State" is the execution source of truth.

Operating rule:
- every meaningful implementation change should map to one checklist item below
- before starting a new major implementation slice, check the next incomplete item in this document
- after completing a slice, update the checklist state here
- do not treat ad hoc chat plans as canonical when they diverge from this file

