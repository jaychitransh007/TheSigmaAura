# Application Layer — Implementation Specification

Last updated: March 16, 2026

## Current Implementation Status

This document is both the target v1 contract and the current implementation reference for `modules/agentic_application`.

Implemented now:
- active runtime entrypoint in `agentic_application/api.py` with `AgenticOrchestrator`
- saved user-context loading from onboarding/profile-analysis/style-preference persistence
- rule-based live-context extraction with phrase-priority matching
- server-side conversation-memory carry-forward across follow-up turns
- LLM-only planning via Outfit Architect (gpt-5.4) — no deterministic fallback
- concept-first paired planning handled entirely by the LLM (color coordination, volume balance, pattern distribution)
- strict JSON schema with enum-constrained hard filter vocabulary (no free-form filter values)
- hard filters: `gender_expression`, `styling_completeness`, `garment_category`, `garment_subtype`
- soft signals via embedding similarity only: `occasion_fit`, `formality_level`, `time_of_day`
- no filter relaxation — single search pass per query, no retry with dropped filters
- embedding retrieval from `catalog_item_embeddings` with hydration from `catalog_enriched`
- direction-aware retrieval: `needs_bottomwear` for tops, `needs_topwear` for bottoms, `complete` for complete outfits
- deterministic assembly and LLM evaluation with graceful evaluator fallback
- architect failure returns error to user (no silent degradation)
- latency tracking via `time.monotonic()` on architect, search, and evaluator (persisted as `latency_ms`)
- persisted turn artifacts: live context, memory, plan, applied filters, retrieved IDs, assembled candidates, final recommendations
- response formatting for `outfits` (max 3 outfits)
- virtual try-on via Gemini (`gemini-3.1-flash-image-preview`) with parallel image generation, inline UI rendering
- canonical product URL persistence during catalog ingestion, with runtime product links resolved from persisted canonical URLs
- catalog admin and ops support URL backfill for older `catalog_enriched` rows that still lack canonical product URLs

Still incomplete:
- evaluator still needs stronger prompt/server-side validation beyond the current persisted-memory and delta payloads
- follow-up refinement for `change_color` and `similar_to_previous` now uses persisted recommendation attributes, with remaining work focused on deeper rule expansion rather than missing execution
- application boundaries are cleaner now, but `onboarding` and `catalog_retrieval` are still mediated through gateway modules rather than fully consolidated domain ownership
- evaluator fallback behavior is not yet perfectly aligned with the documented degradation contract

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
| Outfit Architect | `gpt-5.4` | OpenAI | JSON schema (strict) |
| Outfit Evaluator | `gpt-5.4` | OpenAI | JSON schema (strict) |
| Orchestrator (intent + memory) | `gpt-5.4` | OpenAI | JSON schema (strict) |
| User Profiler (visual) | `gpt-5.4` | OpenAI | JSON schema (strict), reasoning effort: high |
| User Profiler (textual) | `gpt-5.4` | OpenAI | JSON schema (strict) |
| User Analysis (onboarding) | `gpt-5.4` | OpenAI | JSON schema (strict), reasoning effort: high |
| Query Embedding | `text-embedding-3-small` | OpenAI | 1536-dimensional vector |
| Virtual Try-on | `gemini-3.1-flash-image-preview` | Google | Image generation |
| Catalog Enrichment | `gpt-5-mini` | OpenAI | JSON schema |

Architect, evaluator, orchestrator, and profiler use OpenAI's `json_schema` response format with strict validation. The architect has no fallback — failure returns an error to the user. The evaluator has a graceful fallback that ranks by assembly_score. Virtual try-on uses Google Gemini with direct API key authentication (not Vertex AI / service accounts).

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
    +--> 2. Occasion Resolver (rule-based, no LLM)
    |
    +--> 3. Conversation Memory (build + apply from session_context_json)
    |
    v
4. Outfit Architect (gpt-5.4, JSON schema)
    |
    v
5. Catalog Search Agent
    |    +--> text-embedding-3-small (1536 dim)
    |    +--> catalog_item_embeddings (pgvector cosine)
    |    +--> catalog_enriched (hydration)
    |    +--> Hard filters: gender_expression, styling_completeness, garment_category, garment_subtype
    |    +--> No filter relaxation — single search pass per query
    |
    v
6. Outfit Assembler (deterministic compatibility pruning)
    |
    v
7. Outfit Evaluator (gpt-5.4, JSON schema, fallback: assembly_score ranking)
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
    plan_type: str | None
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
- `last_plan_type` — `complete_only` / `paired_only` / `mixed`
- `last_recommendations` — enriched recommendation summaries (colors, garment categories, subtypes, roles, occasion fits, formality levels, pattern types, volume profiles, fit types, silhouette types)
- `last_occasion` — resolved occasion signal
- `last_live_context` — full live context snapshot
- `last_response_metadata` — response metadata dict

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

### Hard filters

Global hard filters:
- `gender_expression` (derived from user gender: male → masculine, female → feminine)

Direction-specific hard filters:
- complete outfit directions use `styling_completeness = complete`
- paired top directions use `styling_completeness = needs_bottomwear`
- paired bottom directions use `styling_completeness = needs_topwear`

Query-document-extracted hard filters (server-side extraction from architect output):
- `garment_category`
- `garment_subtype`

NOT hard filters (soft signals via embedding similarity only):
- `occasion_fit`
- `formality_level`
- `time_of_day`

No filter relaxation — single search pass per query. If a query returns insufficient results, it is not retried with dropped filters.

Valid hard filter vocabulary (enforced in architect JSON schema):

| Filter key | Valid values |
|---|---|
| `styling_completeness` | `complete`, `needs_bottomwear`, `needs_topwear`, `needs_innerwear`, `dual_dependency` |
| `garment_category` | `top`, `bottom`, `set`, `one_piece`, `outerwear` |
| `garment_subtype` | `shirt`, `tshirt`, `blouse`, `sweater`, `sweatshirt`, `hoodie`, `cardigan`, `tunic`, `kurta_set`, `trouser`, `pants`, `jeans`, `track_pants`, `shorts`, `skirt`, `dress`, `gown`, `saree`, `anarkali`, `kaftan`, `playsuit`, `salwar_set`, `salwar_suit`, `co_ord_set`, `blazer`, `jacket`, `coat`, `shacket` |
| `gender_expression` | `masculine`, `feminine`, `unisex` |

Important:
- for v1, do not globally force complete outfits
- pairing must be supported in v1

## 6. Orchestrator

### Purpose

Entry point for every recommendation request.

### Responsibilities

- load user context
- resolve live message context
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
    evaluated = await outfit_evaluator(candidates, combined, plan)
    response = format_response(evaluated, combined, plan)

    await persist_turn_state(request, combined, plan, retrieved, evaluated, response)
    return response
```

### Active runtime notes

- No filter relaxation — single search pass per query.
- `gender_expression` is always applied and never relaxed.
- Architect has no fallback — LLM failure returns an error to the user.
- Evaluator has a graceful fallback: ranks by `assembly_score` if LLM fails.
- Latency is tracked per agent via `time.monotonic()` and persisted as `latency_ms` on `model_call_logs` and `tool_traces`.

## 7. Outfit Architect

### Purpose

Translate user context into retrieval directions.

### Important design decision

The architect should not output freeform prose only. It should return JSON plus a structured labeled query document per direction.

### Output

```python
class RecommendationPlan:
    plan_type: str                 # complete_only | paired_only | mixed
    retrieval_count: int           # default 12 per query
    directions: list[DirectionSpec]
    plan_source: str               # always "llm" (no fallback)


class DirectionSpec:
    direction_id: str              # A | B | C
    direction_type: str            # complete | paired
    label: str
    queries: list[QuerySpec]


class QuerySpec:
    query_id: str
    role: str                      # complete | top | bottom
    hard_filters: dict
    query_document: str            # structured labeled retrieval doc
```

### V1 direction policy

Allowed:
- one complete-outfit direction
- one paired direction
- optionally both

Not allowed in v1:
- three-piece directions

### Concept-first paired planning

For paired directions, the architect LLM uses a concept-first approach as instructed by the system prompt:

1. **Define the outfit vision first**: The LLM decides the overall color scheme, volume balance, pattern distribution, and fabric story as one coherent concept.
2. **Decompose into role-specific queries**: The top query and bottom query have DIFFERENT, COMPLEMENTARY parameters derived from the concept.

Key concept rules (instructed in `prompt/outfit_architect.md`):

**Color coordination** — Top and bottom should have contrasting or complementary colors, NOT identical colors. Bottoms typically anchor with neutrals (navy, black, charcoal, olive, khaki). Tops carry the accent or statement color. Uses the user's SeasonalColorGroup palette.

**Volume balance** — Top and bottom should create visual balance. If one piece is relaxed/oversized, the other should be slim/fitted. Uses the user's FrameStructure to decide which piece gets more volume.

**Pattern distribution** — Typically ONE piece carries the pattern and the other is solid. Pattern usually goes on top unless the user requests otherwise. Both patterned only for high risk-tolerance users.

**Fabric coordination** — Formal → both structured. Smart casual → top relaxed, bottom structured. Casual → top relaxed, bottom balanced.

The paired top and bottom queries MUST have different PrimaryColor, VolumeProfile, PatternType, and FabricDrape values reflecting the coordinated outfit concept. This is enforced by the LLM prompt, not by deterministic code.

Complete outfit directions are NOT affected by the concept layer — they use uniform parameters.

### Query document format

The architect's `query_document` should mirror the catalog embedding representation:
- structured labeled sections
- consistent vocabulary
- not freeform paragraph-only output

Required sections:
- `USER_NEED`
- `PROFILE_AND_STYLE`
- `GARMENT_REQUIREMENTS`
- `FABRIC_AND_BUILD`
- `PATTERN_AND_COLOR`
- `OCCASION_AND_SIGNAL`

### Follow-up intent handling in planner

The architect receives enriched prior recommendation context via `combined_context.previous_recommendations`, which includes:
- `primary_colors`, `garment_categories`, `garment_subtypes`, `roles`
- `occasion_fits`, `formality_levels`, `pattern_types`, `volume_profiles`, `fit_types`, `silhouette_types`

Follow-up intent effects on planning:
- `increase_boldness` — shifts query vocabulary toward bolder choices
- `decrease_formality` / `increase_formality` — adjusts target formality
- `change_color` — rewrites styling goal away from persisted prior colors
- `full_alternative` — requests entirely different direction
- `more_options` — requests additional candidates in same direction
- `similar_to_previous` — reuses prior color, occasion, plan shape, and silhouette signals

### Output format

Return strict JSON.

Do not parse marker-delimited text.

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
- search embeddings
- fetch matching `catalog_enriched` rows by `product_id`

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

### V1 pairing scope

Only:
- `top + bottom`

Not in v1:
- three-piece outfits
- accessory pairing
- outerwear layering logic

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
    assembly_score: float
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

### Evaluation criteria

- body harmony
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
    item_ids: list[str]
```

### Important rule

Rank by actual fit for this user, not by vector similarity score.

Similarity is retrieval input, not recommendation truth.

### Fallback behavior

If the LLM evaluator fails, the fallback ranks candidates by `assembly_score` (average similarity minus compatibility penalties). The fallback also generates synthetic reasoning notes. For follow-up intents, the fallback uses candidate-by-candidate deltas against the previous recommendation to explain color/silhouette shifts.

### Output normalization

Sparse LLM outputs are backfilled: if the evaluator returns fewer notes than expected for follow-up turns, the system normalizes them using follow-up deltas computed from the persisted previous recommendation summaries.

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
    outfits: list[OutfitCard]
    follow_up_suggestions: list[str]
    metadata: dict
```

### Hard output cap

The response formatter caps output to a maximum of 3 outfits (`MAX_FORMATTED_OUTFITS = 3`).

### Outfit card rules

Each outfit card should contain:
- recommendation title
- overall reasoning
- body note
- color note
- style note
- occasion note
- one or more product cards
- virtual try-on image (optional, generated by the try-on stage)

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
5. UI renders try-on images inline above each outfit's product cards

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
- these intents are detected and persisted today
- `increase_boldness`, `decrease_formality`, `increase_formality`, `full_alternative`, and `more_options` have meaningful runtime effect
- `change_color` and `similar_to_previous` affect LLM planning and evaluation payloads through persisted recommendation summaries
- persisted recommendation summaries are used to preserve prior color, occasion, plan shape, and silhouette-level signals during follow-up refinement

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
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Focused suites used for the application layer:

```bash
python3 -m unittest tests.test_agentic_application -v
python3 -m unittest tests.test_agentic_application_api_ui -v
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
- return a simpler deterministic ranking using `assembly_score`
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
- `style_preference.primaryArchetype`

The system should degrade gracefully with partial body or detail attributes.

## 15. Performance Targets

Target latency:

```text
Profile load              < 50ms
Context resolution        < 10ms
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
- `outfit_assembler.py`

Support:
- complete outfit passthrough
- top+bottom pairing

### Step 5

Build:
- `outfit_evaluator.py`

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
3. `occasion_resolver`
4. `outfit_architect`
5. `catalog_search`
6. `outfit_assembly`
7. `outfit_evaluation`
8. `response_formatting`
9. `virtual_tryon`

Each stage emits `started` and `completed` (or `failed`) events with timestamps.

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

### Onboarding endpoints (mounted via onboarding gateway)

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/onboarding/send-otp` | Send OTP to mobile |
| POST | `/v1/onboarding/verify-otp` | Verify OTP, create user if new |
| POST | `/v1/onboarding/profile` | Save profile (name, DOB, gender, height, waist, profession) |
| POST | `/v1/onboarding/images/normalize` | Normalize image for 3:2 crop |
| POST | `/v1/onboarding/images/{category}` | Upload image (full_body, headshot, veins) |
| GET | `/v1/onboarding/style-archetype-session` | Load style archetype selection UI |
| POST | `/v1/onboarding/style-preference-complete` | Save style preference |
| POST | `/v1/onboarding/analysis/start` | Launch 4-agent analysis |
| POST | `/v1/onboarding/analysis/status` | Check analysis completion |
| POST | `/v1/onboarding/analysis/rerun` | Rerun specific analysis agent |

### Catalog admin endpoints (mounted via catalog admin router)

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/admin/catalog/upload` | Upload CSV file |
| GET | `/v1/admin/catalog/status` | Catalog sync status |
| POST | `/v1/admin/catalog/items/sync` | Sync enriched catalog rows |
| POST | `/v1/admin/catalog/items/backfill-urls` | Backfill missing product URLs |
| POST | `/v1/admin/catalog/embeddings/sync` | Generate and sync embeddings |

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

The following still block full completion:
- evaluator/spec fallback wording still needs to remain synchronized if the degradation contract changes again
- direct `agentic_application` imports from `onboarding.*` and `catalog_retrieval.*` still need boundary cleanup
- canonical product URL ingestion still needs to replace runtime URL synthesis
