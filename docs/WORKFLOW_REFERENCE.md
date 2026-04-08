# Workflow Reference — Intent Execution Flows

Last updated: April 8, 2026 (Phase 12E close-out)

> **What this is (and isn't):** This is **reference documentation for humans
> reading the codebase**. It describes how each intent is executed by the
> orchestrator so you can navigate the code without tracing every branch
> yourself. It is **not loaded at runtime** by any agent, planner, or
> handler — no Python file in `modules/` reads this markdown. The runtime
> behavior is defined entirely by `modules/agentic_application/src/agentic_application/orchestrator.py`
> and the per-handler methods it dispatches to. **If this document and the
> code disagree, the code wins.** When you change a handler, update this
> file to match; when you read this file, verify against the code before
> relying on it for anything load-bearing.

**Registry:** All intent identifiers are defined as `StrEnum` constants in `agentic_application/intent_registry.py`. The copilot planner JSON schema, orchestrator dispatch, and all agent code import from this single source of truth — that enum, not this document, is the authoritative intent list.

---

## Phase 12 Summary (Current State)

The Phase 12 re-architecture (Phases 12A–12E, completed April 2026) consolidated the intent taxonomy from 12 → 7 advisory + feedback + silent wardrobe_ingestion, moved evaluation to a visual-grounded post-tryon position, and split inline planner-text generation into a dedicated `StyleAdvisorAgent`. This summary lists the **current** taxonomy and pipeline shapes; the per-intent sections below contain the historical detail and may reference removed paths — refer to this summary for what runs today.

### Current intent taxonomy (7 advisory + feedback + 1 silent)

| Intent | Action | Pipeline shape |
|---|---|---|
| `occasion_recommendation` | `RUN_RECOMMENDATION_PIPELINE` | architect → search → assemble → reranker → tryon (top-3, parallel) → visual_evaluator → format. Legacy text-only `OutfitEvaluator` is the fallback when the user has no full-body photo. Absorbs the old `product_browse` intent via `target_product_type`. |
| `pairing_request` | `RUN_RECOMMENDATION_PIPELINE` | Same as occasion_recommendation, with `enriched_data["is_anchor"]=True` on the synthetic anchor `RetrievedProduct`. The diversity pass exempts anchors so all 3 outfits survive. |
| `garment_evaluation` | `RUN_GARMENT_EVALUATION` | tryon → visual_evaluator → format with optional buy/skip verdict. Replaces `shopping_decision`, `garment_on_me_request`, and `virtual_tryon_request`. Photo-only input. `purchase_intent: bool` from the planner controls whether the verdict block renders. |
| `outfit_check` | `RUN_OUTFIT_CHECK` | visual_evaluator on the user's photo → format → async decomposition. No try-on (the user is already wearing the outfit), no architect call. |
| `style_discovery` | `RESPOND_DIRECTLY` | Layered: deterministic topical helpers (collar, color, pattern, silhouette, archetype) for matched topics; `StyleAdvisorAgent` LLM fallback in `discovery` mode for open-ended questions. |
| `explanation_request` | `RESPOND_DIRECTLY` | Layered: `StyleAdvisorAgent` in `explanation` mode when `previous_recommendations` exists; deterministic explanation summary as the fallback. |
| `feedback_submission` | `SAVE_FEEDBACK` | Pure event capture, no LLM. Drives `comfort_learning` for `like` events. |
| `wardrobe_ingestion` | `SAVE_WARDROBE_ITEM` | **Silent** — not exposed in the planner prompt's user-facing intent list. Available for programmatic / bulk upload paths only. |

### Removed in Phase 12

- `capsule_or_trip_planning` — handler deleted (Phase 12A); to return in a future phase
- `product_browse` — folded into `occasion_recommendation` via `CopilotResolvedContext.target_product_type`
- `virtual_tryon_request` — absorbed into `garment_evaluation`
- `shopping_decision` — absorbed into `garment_evaluation`
- `garment_on_me_request` — absorbed into `garment_evaluation`

### Key building blocks added in Phase 12

| Component | Phase | Purpose |
|---|---|---|
| `agents/visual_evaluator_agent.py` | 12B | Vision-grounded per-candidate evaluator that replaces text-only `OutfitEvaluator` and `OutfitCheckAgent`. 9 dimension scores (8 existing + new `weather_time_pct`), 8 archetype scores, optional `overall_verdict`/`strengths`/`improvements`. Three modes: `recommendation`, `single_garment`, `outfit_check`. |
| `agents/reranker.py` | 12B | Deterministic top-N pruning before the expensive try-on stage. `final_top_n=3`, `pool_top_n=5` defaults; the over-generation pool gives the orchestrator headroom when a try-on fails the quality gate. |
| `agents/style_advisor_agent.py` | 12C | LLM advisor for open-ended `style_discovery` and `explanation_request` (against prior turn artifacts). Returns structured advice with prose answer + bullets + cited attributes + dominant directions. |
| Four thinking directions | 12C | Reasoning axes propagated through architect / visual evaluator / advisor prompts: physical+color, comfort, occasion, weather/time. NOT fixed weights — the agent identifies which 1-2 dominate per turn. |
| `weather_context` / `time_of_day` / `target_product_type` | 12A/C | New `CopilotResolvedContext` fields extracted by the planner, consumed by the architect and visual evaluator. |
| `purchase_intent: bool` | 12A | New `CopilotActionParameters` field. Replaces the legacy `verdict` string. Controls whether the `garment_evaluation` formatter renders the buy/skip verdict block. |
| `is_anchor` flag on candidate items | 12D | Set by orchestrator anchor injection; consumed by `_enforce_cross_outfit_diversity` to exempt anchor products from the "no repeats" rule. Fixes the pre-existing bug where pairing turns collapsed to 1 outfit. |
| Wardrobe-anchor image resolution | 12D follow-up (April 8, 2026) | `_product_to_item` now resolves `image_url` from `enriched_data["image_path"]` and tags wardrobe rows with `source="wardrobe"`. `tryon_service.generate_tryon_outfit` dispatches HTTP(S) URLs to `_download_image` and local `data/...` paths to `_load_local_image`. Without this, the visual-eval try-on render path silently dropped wardrobe-anchor garments because their `image_url` was empty, and Gemini hallucinated a stand-in instead of using the user's uploaded photo. |
| `enrichment_status` on saved wardrobe rows | 12D | New top-level field on the dict returned by `save_wardrobe_item` so the orchestrator can detect failed enrichment without parsing nested JSON. The orchestrator returns a clarification asking for a clearer photo when this is `"failed"`. |
| Tryon over-generation metrics | 12E | `tryon_attempted_count`, `tryon_succeeded_count`, `tryon_quality_gate_failures`, `tryon_overgeneration_used`, `evaluator_path` surfaced in `response.metadata` and `dependency_validation_events.metadata_json` for the operations dashboard. |

### What stays the same

The architect (`OutfitArchitect`), catalog search agent (`CatalogSearchAgent`), assembler (`OutfitAssembler`), response formatter (`ResponseFormatter`), try-on service (`TryonService`), and try-on quality gate (`TryonQualityGate`) are unchanged in their core responsibilities. Phase 12 added new components alongside them and changed the **order** of pipeline stages, not the per-stage logic.

### How to read the per-intent sections below

The detailed sections that follow describe the **pre-Phase 12** flow per intent. They are still useful as historical context and as a guide to which file holds which logic. **For current behavior, refer to the table above.** The orchestrator code (`process_turn`, `_handle_planner_pipeline`, `_handle_garment_evaluation`, `_handle_outfit_check`, `_handle_style_discovery`, `_handle_explanation_request`) is the authoritative source — this doc is reference, not contract.

---

**Common Entry Flow:** Every user message follows this path before intent-specific handling:

```
User message
  → process_turn() [orchestrator.py]
    → Load user context via OnboardingGateway
    → Build conversation memory from prior turn state
    → Build planner input (message + context + history + profile richness)
    → Copilot Planner [gpt-5.4] → classifies intent + selects action
    → Apply planner overrides (wardrobe-first, pairing detection, source preference)
    → Dispatch to handler based on action
```

---

## 1. Occasion Outfit Recommendation

**Intent:** `Intent.OCCASION_RECOMMENDATION`
**Action:** `Action.RUN_RECOMMENDATION_PIPELINE`
**Trigger:** "What should I wear to X?", "Dress me for a dinner date", "Find me an office look"

### Step-by-Step Flow

```
1. Copilot Planner [gpt-5.4]
   ├── Input: message + user context + conversation history
   ├── Output: intent=occasion_recommendation, action=run_recommendation_pipeline
   ├── Extracts: occasion_signal, formality_hint, time_hint, style_goal
   └── DB: repo.log_model_call(call_type="copilot_planner")

2. Image Requirement Gate [deterministic — runs before dispatch for ALL intents]
   ├── If message references "this shirt/piece/garment" but no image and no previous anchor:
   │   └── Force ask_clarification (see Pairing workflow step 2 for details)
   └── Otherwise: proceed

3. Planner Overrides via _apply_planner_overrides()
   │  Deterministic keyword checks that CORRECT the LLM planner's classification
   │  when phrase signals are more reliable than the model's output.
   │
   ├── Catalog follow-up override
   │   └── "show me catalog options" after wardrobe answer → forces followup_intent="catalog_followup"
   ├── Follow-up intent phrase override
   │   └── Formality/boldness phrases → overrides followup_intent + sets formality_hint
   ├── Pairing request override
   │   └── "what goes with this" + attached image/previous anchor → overrides intent→PAIRING_REQUEST
   ├── Outfit check override
   │   └── "how does this look" → overrides intent→OUTFIT_CHECK, action→RUN_OUTFIT_CHECK
   └── Source preference
       └── "from my wardrobe"/"from the catalog" → appends wardrobe_first or catalog_only to specific_needs

3. Wardrobe-First Check (if wardrobe items exist + not catalog-forced)
   ├── Attempt: _build_wardrobe_first_occasion_response()
   │   ├── Find wardrobe items matching occasion + formality
   │   ├── Score by: occasion match (3pts), formality match (2pts), color palette (1pt)
   │   ├── Build outfit card from top-scoring wardrobe items
   │   ├── Generate catalog upsell: "Want to see catalog options too?"
   │   └── Run gap analysis: identify missing roles for occasion
   ├── If successful → return immediately (skip full pipeline)
   └── If insufficient → try _build_wardrobe_only_occasion_fallback()
       ├── Return partial wardrobe outfit + gap analysis
       └── Suggest catalog gap fillers

4. Full Recommendation Pipeline (if wardrobe path not taken)
   │
   ├── Stage 1: Outfit Architect [gpt-5.4]
   │   ├── Input: CombinedContext (profile, live context, hard filters, previous recs)
   │   ├── Output: ArchitectPlan with directions (plan_type, query specs)
   │   ├── Plan types: complete_only | paired_only | mixed
   │   ├── Concept-first: color coordination, volume balance, pattern distribution
   │   └── DB: repo.log_model_call(call_type="outfit_architect")
   │
   ├── Stage 2: Catalog Search [pgvector]
   │   ├── Embed query document via text-embedding-3-small (1536d)
   │   ├── Hard filters: gender_expression, styling_completeness, garment_category, garment_subtype
   │   ├── Soft signals via embedding similarity: occasion, formality, time_of_day, color
   │   ├── No filter relaxation — single search pass, no retry
   │   ├── Retrieve: 12 products per query direction
   │   └── Hydrate: product_id → catalog_enriched row
   │
   ├── Stage 3: Outfit Assembly [deterministic]
   │   ├── Complete directions: each product → one candidate (score = similarity)
   │   ├── Paired directions: top × bottom cross-product (capped at 15 each)
   │   ├── Compatibility checks: formality, occasion, color temp, pattern, volume, fit, texture
   │   └── MAX_PAIRED_CANDIDATES = 30
   │
   ├── Stage 4: Outfit Evaluation [gpt-5.4]
   │   ├── Input: all candidates + user context + previous recommendation deltas
   │   ├── Scores per outfit (16 fields):
   │   │   ├── 8 evaluation criteria: body_harmony, color_suitability, style_fit,
   │   │   │   risk_tolerance, occasion, comfort_boundary, specific_needs, pairing_coherence
   │   │   └── 8 style archetypes: classic, dramatic, romantic, natural,
   │   │       minimalist, creative, sporty, edgy
   │   ├── Graceful fallback: criteria from assembly_score if LLM fails
   │   ├── Hard cap: maximum 5 evaluated recommendations
   │   └── DB: repo.log_model_call(call_type="outfit_evaluator")
   │
   ├── Stage 5: Response Formatting [deterministic]
   │   ├── Filter restricted items (lingerie, etc.)
   │   ├── Rank outfits by evaluation scores
   │   ├── Max 3 outfit cards per response
   │   ├── Intent-aware opening message + follow-up suggestion chips
   │   └── Build recommendation confidence (9-factor scoring)
   │
   └── Stage 6: Virtual Try-On [gemini-3.1-flash-image-preview]
       ├── For each outfit: extract garment IDs → cache lookup
       ├── Cache hit → reuse existing image (skip generation)
       ├── Cache miss → generate via Gemini (parallel, max 3 workers)
       │   ├── Input: user full_body image + first product image
       │   ├── Body-preserving prompt (immutable geometry)
       │   └── Quality gate: TryonQualityGate.evaluate()
       └── DB: repo.find_tryon_image_by_garments(), repo.insert_tryon_image()

5. Database Persistence
   ├── repo.finalize_turn() — saves turn + resolved_context + pipeline artifacts
   ├── repo.update_conversation_context() — last_recommendations, last_occasion, memory
   ├── _persist_catalog_interactions() — logs each outfit interaction
   ├── _persist_recommendation_confidence()
   └── _persist_dependency_turn_event()
```

### Response Structure

| Field | Value |
|-------|-------|
| `response_type` | `"recommendation"` |
| `outfits` | Up to 3 `OutfitCard` objects with items, scores, tryon_image |
| `metadata.answer_source` | `"wardrobe_first"` or `"catalog_pipeline"` |
| `metadata.recommendation_confidence` | 9-factor confidence object |
| `follow_up_suggestions` | e.g., "Show me bolder options", "Change the color palette" |

---

## 2. Garment Pairing

**Intent:** `Intent.PAIRING_REQUEST`
**Action:** `Action.RUN_RECOMMENDATION_PIPELINE`
**Trigger:** "What goes with this?", "Style this shirt", "Pair this blazer"

### Step-by-Step Flow

```
1. Copilot Planner [gpt-5.4]
   └── May classify as occasion_recommendation initially

2. Image Requirement Gate [deterministic — before dispatch]
   ├── Detects demonstrative references: "this shirt", "with this", "pair this", "style this"
   ├── Checks: has_attached_image? has_previous_anchor? (from prior turn's "Attached garment context:")
   ├── If demonstrative reference + NO image + NO previous anchor:
   │   ├── Force action → ASK_CLARIFICATION
   │   ├── Response: "Could you attach a photo of the garment you'd like me to build an outfit around?"
   │   ├── Suggestions: ["Upload a photo", "Pick from my wardrobe", "Show me office outfits instead"]
   │   └── STOP — do not proceed to pipeline
   └── If image attached OR previous anchor exists: proceed to step 3

3. Planner Override: _message_requests_pairing() [corrects LLM misclassification]
   ├── Demonstrative phrases ("with this", "pair this"): require attached image OR previous anchor
   ├── Wardrobe phrases ("what goes with my"): always trigger without image
   ├── Generic phrases ("complete the outfit"): always trigger without image
   ├── If triggered: override intent → PAIRING_REQUEST, action → RUN_RECOMMENDATION_PIPELINE
   ├── Extract anchor piece title from attached item or previous context
   └── Common case: planner classifies as occasion_recommendation, override corrects to pairing_request

4. Full Pipeline (same 6 stages as occasion recommendation — no short-circuit paths)
   │
   ├── Stage 1: Outfit Architect [gpt-5.4]
   │   ├── Receives anchor_garment in LiveContext (title, category, subtype, color, source)
   │   ├── Architect prompt instructs: "Do NOT generate a query for the anchor's role"
   │   ├── Only searches for complementary roles (e.g., anchor=top → search bottom, shoes)
   │   └── Plans directions around the anchor, not replacing it
   │
   ├── Stage 2: Catalog Search [pgvector]
   │   └── Retrieves items for complementary roles (bottom if anchor is top, etc.)
   │
   ├── Stage 2.5: Anchor Injection [deterministic]
   │   ├── If anchor_garment exists + plan is paired_only:
   │   │   inject anchor as synthetic RetrievedProduct with role matching its category
   │   └── e.g., anchor is a top → inject as role=top so assembler can pair with retrieved bottoms
   │
   ├── Stage 3: Outfit Assembly [deterministic]
   │   └── Pairs anchor (top) with retrieved complementary items (bottoms)
   │
   ├── Stage 4: Outfit Evaluation [gpt-5.4]
   │   └── Scores all candidates (8 criteria + 8 archetypes)
   │
   ├── Stage 5: Response Formatting
   │   └── Max 3 outfit cards with source labeling
   │
   └── Stage 6: Virtual Try-On [gemini-3.1-flash-image-preview]
       └── Generates try-on image for each outfit (2:3 aspect ratio)

5. Persist: finalize_turn, update_conversation_context, recommendation_confidence, catalog_interactions
```

### Key Difference from Occasion
- The architect receives `target_piece` as the anchor constraint
- Searches are constrained to **complementary roles** relative to the anchor garment
- Anchor piece is never echoed back as the full answer
- Full evaluation and try-on are always performed (no short-circuit paths)

---

## 3. Style Discovery

**Intent:** `Intent.STYLE_DISCOVERY`
**Action:** `Action.RESPOND_DIRECTLY`
**Trigger:** "What colors suit me?", "What style am I?", "What collar works for me?"

### Step-by-Step Flow

```
1. Copilot Planner [gpt-5.4]
   └── intent=style_discovery, action=respond_directly

2. Dispatch → _handle_direct_response() → _handle_style_discovery()

3. Profile Data Extraction
   ├── Fetch analysis status via onboarding_gateway
   ├── Extract derived_interpretations:
   │   ├── SeasonalColorGroup (Spring/Summer/Autumn/Winter)
   │   ├── BaseColors, AccentColors, AvoidColors
   │   ├── ContrastLevel (Low → High)
   │   ├── FrameStructure (Light+Narrow → Solid+Broad)
   │   └── HeightCategory (Petite/Average/Tall)
   ├── Extract attributes: BodyShape
   └── Extract style_preference: primaryArchetype, secondaryArchetype

4. Topic Detection via _detect_style_advice_topic()
   ├── Keywords: "color" → color, "collar"/"neckline" → collar, "pattern" → pattern,
   │   "silhouette" → silhouette, "archetype"/"style" → archetype
   └── Default: "general"

5. Response Generation [NO LLM — rule-based]
   ├── color: warm/cool palette advice, complementary colors, contrast guidance
   ├── collar/neckline: body-shape-aware (hourglass → V-neck, etc.)
   ├── pattern: contrast-aware (high contrast → sharp patterns, low → soft)
   ├── silhouette: waist definition, length proportions per height/frame
   ├── archetype: primary+secondary blend explanation
   └── Append confidence disclaimer if profile_confidence < 70%

6. DB: repo.finalize_turn(), repo.update_conversation_context()
```

### Response Metadata

| Field | Value |
|-------|-------|
| `metadata.answer_source` | `"style_discovery_handler"` |
| `metadata.style_discovery.advice_topic` | detected topic |
| `metadata.style_discovery.evidence` | e.g., `["seasonal:Spring", "contrast:High"]` |
| `outfits` | `[]` (no product recommendations) |

---

## 4. Explanation Request

**Intent:** `Intent.EXPLANATION_REQUEST`
**Action:** `Action.RESPOND_DIRECTLY`
**Trigger:** "Why did you recommend this?", "How does this outfit work?", "Explain the confidence"

### Step-by-Step Flow

```
1. Copilot Planner [gpt-5.4]
   └── intent=explanation_request, action=respond_directly

2. Dispatch → _handle_direct_response() → _handle_explanation_request()

3. Previous Turn Context Access [NO LLM — rule-based]
   ├── Read previous_context.last_recommendations (array of recommendation summaries)
   ├── Read previous_context.last_response_metadata
   ├── Extract top recommendation (rank 0): title, colors, categories, occasion_fits
   └── Extract confidence metadata from last turn

4. Explanation Construction
   ├── Item title: "I picked {title} because it matched the strongest signals..."
   ├── Colors + categories: "The fit came from {colors} and {categories}..."
   ├── Occasion: "It also lined up with the occasion signal around {occasion}..."
   └── Confidence band: "My confidence on that answer was {band}..."

5. DB: repo.finalize_turn(), repo.update_conversation_context()
```

### Response Metadata

| Field | Value |
|-------|-------|
| `metadata.answer_source` | `"explanation_handler"` |
| `metadata.explanation.target_title` | explained item title |
| `metadata.explanation.recommendation_confidence_band` | confidence level |
| `outfits` | `[]` (no product recommendations) |

---

## 5. Outfit Check / Critique

**Intent:** `Intent.OUTFIT_CHECK`
**Action:** `Action.RUN_OUTFIT_CHECK`
**Trigger:** "How does this look?", "Rate my outfit", "Check what I'm wearing"

### Step-by-Step Flow

```
1. Copilot Planner [gpt-5.4]
   └── intent=outfit_check, action=run_outfit_check

2. Planner Override: _message_requests_outfit_check()
   ├── Keyword match: "how does this look", "rate my outfit", "outfit check"
   └── If match: override intent → OUTFIT_CHECK, action → RUN_OUTFIT_CHECK

3. Dispatch → _handle_outfit_check()

4. Vision-Based Outfit Evaluation [gpt-5.4]
   ├── Agent: OutfitCheckAgent.evaluate()
   ├── Input: user_context, outfit_description, occasion_signal, image_path
   ├── Output: OutfitCheckResult
   │   ├── overall_verdict: "Strong" | "Solid" | "Needs work"
   │   ├── overall_score_pct: 0-100
   │   ├── Scoring dimensions (5):
   │   │   ├── body_harmony_pct
   │   │   ├── color_suitability_pct
   │   │   ├── style_fit_pct
   │   │   ├── pairing_coherence_pct
   │   │   └── occasion_pct
   │   ├── strengths: list of what works
   │   ├── improvements: list of {suggestion, swap_detail, swap_source}
   │   └── style_archetype_read: 8 archetype percentages
   └── DB: repo.log_model_call(call_type="outfit_check")

5. Async Outfit Decomposition (background thread)
   ├── decompose_outfit_image() — vision-based garment detection
   ├── Save decomposed garments via onboarding_gateway
   └── Each garment enriched with 46 attributes

6. Wardrobe Overlap Check
   ├── Compare detected garments/colors to existing wardrobe
   ├── Scoring: garment match (+2), color match (+1)
   └── Output: has_duplicate, duplicate_detail, overlap_level

7. Improvement Suggestions from Wardrobe
   ├── For each improvement in check result:
   │   ├── If swap_source="wardrobe": find matching wardrobe items
   │   └── Prioritize by occasion match
   └── Build: list of wardrobe swap suggestions with reasoning

8. Gap Analysis
   └── Identify missing wardrobe roles for the stated occasion

9. Response Assembly
   ├── Overall note + strengths + improvements + wardrobe suggestions
   ├── Confidence disclaimer if profile_confidence < 70%
   └── Optional catalog upsell

10. DB: repo.finalize_turn() (sync), decomposed garments (async), context update
```

### Response Structure

| Field | Value |
|-------|-------|
| `response_type` | `"recommendation"` |
| `outfits` | 1 `OutfitCard` with all scoring dimensions + archetype read |
| `metadata.outfit_check.overall_verdict` | "Strong" / "Solid" / "Needs work" |
| `metadata.outfit_check.overall_score_pct` | 0-100 |
| `metadata.outfit_check.wardrobe_suggestions` | swap options from wardrobe |
| `follow_up_suggestions` | "What would improve this?", "Show wardrobe swaps" |

---

## 6. Shopping Decision

> **REMOVED IN PHASE 12A** — `Intent.SHOPPING_DECISION` and `Action.RUN_SHOPPING_DECISION` no longer exist. This intent was absorbed into the merged `garment_evaluation` intent. The planner classifies "should I buy this?" turns as `garment_evaluation` with `action_parameters.purchase_intent=true`. The new pipeline (Phase 12B) is `tryon → visual_evaluator → format`, with the buy/skip verdict computed deterministically by the response formatter from evaluator scores + wardrobe overlap. See the Phase 12 Summary at the top of this document. The detailed flow below is historical and no longer runs.

**Intent:** `Intent.SHOPPING_DECISION` *(removed)*
**Action:** `Action.RUN_SHOPPING_DECISION` *(removed)*
**Trigger:** "Should I buy this?", "Is this worth it?", "Buy or skip?"

### Step-by-Step Flow

```
1. Copilot Planner [gpt-5.4]
   └── intent=shopping_decision, action=run_shopping_decision

2. Dispatch → _handle_shopping_decision()

3. Product Detection
   ├── Extract URLs from message or action_parameters.product_urls
   └── Extract detected garments and colors from planner

4. Wardrobe Overlap Check via _compute_wardrobe_overlap()
   ├── Compare product to existing wardrobe items
   ├── Scoring: garment match (+2), color match (+1)
   └── Output: has_duplicate, duplicate_detail, overlap_level (strong/moderate/none)

5. Pairing Suggestions via _build_shopping_pairing_suggestions()
   ├── Find wardrobe items that would pair with the product
   ├── Exclude same-category items
   └── Return: list of {wardrobe_item, pairing_note}

6. Shopping Decision Agent [gpt-5.4]
   ├── Input: user_context, product_description, product_urls, detected_garments,
   │   detected_colors, occasion_signal, wardrobe_overlap, pairing_suggestions
   ├── Output: ShoppingDecisionResult
   │   ├── verdict: "buy" | "skip"
   │   ├── verdict_confidence: 0-100
   │   ├── verdict_note: explanation
   │   ├── concerns: list of issues
   │   ├── if_you_buy: next steps
   │   └── instead_consider: alternatives if skipping
   └── DB: repo.log_model_call(call_type="shopping_decision")

7. Gap Analysis — identify wardrobe gaps for occasion

8. Response Assembly
   ├── Verdict + reasoning + duplicate warning + concerns
   ├── Pairing suggestions + gap analysis
   └── Confidence disclaimer if profile_confidence < 70%

9. DB: repo.finalize_turn(), context update, dependency event
```

### Response Metadata

| Field | Value |
|-------|-------|
| `metadata.shopping_decision.verdict` | `"buy"` or `"skip"` |
| `metadata.shopping_decision.verdict_confidence` | 0-100 |
| `metadata.shopping_decision.concerns` | list of issues |
| `metadata.shopping_decision.if_you_buy` | next steps |
| `metadata.shopping_decision.instead_consider` | alternatives |
| `outfits` | `[]` (no outfit cards) |

---

## 7. Capsule / Trip Planning

> **REMOVED IN PHASE 12A** — `Intent.CAPSULE_OR_TRIP_PLANNING` and the `_handle_capsule_or_trip_planning` handler were deleted. Capsule and multi-day planning will return as a dedicated phase later. Today, multi-day requests fall through to `occasion_recommendation` and produce a single recommendation. See the Phase 12 Summary at the top of this document. The detailed flow below is historical and no longer runs.

**Intent:** `Intent.CAPSULE_OR_TRIP_PLANNING` *(removed)*
**Action:** `Action.RESPOND_DIRECTLY` *(removed for this intent)*
**Trigger:** "Plan my outfits for a 5-day trip", "Build a workweek capsule", "Pack for a beach weekend"

### Step-by-Step Flow

```
1. Copilot Planner [gpt-5.4]
   └── intent=capsule_or_trip_planning, action=respond_directly

2. Dispatch → _handle_direct_response() → _handle_capsule_or_trip_planning()

3. Trip Duration Extraction [NO LLM — regex + keyword]
   ├── Regex: "\b(\d+)\s*day\b" → extract day count
   ├── Keywords: "workweek" (5), "weekend" (2), "trip" (3 default)
   ├── Target outfit count: min(10, max(3, days × 2))
   └── Context labels: ["travel day", "daytime", "meeting", "dinner", "off duty", ...]

4. Wardrobe Item Classification
   └── Categorize into roles: top, bottom, one_piece, shoe

5. Outfit Generation [NO LLM — algorithmic]
   │
   ├── Phase 1: Build candidates from wardrobe
   │   ├── For each one_piece: [one_piece, shoe]
   │   ├── For each top+bottom: [top, bottom, shoe]
   │   └── Track item reuse via seen_signatures (avoid duplicates)
   │
   ├── Phase 2: Select best outfits (greedy scoring)
   │   ├── Novelty: items used < 3 times score higher
   │   ├── Role variety: more distinct roles score higher
   │   └── Greedy selection until target count reached
   │
   ├── Phase 3: Build hybrid outfits (if gaps remain)
   │   ├── Use _select_catalog_items() to fill missing roles
   │   └── Mix wardrobe items + catalog fillers
   │
   └── Phase 4: Repeat base outfits if still short of target

6. Gap Analysis
   ├── Identify missing roles: "missing bottoms", "missing shoes"
   ├── Search catalog for gap fillers
   └── Preferred colors: colors already present in selected outfits

7. Packing List Assembly
   ├── Deduplicate items across all outfits
   └── Build: list of {product_id, title, source}

8. Response Assembly
   ├── Summary: "I mapped out {N} looks across {days} days"
   ├── Lists gap items + top catalog gap fillers
   └── Mentions primary archetype if available

9. DB: repo.finalize_turn(), context update, dependency event
```

### Response Structure

| Field | Value |
|-------|-------|
| `outfits` | Multiple `OutfitCard` objects (up to 10), titled by context label |
| `metadata.capsule_plan.trip_days` | extracted day count |
| `metadata.capsule_plan.packing_list` | deduplicated item list |
| `metadata.capsule_plan.gap_items` | missing wardrobe roles |
| `metadata.capsule_plan.catalog_gap_fillers` | catalog items to fill gaps |

---

## 8. Virtual Try-On

> **REMOVED IN PHASE 12A** — `Intent.VIRTUAL_TRYON_REQUEST` and `Action.RUN_VIRTUAL_TRYON` were absorbed into `garment_evaluation`. "Try this on me" requests now classify as `garment_evaluation` with `purchase_intent=false`; the same `tryon → visual_evaluator → format` pipeline runs and the formatter renders the try-on image as the hero of the response card without a buy/skip verdict block. The standalone `/v1/tryon` REST endpoint in `api.py` is unchanged and still serves direct try-on requests for non-chat surfaces. See the Phase 12 Summary at the top of this document. The detailed flow below is historical and no longer runs.

**Intent:** `Intent.VIRTUAL_TRYON_REQUEST` *(removed)*
**Action:** `Action.RUN_VIRTUAL_TRYON` *(removed)*
**Trigger:** "Show this on me", "Try this on me", "What would I look like in this?"

### Step-by-Step Flow

```
1. Copilot Planner [gpt-5.4]
   └── intent=virtual_tryon_request, action=run_virtual_tryon

2. Dispatch → _handle_planner_virtual_tryon()

3. Product URL Extraction
   └── Regex match: https?://\S+ from message

4. Person Image Validation
   ├── Fetch person image via onboarding_gateway.get_person_image_path()
   └── If missing → return error: graceful_policy_message("missing_person_image")

5. Try-On Generation [gemini-3.1-flash-image-preview]
   ├── Service: TryonService.generate_tryon()
   ├── Input: person_image_path + product_image_url
   ├── Image preprocessing: resize to max 1024px (Pillow/LANCZOS)
   ├── Prompt: body-preserving — treats person's body as immutable geometry
   └── Output: result with data_url (base64 generated image)

6. Quality Gate Evaluation
   ├── Service: TryonQualityGate.evaluate()
   ├── Checks: body detection, image quality, garment fidelity, distortion
   ├── Output: passed (bool), reason_code, message
   ├── If PASSED → attach image to response
   └── If FAILED → safe fallback message, no image shown

7. Policy Event Logging
   ├── If passed: policy_event_type="virtual_tryon_guardrail", reason="quality_gate_passed"
   └── If failed: reason_code from quality gate (e.g., "body_detection_failed")

8. DB: repo.finalize_turn(), repo.insert_tryon_image() (if passed), context update
```

### Safety Contract
- Try-on **fails closed** — bad output is never shown to the user
- Every quality gate decision is logged as a policy event
- Graceful degradation: outfit returned without try-on on generation failure

---

## 9. Garment-on-Me Query

> **REMOVED IN PHASE 12A** — `Intent.GARMENT_ON_ME_REQUEST` was absorbed into `garment_evaluation`. The merged intent runs `tryon → visual_evaluator → format` regardless of whether the user framed it as suitability ("would this suit me?", `purchase_intent=false`) or purchase ("should I buy this?", `purchase_intent=true`). The visual evaluator scores the rendered try-on against the user's profile, not just attribute-matched signals. See the Phase 12 Summary at the top of this document. The detailed flow below is historical and no longer runs.

**Intent:** `Intent.GARMENT_ON_ME_REQUEST` *(removed)*
**Action:** `Action.RESPOND_DIRECTLY` *(removed for this intent)*
**Trigger:** "Would this suit me?", "Is this my style?", "How would this look on me?"

### Step-by-Step Flow

```
1. Copilot Planner [gpt-5.4]
   ├── intent=garment_on_me_request, action=respond_directly
   └── Generates personalized answer using profile context

2. Dispatch → _handle_direct_response()
   ├── No dedicated handler (unlike style_discovery or explanation_request)
   └── Falls through to copilot_planner.assistant_message

3. Response: Planner's LLM-generated personalized assessment
   ├── Based on: user profile, style archetype, body shape, color analysis
   ├── Considers: garment description from message or attached image
   └── No separate agent call (unlike outfit_check which uses OutfitCheckAgent)

4. DB: repo.finalize_turn(handler="copilot_planner_direct"), context update
```

### Key Difference from Outfit Check
- **Garment-on-Me** = "Would this garment suit me?" → planner-generated opinion
- **Outfit Check** = "How does my current outfit look?" → structured multi-dimensional scoring via dedicated agent

---

## 10. Wardrobe Ingestion

**Intent:** `Intent.WARDROBE_INGESTION`
**Action:** `Action.SAVE_WARDROBE_ITEM`
**Trigger:** "Save this to my wardrobe", "Add this to my closet"

### Step-by-Step Flow

```
1. Copilot Planner [gpt-5.4]
   └── intent=wardrobe_ingestion, action=save_wardrobe_item

2. Dispatch → _handle_planner_wardrobe_save()

3. Wardrobe Item Saving via _save_chat_wardrobe_item()
   ├── Calls: onboarding_gateway.save_wardrobe_item_from_chat()
   ├── Input: external_user_id, message (item description), image (if attached)
   └── Output: saved item with {id, title, ...}

4. Item Enrichment (during save)
   ├── Vision-API enrichment: 46 attributes per garment
   │   ├── garment_category, garment_subtype
   │   ├── primary_color, secondary_color, pattern_type
   │   ├── formality_level, occasion_fit
   │   ├── silhouette_type, volume_profile, fit_type
   │   └── ... (full enrichment attribute set)
   └── Dual-layer image moderation (heuristic + vision API)
       ├── Reject: nude/explicit images, non-garment uploads, minors
       └── Policy event logged for every moderation decision

5. DB: user_wardrobe_items (insert), repo.finalize_turn(), context update
```

### Moderation Contract
- Non-garment images are rejected before saving
- Lingerie/restricted categories are flagged per policy
- Every moderation decision creates an auditable policy event

---

## 11. Feedback Submission

**Intent:** `Intent.FEEDBACK_SUBMISSION`
**Action:** `Action.SAVE_FEEDBACK`
**Trigger:** "I liked this", "Didn't like the second outfit", "Too safe for me"

### Step-by-Step Flow

```
1. Copilot Planner [gpt-5.4]
   └── intent=feedback_submission, action=save_feedback

2. Dispatch → _handle_planner_feedback()

3. Context Extraction
   ├── Extract event_type (like/dislike) from action_parameters
   ├── Read last_recommendations from previous turn context
   ├── Identify target: item_ids, outfit_rank, target_turn_id
   └── Extract notes from user message

4. Feedback Persistence via _persist_chat_feedback()
   ├── DB: repo.create_feedback_event()
   │   ├── event_type: "like" | "dislike"
   │   ├── item_ids: array of garment IDs
   │   ├── outfit_rank: which outfit (0-indexed)
   │   ├── notes: user's message text
   │   └── target_turn_id: links to the recommended turn
   └── Correlation: conversation_id + turn_id + outfit_rank

5. Comfort Learning Trigger (for "like" events)
   ├── Check if liked garment colors are outside current seasonal groups
   ├── If yes → record high-intent signal in user_comfort_learning
   ├── Threshold: 5 high-intent signals → update seasonal palette
   └── Max 2 seasonal groups per user

6. DB: feedback_events, repo.finalize_turn(), context update (last_feedback_summary)
```

### Downstream Effects
- **Comfort learning:** Outfit likes for garments outside current seasonal groups gradually refine the user's color palette
- **Recommendation refinement:** Feedback shapes future recommendations through conversation memory
- **Profile confidence:** Feedback volume contributes to confidence scoring

---

## 12. Product Browse

> **REMOVED IN PHASE 12A** — `Intent.PRODUCT_BROWSE` and `Action.RUN_PRODUCT_BROWSE` were folded into `occasion_recommendation`. Browse-by-category requests ("show me shirts") now classify as `occasion_recommendation` with `CopilotResolvedContext.target_product_type` set to the canonical garment subtype and `occasion_signal` left null. The architect plans a single-garment direction targeting that subtype rather than a full top+bottom outfit, and the rest of the recommendation pipeline runs as normal. See the Phase 12 Summary at the top of this document. The detailed flow below is historical and no longer runs.

**Intent:** `Intent.PRODUCT_BROWSE` *(removed)*
**Action:** `Action.RUN_PRODUCT_BROWSE` *(removed)*
**Trigger:** "Show me shirts", "Find me blue dresses", "Browse jackets", "Suggest some trousers"

### Step-by-Step Flow

```
1. Copilot Planner [gpt-5.4]
   └── intent=product_browse, action=run_product_browse

2. Dispatch → _handle_product_browse()

3. Extract Constraints [NO LLM]
   ├── detected_garments from action_parameters → map via GARMENT_TERM_TO_FILTER
   │   └── e.g., "shirt" → (category="top", subtype="shirt")
   ├── detected_colors from action_parameters → used in query document
   └── formality_hint from resolved_context (if any)

4. Build Minimal Search Plan [NO LLM]
   ├── Single DirectionSpec with single QuerySpec
   ├── Query document: "A {color} {garment} for {formality}. {profile palette hint}"
   └── Hard filters: gender_expression + garment_category + garment_subtype

5. Catalog Search [pgvector — embedding only, no LLM]
   ├── Reuses CatalogSearchAgent.search() public API
   ├── Embed query document → cosine similarity → hydrate → restricted filter
   └── Retrieve up to 12 products

6. Build Individual Product Cards
   ├── Each product as its own OutfitCard (rank=i+1, 1 item)
   └── NOT grouped as outfits — individual items

7. Follow-up suggestions:
   ├── "Style this piece" → pairing_request
   ├── "Show me more like this" → product_browse continuation
   ├── "Try this on me" → virtual_tryon_request
   └── "Build an outfit around one of these" → occasion_recommendation

8. DB: repo.finalize_turn(), repo.update_conversation_context(), dependency_event
```

### Key Differences from Occasion Recommendation
- **No Outfit Architect** — no direction planning needed
- **No Assembler** — no outfit grouping needed
- **No Evaluator** — no body harmony scoring for a catalog browse
- **No Virtual Try-On** — user can request as follow-up
- **Faster** — just embed + search + format (single LLM call: planner only)
- **Individual products, not outfits** — each result is a standalone item card

### Response Metadata

| Field | Value |
|-------|-------|
| `response_type` | `"product_browse"` |
| `metadata.answer_source` | `"product_browse_handler"` |
| `metadata.product_count` | number of items returned |
| `metadata.browse_constraints` | garment label, colors, formality, hard filters |
| `outfits` | Individual product cards (1 item each) |

---

## Follow-Up Intent Handling

When a user follows up on a previous response, the system detects one of 7 follow-up intents that modify the recommendation pipeline:

| Follow-Up Intent | Effect on Pipeline |
|------------------|--------------------|
| `increase_boldness` | Architect shifts toward bolder colors and patterns |
| `decrease_formality` | Architect lowers formality constraints |
| `increase_formality` | Architect raises formality constraints |
| `change_color` | Architect preserves non-color dimensions, shifts colors; Assembler penalizes +0.10 per overlapping color with previous |
| `full_alternative` | Architect generates entirely new direction |
| `more_options` | Architect expands search breadth |
| `similar_to_previous` | Architect preserves all dimensions; Assembler boosts -0.05 for matching occasion, -0.03 per shared color |

Follow-up intents are detected by the copilot planner via `resolved_context.followup_intent` and propagated through conversation memory to the architect, assembler, evaluator, and response formatter.

---

## LLM Model Usage Summary

### Phase 12 (Current)

| Component | Model | When Called | Intents |
|-----------|-------|------------|---------|
| Copilot Planner | gpt-5.4 | Every turn | All 7 advisory + feedback + silent wardrobe_ingestion |
| Outfit Architect | gpt-5.4 | Recommendation pipeline | occasion_recommendation, pairing_request |
| Visual Evaluator (Phase 12B) | gpt-5.4 (vision) | Per-candidate after try-on; replaces text-only OutfitEvaluator and OutfitCheckAgent | occasion_recommendation, pairing_request, garment_evaluation, outfit_check |
| Outfit Evaluator (legacy) | gpt-5.4 | Fallback when user has no full-body photo or visual path raises | occasion_recommendation, pairing_request |
| Style Advisor (Phase 12C) | gpt-5.4 | Open-ended style discovery + explanation against prior recommendations | style_discovery (general topic), explanation_request (when previous_recommendations exists) |
| Wardrobe Enrichment | gpt-5-mini (vision) | On every chat-uploaded garment image + outfit decomposition | wardrobe_ingestion (silent), pairing_request (when image attached), outfit_check (async decomposition), garment_evaluation (when image attached) |
| Try-On Service | gemini-3.1-flash-image-preview | Inline before visual evaluator (Phase 12B) for all top-3 candidates in parallel | occasion_recommendation, pairing_request, garment_evaluation |
| Outfit Check Agent (legacy) | gpt-5.4 | Kept until tests are migrated off it; not called by the Phase 12 outfit_check path | (none in production after Phase 12B rewire) |

**No LLM calls** (deterministic only):
- `feedback_submission`
- `style_discovery` topical questions (collar / neckline / pattern / silhouette / archetype / color use the deterministic Phase 11 helpers)
- `explanation_request` when no `previous_recommendations` exists (uses the deterministic explanation summary)
- `outfit_check` decomposition save (the actual evaluation is the Visual Evaluator above; the async decomposition pipeline is vision-API but not via the orchestrator's main thread)
- `wardrobe_ingestion` silent saves (the enrichment vision call is part of the save path; the orchestrator doesn't make additional LLM calls)

### Per-turn LLM call counts (Phase 12)

| Intent | LLM calls | Image generation calls |
|---|---|---|
| `occasion_recommendation` (visual path, user has photo) | planner (1) + architect (1) + visual_evaluator (3 parallel) = 5 | tryon ×3 in parallel |
| `occasion_recommendation` (legacy text path, no photo) | planner (1) + architect (1) + outfit_evaluator (1) = 3 | 0 |
| `pairing_request` (visual path) | planner (1) + architect (1) + visual_evaluator (3 parallel) = 5 | tryon ×3 |
| `garment_evaluation` | planner (1) + visual_evaluator (1) = 2 | tryon ×1 |
| `outfit_check` | planner (1) + visual_evaluator (1) = 2 | 0 (no try-on; user is already in the photo) |
| `style_discovery` topical | planner (1) = 1 | 0 |
| `style_discovery` general | planner (1) + style_advisor (1) = 2 | 0 |
| `explanation_request` with prior context | planner (1) + style_advisor (1) = 2 | 0 |
| `explanation_request` no prior context | planner (1) = 1 | 0 |
| `feedback_submission` | planner (1) = 1 | 0 |

---

## Database Write Summary (Phase 12)

| Table | Written By | Intents |
|-------|-----------|---------|
| `conversation_turns` | `repo.finalize_turn()` | All advisory + feedback |
| `conversations.session_context_json` | `repo.update_conversation_context()` | All advisory + feedback |
| `model_calls` | `repo.log_model_call()` | occasion_recommendation, pairing_request, outfit_check, garment_evaluation |
| `feedback_events` | `repo.create_feedback_event()` | feedback_submission |
| `user_wardrobe_items` | `onboarding_gateway.save_wardrobe_item()` | pairing_request (anchor upload), garment_evaluation (anchor upload), outfit_check (async decomposition), explicit `wardrobe_ingestion` save |
| `virtual_tryon_images` | `repo.insert_tryon_image()` | occasion_recommendation, pairing_request (Phase 12B inline), garment_evaluation |
| `catalog_interaction_history` | `_persist_catalog_interactions()` | occasion_recommendation, pairing_request |
| `confidence_history` | `_persist_recommendation_confidence()` | occasion_recommendation, pairing_request |
| `policy_event_log` | `_persist_policy_event()` | wardrobe_ingestion, garment_evaluation (try-on policy events via `/v1/tryon` endpoint) |
| `dependency_validation_events` | `_persist_dependency_turn_event()` | All advisory + feedback. Now includes Phase 12E `evaluator_path` and `tryon_stats` for the operations dashboard |
| `user_comfort_learning` | comfort_learning service | feedback_submission (like events) |
