# Workflow Reference — Intent Execution Flows

Last updated: April 5, 2026

> **Runtime role:** This is the system's canonical execution plan reference. After the copilot planner classifies a user message into one of the 12 intents, the orchestrator follows the workflow defined here to produce a response. Every handler, branching condition, database operation, and LLM call is documented. This file is the authoritative source for how each intent is executed — agents and planners should stick to these flows.

**Registry:** All intent identifiers are defined as `StrEnum` constants in `agentic_application/intent_registry.py`. The copilot planner JSON schema, orchestrator dispatch, and all agent code import from this single source of truth.

**Canonical location:** `knowledge/workflow_reference.md` (mirrored to `docs/WORKFLOW_REFERENCE.md` for documentation navigation).

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

2. Planner Overrides via _apply_planner_overrides()
   │  Deterministic keyword checks that CORRECT the LLM planner's classification
   │  when phrase signals are more reliable than the model's output.
   │
   ├── Catalog follow-up override
   │   └── "show me catalog options" after wardrobe answer → forces followup_intent="catalog_followup"
   ├── Follow-up intent phrase override
   │   └── Formality/boldness phrases → overrides followup_intent + sets formality_hint
   ├── Targeted item override
   │   └── "show me shirts" → overrides intent→OCCASION_RECOMMENDATION, action→RUN_RECOMMENDATION_PIPELINE
   ├── Pairing request override
   │   └── "what goes with this" + attached image → overrides intent→PAIRING_REQUEST, extracts anchor piece
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

2. Planner Override: _message_requests_pairing() [corrects LLM misclassification]
   ├── Keyword match: "goes with", "pair with", "style this", "complete the outfit"
   ├── If match + planner said something else: override intent → PAIRING_REQUEST, action → RUN_RECOMMENDATION_PIPELINE
   ├── Extract anchor piece title from attached item or previous context
   └── Common case: planner classifies as occasion_recommendation, override corrects to pairing_request

3. Route Selection (3 paths):

   Path A: Catalog-Image Pairing
   ├── Condition: attachment_source == "catalog_image"
   ├── Extract anchor from catalog item metadata
   ├── Determine complementary roles (top→bottom, bottom→top, etc.)
   ├── Select catalog pairings via _select_catalog_items()
   ├── Build outfit card: [anchor + 2 catalog pairings]
   └── Return immediately

   Path B: Wardrobe-First Pairing
   ├── Condition: wardrobe items exist + target piece identifiable
   ├── _find_target_wardrobe_piece() — fuzzy match on message keywords
   ├── _select_wardrobe_pairings()
   │   └── Score by: role complementarity (4pts), occasion match (2pts)
   ├── _select_catalog_items() — 2 catalog alternatives
   ├── Build two outfit cards:
   │   ├── Rank 1: [target + wardrobe pairings] (source: wardrobe)
   │   └── Rank 2: [target + catalog alternatives] (source: catalog)
   └── Return immediately

   Path C: Full Catalog Pipeline
   ├── Condition: neither wardrobe path matches
   ├── Target piece becomes anchor constraint for architect
   └── Runs full 6-stage pipeline (same as occasion_recommendation)
```

### Key Difference from Occasion
- Wardrobe-first pairing produces **hybrid outfits** (wardrobe anchor + catalog fillers)
- Searches are constrained to **complementary roles** relative to the anchor garment
- Anchor piece is never echoed back as the full answer

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

**Intent:** `Intent.SHOPPING_DECISION`
**Action:** `Action.RUN_SHOPPING_DECISION`
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

**Intent:** `Intent.CAPSULE_OR_TRIP_PLANNING`
**Action:** `Action.RESPOND_DIRECTLY`
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

**Intent:** `Intent.VIRTUAL_TRYON_REQUEST`
**Action:** `Action.RUN_VIRTUAL_TRYON`
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

**Intent:** `Intent.GARMENT_ON_ME_REQUEST`
**Action:** `Action.RESPOND_DIRECTLY`
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

**Intent:** `Intent.PRODUCT_BROWSE`
**Action:** `Action.RUN_PRODUCT_BROWSE`
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

| Component | Model | When Called | Intents |
|-----------|-------|------------|---------|
| Copilot Planner | gpt-5.4 | Every turn | All 12 |
| Outfit Architect | gpt-5.4 | Recommendation pipeline | occasion, pairing |
| Outfit Evaluator | gpt-5.4 | Recommendation pipeline | occasion, pairing |
| Outfit Check Agent | gpt-5.4 | Outfit check handler | outfit_check |
| Shopping Decision Agent | gpt-5.4 | Shopping decision handler | shopping_decision |
| Virtual Try-On | gemini-3.1-flash-image-preview | Try-on generation | virtual_tryon, occasion (post-pipeline) |

**No LLM calls:** style_discovery, explanation_request, capsule_or_trip_planning, garment_on_me (uses planner output), wardrobe_ingestion, feedback_submission, product_browse (uses planner output only — no additional LLM calls beyond the planner).

---

## Database Write Summary

| Table | Written By | Intents |
|-------|-----------|---------|
| `conversation_turns` | `repo.finalize_turn()` | All 12 |
| `conversations.session_context_json` | `repo.update_conversation_context()` | All 12 |
| `model_calls` | `repo.log_model_call()` | occasion, pairing, outfit_check, shopping_decision |
| `feedback_events` | `repo.create_feedback_event()` | feedback_submission |
| `user_wardrobe_items` | `onboarding_gateway.save_wardrobe_item()` | wardrobe_ingestion, outfit_check (async decomposition) |
| `virtual_tryon_images` | `repo.insert_tryon_image()` | virtual_tryon, occasion (post-pipeline) |
| `catalog_interaction_history` | `_persist_catalog_interactions()` | occasion, pairing |
| `confidence_history` | `_persist_recommendation_confidence()` | occasion, pairing |
| `policy_event_log` | `_persist_policy_event()` | virtual_tryon, wardrobe_ingestion |
| `dependency_validation_events` | `_persist_dependency_turn_event()` | All 12 |
| `user_comfort_learning` | comfort_learning service | feedback_submission (like events) |
