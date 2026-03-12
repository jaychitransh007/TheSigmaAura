# Application Layer — Implementation Specification

Last updated: March 12, 2026

## Current Implementation Status

This document is both the target v1 contract and the current implementation reference for `modules/agentic_application`.

Implemented now:
- active runtime entrypoint in `agentic_application/api.py` with `AgenticOrchestrator`
- saved user-context loading from onboarding/profile-analysis/style-preference persistence
- rule-based live-context extraction with phrase-priority matching
- server-side conversation-memory carry-forward across follow-up turns
- LLM planning with deterministic fallback to `complete_only`, `paired_only`, or `mixed`
- embedding retrieval from `catalog_item_embeddings` with hydration from `catalog_enriched`
- direction-aware retrieval for complete outfits and top/bottom pairing
- deterministic assembly and LLM evaluation with graceful fallback
- persisted turn artifacts: live context, memory, plan, applied filters, retrieved IDs, assembled candidates, final recommendations
- response formatting for `outfits` plus compatibility fallback for older `recommendations`
- runtime URL synthesis from `store + handle` when canonical absolute product URLs are absent in catalog rows

Still incomplete:
- evaluator is not explicitly conditioned on persisted conversation memory beyond merged live context
- follow-up refinement for `change_color` and `similar_to_previous` is still heuristic, not full constraint editing
- retry logic only relaxes `occasion_fit`, then `formality_level`
- application imports still cross legacy module boundaries in some places

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
Orchestrator
    |
    +--> User Context Builder ----> User Profile Store
    |
    +--> Occasion Resolver
    |
    v
Outfit Architect (LLM)
    |
    v
Catalog Search Agent
    |
    +--> Embedding API
    +--> catalog_item_embeddings
    +--> catalog_enriched
    |
    v
Outfit Assembler
    |
    v
Outfit Evaluator (LLM)
    |
    v
Response Formatter
    |
    v
User Response
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

## 4. Combined Context

The orchestrator merges saved user context and live context into one payload.

```python
class CombinedContext:
    user: UserContext
    live: LiveContext
    conversation_memory: dict | None
    hard_filters: dict
    previous_recommendations: list[dict] | None
```

### Hard filters

Global hard filters:
- `GenderExpression`

Conditional hard filters:
- `OccasionFit`
- `FormalityLevel`

Direction-specific filters:
- complete outfit directions use `StylingCompleteness = complete`
- pairing directions use `StylingCompleteness = needs_pairing`

Current runtime also derives query-document filters server-side from architect output and can relax:
- `occasion_fit`
- `formality_level`

Important:
- for v1, do not globally force complete outfits
- pairing must be supported in v1

## 5. Orchestrator

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

- Filter relaxation order is: no relaxation, then drop `occasion_fit`, then drop `occasion_fit` and `formality_level`.
- `GenderExpression` is never relaxed.
- Planner and evaluator both have deterministic fallbacks so the request can still complete if an LLM step fails.

## 6. Outfit Architect

### Purpose

Translate user context into retrieval directions.

### Important design decision

The architect should not output freeform prose only. It should return JSON plus a structured labeled query document per direction.

### Output

```python
class RecommendationPlan:
    plan_type: str                 # complete_only | paired_only | mixed
    retrieval_count: int           # 10-20 per query
    directions: list[DirectionSpec]


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

### Output format

Return strict JSON.

Do not parse marker-delimited text.

## 7. Catalog Search Agent

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

Use current normalized retrieval filter fields from the embedding table, such as:
- `garment_category`
- `garment_subtype`
- `styling_completeness`
- `gender_expression`
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

## 8. Outfit Assembler

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

At minimum:
- same `GenderExpression`
- same or compatible `FormalityLevel`
- same or compatible `OccasionFit`
- compatible `ColorTemperature`
- compatible `PatternType / PatternScale`
- avoid extreme volume conflict

### Output

```python
class OutfitCandidate:
    candidate_id: str
    direction_id: str
    candidate_type: str          # complete | paired
    items: list[dict]
    assembly_score: float
    assembly_notes: list[str]
```

### Candidate control

Limit paired combinations aggressively before evaluation.

Recommended:
- retrieve 10-15 per query
- prune to top 12 per role
- keep top 20-30 assembled pairs max

## 9. Outfit Evaluator

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

## 10. Response Formatter

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

### Outfit card rules

Each outfit card should contain:
- recommendation title
- overall reasoning
- body note
- color note
- style note
- occasion note
- one or more product cards

## 11. Conversation State

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
- `change_color` and `similar_to_previous` are only partially expressed through current heuristics

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
python3 -m unittest tests.test_conversation_api_ui -v
```

### Follow-up rule

Follow-up requests should operate on persisted prior recommendations, not only on text history.

## 12. Error Handling

### Error categories

- profile missing
- profile incomplete
- architect failed
- embedding failed
- retrieval failed
- no results
- evaluator failed

### Graceful degradation

If evaluator fails:
- return top retrieved candidates with simpler explanations

If no results:
- relax only safe filters

### Filter relaxation

For v1, do not relax:
- `GenderExpression`

Relax in this order:
- `OccasionFit`
- `FormalityLevel`

Only relax `StylingCompleteness` if the product decision changes later.
For current v1 pairing support, `StylingCompleteness` is direction-defining and should remain stable.

## 13. Profile Validation

Minimum required profile for recommendation:
- `gender`
- `SeasonalColorGroup`
- `style_preference.primaryArchetype`

The system should degrade gracefully with partial body or detail attributes.

## 14. Performance Targets

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

Target total              < 9000ms
```

## 15. Implementation Sequence

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

Then reduce `conversation_platform` to compatibility wrappers.

## 16. Final v1 Definition of Done

The Application Layer is considered complete for v1 when:

- user message intake is active
- saved profile context is loaded correctly
- live context is resolved deterministically
- architect returns structured JSON directions
- retrieval supports both complete outfits and pairing
- assembler builds top+bottom combinations
- evaluator ranks complete and paired candidates
- formatter returns 3-5 outfit recommendations
- follow-up requests refine prior recommendations
- runtime is owned by `modules/agentic_application`
- `conversation_platform` is no longer the canonical application module
