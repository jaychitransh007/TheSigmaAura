# Workflow Reference — Intent Execution Flows

Last updated: May 6, 2026 (post-PR-#101: rater on a 6-dim 1/2/3 scale; episodic memory at the architect; source_preference→catalog default; composer-emitted card names; threshold 50)

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

## Current State (post-R7, May 6, 2026)

The system has evolved across three major reshapings since the original Phase 12 architecture: Phase 12 itself (intent consolidation, April 2026), the LLM ranker rollout (Composer + Rater replace deterministic Assembler + Reranker, May 3 2026), and the May 5–6 sweep that introduced the R7 6-dim 1/2/3 rater, episodic memory at the architect, the auto→catalog default routing, and per-outfit composer names. This summary describes what runs today; the per-intent sections below contain historical detail and may reference removed paths — refer here for the current shape.

### Current intent taxonomy (6 intents, 5 actions)

| Intent | Action | Pipeline shape |
|---|---|---|
| `occasion_recommendation` | `RUN_RECOMMENDATION_PIPELINE` | planner → (optional wardrobe-first short-circuit) → architect → search → composer (LLM, emits per-outfit `name`) → rater (LLM, 6 dims on 1/2/3) → threshold gate (50) → tryon (top-3 parallel) → format. Default `source_preference="auto"` routes to the catalog (PR #82); wardrobe-first only fires when explicit AND ≥2-per-role coverage holds. Absorbs the old `product_browse` intent via `target_product_type`. |
| `pairing_request` | `RUN_RECOMMENDATION_PIPELINE` | Same as occasion_recommendation, with `enriched_data["is_anchor"]=True` on the synthetic anchor `RetrievedProduct`. The diversity pass exempts anchors so all 3 outfits survive. Photo upload is mandatory. |
| `style_discovery` | `RESPOND_DIRECTLY` | Layered: deterministic topical helpers (collar, color, pattern, silhouette, archetype) for matched topics; `StyleAdvisorAgent` LLM fallback in `discovery` mode for open-ended questions. |
| `explanation_request` | `RESPOND_DIRECTLY` | Layered: `StyleAdvisorAgent` in `explanation` mode when `previous_recommendations` exists; deterministic explanation summary as the fallback. |
| `feedback_submission` | `SAVE_FEEDBACK` | Pure event capture, no LLM. Writes a `feedback_events` row (event_type ∈ {`like`, `dislike`}); the row's `turn_id` + `garment_id` is the same signal `list_recent_user_actions` reads to build the architect's episodic memory on subsequent turns. |
| `wardrobe_ingestion` | `SAVE_WARDROBE_ITEM` | **Silent** — not exposed in the planner prompt's user-facing intent list. Available for programmatic / bulk upload paths only. |

### Removed since Phase 12

- `capsule_or_trip_planning` — handler deleted (Phase 12A); to return in a future phase
- `product_browse` — folded into `occasion_recommendation` via `CopilotResolvedContext.target_product_type`
- `virtual_tryon_request` / `shopping_decision` / `garment_on_me_request` — absorbed into `garment_evaluation` (Phase 12A)
- **`garment_evaluation`** — removed in V2 (May 5 2026) when `visual_evaluator_agent.py` was deleted. "Should I buy this?" + "How does this look on me?" requests are now handled by `pairing_request` (the user uploads the anchor; the system pairs it with complementary pieces; the resulting card inherently shows whether the piece works).
- **`outfit_check`** — removed in V2 alongside `visual_evaluator`. Standalone outfit evaluation isn't a live flow today.
- **`visual_evaluator_agent.py`** — the entire vision-grounded evaluator was removed in V2. The Rater is now the sole evaluator, scoring composed outfits on six 1/2/3 sub-scores. The legacy 8-axis archetype + 9-dim fit/eval split-polar radar is gone; the OutfitCard radar is now a 6-axis hexagon (5-axis pentagon for `complete` outfits) populated directly from rater sub-scores.

### Current rater rubric (R7, PR #101 May 5 2026)

| Dim | Default weight | What's scored |
|---|---:|---|
| `occasion_fit` | 0.25 | occasion + time-of-day match (formality scored separately) |
| `color_harmony` | 0.20 | inter-item palette agreement + season/undertone fit |
| `body_harmony` | 0.15 | anatomy snapshot ↔ silhouette/fit |
| `pairing` | 0.15 | fit-type compatibility + fabric pairing (multi-item only; drops to None for `complete` outfits) |
| `formality` | 0.13 | request-formality match + inter-item formality consistency |
| `statement` | 0.12 | pattern density + embellishment intensity, weighed against the user's risk_tolerance and the occasion |

Each sub-score is a **discrete integer in `{1, 2, 3}`** — schema-locked via `enum: [1, 2, 3]` per property. 1 = clear miss, 2 = works, 3 = clear win. The 1/2/3 scale was deliberate: LLMs cluster ~70–90 on a 0–100 scale with no real discrimination; a discrete 3-point choice forces honest sub-scores.

The orchestrator blends them in Python via `compute_fashion_score`:

```
raw   = Σ subscore × weight        (1.0 .. 3.0)
score = ((raw − 1) / 2) × 100      (0 .. 100)
```

All-1s outfit → 0. All-2s → 50. All-3s → 100. The threshold gate at `_RECOMMENDATION_FASHION_THRESHOLD = 50` (PR #101) lands on "every dim is at least neutral barely clears" — an outfit at 2 across the board barely clears; one with even one "1" on a heavily-weighted axis falls below.

Five weight profiles, picked by `select_weight_profile()` from planner-resolved context, all summing to 1.0:

- **default** (the table above)
- **ceremonial** — `occasion_fit` + `formality` dominate; fired when occasion ∈ {wedding, festival, ceremony, …}
- **slimming** — `body_harmony` leads; fired when user message contains "slimmer" / "taller" / "look thin"
- **bold** — `color_harmony` + `statement` lead; fired on "bold" / "statement" / "colorful"
- **comfortable** — `body_harmony` + `pairing` lead; fired on "comfortable" / "relaxed"

For `complete` (single-item) outfits, `pairing` drops out and the remaining five weights renormalize to sum to 1.0. The Rater emits `pairing: 3` in this case and `compute_fashion_score` ignores it.

`unsuitable=True` is the only hard veto. PR #89 (May 5 2026) removed the `archetypal_preferences.disliked` aggregate-veto rule that was producing systematic empty responses (T12 had 8/8 outfits vetoed); past likes/dislikes are now applied upstream by the Architect (retrieval bias via episodic memory) and the Composer (item-selection bias).

### Episodic memory at the architect (PR #90 / #92 / #93)

The architect input includes `recent_user_actions` — a chronological 30-day timeline of like/dislike events. Each row carries:

- `event_type`: `"like"` or `"dislike"`
- `created_at`: ISO timestamp
- `turn_id`: the turn that produced the outfit
- `user_query`: the chat message that produced the outfit (e.g. "what should I wear to the office")
- `item`: garment attributes — `title`, `primary_color`, `garment_subtype`, `color_temperature`, `pattern_type`, `fit_type`, `silhouette_type`, `embellishment_level`, `formality_level`, `occasion_fit`

Loaded via `ConversationRepository.list_recent_user_actions(user_id, lookback_days=30)`. The architect prompt instructs the LLM to use this as **pattern evidence, not rules** — find context-dependent signals (different occasions can take the same attribute differently — a user who disliked solid navy at the office may still want it for date night), and bias `query_document` text + `hard_filters` toward likes / away from dislikes **in similar contexts**. Capped at 30 most recent events to bound prompt size; configurable via `RECENT_USER_ACTIONS_LOOKBACK_DAYS_DEFAULT`.

PR #92 caught a silent failure: the original snake_case query against `catalog_enriched` returned PostgREST 400-errors (the schema uses PascalCase: `ColorTemperature`, `PatternType`, etc.), and the surrounding `except Exception` swallowed it, so every user got an empty timeline since #90 merged. PR #93 consolidated the catalog attr mapping into a single `_CATALOG_ATTR_MAP` (snake_case prompt key → PascalCase DB column) to prevent the same drift; PR #97 narrowed the broad excepts to `(SupabaseError, httpx.RequestError)` so logic errors propagate instead of silently degrading.

### source_preference routing (PR #82, May 5 2026)

The planner extracts `source_preference` into `CopilotResolvedContext`:

| Value | Trigger | Routing |
|---|---|---|
| `"wardrobe"` | User says "from my wardrobe", "use my wardrobe", "from my closet" | Wardrobe-first short-circuit fires; if the wardrobe meets ≥2 tops AND ≥2 bottoms AND ≥2 one-pieces, the orchestrator builds a wardrobe outfit (with optional hybrid catalog gap-fill) and skips the architect/composer/rater pipeline. Below the gate, falls through to `wardrobe_unavailable` answer-source with the actual counts surfaced. |
| `"catalog"` | User says "from the catalog", "skip my wardrobe", "catalog only" | Full catalog pipeline; wardrobe-first never fires. |
| `"auto"` (default) | Anything else | **Routes to catalog** (default flipped from wardrobe-first in PR #82). Full architect → composer → rater → tryon pipeline. |

Pre-#82, `"auto"` defaulted to wardrobe-first; the resulting confusion (catalog turns getting blocked by thin wardrobes) drove the flip. The minimum-coverage gate when wardrobe IS requested protects against the new failure mode where an opted-in wardrobe-first user has insufficient items.

### Key building blocks

| Component | Source | Purpose |
|---|---|---|
| `agents/copilot_planner.py` | Phase 12 | gpt-5-mini classifies intent + action and resolves `live_context` (occasion_signal, formality_hint, time_of_day, weather_context, source_preference, target_product_type, specific_needs, etc.). Strict structured-output schema with enum-locked intent + action vocabularies. |
| `agents/outfit_architect.py` | Phase 12 → 4.7 router | **gpt-5.2**, `reasoning_effort=low` (down from gpt-5.4 medium per the Phase 1.4 cost-latency swap). Still plans 1–3 directions when invoked, but a router (`composition/router.py`, Phase 4.9) sits in front of `OutfitArchitect.plan()` and tries the deterministic composition engine first when `AURA_COMPOSITION_ENGINE_ENABLED=true`. Engine accepts → architect LLM never runs (architect stage drops 19s → ~0ms); engine falls through → LLM architect runs unchanged. Reads `recent_user_actions` (PR #90) for episodic memory bias on the LLM path. Hard filters limited to `gender_expression` + `garment_subtype`. |
| `composition/engine.py` + `composition/router.py` + `composition/canonicalize.py` | Phase 4.7 + 4.9 + 4.11 (PRs #149, #151) | Deterministic YAML reduction over the 8 style-graph YAMLs. Router applies spec §9 fall-through criteria (`confidence < 0.50`, `yaml_gap`, `needs_disambiguation`, `excessive_widening`) plus pre-engine eligibility gates (`anchor_present`, `followup_request`, `has_previous_recommendations`). Canonicalize bridges free-text planner output to YAML-canonical keys via batched `text-embedding-3-small` nearest-neighbour. RouterDecision metadata flows to `distillation_traces.full_output.router_decision` for observability (panels 21-24). |
| `agents/outfit_composer.py` | LLM ranker (May 3, PR #29) | gpt-5.4, `reasoning_effort=low` (promoted from gpt-5-mini in PR #81 for the heavier reasoning task). Builds up to 10 coherent outfits from the retrieved pool; emits a per-outfit `name` (PR #88, e.g. *"Camel Sand Refined"*) that surfaces as the user-facing card title. Schema-locked `direction_id` enum (PR #80) so the LLM physically can't write a SKU there. Per-attempt `on_attempt` callback gives one `model_call_logs` row per LLM call (PR #80) with real `latency_ms` (PR #95). Smart retry on hallucinated item_ids. |
| `agents/outfit_rater.py` | LLM ranker (May 3, PR #29) + R7 (May 5, PR #101) | gpt-5-mini, `reasoning_effort=minimal`. Scores each composed outfit on six 1/2/3 sub-scores (`occasion_fit`, `body_harmony`, `color_harmony`, `pairing`, `formality`, `statement`). Schema enforces `enum: [1, 2, 3]` per dim. `unsuitable: bool` is the only hard veto; the archetypal-preferences veto was removed in PR #89. Past likes/dislikes are applied upstream — the Rater scores what's in front of it. |
| `agents/style_advisor_agent.py` | 12C | LLM advisor for open-ended `style_discovery` and `explanation_request`. Returns structured advice with prose answer + bullets + cited attributes + dominant directions. |
| `compute_fashion_score()` | `outfit_rater.py` | Deterministic Python blender. `raw = Σ subscore × weight` (1.0..3.0), `score = ((raw − 1) / 2) × 100` (0..100). Drops `pairing` for `complete` outfits and renormalizes the remaining five weights. Five profiles, all summing to 1.0. |
| `_RECOMMENDATION_FASHION_THRESHOLD` | `orchestrator.py:92` | Pre-render gate at `50`. Outfits below the floor or flagged `unsuitable` never reach the user. History: `75` → `60` (PR #81) → `50` (PR #101 R7). |
| `list_recent_user_actions()` | `repositories.py` (PR #90) | Pulls feedback_events for the user (last 30 days, like+dislike), hydrates garment attrs from `catalog_enriched`, joins `user_query` from `conversation_turns`. Cap of 30 events per user. Empty list on cold start. |
| `_wardrobe_meets_minimum_coverage()` | `orchestrator.py` (PR #82) | Returns `(sufficient, counts_by_role)`. Strict-AND: ≥2 tops AND ≥2 bottoms AND ≥2 one-pieces. Used by both `_build_wardrobe_first_occasion_response` (the gate) and `_build_wardrobe_only_occasion_fallback` (the message), threaded via `precomputed_coverage` to avoid double-walking the same wardrobe. |
| `_CATALOG_ATTR_MAP` | `repositories.py` (PR #93) | Single source of truth for snake_case prompt key → PascalCase DB column on `catalog_enriched`. Used by `aggregate_archetypal_feedback` and `list_recent_user_actions`. |
| `weather_context` / `time_of_day` / `target_product_type` | 12A/C | New `CopilotResolvedContext` fields extracted by the planner, consumed by the architect. |
| `is_anchor` flag on candidate items | 12D | Set by orchestrator anchor injection; consumed by `_enforce_cross_outfit_diversity` to exempt anchor products from the "no repeats" rule. Fixes the pre-existing bug where pairing turns collapsed to 1 outfit. |
| Wardrobe-anchor image resolution | 12D follow-up | `_product_to_item` resolves `image_url` from `enriched_data["image_path"]` and tags wardrobe rows with `source="wardrobe"`. `tryon_service.generate_tryon_outfit` dispatches HTTP(S) URLs to `_download_image` and local `data/...` paths to `_load_local_image`. |
| `is_garment_photo` + `garment_present_confidence` | 12D follow-up | Vision model classifies whether the upload is actually a wearable garment BEFORE extracting the 46 attributes. The orchestrator's `non_garment_image` guard fires when `is_garment_photo is False` OR `garment_present_confidence < 0.5`, short-circuiting the entire pipeline and returning a clarification. |
| Try-on parallel renders + over-generation metrics | 12E | `ThreadPoolExecutor`-based parallel render of top-3 candidates. `tryon_attempted_count`, `tryon_succeeded_count`, `tryon_quality_gate_failures`, `tryon_overgeneration_used` surfaced in `response.metadata` for the operations dashboard. |

### Phase 13/13B: Outfit Architect Prompt & Schema Remediation (April 10, 2026)

Scope: correctness, robustness, and retrieval quality improvements to the architect prompt (`prompt/outfit_architect.md`) and its code wrapper. No new pipeline components — this hardens the planning stage.

| Change | Impact |
|---|---|
| `live_context` wired to architect | `weather_context`, `time_of_day`, `target_product_type` now reach the LLM via `_build_user_payload()`. Added to `LiveContext` schema, wired in `_build_effective_live_context()`. |
| `ranking_bias` field | Was a new field on `ResolvedContextBlock` (Phase 13B). **Removed May 3, 2026 (PR #30)** — the LLM Rater reads user context directly, no separate bias plumbing. |
| Occasion-driven structure selection | Removed contradictory "exactly 3, one of each" rule. Architect now creates 2–3 directions using only structures appropriate for the occasion. |
| Style-stretch direction | Third direction pushes user's style one notch beyond comfort zone, gated by riskTolerance. Hard-guarded: fabric/formality/embellishment/AvoidColors not relaxable. |
| Weather-fabric override | Weather overrides occasion for fabric weight/breathability. Hot/humid wedding → silk/crepe not velvet. |
| Occasion calibration consolidation | Merged 3 overlapping sections (Sub-Occasion Calibration + Embellishment Reasoning + Occasion-Fabric Coupling) into one reference table. |
| Anchor conflict resolution | Rules for every anchor category (top/bottom/outerwear/complete). Formality conflict rule: shift supporting garments up. |
| Query doc completeness | Changed from "write not_applicable" to "omit inapplicable fields" for cleaner embedding signal. Per-role omission guide. |
| Retrieval count guidance | Per-request-type table (12 broad, 6 single-garment, 8–10 anchor, 10–15 more_options). |
| Follow-up intent tiebreaker | Priority: change_color > increase/decrease_formality > increase_boldness > full_alternative > similar_to_previous > more_options. |
| Follow-up field mapping | change_color and similar_to_previous rules now reference exact schema field names from previous_recommendations. |
| Inventory starvation fix | Occasion fit > inventory count. Subtypes with ≥1 item are usable. Fallback direction for < 3 items (replaces lowest-confidence direction if exceeding 3 total). |
| Color synonym expansion | PrimaryColor/SecondaryColor use comma-separated synonyms (e.g., "terracotta, rust, burnt orange"). |
| Semantic fabric clusters | FabricTexture/FabricDrape use multi-term phrases for broader embedding match. |
| Thinking Directions position | Moved to after resolved_context rules, before Direction Rules — framing lens, not postscript. |
| `DirectionSpec.direction_type` | Comment updated to `# complete | paired | three_piece` |
| Direction differentiation | Query documents across directions must use noticeably different vocabulary. Similar docs → overlapping retrieval → diversity pass (`MAX_PRODUCT_REPEAT_PER_RUN=1`) drops candidates → only 1-2 outfits survive. Reinforced in Query Document Format and Concept-First Planning sections. |
| Subtype diversification | When multiple directions share a role, vary GarmentSubtype — but only using subtypes present in `catalog_inventory`. Staging showed LLM chose `polo` (0 in catalog), wasting a direction. |
| Office sub-occasion split | "Office / business" split into "Formal office" (paired + three_piece) and "Daily office" (paired only). `daily_office` occasion_signal added. Default: daily_office unless meetings/presentations mentioned. |
| Search timeout retry | `_MAX_SEARCH_WORKERS` 4→2, 1 retry on timeout (error 57014) with 0.5s delay. Staging showed 7 concurrent vector RPCs caused intermittent statement timeouts → 0 products for timed-out queries → 1-outfit responses. |

### Color Analysis Overhaul — 12 Sub-Season Typing (Phase: Color Overhaul)

| Change | Impact |
|---|---|
| SkinUndertone + SkinChroma added to color prompt | 7 attributes extracted (was 5). Olive detection for South Asian users. Zero added latency. |
| EyeClarity → EyeChroma rename | Backward-compat fallback in interpreter for existing DB rows. |
| Weighted warmth score | SkinUndertone(×3) + HairTemp(×2) + EyeColor(×1) replaces single-attribute binary branch. Ambiguous flag. |
| SkinHairContrast | New first-class derived interpretation. Wired to visual evaluator + style advisor. |
| ColorDimensionProfile | Raw warmth/depth/contrast/chroma surfaced as derived interpretation. |
| ~~Draping~~ | Removed — LLM draping had systematic cool-bias. Deterministic interpreter is sole color authority. |
| 12 sub-seasons | Warm/Deep/Soft Autumn, Warm/Light/Clear Spring, Cool/Light/Soft Summer, Cool/Deep/Clear Winter. |
| 12 sub-season palettes | 168 curated colors. Boundary blending for ambiguous users. |
| Anti-hedging calibration | Body type prompt: CALIBRATION section prevents center-bias on VisualWeight/ArmVolume. |
| FrameStructure interpreter fix | Removed height penalty, fixed label mapping. |
| BodyShape → silhouette mapping | Architect prompt maps all 7 body shapes to silhouette strategy, volume guidance, and StructuralFocus. BodyShape overrides FrameStructure for width decisions. |
| Onboarding reorder | Steps: mobile→otp→name→gender→images→dob→body→profession→style (9 steps, was 10). Incremental save after each field. Resume flow pre-fills from existing profile. |
| Phased analysis | Color agent starts after images (phase 1), other_details after DOB (phase 2), body_type after profile save (phase 3). |

Tests: 127+ passing.

### What stays the same

The catalog search agent (`CatalogSearchAgent`) now has timeout retry logic but its core responsibility (embed → search → hydrate) is unchanged. The response formatter (`ResponseFormatter`), try-on service (`TryonService`), and try-on quality gate (`TryonQualityGate`) are unchanged. Phase 12 added new components alongside them; Phase 13/13B hardened the architect's planning quality and search resilience without changing the pipeline shape. **OutfitAssembler was removed in May 3 2026 PR #30**, replaced by the LLM ranker (Composer + Rater).

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
    → Copilot Planner [gpt-5.5] → classifies intent + selects action
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
1. Copilot Planner [gpt-5.5]
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
   ├── Stage 1: Outfit Architect [gpt-5.5]
   │   ├── Input: CombinedContext (profile, live context, hard filters, previous recs)
   │   ├── Output: ArchitectPlan with directions (direction_type per direction, query specs)
   │   ├── 2-3 directions, structure chosen by occasion (not mechanical one-of-each)
   │   ├── Direction types: complete (1 query), paired (top+bottom), three_piece (top+bottom+outerwear)
   │   ├── Concept-first: color coordination, volume balance, pattern distribution, occasion-fabric coupling
   │   └── DB: repo.log_model_call(call_type="outfit_architect")
   │
   ├── Stage 2: Catalog Search [pgvector, parallelized]
   │   ├── Step 1: batch embed ALL query documents in one OpenAI call (text-embedding-3-small, 1536d)
   │   ├── Step 2: parallel search+hydrate via ThreadPoolExecutor (4 workers)
   │   ├── Hard filters: gender_expression (always), garment_subtype (conditional); styling_completeness from direction role; garment_category is soft signal only
   │   ├── Soft signals via embedding similarity: all 46 enrichment attributes including embellishment, visual direction, occasion, formality, color
   │   ├── No filter relaxation — single search pass, 1 retry on timeout (Post-13B)
   │   ├── Retrieve: 12 products per query direction
   │   └── Hydrate: product_id → catalog_enriched row
   │
   ├── Stage 3: Outfit Assembly [deterministic]
   │   ├── Complete directions: each product → one candidate (score = similarity)
   │   ├── Paired directions: top × bottom cross-product (capped at 15 each)
   │   ├── Three-piece directions: top × bottom × outerwear (capped at 10 each, 60/40 weighted scoring)
   │   ├── Role-category validation: top→top, bottom→bottom, outerwear→outerwear, complete→set/one_piece; accessories rejected
   │   ├── Duplicate product check: same product_id cannot appear in multiple roles
   │   ├── Compatibility checks: formality, occasion, color temp, pattern, volume, fit, texture
   │   └── MAX_PAIRED_CANDIDATES = 30
   │
   ├── Stage 4: Outfit Evaluation [gpt-5-mini]
   │   ├── Input: all candidates + user context + previous recommendation deltas
   │   ├── Scores per outfit (16 fields):
   │   │   ├── 8 evaluation criteria: body_harmony, color_suitability, style_fit,
   │   │   │   risk_tolerance, occasion, comfort_boundary, specific_needs, pairing_coherence
   │   │   └── 8 style archetypes: classic, dramatic, romantic, natural,
   │   │       minimalist, creative, sporty, edgy
   │   ├── Graceful fallback: criteria from fashion_score if LLM fails
   │   ├── Hard cap: maximum 5 evaluated recommendations
   │   └── DB: repo.log_model_call(call_type="visual_evaluator")
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
| `outfits` | Up to 3 `OutfitCard` objects with items, scores, tryon_image. The catalog-pipeline gate (`_RECOMMENDATION_FASHION_THRESHOLD = 75` in `orchestrator.py`) drops any candidate whose `fashion_score` falls below 75; if **zero** candidates clear, `_build_low_confidence_catalog_response` runs instead and returns `outfits=[]` with an honest "I couldn't find a strong match" message + refine / show-closest / shop CTAs. The wardrobe-first path uses the equivalent `_RECOMMENDATION_CONFIDENCE_THRESHOLD = 0.75` floor on its normalized item score. |
| `metadata.answer_source` | `"wardrobe_first"`, `"catalog_pipeline"`, `"hybrid"`, or `"catalog_low_confidence"` (no outfits cleared the threshold) |
| `metadata.recommendation_confidence` | 9-factor confidence object |
| `metadata.low_confidence_top_match_score` | Only set when `answer_source == catalog_low_confidence` — the highest `fashion_score` seen (normalized to 0–1 in this metadata field), surfaced for ops dashboards (never shown to the user) |
| `follow_up_suggestions` | e.g., `"Show me options to buy"` (catalog upsell CTA — was `"Show me better options from the catalog"` pre-May 3), `"Show me bolder options"`, `"Refine the request"` |

---

## 2. Garment Pairing

**Intent:** `Intent.PAIRING_REQUEST`
**Action:** `Action.RUN_RECOMMENDATION_PIPELINE`
**Trigger:** "What goes with this?", "Style this shirt", "Pair this blazer"

### Step-by-Step Flow

```
1. Copilot Planner [gpt-5.5]
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
   ├── Stage 1: Outfit Architect [gpt-5.5]
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
   ├── Stage 4: Outfit Evaluation [gpt-5-mini]
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
1. Copilot Planner [gpt-5.5]
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
1. Copilot Planner [gpt-5.5]
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
1. Copilot Planner [gpt-5.5]
   └── intent=outfit_check, action=run_outfit_check

2. Planner Override: _message_requests_outfit_check()
   ├── Keyword match: "how does this look", "rate my outfit", "outfit check"
   └── If match: override intent → OUTFIT_CHECK, action → RUN_OUTFIT_CHECK

3. Dispatch → _handle_outfit_check()

4. Vision-Based Outfit Evaluation [gpt-5-mini]
   ├── Agent: VisualEvaluatorAgent.evaluate_candidate() (mode="outfit_check")
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
1. Copilot Planner [gpt-5.5]
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
1. Copilot Planner [gpt-5.5]
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
1. Copilot Planner [gpt-5.5]
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
1. Copilot Planner [gpt-5.5]
   ├── intent=garment_on_me_request, action=respond_directly
   └── Generates personalized answer using profile context

2. Dispatch → _handle_direct_response()
   ├── No dedicated handler (unlike style_discovery or explanation_request)
   └── Falls through to copilot_planner.assistant_message

3. Response: Planner's LLM-generated personalized assessment
   ├── Based on: user profile, style archetype, body shape, color analysis
   ├── Considers: garment description from message or attached image
   └── No separate agent call (uses VisualEvaluatorAgent in single_garment mode)

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
1. Copilot Planner [gpt-5.5]
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
1. Copilot Planner [gpt-5.5]
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
1. Copilot Planner [gpt-5.5]
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
   └── Hard filters: gender_expression (always) + garment_subtype (conditional); garment_category is soft signal only

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

### Phase 12 + Latency Push 4.7+ (Current)

> **2026-05-07 update** — model + path table revised after PRs #149-#155. Architect + composer now run on **gpt-5.2 reasoning_effort=low** (Phase 1.4 swap, May 13 2026). Architect on the engine path skips the LLM entirely; see "Composition router path" row below.

| Component | Model | When Called | Intents |
|-----------|-------|------------|---------|
| Copilot Planner | gpt-5-mini | Every turn | All 7 advisory + feedback + silent wardrobe_ingestion |
| **Composition router path (4.7+)** | none — deterministic YAML reduction (~0ms compute, ~150ms canonicalize embed when needed) | Recommendation pipeline when `AURA_COMPOSITION_ENGINE_ENABLED=true` AND no anchor / no followup / no prior recs / canonicalize succeeds / engine confidence ≥ 0.50. Bypasses the architect LLM entirely on accept. Model_call_logs row is stamped `model='composition_engine'`. | occasion_recommendation, pairing_request |
| Outfit Architect (LLM fallback) | gpt-5.2 | Same intents, but only when the engine path falls through (yaml_gap / low_confidence / needs_disambiguation / excessive_widening / ineligibility). System prompt composed at request time: 4.8K-token base + optional anchor module + optional follow-up module. | occasion_recommendation, pairing_request |
| Visual Evaluator | gpt-5-mini (vision) | Per-candidate after try-on; sole evaluator in the system (legacy agents removed) | occasion_recommendation, pairing_request, garment_evaluation, outfit_check |
| Style Advisor | gpt-5.5 | Open-ended style discovery + explanation against prior recommendations | style_discovery (general topic), explanation_request (when previous_recommendations exists) |
| Wardrobe Enrichment | gpt-5-mini (vision) | On every chat-uploaded garment image + outfit decomposition | wardrobe_ingestion (silent), pairing_request (when image attached), outfit_check (async decomposition), garment_evaluation (when image attached) |
| Try-On Service | gemini-3.1-flash-image-preview | Inline before visual evaluator for the top-3 candidates. Renders run in a `ThreadPoolExecutor` parallel batch; cache hits (per `find_tryon_image_by_garments`) short-circuit inside the thread before the Gemini call. INFO logs emit `tryon parallel batch: N/N succeeded (cold=K, cache_hit=M) in Xms wallclock` per batch. | occasion_recommendation, pairing_request, garment_evaluation |

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
| `occasion_recommendation` (visual failure fallback) | planner (1) + architect (1) = 2 (visual evaluator failed → graceful empty response, no legacy evaluator) | 0 |
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

---

# Phase History (migrated May 3, 2026)

_Migrated from `CURRENT_STATE.md`. The full historical decision log of Phases 9–15, plus the parked architectural considerations, cleanup plans, and color-system overhauls. Anyone wanting to understand WHY the system looks the way it does — read here. Anyone wanting to know what's running RIGHT NOW — read APPLICATION_SPECS.md § Live System Reference._

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

## Phase 15: Intent-Organized UI Rearchitecture (P0 — Completed)

**Goal:** replace the chat-organized interface with an intent-organized, PDP-first discovery surface. Users interact via a query input and browse PDP carousels — not chat transcripts. History is grouped by intent (outfit recommendations, pairings, outfit checks), not by conversations.

**Why now:** Chat is the wrong metaphor for a fashion product. Three failure modes confirmed by live usage:
1. **Conversations are bad containers** — a user asking "wedding outfit" then "office look" in the same thread creates a jumbled transcript. Users think in intents ("my wedding looks"), not conversations.
2. **Chat bubbles bury the product** — the outfit PDP card (which carries the real value) renders as an interruption inside a text stream. In fashion, the product IS the interface.
3. **Vertical scroll is wrong for outfit comparison** — left/right carousel navigation matches shopping behaviour. Vertical scroll matches messaging. Aura should feel like shopping, not messaging.

**Architectural shift:**
- Landing page → **discovery surface**: centered input + PDP carousel for the active request + context summary + follow-up chips + recent intent groups below
- Response rendering → **PDP carousels** (not chat bubbles): the same `buildOutfitCard` component, arrayed horizontally with swipe/arrow navigation
- History → **intent-organized tabs** (not conversation sidebar): Outfits (recommendations + pairings + their try-ons), Checks (outfit check history)
- Trial Room → **embedded in Outfits** (not a separate tab): try-on images live inside the intent group that generated them
- Iterations → **stacked carousels within an intent group**: "Show alternatives" adds a new carousel row below the original, not a new chat bubble

**Navigation model:**

| Tab | What it shows | Data source |
|---|---|---|
| **Home** | Discovery input + active request PDP carousel + recent intent previews | Live pipeline response + `/v1/users/{id}/intent-history` |
| **Outfits** | Intent-organized history for `occasion_recommendation` + `pairing_request` + `capsule_or_trip_planning`. Each group = context header + PDP carousel + embedded try-ons. Vertical scroll between groups, horizontal swipe within. | `/v1/users/{id}/intent-history?types=occasion_recommendation,pairing_request,capsule_or_trip_planning` |
| **Checks** | Outfit check history. Uploaded photo + verdict card per check. | `/v1/users/{id}/intent-history?types=outfit_check` |
| **Wardrobe** | Stays as-is (borderless closet grid) | Existing endpoints |
| **Saved** | Stays as-is (wishlist) | Existing endpoints |

**What stays (zero rework):**
- Backend orchestrator, agents, pipeline, repos, schemas — the same pipeline that produces outfits today
- PDP card component (`buildOutfitCard`) — hero image, products, chart, feedback strip
- Wardrobe surface, Saved/Wishlist surface
- Confident Luxe design tokens, typography, motion, dark mode
- All outfit persistence, read-time hydration, stage messages
- Conversation model in the DB (turns still belong to conversations; the frontend just groups by intent instead of exposing conversations)

**What changes:**
- `modules/platform_core/src/platform_core/ui.py` — landing page, response rendering, history surfaces, navigation
- One new API endpoint (`/v1/users/{id}/intent-history`)
- Navigation: Chat · Wardrobe · Looks · Saved · Trial Room → **Home · Outfits · Checks · Wardrobe · Saved**

**PDP carousel interaction model:**
- One PDP visible at a time on mobile, 2-up on desktop with peek of next
- Swipe or arrow keys to navigate
- `1/N` counter badge (reuses the existing image-counter pattern)
- Follow-up chips below the carousel: clicking sends a new request → adds a new carousel row to the same intent group (iteration without starting over)
- Context summary above each carousel: "3 looks for a summer wedding · wardrobe-first · Apr 10"

**Iteration stacking:**
- User asks: "Dress me for a wedding" → 3 PDP cards in carousel
- User clicks "More formal" → same intent group, second carousel row: "Iteration 2 · more formal"
- User types: "Try navy instead" → third carousel row: "Iteration 3 · navy direction"
- All iterations live in the same group, scrollable. Context header updates.

### Phase 15A — Intent-grouped history endpoint (backend)

Status: **complete** (verified May 1, 2026 — `GET /v1/users/{user_id}/intent-history` lives at `api.py:1089`; consumed by both Outfits and Checks tabs).

New `GET /v1/users/{id}/intent-history` endpoint.

Checklist:
- [x] group turns by (`primary_intent`, `occasion_signal`, `conversation_id`, date)
- [x] for each group, return: intent type, occasion label, date, context summary, turn count
- [x] for each turn within a group, return: user message (as context), assistant message (as summary), resolved_context with outfits (using existing read-time hydration)
- [x] embed try-on images per group via existing `virtual_tryon_images` lookup
- [x] support `?types=` filter param for the Outfits vs Checks tab split
- [x] test coverage

Verification:
- endpoint returns grouped structure, not flat list
- groups sort by most recent first
- try-on images present where available
- hydration fires for historical turns missing outfits

### Phase 15B — Discovery landing page (frontend)

Status: **complete** (verified May 1, 2026 — `view-home` class active, PDP carousel + counter + chips + thinking line all rendered via `platform_core/ui.py`).

Replace the chat feed with a discovery layout.

Checklist:
- [x] centered input bar at the top (search-bar energy: wider, no +button popover, just text input + send)
- [x] italic Fraunces headline above: "What are we wearing." (reuse the welcome-headline)
- [x] on submit: PDP carousel slides in below the input
- [x] context summary line above the carousel (occasion · source · count)
- [x] horizontal swipe/arrow navigation between PDP cards within the carousel
- [x] `1/N` counter badge on the carousel (reuses image-counter pattern)
- [x] follow-up chips below the carousel (reuse existing follow-up chip rendering)
- [x] below the active request: compact preview cards for recent intent groups (tap to expand into the Outfits tab)
- [x] stage bar / "thinking" indicator renders as a subtle line below the input, not a chat bubble

Verification:
- no chat bubbles visible anywhere on the landing page
- PDP cards render identically to the existing `buildOutfitCard` output
- swipe/arrow navigation works on mobile and desktop
- follow-up chips send a new request that appends a carousel row, not a chat message

### Phase 15C — Outfits tab (intent-organized history)

Status: **complete** (verified May 1, 2026 — Outfits tab fetches at `ui.py:4404`, renders intent groups with embedded carousels + try-on images).

New tab replacing Looks + Trial Room.

Checklist:
- [x] fetch from `/v1/users/{id}/intent-history?types=occasion_recommendation,pairing_request,capsule_or_trip_planning`
- [x] render each intent group as a section: context header + PDP carousel
- [x] try-on images embedded in PDP cards (via the existing click-to-cycle hero)
- [x] iterations within a group render as stacked carousel rows with iteration labels
- [x] vertical scroll between groups, horizontal swipe within each carousel
- [x] empty state: Fraunces italic "Nothing styled yet."
- [x] tap a group's context header to re-enter the conversation (loads the intent group into the Home tab's active request area for iteration)

Verification:
- groups appear in reverse chronological order
- each group has a correct context header (intent · occasion · date · count)
- PDP cards within each group match what the user saw live
- try-on images present where the live flow generated them

### Phase 15D — Checks tab

Status: **complete** (verified May 1, 2026 — Checks tab fetches at `ui.py:4469`, including `garment_evaluation` records alongside `outfit_check`).

Checklist:
- [x] fetch from `/v1/users/{id}/intent-history?types=outfit_check` (broadened to also include `garment_evaluation`)
- [x] render each check as a card: uploaded outfit photo (from the turn's attached image) + stylist verdict text + check metrics
- [x] empty state: "No outfit checks yet."

### Phase 15E — Remove legacy surfaces

Checklist:
- [x] remove chat bubble rendering from the response flow (keep `renderAssistantMarkup` for the context summary text)
- [x] remove the conversation history sidebar (`history-rail`, `loadConversationHistory`, ⌘K toggle)
- [x] remove Trial Room tab (content now lives in Outfits via embedded try-ons)
- [x] merge Looks tab into Outfits (or keep as a "browse all" toggle: `BY INTENT · ALL`)
- [x] update header nav: Home · Outfits · Checks · Wardrobe · Saved
- [x] update view-switching CSS (`body.view-X` classes)

Verification:
- no chat bubbles in any user-facing surface
- no conversation history sidebar
- no standalone Trial Room tab
- all 5 tabs render and navigate correctly
- full test suite green

### Phase 15F — Polish + iteration flow

Checklist:
- [x] carousel transitions: CSS transform + `--dur-2` easing on slide
- [x] swipe gesture support: touch events on mobile, arrow keys on desktop
- [x] iteration stacking: follow-up request adds a new carousel row within the same intent group on the Home tab
- [x] iteration labels: "Iteration 2 · more formal" above each stacked carousel
- [x] input bar behaviour: typing a completely new request starts a new intent group; clicking a follow-up chip iterates the current one
- [x] responsive: mobile = full-width single-card swipe; desktop = 2-up with peek
- [x] Fraunces italic empty states on every tab
- [x] motion: carousel slide uses `--dur-2` + `--ease`, stagger entrance on Outfits tab groups

### Success criteria (entire phase)

- the product feels like a fashion discovery surface, not a chatbot
- outfit PDP cards are the primary visual unit, not chat bubbles
- history is organized by intent, not by conversation thread
- users can iterate on any historical intent group by tapping it
- try-on images live inside their outfit groups, not in a separate gallery
- the backend is minimally changed (one new endpoint + existing pipeline)
- Confident Luxe design tokens carry through every surface
- full test suite green

### Risks

- **Loss of conversational nuance.** Some users may want to see the full transcript. Mitigation: store it (conversations stay in DB), add an expandable "View full conversation" link per intent group as a detail affordance.
- **Grouping heuristic.** Deciding which turns belong to the same intent group is fuzzy when a user pivots mid-conversation. Mitigation: group by `conversation_id` + `primary_intent` + `occasion_signal`. Intent change within a conversation = new sub-group.
- **Follow-up routing for old groups.** Iterating on a weeks-old intent group needs the right conversation context. Mitigation: intent group maps 1:1 to a conversation_id; clicking "iterate" reloads that conversation's session_context.

---

## Phase 14: Confident Luxe Design Refinement (P0 — Completed)

**Goal:** migrate the live UI from the legacy warm-cream + rose-wine direction to the refined "Confident Luxe" token set defined in `docs/DESIGN.md` (§ Brand Direction — Confident Luxe). Phase 11A delivered the stylist-studio *architecture* (information architecture, component vocabulary, tab model). Phase 14 replaces the *visual language* on top of that architecture so the surface reads as premium fashion authority rather than warm-craft boutique.

**Why now:** user feedback on the current UI is that it reads "unprofessional and backward" — the architecture is sound but the palette (`#f6f0ea` cream + `#6f2f45` wine), the serif pairing (Cormorant Garamond + Avenir Next), the ambient drop shadows on static cards, and the lack of dark mode together carry a warm-craft feel instead of confident-luxe maison authority. The brand direction needs to shift without touching the backend or the information architecture.

**Scope — visual language only:**
- `modules/platform_core/src/platform_core/ui.py` — HTML, CSS, JS (~3,552 lines). This is where all chat / wardrobe / looks / profile surfaces live.
- `modules/user/src/user/ui.py` — onboarding and OTP surfaces (~3,144 lines).
- `modules/catalog/src/catalog/ui.py` — catalog admin (~578 lines). Admin surfaces can adopt the refined tokens but are not required to carry tonal moments.
- `docs/DESIGN.md` — ✅ updated (refined brand direction, refined tokens, tonal moments, voice, dark mode).
- `docs/DESIGN_SYSTEM_VALIDATION.md` — ✅ updated (new typography check, new colour check, new hairline-vs-shadow check, new dark-mode journey, new Confident Luxe tonal audit).

**Out of scope (explicitly):**
- backend, repositories, schemas, agents, pipelines, API endpoints
- information architecture (tabs, views, CRUD flows) — Phase 11A stands
- framework migration (the server-rendered f-string architecture stays)
- new dependencies beyond Google Fonts (Fraunces, Inter, JetBrains Mono — all SIL OFL, zero paid fonts)

### Step 1 — Token pass and typography swap (highest impact)

Status: **complete** (verified May 1, 2026 — legacy hex grep returns 0 hits across `modules/**/ui.py`; Fraunces/Inter/JetBrains Mono link present; `data-theme` attribute and `aura_theme` persistence wired).

This single step does 60–70% of the visual work. It touches only the top `<style>` block and the `<link rel="stylesheet">` head of each UI file.

Checklist:
- [x] drop the refined CSS custom properties defined in `docs/DESIGN.md` § Example Semantic Tokens into the top of `platform_core/ui.py`, `user/ui.py`, and `catalog/ui.py` — one shared `:root` block per file for now (deduplication can come later)
- [x] add `[data-theme="dark"]` block with dark-mode token equivalents
- [x] preconnect and load Google Fonts: `Fraunces` (variable, with `opsz` and `SOFT` axes), `Inter` (variable), and `JetBrains Mono`. All SIL OFL. One preconnect + one stylesheet link.
- [x] replace `font-family: "Avenir Next", "Segoe UI", sans-serif` body rule with `"Inter", -apple-system, "Helvetica Neue", sans-serif`
- [x] replace `font-family: "Cormorant Garamond", Georgia, serif` display rule with `"Fraunces", "Cormorant Garamond", Georgia, serif` (Cormorant stays in the fallback stack so nothing regresses if the font fails to load)
- [x] retire every literal reference to `#f6f0ea`, `#efe6dc`, `#fffaf5`, `#6f2f45`, `#b88b96`, `#5f6a52`, `#b08a4e` in CSS strings — replace with the new `--canvas`, `--surface`, `--accent`, `--signal` variables. No literal hex values for retired tokens are permitted post-step.
- [x] remove drop shadows from static card rules (`.outfit-card`, `.closet-card`, `.profile-card`, etc.) — replace with `1px solid var(--line)`
- [x] keep shadows only on `.modal-box` (`--shadow-modal`), popovers (`--shadow-pop`), and `.composer-outer:focus-within`
- [x] implement a theme toggle stub (persists to `localStorage.aura_theme`, honours `prefers-color-scheme` on first load)

Verification:
- legacy hex grep returns zero hits: `rg '#f6f0ea|#6f2f45|#b88b96|#efe6dc|#fffaf5|#5f6a52|#b08a4e' modules/**/ui.py`
- Fraunces is the primary display family on every surface; Cormorant Garamond only appears in the fallback list, never as the first family
- Inter is the primary body / UI family; Avenir Next only appears in the fallback list
- screenshots show warm ivory canvas, espresso ink text, oxblood active states
- full test suite still green: `python3 -m pytest tests/ -v`

### Step 2 — Chat view rebuild (empty state, composer, bubbles, history drawer)

Status: **superseded by Phase 15** (chat surface entirely replaced by intent-organized discovery). The chat-bubble feed and history sidebar were removed; the discovery input + PDP carousel pattern stands in for everything below. Items kept here as historical record of the abandoned in-flight design direction.

Checklist (N/A — chat surface removed):
- [N/A] ~~rebuild the chat empty state~~ — discovery landing page with Fraunces italic *"What are we wearing."* welcome shipped instead
- [N/A] ~~strip background + border from agent chat bubbles~~ — chat bubbles removed entirely
- [N/A] ~~keep the user bubble but restyle~~ — chat bubbles removed entirely
- [N/A] ~~restyle composer~~ — composer redesigned with `+` menu in the discovery layout
- [N/A] ~~replace the permanent 280px history sidebar with a drawer~~ — sidebar removed; intent-history endpoint + Outfits/Checks tabs replace it
- [N/A] ~~outfit cards inline in chat~~ — outfit cards now live inside the PDP carousel on Home + Outfits surfaces
- [N/A] ~~follow-up groups render under uppercase headers~~ — chips render below the carousel; group headers absorbed into the iteration-stacking model

Verification:
- empty state displays italic display type at 72/76
- no agent bubble carries a background colour or shadow
- history drawer opens via ⌘K and via left-edge hover, closes via Escape and backdrop click
- Phase 11A "chat welcome screen with progressive disclosure" behaviour still works under the new visual

### Step 3 — Wardrobe restyle (grid, filters, add-item drawer)

Status: **complete** (verified May 1, 2026 — borderless 5-col closet grid, hairline-underline search, `aura_wardrobe_filters` localStorage preserved, right-edge Add Item drawer shipped).

Checklist:
- [x] rebuild wardrobe header: `display-lg` "Wardrobe" + mono item count + season/palette badge in `--signal`
- [x] convert filter row to uppercase label chips only — three rows: *Category · Color · Occasion*. Retire colour-pill backgrounds; active state = filled `--ink` on `--canvas`.
- [x] convert the search bar to a hairline-underline input positioned at the far right of the filter row
- [x] restyle closet cards: no border, no shadow, no background — just 4:5 photo + metadata below. Hover = image dims 4%, title underlines.
- [x] convert "+ Add Item" modal to a right-edge drawer (480px wide on desktop, full-screen on mobile). Photo upload top, underline-input metadata form below.
- [x] keep the edit and delete modals but restyle with the new tokens; modals keep centre-overlay pattern (don't migrate to drawer)
- [x] preserve all existing filter behaviour (`aura_wardrobe_filters` localStorage, `Occasion-ready` metadata match, category and colour logic) — only the rendering changes

Verification:
- closet cards carry zero box-shadow
- `Occasion-ready` chip still filters by enrichment metadata (verify one `occasion_fit=wedding` item appears and one `everyday` item does not)
- edit / delete backend calls still fire correctly (`PATCH` / `DELETE /v1/onboarding/wardrobe/items/{id}`)

### Step 4 — Looks (results) rebuild as lookbook

Status: **superseded by Phase 15** (Looks tab merged into Outfits + Saved tabs; outfit cards now live in intent-grouped carousels; verdict cards persist on `garment_evaluation` responses).

Checklist (N/A — Looks tab removed in Phase 15E):
- [N/A] ~~rename the "Results" tab to "Looks"~~ — replaced by 5-tab nav (Home / Outfits / Checks / Wardrobe / Saved)
- [N/A] ~~two tabs inside Looks: SAVED and HISTORY~~ — Saved is its own tab; history lives on Outfits
- [N/A] ~~grid of outfit cards~~ — Outfits tab uses intent-grouped PDP carousels instead of a flat grid
- [N/A] ~~click = full-screen lookbook view~~ — interaction now lands the user back on Home with the intent group loaded for iteration
- [x] verdict rendering for buy/skip responses preserved on `garment_evaluation` (display italic verdict + reasoning)
- [x] preserve the split polar bar chart (style archetype + fit evaluation) — chart still renders on the PDP card

Verification:
- verdict cards render italic display type for the verdict word
- split polar bar chart axes use CSS variables, not literal hex
- saved looks still load from `virtual_tryon_images` / past recommendations via existing endpoints

### Step 5 — Profile as style dossier

Status: **complete** (verified May 1, 2026 — `display-xl` name hero, three-card layout for Body / Colour / Style Code, theme toggle, Recent Signals timeline all shipped).

Checklist:
- [x] hero: name in `display-xl` (72px), one-line style statement in `body`
- [x] three cards side-by-side on desktop, stacked on mobile: **Body** (shape + measurements), **Colour** (season + base / accent / avoid swatches — champagne 1px rule allowed here), **Style Code** (style adjectives rendered as oversized quote blocks in display italic, one per line, no punctuation)
- [x] add a "Recent signals" timeline below the three cards: what the system has learned (*"prefers midi over mini"*, *"leans minimalist in winter"*) — sourced from existing user analysis data (May 1, 2026: deterministic service `agentic_application/services/recent_signals.py` reads `user_comfort_learning` + `feedback_events` + `catalog_interaction_history`, exposed at `GET /v1/users/{id}/recent-signals`, rendered on the profile page below the Palette card. 8 unit tests in `tests/test_recent_signals.py`.)
- [x] inline edit toggle stays, but becomes a per-card ghost text button, not a single page-level pencil
- [x] theme toggle lives here as a one-sentence affordance

Verification:
- style code adjectives render in display italic
- swatches still reflect the user's base / accent / avoid palette from the existing colour palette system (P0 item from 2026-04-05)
- edit mode still calls the existing profile PATCH endpoint

### Step 6 — Dark mode polish + motion system

Status: **complete** (verified May 1, 2026 — `--dur-1/2/3`, `--ease`, `prefers-reduced-motion`, view-transition, stagger, and stylist-voice loading copy all present in `platform_core/ui.py`).

Checklist:
- [x] verify every surface under `[data-theme="dark"]` — canvas, surface, surface-sunk, ink, lines, accent, signal, positive, negative
- [x] add the single motion easing curve and three duration tokens to the shared style block
- [x] add view-transition fade+rise on `body.view-X` switches using `--dur-3` + `--ease`
- [x] add the "runway program" track-in detail to section labels (uppercase labels animate in from 4–6px left) — once per view only, honour `prefers-reduced-motion`
- [x] add staggered entrance (60ms stagger, `--dur-2`) to outfit card grids in Looks (re-applied to Outfits tab post-Phase 15)
- [x] add stylist-voice loading copy: `Laying pieces on the table.`, `Looking through your closet.`, `Pairing this back for you.`, `Finding something that fits.` (driven by existing pipeline stage events)

Verification:
- dark mode parity on every primary surface (home, chat, wardrobe, looks, profile, product sheet, all modals)
- `prefers-reduced-motion: reduce` disables all stagger and track-in motion
- no animation uses a curve other than `--ease`
- no duration outside `--dur-1 / --dur-2 / --dur-3`

### Success criteria (entire phase)

- the light-mode surface reads as confident-luxe maison, not warm-craft boutique
- dark mode parity is complete across every primary surface
- zero legacy hex values remain in the CSS for retired tokens
- Cormorant Garamond and Avenir Next appear only as font fallbacks, never as the primary family
- no static card carries a drop shadow
- the `docs/DESIGN_SYSTEM_VALIDATION.md` checklist (updated for Confident Luxe) is fully green on both 375 mobile and 1440 desktop, in both light and dark mode
- the full test suite (`python3 -m pytest tests/ -v`) remains green — Phase 14 is a visual-language change and must not regress any backend behaviour
- user feedback on "unprofessional / backward" no longer applies

### Risks and mitigations

- **Font licensing.** Resolved: the full target stack (Fraunces, Inter, JetBrains Mono) is SIL OFL and served by Google Fonts. No paid faces, no commercial gate. PP Editorial New, Söhne, GT Sectra, and other paid candidates are out of scope.
- **IIFE semicolon bug in `platform_core/ui.py`.** Adjacent IIFEs in f-strings must end with `;` to survive ASI. Known hazard — enforce review on every new IIFE block added in steps 2–6.
- **Hardcoded hex values scattered beyond the token block.** Step 1 verification grep is mandatory to catch them.
- **Polar bar chart regressions.** The chart colours are currently hardcoded in JS. Step 4 recolour must pass the chart accessibility check (`role="img"` + `aria-label`) already in the validation checklist.

---

## Immediate Next Item

### Phase 14 Follow-up: Outfit PDP Card Polish (April 12 2026)

**Problem:** The outfit PDP card (3-column grid inside the chat feed) carries several warm-craft / dashboard artefacts that survived the Phase 14 token pass. Confirmed via live dark-mode screenshot.

Checklist:
- [x] **Price format** — strip `.0` decimal, add comma separator (`Rs. 2,275` not `Rs. 2275.0`), render in JetBrains Mono
- [x] **Summary text** — render italic, `--ink-3` colour, slightly smaller — reads as a stylist caption, not a competing headline
- [x] **Title** — Fraunces italic on `.outfit-title` (tonal moment: the outfit name is a styling verdict)
- [x] **Per-item source labels** — each product row shows `YOURS` or `SHOP` in uppercase `label` type above the item title
- [x] **BUY NOW** — Confident Luxe text-link style (ink underline, no fill)
- [x] **Polar chart** — always visible (user preference), no toggle
- [x] **Card border-radius** — `var(--radius-md)` (8px) confirmed
- [x] **Hero layout** — 2-column `1fr / 36%` grid, hero with `aspect-ratio: 3/4` and `object-fit: cover`, thumbnails hidden (click hero to cycle + `1/N` counter badge)
- [x] **Feedback icons** — SVG line-art heart (like) and X (dislike), `currentColor` inheriting
- [x] **Chat feed widened** — 720px → 960px so cards have breathing room; bubbles self-limit via `max-width: 82%`
- [x] **Dislike form restyled** — hairline chips, underline textarea, ink-fill Submit, hairline Cancel
- [x] **Feedback UX redesign** — move feedback from header to bottom of info panel as a contextual feedback strip:
  - Left: heart icon for quick "I like this" (one-tap positive signal)
  - Right: *"What would you change?"* text prompt (looks like a placeholder, invites constructive feedback)
  - Clicking "What would you change?" expands the reaction chips + textarea inline below
  - Removes the binary like/dislike framing — replaces it with a constructive feedback flow
  - Sits after the full evaluation: see outfit → read products → check chart → react

**Scope:** CSS + JS in `modules/platform_core/src/platform_core/ui.py`, zero backend changes.

---

### ✅ CLOSED — Parallelize catalog retrieval: batch embeddings + concurrent search (April 10 2026)

**Problem:** The catalog search pipeline makes **18 sequential network calls** for a typical broad request (6 queries × 3 calls each: embed → search → hydrate). Each cycle is ~300-500ms, totalling ~2-3 seconds just for retrieval — the largest latency contributor in the pipeline.

**Current flow (sequential):**
```
for each of 6 queries:
    embed_texts([1 document])       → OpenAI API call (~200ms)
    similarity_search(embedding)    → Supabase RPC call (~150ms)
    _hydrate_matches(product_ids)   → Supabase REST call (~100ms)
Total: ~6 × 450ms ≈ 2.7 seconds
```

**Optimized flow:**
```
Step 1: embed_texts([all 6 documents])  → 1 OpenAI API call (~250ms)
Step 2: ThreadPoolExecutor(4 workers):
    parallel: search + hydrate query A1  (~200ms)
    parallel: search + hydrate query B1  (~200ms)
    parallel: search + hydrate query B2  (~200ms)
    parallel: search + hydrate query C1  (~200ms)
    parallel: search + hydrate query C2  (~200ms)
    parallel: search + hydrate query C3  (~200ms)
                                        → wall clock ~200-400ms (2 rounds of 4)
Total: ~250ms + 400ms ≈ 650ms (~4x speedup)
```

**Feasibility (verified):**
- `embed_texts()` already accepts a list of texts and batches internally (EMBED_BATCH_SIZE=50). Currently called with 1 text per query — just needs to be called once with all 6.
- OpenAI SDK (httpx) is thread-safe. SupabaseRestClient (urllib, no mutable state) is thread-safe. Both verified by examining instance variables and request isolation.
- Codebase already uses `ThreadPoolExecutor` for visual evaluation (3 workers) and try-on rendering (3 workers) — proven pattern.
- Per-query latency logging preserved via individual future results.

**Implementation plan (single file change: `catalog_search_agent.py`):**

- **Step 1 — Batch embedding**: Before the query loop, collect all query documents into a list. Call `embed_texts(all_documents)` once. Map embeddings back to queries by index.

- **Step 2 — Prepare tasks**: For each query, pre-compute the merged filters (same as today). Build a list of `(query, direction_id, embedding, filters)` task tuples.

- **Step 3 — Parallel search+hydrate**: Use `ThreadPoolExecutor(max_workers=min(len(tasks), 4))` to run `_search_single_query()` for each task concurrently. Each task does: similarity_search → filter disliked/prev_rec → hydrate → return RetrievedSet.

- **Step 4 — Collect results**: Gather RetrievedSet results from futures, sort by (direction_id, query_id) for deterministic ordering.

- **Step 5 — Logging**: Log batch embedding time once. Log per-query search+hydrate time from each future. Total search time still captured by orchestrator.

**What does NOT change:**
- Filter logic (merge_filters, build_directional_filters, hard_filters) — unchanged
- Similarity search SQL function — unchanged
- Hydration from catalog_enriched — unchanged
- Product exclusion (disliked + previous_rec) — unchanged
- Assembler, reranker, evaluator — unchanged
- Result quality — identical; same queries, same filters, same embeddings, same products

**Risk:** Supabase connection pool under concurrent load. Mitigation: cap at 4 workers (same as visual eval uses 3). The Supabase REST API handles concurrent HTTP requests natively.

---

### User Feedback Analysis — 449 events, 119 unique dislikes (March 16 – April 10 2026)

**Summary:** 449 feedback events (185 likes, 264 dislikes). 119 unique dislike notes (deduped by conversation+turn). Categorized into 12 axial codes mapped to system components.

| # | Category | Count | System Component | Status |
|---|----------|-------|------------------|--------|
| 1 | **Virtual Try-on Quality** | 29 | Try-on renderer (Gemini) | **OPEN** — proportions distorted, face changed, accessories/tattoos transferred from garment model, pants changed, existing clothing visible under tried-on garment. Quality gate exists but doesn't catch these. |
| 2 | **Wrong Pairing** | 26 | Assembler + Architect | **PARTIALLY FIXED** — role-category validation blocks accessories, duplicate-product check blocks same item in multiple roles. Remaining: color/style coherence in cross-product pairings still produces odd combos ("kurta with random trousers"). |
| 3 | **Occasion Mismatch** | 24 | Architect query docs | **MOSTLY FIXED** — occasion-fabric coupling, sub-occasion calibration, time-of-day inference, embellishment level in query docs all shipped. Remaining: joggers/casual trousers still appearing for formal occasions (catalog data quality — see #10). |
| 4 | **Color Dislike** | 16 | Architect color guidance | **PARTIALLY FIXED** — evening color shift (deep palette) shipped. Remaining: accent color saturation too aggressive ("too bright", "accent color all over the place"), avoid-colors not always respected. |
| 5 | **Body Fit Issues** | 12 | Architect visual direction + Assembler | **PARTIALLY FIXED** — VISUAL_DIRECTION now in query docs (LineDirection, VerticalWeightBias). Remaining: "slim jeans makes me look ugly" repeated 6x across dates — body-shape-aware fit type selection not strong enough. |
| 6 | **Style Mismatch** | 9 | Architect style preference | **PARTIALLY FIXED** — style archetype override rule exists. Remaining: "not me", "I would never wear this" — the system doesn't learn from repeated style rejections across conversations. |
| 7 | **Wrong Garment Type** | 9 | Architect + Catalog search | **PARTIALLY FIXED** — garment_subtype hard filter is conditional. Remaining: "I asked for shirts, got tshirts" — when user names a specific type but catalog pool is thin, the system substitutes similar subtypes instead of saying "no results." |
| 8 | **Catalog Data Quality** | 9 | Enrichment + Catalog admin | **PARTIALLY FIXED** — accessories removed, outerwear recategorized. Remaining: joggers tagged as trousers, casual trousers tagged as formal. Need catalog-wide audit of GarmentSubtype accuracy for bottomwear. |
| 9 | **Pattern Dislike** | 8 | Architect pattern guidance | **OPEN** — "too much patterns", "I don't like these patterns." Pattern distribution rules exist in the prompt but pattern intensity/user preference not calibrated. |
| 10 | **Structural Bugs** | 6 | Assembler + Filters | **FIXED** — jacket+blazer double-outerwear (strict role-category separation), pocket square as bottomwear (accessories purged + category validation). |
| 11 | **Repeat Items** | 4 | Reranker + Previous-rec exclusion | **FIXED** — cross-outfit diversity cap (MAX_PRODUCT_REPEAT_PER_RUN=1), previous recommendation exclusion on follow-ups, reranker round-robin. |
| 12 | **Other** | 14 | Various | Mixed — "would require a third piece" (three_piece now shipped), "I liked the pant but not the topwear" (per-item like/dislike not yet actionable). |

**Top 3 unaddressed issues by impact:**

1. **Virtual try-on quality (29 feedbacks)** — the single largest complaint category. Proportions distorted, face altered, garment details changed, accessories/tattoos transferred from product model images. The quality gate catches gross failures but not subtle distortions. Needs: try-on prompt refinement, post-render visual consistency check, garment model accessory stripping.

2. **Joggers/casual trousers in formal contexts (9+ feedbacks across occasion + catalog)** — joggers and casual trousers tagged as `trouser` with `formality: smart_casual` appear in formal/ceremonial queries. Need: catalog-wide GarmentSubtype audit for bottomwear — reclassify joggers as `track_pants` or `jogger`, casual trousers as `casual_trouser` distinct from `trouser`.

3. **Color/pattern intensity not personalized (24 feedbacks across color + pattern)** — "too bright", "accent color all over", "too much patterns", "I don't like these patterns." The system uses the user's seasonal palette but doesn't calibrate color saturation intensity or pattern density to the user's risk tolerance. Need: map risk_tolerance (conservative/moderate/adventurous) to ColorSaturation and PatternScale ranges in the architect prompt.

---

### ✅ CLOSED — Occasion-fabric coupling + sub-occasion formality calibration in architect (April 10 2026)

**Problem:** User feedback from conversation `2035c3cb` (wedding engagement) shows two quality failures even after structural fixes:

1. **Occasion mismatch** — "western looks for wedding engagement" returned a casual cotton shirt + beige trousers (reads "office", not "celebration") and a velvet blazer set (reads "event" but not "engagement ceremony"). User feedback on 5/6 items: *"Not an outfit for festive or ceremonial occasion."*

2. **Formality miscalibration** — traditional turn returned an ornate sherwani set. User feedback: *"Too much."* Engagement is semi-formal/polished, not full-formal/heavy embellishment like a wedding ceremony.

**Root causes:**

- The architect treats occasion as a label (`OccasionSignal: wedding_engagement`) in the OCCASION_AND_SIGNAL section of the query document, but doesn't let it **drive fabric and construction choices**. A cotton shirt can never read "engagement ceremony" regardless of color — the fabric itself carries formality signal. The FABRIC_AND_BUILD section is generated independently of the occasion.

- The architect has no sub-occasion calibration. `wedding_engagement` maps to `semi_formal`, same as a work dinner. But an engagement ceremony calls for statement fabrics (silk, velvet, structured wool, satin), rich textures, and elevated construction — not just "semi-formal fit and silhouette."

- For "western + festive", the narrow intersection of western silhouettes that carry celebratory presence requires very specific query vocabulary: structured suiting fabrics, statement colors, textured weaves, sharp tailoring. The current query docs don't push this hard enough.

**Implementation plan (2 steps, prompt-only):**

- **Step 1 — Occasion-Fabric Coupling** (`prompt/outfit_architect.md`):
  Add a new section after Garment Type Selection:

  ```
  ## Occasion-Fabric Coupling

  When the occasion calls for celebration or ceremony (wedding, engagement,
  party, festive event), the FABRIC_AND_BUILD section of every query MUST
  reflect that — not just the OCCASION_AND_SIGNAL section.

  Celebratory fabrics: silk, satin, velvet, brocade, jacquard, structured
  wool blend, fine suiting. These carry the "dressed for an event" signal
  that cotton, linen, jersey, and knit never do.

  Casual fabrics: cotton, linen, jersey, denim, fleece, knit. These are
  appropriate for casual and smart-casual occasions. They should NEVER
  appear in the FABRIC_AND_BUILD section for ceremonial/festive queries
  even if the user's style preference leans casual.

  The rule: occasion overrides style preference for fabric selection.
  A minimalist who attends an engagement still wears silk or structured
  wool, not cotton — the minimalism shows in silhouette and color, not
  in fabric downgrade.
  ```

- **Step 2 — Sub-Occasion Formality Calibration** (`prompt/outfit_architect.md`):
  Add to the `resolved_context` rules section:

  ```
  ## Sub-Occasion Calibration

  Not all wedding-related events have the same formality:

  | Sub-occasion | Formality | Embellishment | Fabric signal |
  |---|---|---|---|
  | Wedding ceremony | formal | moderate-to-heavy OK | silk, brocade, heavy jacquard |
  | Wedding engagement | semi_formal | subtle-to-moderate, NO heavy | silk, structured wool, velvet, satin |
  | Wedding reception | semi_formal to formal | moderate OK | silk, satin, velvet |
  | Sangeet / mehndi | smart_casual to semi_formal | playful, colorful | silk, cotton-silk blend, printed |
  | Cocktail party | semi_formal | minimal, sharp | suiting wool, silk, structured |

  When the user says "engagement", do NOT reach for heavy embroidery,
  sherwanis, or brocade sets. Reach for polished, clean-lined pieces
  in premium fabrics with subtle texture or embellishment.
  ```

**What changes for the user:**
- "Western looks for wedding engagement" → query docs demand silk/velvet/structured-wool fabrics + semi-formal embellishment → casual cotton shirts dropped from retrieval ranking → user gets blazer in textured wool + silk shirt + tailored trouser
- "Traditional outfit for engagement" → sherwani-level ornateness suppressed → polished kurta sets with subtle embroidery surface instead
- Feedback signal: "Not an outfit for festive or ceremonial occasion" should drop to near-zero

---

### ✅ CLOSED — Three outfit structures: complete, two-piece, three-piece (April 10 2026)

**Problem:** The architect currently only creates `complete` (single garment) and `paired` (top + bottom) directions. For broad occasion requests (wedding, party, office), every response should offer **three structurally different outfit options** so the user sees real variety in silhouette and layering, not just color/brand variations of the same structure.

**Target output for "traditional outfit for wedding engagement":**
- **Direction A (complete):** single complete garment — kurta_set, co_ord_set, suit_set
- **Direction B (two-piece/paired):** top + bottom — kurta + trouser, shirt + trouser
- **Direction C (three-piece):** top + bottom + outerwear — shirt + trouser + nehru_jacket, kurta + trouser + blazer

**PDP behavior by structure:**
- Complete (1 item): 1 garment thumbnail + 1 try-on image + 1 Buy Now link
- Two-piece (2 items): 2 garment thumbnails + 1 try-on image + 2 Buy Now links
- Three-piece (3 items): 3 garment thumbnails + 1 try-on image + 3 Buy Now links

The UI already iterates `items.forEach` for thumbnails and Buy Now links — it's item-count agnostic. No UI changes needed for the card layout. The try-on render already composites all items in a candidate.

**Implementation plan (5 steps):**

- **Step 1 — Architect JSON schema** (`agents/outfit_architect.py`):
  - Add `"three_piece"` to `direction_type` enum: `["complete", "paired", "three_piece"]`
  - Add `"outerwear"` to `role` enum: `["complete", "top", "bottom", "outerwear"]`
  - `plan_type` removed from schema — each direction carries its own `direction_type`

- **Step 2 — Architect prompt** (`prompt/outfit_architect.md`):
  - Remove "Three-piece directions are NOT allowed in v1"
  - Add three_piece direction rules: 3 queries (role=top, role=bottom, role=outerwear)
  - Update Direction Diversity section: occasion-driven structure selection (choose structures appropriate for the occasion, don't mechanically create one-of-each)
  - Add three_piece examples in the Concept-First Paired Planning section (extend to cover outerwear coordination)

- **Step 3 — Directional filters** (`filters.py`):
  - Add `role == "outerwear"` case to `build_directional_filters`:
    `return {"styling_completeness": ["needs_innerwear"]}` — outerwear is a layering piece that needs something underneath

- **Step 4 — Assembler** (`agents/outfit_assembler.py`):
  - Add `_assemble_three_piece` method alongside `_assemble_complete` and `_assemble_paired`
  - Logic: collect tops, bottoms, and outerwear from retrieved sets; score 3-way combinations (top × bottom × outerwear with cap at 10 each to avoid explosion); compatibility scoring reuses `_evaluate_pair` for top+bottom, adds outerwear formality/color coherence check
  - In `assemble()`, dispatch `three_piece` direction_type to the new method
  - `_parse_plan` in outfit_architect.py: handle `three_piece` direction_type

- **Step 5 — Tests + verification**:
  - Add test for `build_directional_filters` with `role="outerwear"`
  - Add test for assembler three-piece assembly
  - Verify complete outfit PDP shows 1 thumbnail + 1 tryon + 1 Buy Now
  - Verify three-piece PDP shows 3 thumbnails + 1 tryon + 3 Buy Now links

---

### ✅ CLOSED — Re-embed Vastramay/Powerlook/CampusSutra from database (April 10 2026)

Executed April 10, 2026. All three stores re-embedded via `POST /v1/admin/catalog/embeddings/resync`:
- Vastramay: 826 processed, 826 saved
- Powerlook: 831 processed, 831 saved
- CampusSutra: 410 processed, 410 saved

Additional cleanup: 61 Koskii/Showoffff items enriched via batch API then re-embedded. 85 dead items (84 Powerlook + 1 Vastramay with delisted products and broken images) deleted. 271 items with empty product URLs deleted.

Final catalog: **14,296 items** — all enriched, all embedded, zero null filter columns.

---

### ✅ CLOSED — Outfit diversity: multi-direction, reranker round-robin, previous-exclusion, URL fix (April 9 2026)

Shipped April 9, 2026. Five changes across the pipeline:

1. **Multi-direction diversity** — architect prompt allows up to 3 directions; explicit rules for using `complete` directions for set garments (kurta_set, co_ord_set) and varying garment types across directions for broad requests.
2. **Reranker direction-aware round-robin** — picks the top candidate from each direction before filling remaining slots by global score. Guarantees one outfit per direction.
3. **Previous recommendation exclusion** — catalog search agent excludes product IDs from `previous_recommendations` on follow-up turns.
4. **Query doc extraction cleanup** — `_QUERY_FILTER_MAPPING` emptied; all query doc lines are soft signals for embeddings only. Architect handles hard_filters explicitly.
5. **Product URL reconstruction** — `resolve_product_url` maps Shopify CDN shop-IDs to verified store domains, fixing missing "Buy Now" links for 271 products across 7 stores.

Tests: 318 passing.

---

### ✅ CLOSED — Smart hard-filter vs soft-signal decision in the architect (April 9 2026)

Shipped April 9, 2026. The architect now uses a tiered filter strategy: `gender_expression` is the only required hard filter; `garment_subtype` is a conditional hard filter (set only when the user names a specific garment type, null for broad requests); `garment_category` and `styling_completeness` are removed from hard_filters entirely and expressed as soft signals in the query document text. The catalog search agent's `build_directional_filters` still injects `styling_completeness` for paired role queries (top/bottom). Tests: 318 passing.

**Files changed:**
- `prompt/outfit_architect.md` — rewrote "Hard Filters vs Soft Signals" section with tiered rules, updated filter vocabulary, added specific-vs-broad examples
- `agents/outfit_architect.py` — `hard_filters.required` reduced from 4 fields to `["gender_expression"]`; `garment_category` and `styling_completeness` removed from properties entirely; `garment_subtype` kept as optional
- `docs/CURRENT_STATE.md` — action plan added and closed

---

### ✅ CLOSED — Multi-value subtype filters for catalog search (April 9 2026)

Shipped April 9, 2026. The architect can now output arrays of plausible garment subtypes per query. The SQL search function matches ANY value in the array. Tests: 318 passing. Migration applied to staging.

**Files changed:**
- `supabase/migrations/20260409140000_multivalue_search_filters.sql` — updated `match_catalog_item_embeddings` to detect if a filter value is a JSONB array and use `= ANY(...)` matching; falls back to exact `=` for plain strings. Applied to staging.
- `prompt/outfit_architect.md` — added `kurta`, `kurti`, `palazzo`, `lehenga_set`, `jumpsuit` to the subtype enum. Added "Multi-value filters" section instructing the architect to pass arrays for broad requests and single values for specific requests, with 4 concrete examples.
- `agents/outfit_architect.py` — `garment_subtype` and `garment_category` schema changed from `{"type": ["string", "null"]}` to `{"anyOf": [string, array, null]}` so the model can return either.
- `filters.py` — `merge_filters` now handles list values: normalizes each element, preserves as a list in the merged dict. The RPC receives a JSONB array.

---

### P0 — Multi-value subtype filters for catalog search (April 9 2026) — historical plan

**Problem:** the architect outputs a single `garment_subtype` string per query (e.g. `"tunic"`). The search function does exact `=` matching. When the user asks for "something traditional like a kurta", the architect picks ONE subtype from its enum, but the catalog may use a different label for the same concept. Result: zero matches for `garment_subtype='tunic'` when the items are tagged `kurta`.

**Fix:** architect outputs arrays of plausible subtypes per query. The search function matches ANY of them via `= ANY(array)`.

**3 changes:**

1. **SQL function** (`match_catalog_item_embeddings`): change each filter line from `cie.X = filter->>'X'` to: if the filter value is a JSONB array, use `cie.X = ANY(SELECT jsonb_array_elements_text(filter->'X'))`, else keep the exact `=` match. Same change for `garment_category`. Applied via new migration.

2. **Architect prompt + schema** (`prompt/outfit_architect.md` + `agents/outfit_architect.py`): change `garment_subtype` and `garment_category` from `{"type": ["string", "null"]}` to `{"type": ["string", "array", "null"], "items": {"type": "string"}}`. Update the prompt to instruct: "For garment_subtype, list ALL plausible subtypes for the occasion (e.g. `["kurta", "tunic", "nehru_jacket"]` not just `"tunic"`). Prefer arrays with 2-4 values."

3. **Filter merging** (`filters.py`): when a filter value is a list, JSON-encode it so the RPC receives a JSONB array. The SQL function detects the type and uses the right matching.

Also: add `kurta` to the subtype enum (it's in the catalog but missing from the architect's list).

---

### ✅ CLOSED — Tabs redesign: Wishlist + Trial Room + Chat wishlist picker (April 9 2026)

Shipped April 9, 2026. The 3-tab layout (Chat / Wardrobe / Results) is now a 4-tab layout (**Chat / Wardrobe / Wishlist / Trial Room**) with a "Select from wishlist" picker in the chat composer. Tests: 318 passing.

**New API endpoints:**
- `GET /v1/users/{user_id}/wishlist` — deduplicated wishlisted products hydrated from `catalog_interaction_history` + `catalog_enriched` (title, price, image, URL, category, color)
- `GET /v1/users/{user_id}/tryon-gallery` — recent try-on renders from `virtual_tryon_images` with browser-safe image URLs

**New API schemas:** `WishlistItem`, `WishlistResponse`, `TryonGalleryItem`, `TryonGalleryResponse` in `api_schemas.py`. New `wishlist_product_id: str` on `CreateTurnRequest`.

**New repository methods:** `list_wishlist_products(user_id)`, `list_tryon_gallery(user_id)` in `repositories.py`.

**UI changes (`ui.py`):**
- 4-tab nav: Chat / Wardrobe / Wishlist / Trial Room
- Wishlist page: grid of catalog product cards (product image, title, price, Buy Now link) loaded from the new endpoint
- Trial Room page: grid of try-on renders (2:3 aspect ratio, click to open full-size, relative timestamp) loaded from the new endpoint
- Chat composer: "Select from wishlist" button (star icon) in the `+` popover, opens a picker modal that loads from `/v1/users/{id}/wishlist`, sets `pendingWishlistProductId` + `pendingWishlistImageUrl`, shows preview chip, default message "Should I buy this [title]?"
- Send handler: sends `wishlist_product_id` in the payload; shows the product image in the user's chat bubble

**Backend (`orchestrator.py`):**
- New `wishlist_product_id` parameter on `process_turn`
- New wishlist_selection path: loads catalog product from `catalog_enriched`, builds `attached_item` with `attachment_source="wishlist_selection"`, appends garment context to `effective_message`, trace step `wishlist_selection`
- No wardrobe persistence, no decomposition (catalog product, not user-owned)
- Full parity with wardrobe_selection path (same flags, same context injection, same evaluator flow)

---

### P0 — Tabs redesign: Wishlist + Trial Room + Chat wishlist picker (April 9 2026) — historical plan

**Goal:** Replace the 3-tab layout (Chat / Wardrobe / Results) with a 4-tab layout (Chat / Wardrobe / Wishlist / Trial Room) and add a "Select from wishlist" option in the chat composer.

#### Current state

| Tab | Data source | Shows |
|---|---|---|
| Chat | conversations / turns | Chat + outfit cards |
| Wardrobe | `user_wardrobe_items` | User-owned garments with enriched attributes |
| Results | `conversation_turns` (recent turns with outfits) | Full outfit result cards from previous conversations |

#### Target state

| Tab | Data source | Shows | New? |
|---|---|---|---|
| **Chat** | conversations / turns | Chat + outfit cards + "Select from wishlist" in composer | Modified (add wishlist picker) |
| **Wardrobe** | `user_wardrobe_items` | User-owned garments (unchanged) | No |
| **Wishlist** | `catalog_interaction_history` WHERE `interaction_type='save'` | Individual wishlisted garments — catalog product image (NOT try-on), title, price, Buy Now | **NEW** |
| **Trial Room** | `virtual_tryon_images` | Try-on render gallery — just the rendered images, no product details, no scores | **RENAMED + reworked from Results** |

#### Data model notes

**Wishlist data** already exists in `catalog_interaction_history`:
- Wishlisted via the heart button on outfit cards → `interaction_type='save'`, `source_surface='product_wishlist'`
- Each row has: `user_id`, `product_id`, `conversation_id`, `turn_id`, `created_at`
- To show the garment image + title + price, we need to JOIN or hydrate from `catalog_enriched` (which has `images__0__src`, `title`, `price`, `url`)
- **New API endpoint needed:** `GET /v1/users/{user_id}/wishlist` → returns deduplicated list of wishlisted products with their catalog image, title, price, product_url

**Trial Room data** already exists in `virtual_tryon_images`:
- Each row has: `user_id`, `file_path` (the rendered try-on image on disk), `garment_ids`, `garment_source`, `conversation_id`, `turn_id`, `created_at`, `quality_score_pct`
- The file_path points to `data/tryon/images/{hash}.jpg` — served via `/v1/onboarding/images/local?path=...`
- **New API endpoint needed:** `GET /v1/users/{user_id}/tryon-gallery` → returns list of try-on images sorted by `created_at DESC`, with the browser-safe image URL

**Wishlist picker in chat** — same pattern as the wardrobe picker:
- "Select from wishlist" button in the `+` popover alongside "Upload image" and "Select from wardrobe"
- Opens a picker modal showing wishlisted products (catalog images, not try-ons)
- Selecting one sets `pendingWishlistProductId` + `pendingWishlistImageUrl`
- The send handler includes `wishlist_product_id` in the payload
- Backend: `process_turn` receives `wishlist_product_id`, loads the product from `catalog_enriched`, builds an `attached_item` dict from the catalog row's enriched attributes, appends garment context to `effective_message` — same as wardrobe selection but sourcing from catalog instead of wardrobe
- **No wardrobe persistence, no decomposition** — the item is a catalog product the user is interested in, not one they own

#### Implementation plan (8 steps)

**Step 1 — New API endpoints (api.py + repositories.py)**
- `GET /v1/users/{user_id}/wishlist` — query `catalog_interaction_history` for `interaction_type='save'`, deduplicate by `product_id`, hydrate each product from `catalog_enriched` (title, price, primary_image_url, product_url, garment_category, primary_color), return as a list
- `GET /v1/users/{user_id}/tryon-gallery` — query `virtual_tryon_images` for the user, order by `created_at DESC`, return browser-safe image URLs + garment_ids + created_at
- Repository methods: `list_wishlist_products(user_id)`, `list_tryon_gallery(user_id)`

**Step 2 — API schema (api_schemas.py)**
- `WishlistItem(product_id, title, price, image_url, product_url, garment_category, primary_color, wishlisted_at)`
- `WishlistResponse(user_id, items: List[WishlistItem])`
- `TryonGalleryItem(id, image_url, garment_ids, garment_source, created_at)`
- `TryonGalleryResponse(user_id, items: List[TryonGalleryItem])`

**Step 3 — Navigation tabs (ui.py HTML)**
- Replace `Results` tab with `Wishlist` and `Trial Room`:
  ```
  Chat | Wardrobe | Wishlist | Trial Room
  ```
- Add CSS for `.view-wishlist .page-wishlist` and `.view-trialroom .page-trialroom`
- Add the two new `<div class="page-view page-wishlist">` and `<div class="page-view page-trialroom">` containers with grid layouts

**Step 4 — Wishlist page (ui.py JS)**
- `loadWishlist()` function: fetch `/v1/users/{user_id}/wishlist`, render a grid of product cards (image, title, price, Buy Now link)
- Card layout: similar to wardrobe grid (3 columns on desktop, 2 on mobile)
- Each card shows the catalog product image (NOT the try-on render)
- "Remove from wishlist" button on each card (calls a new `DELETE /v1/users/{user_id}/wishlist/{product_id}` endpoint)

**Step 5 — Trial Room page (ui.py JS)**
- `loadTryonGallery()` function: fetch `/v1/users/{user_id}/tryon-gallery`, render a masonry/grid of try-on images
- Each card shows: the rendered try-on image (2:3 aspect ratio), date/time
- Clicking an image opens it full-size in a lightbox
- No product details, no scores — pure visual gallery of "how things looked on me"

**Step 6 — Chat composer: "Select from wishlist" button + picker**
- Add third button in the `+` popover: "Select from wishlist" (star icon)
- New picker modal (`wishlistPickerModal`) — loads from `/v1/users/{user_id}/wishlist`, shows catalog images in a grid
- Click handler: sets `pendingWishlistProductId` + `pendingWishlistImageUrl`, shows preview chip, sets default message if input is empty ("Should I buy this [title]?")
- Send handler: saves `pendingWishlistProductId` before `clearImagePreview()`, includes `wishlist_product_id` in the payload when set

**Step 7 — Backend: process_turn handles wishlist_product_id**
- `CreateTurnRequest` gains `wishlist_product_id: str = ""`
- Both turn endpoints pass it through to `process_turn`
- `process_turn` gains `wishlist_product_id: str = ""` parameter
- New path in process_turn: when `wishlist_product_id` is set and `image_data` + `wardrobe_item_id` are empty, load the catalog product from `catalog_enriched`, build an `attached_item` dict from the enriched row, set `attachment_source="wishlist_selection"`, append garment context to `effective_message`
- No wardrobe persistence (it's a catalog product, not user-owned)
- No decomposition
- Trace step: `wishlist_selection`

**Step 8 — Tests + docs**
- New API tests for the two new endpoints
- Smoke test: verify Wishlist and Trial Room tabs render
- Smoke test: verify "Select from wishlist" button exists in the rendered HTML
- Update `CURRENT_STATE.md`, `DESIGN.md`, `APPLICATION_SPECS.md`

#### Risk callouts

- **Catalog hydration for wishlist:** the `catalog_interaction_history` only stores `product_id`. To show title/price/image we need to JOIN or look up each product in `catalog_enriched`. If the catalog is large, this could be slow. Mitigation: query with `product_id IN (...)` filter, limit to 50 most recent wishlist items.
- **Try-on image cleanup:** the `virtual_tryon_images` table accumulates renders indefinitely. For the Trial Room gallery, limit to the 50 most recent. A future retention policy can clean up old renders.
- **Wishlist product_id vs wardrobe item_id:** these are different namespaces. Catalog products have product_ids like `SHOWOFFFF_9856072188180_50510889910548`; wardrobe items have UUIDs. The backend must route to the correct data source based on which ID is provided.
- **"Select from wishlist" attached_item shape:** the catalog product's enriched data has the same 46 attributes as a wardrobe item (they use the same enrichment schema). The `attached_item` dict can be built from the catalog row using the same field names. The only difference is `source="catalog"` instead of `source="wardrobe"`.

---

### ✅ CLOSED — "Select from wardrobe" end-to-end bugs (April 9 2026)

Shipped April 9, 2026. Five bugs fixed in one commit across `ui.py` + `orchestrator.py`. Tests: 318 passing.

1. **Picker no longer overwrites typed message** — `messageEl.value` only set when input is empty
2. **Wardrobe item image shown in user's chat bubble** — new `pendingWardrobeImageUrl` variable saved alongside `pendingWardrobeItemId`; passed to `addBubble` as the bubble image
3. **Decomposition skipped for wardrobe-selected items** — the outfit_check handler's delete + decompose + save block now checks `attachment_source == "wardrobe_selection"` and skips both when true
4. **Debug log elevated to WARNING** — `process_turn: wardrobe_item_id=...` now always visible in terminal
5. **`clearImagePreview()` clears all three pending variables** — `pendingImageData`, `pendingWardrobeItemId`, `pendingWardrobeImageUrl`

---

### P0 — "Select from wardrobe" end-to-end bugs (April 9 2026) — historical plan

Five bugs identified from the wardrobe-selection test flow. All stem from the same root: the "Select from wardrobe" feature was added as a quick frontend wire-up without end-to-end integration testing across the full chat lifecycle.

**Bug 1 — Picker overwrites the user's typed message.**
When the user selects a wardrobe item, the picker click handler unconditionally sets `messageEl.value = "What goes with my " + item.title + "?"`, destroying whatever the user had already typed ("Should I wear this for date tonight?"). The user expects the picker to attach the item, not replace their message.
**Fix:** only set the default message when the input is empty: `if (!messageEl.value.trim()) { messageEl.value = ...; }`.

**Bug 2 — Wardrobe item image not shown in the user's chat bubble.**
`addBubble(message, "user", attachedImage)` passes `attachedImage = pendingImageData` which is empty for wardrobe selections (we intentionally don't set `pendingImageData` to avoid re-uploading). So the user's chat bubble has no image preview — it looks like a text-only message even though a garment was attached.
**Fix:** store the wardrobe item's image URL in a new `pendingWardrobeImageUrl` variable alongside `pendingWardrobeItemId`. In the send handler, use it as the bubble image when no uploaded image exists: `addBubble(message, "user", attachedImage || pendingWardrobeImageUrl)`. Save the URL before `clearImagePreview()` clears it.

**Bug 3 — Outfit decomposition runs on an already-owned wardrobe item.**
When the orchestrator processes a wardrobe-selected item, the outfit_check or garment_evaluation handler decomposes the garment and tries to add decomposed items to wardrobe. For wardrobe-selected items (`attachment_source == "wardrobe_selection"`), decomposition and wardrobe-add should be skipped entirely — the item is already in the user's wardrobe.
**Fix:** in the decomposition path (found in orchestrator's outfit_check and garment_evaluation handlers), check `attached_item.get("attachment_source") == "wardrobe_selection"` and skip decomposition + wardrobe writes when true.

**Bug 4 — `wardrobe_item_id` may not be reaching the backend.**
The debug logs didn't show the `process_turn: wardrobe_item_id=...` line (likely filtered by log level), and the turn data shows no anchor. The JS code looks correct on inspection but the user reports the item "gets removed on sending." Possible causes: a race condition between picker state and send, or the pre-filled message masking the original user intent.
**Fix:** change the debug log from `_log.info` to `_log.warning` so it always shows. Add a `console.log` in the JS payload builder to confirm what's actually in the POST body.

**Bug 5 — After processing, the displayed message reverts to the original instead of showing the pre-filled one.**
The user sees "Should I wear this for date tonight?" in the chat (their original message) but the backend received "What goes with my Black Drawstring Joggers?" (the pre-filled message). This is because the frontend first shows the user's typed text in the bubble, then the response comes back — but the status endpoint returns `user_message` from the DB which is the pre-filled text. On conversation reload, the stored message displays instead of the one the user saw in real time.
**Fix:** this is a consequence of Bug 1. Once the picker stops overwriting the user's message, the stored message will match what the user typed.

**Implementation plan (5 steps, all in `ui.py` + 1 in `orchestrator.py`):**

1. **Picker click handler** — only set `messageEl.value` when input is empty; store `pendingWardrobeImageUrl` alongside `pendingWardrobeItemId`
2. **Send handler** — save `pendingWardrobeImageUrl` before `clearImagePreview()`; pass it to `addBubble` when no uploaded image exists
3. **`clearImagePreview()`** — also clear `pendingWardrobeImageUrl`
4. **Orchestrator decomposition guard** — skip decomposition when `attachment_source == "wardrobe_selection"`
5. **Debug log level** — change `_log.info` to `_log.warning` for the `wardrobe_item_id` log line

---

### ✅ CLOSED — Context retention: carry attached garment across follow-up turns (April 9 2026)

**Bug:** when the user asked "Can I wear this pant for my date tonight?" (Turn 1, garment_evaluation with uploaded image), then followed up with "Show me a date-night outfit with these pants" (Turn 2, pairing_request), the orchestrator lost the garment context. Turn 2 ran without an anchor — the architect searched catalog for BOTH top AND bottom, producing outfits with random joggers/cargo pants instead of using the user's specific Black Track Pants as the anchor bottom.

**Root cause:** no mechanism existed to carry the `attached_item` from one turn's garment_evaluation into the next turn's pairing_request as the anchor. The anchor injection at `orchestrator.py:3723` checks `if intent == PAIRING_REQUEST and attached_item:` — but on a follow-up turn with no new upload/selection, `attached_item` was always `None`.

**Fix (two parts):**

1. **Store:** after every handler returns, if `attached_item` was present (from upload or wardrobe selection), persist a `last_attached_item` dict in the session context (read-merge-write so handler's own context keys aren't overwritten). Clear it on turns without an attached item so it doesn't linger across unrelated topics.

2. **Load:** at the TOP of `process_turn`, after the `wardrobe_item_id` and `image_data` blocks, if `attached_item` is still `None` AND `previous_context` has a `last_attached_item` with a valid `id`, use it as this turn's `attached_item`. The attached context string is appended to `effective_message` so the planner sees the garment attributes.

The anchor injection at line 3723 then finds `attached_item` populated and correctly sets `initial_live_context.anchor_garment`, so the architect plans for only the complementary role (tops for the anchor pants) instead of searching both roles from catalog.

**Files changed:**
- `orchestrator.py` — two new blocks: "Carry forward previous turn's attached item" (load) + "Store last_attached_item" (persist). Both are best-effort with try/except so failures don't block responses.
- `docs/CURRENT_STATE.md` — this close-out.

---

### ✅ CLOSED — Fix duplicate wardrobe rows on "Select from wardrobe" pairing (April 9 2026)

**Bug:** when the user selected an existing wardrobe item via the "Select from wardrobe" chat composer, the frontend fetched the item's image as a blob, converted it to base64, and re-sent it as `image_data` in the turn request — exactly like a new upload. The backend then re-enriched and re-saved it, creating a **duplicate wardrobe row** for an item the user already owned.

**Fix:** the frontend now sends `wardrobe_item_id` (the existing row's UUID) instead of re-uploading the image bytes. The backend's `process_turn` checks for `wardrobe_item_id` first: if present, it loads the existing wardrobe item directly from `user_wardrobe_items` — no re-enrichment, no re-save, no duplicate. The existing item's enriched attributes flow into the planner + architect + evaluator exactly as before.

Files changed:
- `platform_core/api_schemas.py` — added `wardrobe_item_id: str = ""` to `CreateTurnRequest`
- `api.py` — both turn endpoints pass `wardrobe_item_id` through to `process_turn`
- `orchestrator.py` — new `wardrobe_item_id` parameter on `process_turn`; when present and `image_data` is empty, loads the matching item from `get_wardrobe_items` and sets `attachment_source="wardrobe_selection"`, `is_garment_photo=True`, `garment_present_confidence=1.0`
- `ui.py` — wardrobe picker click handler sends `wardrobe_item_id` and shows a preview chip without setting `pendingImageData`; send-message handler includes `wardrobe_item_id` in the payload when no image is attached

**Two paths, clearly separated:**
- **Upload new image** → `image_data` set, `wardrobe_item_id` empty → enrichment runs → persisted to wardrobe (if intent allows) → standard path
- **Select from wardrobe** → `image_data` empty, `wardrobe_item_id` set → existing item loaded directly → no enrichment, no persistence → standard path

---

### ✅ CLOSED — Remove legacy OutfitEvaluator fallback (April 9 2026, codebase cleanup)

Shipped April 9, 2026. Removed `OutfitEvaluator` (540 lines) + `prompt/outfit_evaluator.md` and replaced the fallback branch with a graceful empty-response path. Test count: **318 passing** (was 331, -13 removed tests that exercised the deleted evaluator's unit-level functions or the legacy-fallback code path).

Files removed:
- `modules/agentic_application/src/agentic_application/agents/outfit_evaluator.py` — 540 lines deleted
- `prompt/outfit_evaluator.md` — legacy prompt deleted

Files modified:
- `orchestrator.py` — the `if not evaluated:` fallback block at ~line 4065 no longer calls `self.outfit_evaluator.evaluate(...)`. Instead it logs a warning ("Visual evaluator produced zero results") and leaves `evaluated = []`. The downstream `ResponseFormatter` already returns a clean "I couldn't return safe outfit recommendations for this request" message when outfits is empty — so the user gets a graceful retry-prompt instead of a degraded text-only response from a legacy evaluator with an incompatible scoring shape. Removed the import and `self.outfit_evaluator = OutfitEvaluator()` instantiation.
- `tests/test_agentic_application.py` — removed 12 unit test methods that called deleted functions (`_build_eval_payload`, `_candidate_delta`, `_fallback_evaluations`, `_followup_reasoning_defaults`, `OutfitEvaluator()`), removed 1 stage-emission test for the legacy path, removed all `orchestrator.outfit_evaluator.evaluate = Mock(...)` lines from integration tests, fixed 3 broken `with patch(...)` blocks where removing the evaluator mock left an empty `patch()` call. Updated 1 test assertion that assumed the fallback would produce non-empty recommendations.

**Cumulative cleanup result (OutfitCheckAgent + OutfitEvaluator):**
- **-1,234 lines of legacy evaluator code** across 4 files
- The `VisualEvaluatorAgent` is now the **sole evaluator** in the system
- Photo upload is mandatory at onboarding, so the visual path is always attempted
- On transient visual-evaluator failures (rare: Gemini/OpenAI outage, timeout), the user gets a clean "try again" message instead of an inconsistent legacy-scored response

---

### P0 — Remove legacy OutfitEvaluator fallback (April 9 2026) — historical plan

**Context:** photo upload is mandatory at onboarding, so `person_image_path` is always present for any user who passes the onboarding gate. The `OutfitEvaluator` (540 lines) is the legacy text-only recommendation evaluator that fires as a fallback at `orchestrator.py:4065-4068` when the Phase 12B `VisualEvaluatorAgent` returns zero results. With mandatory photos, the only scenario that triggers this fallback is a **visual evaluator exception** (Gemini/OpenAI outage, timeout, code bug) — not "user has no person photo."

540 lines of legacy code for a rare exception-recovery path is excessive. The alternative: replace the fallback with a **3-line graceful empty-response** that logs the failure and returns a friendly "I couldn't evaluate outfits right now, please try again" message — the same pattern we use for other transient failures (architect failure, enrichment failure, etc.). A degraded text-only response from a legacy evaluator that uses a different scoring shape (no vision, no confidence scaling, different archetype weights) is arguably WORSE than a clean "try again" because it produces inconsistent quality signals in the user's conversation history.

**Implementation plan:**
- **Step 1** — Replace the `if not evaluated:` fallback block at `orchestrator.py:4065-4068` with a graceful empty-response path: log a warning, set `evaluated = []`, and let the downstream `if not evaluated` → empty-response formatter handle it (the response formatter already returns a "I couldn't return safe outfit recommendations" message when `outfits` is empty).
- **Step 2** — Delete `agents/outfit_evaluator.py` (540 lines) and `prompt/outfit_evaluator.md`.
- **Step 3** — Remove the import and `self.outfit_evaluator = OutfitEvaluator()` instantiation from `orchestrator.py`.
- **Step 4** — Remove any test patches for OutfitEvaluator. Run full suite, close out, commit, push.

---

### ✅ CLOSED — Remove dead legacy OutfitCheckAgent (April 9 2026, codebase cleanup)

Shipped April 9, 2026. Removed `OutfitCheckAgent` (254 lines) and its prompt file — zero runtime callers since Phase 12B. Test count: **331 passing** (was 332, -1 removed test that directly instantiated the deleted agent).

Files removed:
- `modules/agentic_application/src/agentic_application/agents/outfit_check_agent.py` — 254 lines deleted
- `prompt/outfit_check.md` — legacy prompt deleted

Files modified:
- `orchestrator.py` — removed the import and `self.outfit_check_agent = OutfitCheckAgent()` instantiation. Added a comment noting that the legacy `OutfitEvaluator` (text-only fallback) stays until Phase 12E.
- `tests/test_agentic_application.py` — removed the import, removed `test_outfit_check_agent_uses_responses_api_with_json_schema` (was the only test that directly instantiated the agent), removed all `patch("agentic_application.orchestrator.OutfitCheckAgent")` lines from every `with` block that mocked it (10 occurrences across multiple test methods).

**Still alive (Phase 12E retirement target):** `OutfitEvaluator` (`agents/outfit_evaluator.py`, 540 lines) + `prompt/outfit_evaluator.md` — the text-only recommendation evaluator that fires as a fallback when `VisualEvaluatorAgent` returns zero results (rare but possible when the user has no person photo). Removing it requires the visual evaluator to degrade gracefully for no-image turns.

---

### P0 — Remove dead legacy OutfitCheckAgent (April 9 2026, codebase cleanup) — historical plan

**Context:** a full codebase audit found that `OutfitCheckAgent` (254 lines) and its prompt file `prompt/outfit_check.md` have **zero runtime callers**. The agent is imported and instantiated by the orchestrator (`self.outfit_check_agent = OutfitCheckAgent()`, line 92) but no method on it is ever called at runtime — the Phase 12B `VisualEvaluatorAgent` replaced all of its call sites. The comment says "kept until tests are migrated off it", but the only test references are `patch("agentic_application.orchestrator.OutfitCheckAgent")` stubs that just suppress the import — they don't exercise the agent's logic.

**Separate from this cleanup:** `OutfitEvaluator` (the legacy **text-only** recommendation evaluator, 540 lines) IS still called as a fallback at `orchestrator.py:4064` when the visual evaluator returns zero results. That agent stays until Phase 12E makes the visual evaluator degrade gracefully for no-person-image turns.

**Implementation plan:**
- **Step 1** — Delete `modules/agentic_application/src/agentic_application/agents/outfit_check_agent.py` and `prompt/outfit_check.md`.
- **Step 2** — Remove the import (`from .agents.outfit_check_agent import OutfitCheckAgent`) and instantiation (`self.outfit_check_agent = OutfitCheckAgent()`) from `orchestrator.py`.
- **Step 3** — Remove `OutfitCheckAgent` from `patch()` calls in `tests/test_agentic_application.py` (the mock is a stub that just prevents import errors; removing the agent makes the mock unnecessary).
- **Step 4** — Run the full test suite, close out this P0, commit, push.

---

### ✅ CLOSED — Distributed per-turn traces (April 9 2026)

Shipped April 9, 2026. One `turn_traces` row per conversation turn capturing input → intent → context snapshot → step-by-step workflow → evaluation → user response signal → end-to-end latency. Migration applied to staging Supabase. Test count: **332 passing** (was 329, +3 new `TurnTraceBuilder` unit tests).

Files touched:
- **`supabase/migrations/20260409120000_turn_traces.sql`** — new table with columns for all 10 signal groups (input, intent, context, steps JSONB array, evaluation, user_response, total_latency_ms), indexed on turn_id (unique), conversation_id, user_id, primary_intent, created_at. Applied to staging via `supabase db push`.
- **`modules/platform_core/src/platform_core/repositories.py`** — added `insert_turn_trace(...)` and `update_turn_trace_user_response(...)` to `ConversationRepository`. The update method is best-effort (missing rows don't break callers).
- **`modules/agentic_application/src/agentic_application/tracing.py`** — new `TurnTraceBuilder` class: lightweight in-memory accumulator with `add_step(step, model, input_summary, output_summary, latency_ms, status, error)`, `set_intent(...)`, `set_context(...)`, `set_evaluation(...)`, and `build() → dict`. No I/O — just dict accumulation.
- **`modules/agentic_application/src/agentic_application/orchestrator.py`**:
  - Import `TurnTraceBuilder`.
  - Instantiate at the top of `process_turn` with turn_id, conversation_id, user_id, message, has_image.
  - `trace_start(step, model, input_summary)` / `trace_end(step, output_summary, status, error)` helpers alongside every existing `emit()` call — dual-write: SSE thinking bubble for the UI + trace step for the DB. Currently instruments `validate_request`, `wardrobe_enrichment`, and `copilot_planner` as the first landing; downstream steps (architect, search, assembly, reranker, render, evaluator, formatter) can be added incrementally by the same `trace_start/trace_end` pattern without touching the builder.
  - After the planner, `trace.set_intent(...)` and `trace.set_context(query_entities=...)` snapshot the classified intent and extracted entities.
  - Dispatch block restructured: handler results are captured into `handler_result`, then `trace.set_evaluation(...)` extracts the evaluator_path / answer_source / outfit_count from the result, then `_persist_trace(trace)` persists the full trace to `turn_traces`. Best-effort: trace persistence failures log a warning but never block the response.
  - New `_persist_trace(trace)` helper on the orchestrator.
- **`modules/agentic_application/src/agentic_application/api.py`** — feedback endpoint now calls `repo.update_turn_trace_user_response(turn_id, {feedback_type, notes, item_ids, outfit_rank})` after persisting `feedback_events`, so the turn trace row retroactively captures what the user thought of the response. Best-effort (wrapped in try/except so feedback is never blocked).
- **`tests/test_agentic_application.py`** — 3 new unit tests in `TurnTraceBuilderTests`:
  1. `test_build_produces_correct_shape` — full trace with 2 steps, intent, context, evaluation
  2. `test_build_empty_produces_valid_shape` — empty trace still returns a well-formed dict
  3. `test_add_step_with_error` — error step with status="error" and error message

**What's instrumented in this first landing:**
- `validate_request` step (latency)
- `wardrobe_enrichment` step (model=gpt-5-mini, input=image, output=is_garment+category+color, latency)
- `copilot_planner` step (model=gpt-5.4, input=message, output=intent+action+overrides, latency)
- Intent + query_entities snapshot
- Evaluation summary (evaluator_path, answer_source, outfit_count, response_type)
- Total end-to-end latency
- User feedback correlation (retroactive update from the feedback endpoint)

**What can be added incrementally** (same `trace_start/trace_end` pattern, one edit per step):
- `onboarding_gate`, `user_context` steps
- `outfit_architect`, `catalog_search`, `outfit_composer`, `outfit_rater` steps
- `tryon_render`, `visual_evaluator`, `response_formatting` steps
- Profile snapshot (profile_confidence_pct, gender, seasonal, body_shape, archetypes)
- Wishlist + purchase click correlation
- Next-message correlation (requires adding a `list_turns limit=2` method to the repo)

---

### P0 — Distributed per-turn traces (April 9 2026) — historical plan retained for reference

**Goal:** one `turn_traces` row per conversation turn that captures the full lifecycle — input, intent, context snapshot, step-by-step workflow (model, summarized I/O, latency, status), final evaluation, user's subsequent response signal, and end-to-end latency — so that debugging a turn, finding slow steps, and correlating user satisfaction with pipeline shape are all single-table queries.

**Why the current infra isn't enough:** signals already exist but are scattered across 6+ tables (`conversation_turns`, `model_call_logs`, `tool_traces`, `dependency_validation_events`, `policy_event_log`, `feedback_events`, `confidence_history`). Answering "what happened on turn X step-by-step?" requires 5+ JOINs and parsing multiple JSONB blobs. The `stage_callback` / `emit()` calls in the orchestrator are the closest thing to a workflow trace but are ephemeral (SSE to the browser, never persisted).

**Schema — one row per turn in `turn_traces`:**

| Column group | Columns | Shape |
|---|---|---|
| **Identifiers** | `id`, `turn_id` (FK unique), `conversation_id`, `user_id` | UUIDs + text |
| **1. Input** | `user_message`, `has_image`, `image_classification` | text + bool + JSONB |
| **2. Intent** | `primary_intent`, `intent_confidence`, `action`, `reason_codes` | text + real + text + text[] |
| **3. Context** | `profile_snapshot`, `query_entities` | JSONB × 2 |
| **4-6, 9. Workflow + Steps** | `steps` | JSONB array: `[{step, model, input_summary, output_summary, latency_ms, status, error}]` |
| **7. Evaluation** | `evaluation` | JSONB: `{path, outfit_count, source, match_scores, verdict}` |
| **8. User response** | `user_response` | JSONB: `{next_message_intent, feedback_type, notes, wishlisted, purchased, response_ms}` — filled retroactively |
| **10. Latency** | `total_latency_ms` | integer |
| **Timestamps** | `created_at`, `updated_at` | timestamptz |

**Steps array** — one element per pipeline stage (11 for a full pairing_request, 4-6 for simpler intents): `validate_request` → `onboarding_gate` → `wardrobe_enrichment` → `copilot_planner` → `outfit_architect` → `catalog_search` → `outfit_composer` → `outfit_rater` → `tryon_render` → `visual_evaluator` → `response_formatting`. Each element carries `{step, model, input_summary, output_summary, latency_ms, status, error}`.

> **Phase 4.7+ note:** the `outfit_architect` step also encompasses the composition router (PR #149) and engine path. On engine-accepted turns, the `outfit_architect` step's underlying `model_call_logs` row is stamped `model='composition_engine'` (PR #153), `model_call_logs.prompt_tokens=0`, and the corresponding `distillation_traces` row carries a `router_decision` block with `used_engine`, `fallback_reason`, `engine_confidence`, `engine_ms`, `yaml_gaps`, `provenance_summary`. There is no separate `composition_engine` element in the steps array — by design, the engine sits *inside* the architect stage so existing dashboards group correctly under "outfit_architect" (just with a different model id).

**User response correlation** — `user_response` starts as `'{}'` and is updated retroactively when the next signal arrives: next message (from the following `process_turn`), feedback (from the feedback endpoint), wishlist (from the wishlist endpoint), or purchase click (when tracked). Single `UPDATE ... WHERE turn_id = ?`.

**Implementation plan (Steps 1-7):**

- **Step 1 — Migration.** Create `turn_traces` table on staging Supabase via direct SQL. Add indexes on `turn_id` (unique), `conversation_id`, `user_id`, `primary_intent`, `created_at`. Migration file at `supabase/migrations/20260409120000_turn_traces.sql`.
- **Step 2 — Repository.** Add `insert_turn_trace(...)` and `update_turn_trace_user_response(...)` to `ConversationRepository` in `repositories.py`.
- **Step 3 — TurnTraceBuilder.** New lightweight class in `modules/agentic_application/src/agentic_application/tracing.py` that accumulates steps during `process_turn`. Methods: `add_step(step, model, input_summary, output_summary, latency_ms, status, error)`, `set_intent(...)`, `set_context(profile_snapshot, query_entities)`, `set_evaluation(...)`, `build() → dict` (returns the full trace row payload).
- **Step 4 — Wire into orchestrator.** Instantiate `TurnTraceBuilder` at the top of `process_turn`. At each existing `emit()` call site, also call `trace.add_step(...)`. At the end of every handler path (recommendation pipeline, garment_evaluation, outfit_check, style_discovery, explanation, clarification, direct response), call `repo.insert_turn_trace(trace.build())`. Capture end-to-end latency via `time.monotonic()` at the top and bottom of `process_turn`.
- **Step 5 — User response correlation.** In the feedback endpoint (`api.py`), after persisting feedback_events, also call `repo.update_turn_trace_user_response(turn_id, {feedback_type, notes, item_ids})`. In the wishlist endpoint, same. At the TOP of `process_turn`, look up the previous turn_id from `previous_context` and update its trace's `user_response.next_message_intent`.
- **Step 6 — Tests.** Unit tests for `TurnTraceBuilder` (build with steps, build empty, build with partial context). Integration test: mock orchestrator process_turn and verify `repo.insert_turn_trace` is called with the expected shape.
- **Step 7 — Docs + commit.** Close out this P0. Add Panels 15-17 to `OPERATIONS.md` (Turn Latency Distribution, Step Latency Heatmap, User Response Rate). Update `WORKFLOW_REFERENCE.md` with the tracing contract.

**What this does NOT change:** no new LLM calls; no external dependencies (no OTel SDK/collector); no frontend changes (SSE thinking bubble keeps working via `emit()`); no change to `resolved_context_json` (the trace is a parallel record, not a replacement); minimal latency impact (one INSERT per turn at the end of `process_turn`).

---

### ✅ CLOSED — Non-garment image detection on chat upload (April 9 2026)

Shipped April 9, 2026. The wardrobe enrichment now explicitly classifies whether the uploaded image actually shows a wearable garment, and the orchestrator surfaces a clarification before any downstream pipeline runs when it doesn't. Test count: **329 passing** (was 325, +4 new regression tests).

Files touched:
- `modules/user/src/user/wardrobe_enrichment.py` — added `is_garment_photo: boolean` and `garment_present_confidence: number 0-1` to the wardrobe-specific JSON schema (catalog enrichment unaffected, it uses its own `schema_builder.py`). Added a clear instruction at the top of the user_text telling the model to set `is_garment_photo=false` and null all attributes for non-garment images (chart, screenshot, document, landscape, food, animal, person without clothing).
- `modules/user/src/user/service.py` — `save_wardrobe_item` pulls `is_garment_photo` and `garment_present_confidence` out of `extracted["attributes"]` and stashes them on both the persisted-row return dict AND the pending dict (used by the orchestrator's deferred-persist path). Default to `True` / `1.0` when absent so old wardrobe rows pre-dating this fix don't get treated as non-garments.
- `modules/agentic_application/src/agentic_application/orchestrator.py`:
  - New non-garment guard right after the existing `enrichment_failed` block (~line 947): checks `is_garment_photo is False` OR `garment_present_confidence < 0.5`, sets `Action.ASK_CLARIFICATION` with the "I couldn't see a garment in that photo" copy, appends `non_garment_image` to the override reason codes, exempts `garment_evaluation` (same exemption as the failed-enrichment guard).
  - The wardrobe-persistence promotion block also now checks `plan_result.action != Action.ASK_CLARIFICATION` so that even if the intent is `pairing_request` / `outfit_check`, a non-garment upload that flipped the action to ASK_CLARIFICATION never reaches `user_wardrobe_items`.
- `tests/test_agentic_application.py` — 4 new regression tests in `Phase12DAnchorAndEnrichmentTests`:
  1. `test_non_garment_upload_returns_clarification` — explicit `is_garment_photo=False` short-circuits the pipeline, no wardrobe write, `non_garment_image` reason code present
  2. `test_low_confidence_upload_returns_clarification` — defence-in-depth: `is_garment_photo=True` but `confidence=0.32` still triggers the clarification
  3. `test_garment_upload_passes_through_when_high_confidence` — happy path: real garment with `is_garment_photo=True` + `confidence=0.95` proceeds normally and persists
  4. `test_garment_evaluation_exempt_from_non_garment_guard` — `garment_evaluation` intent reaches the visual evaluator even when `is_garment_photo=False` (the visual evaluator can handle edge cases the enrichment can't)

**Verification on the next staging "Find me a completing outfit from catalog" + chart image upload:**
- The chart image is enriched, the model returns `is_garment_photo=false` + `garment_present_confidence ≤ 0.3`
- The orchestrator's non-garment guard fires
- The user sees: *"I couldn't see a garment in that photo — it looks like something else. Could you upload a clearer photo of the piece you'd like me to pair with?"*
- No wardrobe row is created
- No architect / catalog search / evaluator runs
- The `intent_reason_codes` array in the response metadata contains `non_garment_image`

**Defence-in-depth that ALSO landed:** the wardrobe-persistence promotion block now skips when the action is `ASK_CLARIFICATION`. This means future override paths that flip the action (failed enrichment, non-garment, image-required-for-pairing, etc.) will never accidentally persist to the wardrobe even if the intent is in the allow-list.

---

### P0 — Non-garment image detection on chat upload (April 9 2026) — historical plan retained for reference

Discovered April 9, 2026 from manual staging test. The user uploaded a chart image (not a garment) and typed "Find me a completing outfit from catalog". The expected behaviour was a clarification asking for a real garment photo. Actual behaviour:

1. Image was saved to `user_wardrobe_items` with garbage low-confidence attributes
2. The architect planned a pairing pipeline against the garbage anchor
3. Random outfits were recommended "completing" a chart

**Why it happened — three layered gaps:**

1. **No explicit "is this a garment?" check anywhere.** `wardrobe_enrichment.py`'s system prompt opens with "You are a precision garment analyst" — it presumes the input IS a garment. The JSON schema is `strict: True` with every field `required`, so the model is structurally forced to return values for all 46 attributes even on a non-garment image.
2. **The existing `enrichment_failed` guard is too coarse.** `orchestrator.py:694-704` only fires when ALL three critical fields (`garment_category`, `garment_subtype`, `title`) come back as empty strings. For an ambiguous non-garment image the model usually picks the closest enum value with low-but-nonzero confidence, so the guard sees non-empty strings and concludes "enrichment succeeded".
3. **The wardrobe-write gate is intent-only.** The Phase 12D follow-up `f979e2a` made wardrobe persistence intent-gated. `pairing_request` is in the gate's allow-list, so a `pairing_request` upload was persisted regardless of whether it was actually a garment.

**Implementation plan (Steps 1-6, this commit):**

- **Step 1 — Enrichment schema + prompt** (`modules/user/src/user/wardrobe_enrichment.py`):
  - Add two new fields to `response_format()`'s schema: `is_garment_photo: boolean` (required) and `garment_present_confidence: number 0-1` (required). These live alongside the existing 46 attributes; the model is forced to return them.
  - Catalog enrichment uses its own `schema_builder.py` and is unaffected.
  - Add a clear instruction to the wardrobe-specific `user_text` (NOT to the shared `system_prompt.txt`, which is also used by catalog enrichment): *"FIRST decide whether the image actually shows a wearable garment. If the image shows anything else — a chart, screenshot, document, landscape, food, animal, person without visible clothing, or any non-garment object — set `is_garment_photo` to `false`, set `garment_present_confidence` to a low value (≤ 0.3), and return null for all garment attributes. Do NOT guess garment attributes for non-garment images. The user will be asked to upload a clearer photo."*

- **Step 2 — Surface the flag on the saved dict** (`modules/user/src/user/service.py`):
  - In `save_wardrobe_item`, after the enrichment call succeeds, pull `is_garment_photo` and `garment_present_confidence` out of `extracted["attributes"]` and stash them on the returned dict at the top level (alongside the existing `enrichment_status` field).
  - The pending dict (used by the orchestrator's deferred-persist path) gets the same fields.

- **Step 3 — Orchestrator non-garment guard + clarification** (`modules/agentic_application/src/agentic_application/orchestrator.py`):
  - After the existing `enrichment_failed` block (lines 917-934) and BEFORE the wardrobe-persistence promotion block (lines 952-995), add a new check:
    ```python
    if (
        attached_item
        and (
            attached_item.get("is_garment_photo") is False
            or (attached_item.get("garment_present_confidence") or 0) < 0.5
        )
        and plan_result.intent != Intent.GARMENT_EVALUATION
    ):
        plan_result.action = Action.ASK_CLARIFICATION
        plan_result.assistant_message = (
            "I couldn't see a garment in that photo — it looks like "
            "something else. Could you upload a clearer photo of the "
            "piece you'd like me to pair with?"
        )
        plan_result.follow_up_suggestions = [
            "Upload a clearer photo",
            "Pick from my wardrobe",
            "Show me outfit ideas instead",
        ]
        if "non_garment_image" not in override_reasons:
            override_reasons.append("non_garment_image")
    ```
  - This must run BEFORE the persistence promotion so non-garment uploads never reach `user_wardrobe_items`. `garment_evaluation` is exempt because the visual evaluator works on image bytes directly and might handle edge cases the enrichment can't (same exemption as the existing `wardrobe_enrichment_failed` guard).

- **Step 4 — Defence-in-depth low-confidence fallback** (same orchestrator block):
  - The model might occasionally say `is_garment_photo=true` for an ambiguous case (printed catalog page, screenshot of a fashion website, etc.). The OR clause `(garment_present_confidence or 0) < 0.5` already catches "model said yes but wasn't sure" — this is the fallback baked into Step 3's check.
  - Threshold 0.5 chosen because real garment photos consistently come back ≥ 0.9 in the existing confidence numbers; 0.5 is a wide safety margin.

- **Step 5 — Regression tests** (`tests/test_agentic_application.py`):
  1. `test_non_garment_upload_returns_clarification` — orchestrator returns clarification + `non_garment_image` reason code when `attached_item.is_garment_photo is False`
  2. `test_low_confidence_upload_returns_clarification` — same when `garment_present_confidence < 0.5` even if `is_garment_photo=True`
  3. `test_non_garment_upload_does_not_persist_wardrobe` — `persist_pending_wardrobe_item` is never called when the upload is non-garment
  4. `test_garment_upload_passes_through_when_high_confidence` — happy path: `is_garment_photo=True` and confidence ≥ 0.5 proceed to the pipeline normally

- **Step 6 — Close-out + tests + push** (`docs/CURRENT_STATE.md`, full suite):
  - Replace the P0 with a `✅ CLOSED` summary noting file/test list
  - Run `pytest tests/ -q` and verify the new tests + previous 325 all pass

**Risk callouts:**
- gpt-5-mini may not always set `is_garment_photo=false` reliably for borderline images. Mitigation: the confidence threshold catches cases where the model says yes but is unsure.
- Real garment photos that happen to have low confidence (blurry, dark, partial frame) will trigger the clarification — this is the right call; the user can re-upload with a better photo.
- Existing wardrobe rows (saved before this fix) won't have `is_garment_photo` / `garment_present_confidence` in their `metadata_json`. The check uses `.get(...)` with default behaviour so old rows are treated as garments (no false-positive clarifications on old data).

This is a Phase 12D follow-up: Phase 12D fixed enrichment retry logic and persistence intent-gating but didn't validate that the upload was actually a garment in the first place.

---

### ✅ CLOSED — Polar bar chart polish + assistant markup parser (April 9 2026, late-day rollup)

Six small follow-up commits after the initial split polar bar chart landing, all in `modules/platform_core/src/platform_core/ui.py`:

1. **`b76a604`** — Removed `style_fit_pct` from the bottom-semicircle Fit profile criteria. The 8 archetype scores in the top semicircle already convey the style dimension visually, so a separate "Style" axis on the bottom was double-counting. The backend still scores `style_fit_pct` (it informs `match_score` and the purchase verdict average); only the radar rendering drops it.
2. **`3d53115` → `f1fa0ae` → `5d8f056`** — Sized the chart canvas to fit inside the `.outfit-info` column's ~280px usable width (260×280, then 290×320 native) instead of stretching a wider canvas non-uniformly via `max-width: 100%`. The non-uniform CSS scaling was the root cause of the "compressed and elliptical rings" complaint — once the canvas width matched the column, rings rendered as true circles. `aspect-ratio: 290 / 320 + max-width: 100%` handles narrow viewports proportionally.
3. **`955e31c`** — Replaced the staggered double-ring label pattern with a single circular ring at `pLabelR=115`. The staggering had been a workaround for the centermost-label collision (Natural / Minimalist in the 8-axis top semicircle) but read as visually noisy / random. Single ring + a slightly larger canvas + a slightly larger labelR makes the labels orbit cleanly.
4. **`ed4589b`** — Added a `labelXNudge` of ±9px for labels with `0 < |cos| < 0.28` so the two centermost labels of each semicircle (Natural at `i=3`, Minimalist at `i=4` in the top semicircle) sit visibly apart instead of reading as a single concatenated phrase ("Natural Minimalist"). The nudge only fires for labels straddling the vertical centre; all other labels keep their natural positions.
5. **`8cf07ce`** — Removed the "Style profile" / "Fit profile" legend below the canvas. The axis labels themselves are already color-coded (purple `#7F77DD` for archetypes, burgundy `#8B3055` for fit dimensions), so a separate caption was redundant.
6. **`52a6ede` → `7a4b3ca` → `1ac51a0`** — Added `renderAssistantMarkup` parser so assistant chat bubbles render `\n\n`-delimited paragraphs and `• `-prefixed bullet lines as proper `<p>` and `<ul><li>` HTML. Previously the StyleAdvisor responses for `style_discovery` / `explanation_request` came back as a wall of text with bullets inline (the `.bubble` CSS default `white-space: normal` was collapsing the newlines). The fix added two follow-up commits because the JS lives inside an f-string and Python was eating the single-escaped `\n` / `\r\n` in JS regex literals AND in JS comments — both required double-escaping (`\\n`, `\\r\\n`) before the rendered JS parsed cleanly. Defence-in-depth: new `test_ui_html_inline_javascript_parses_cleanly` test that pipes the rendered `<script>` block through `node --check` so this entire class of bug fails fast in the future.

**Test count: 323 passing** (was 322, +1 from the new JS parse test).

After all six commits, the PDP card chart looks like this:
- Top semicircle: 8 archetype labels (Classic / Dramatic / Romantic / Natural / Minimalist / Creative / Sporty / Edgy) on a single ring at `pLabelR=115`, with Natural / Minimalist nudged 9px apart for breathing room. Purple polygon arcs, no confidence scaling.
- Bottom semicircle: 4-7 fit profile axes (Body / Color / Risk / Comfort always; Pairing / Occasion / Needs when their gating condition is met; `style_fit_pct` excluded). Burgundy polygon arcs, values scaled by `profileConfPct / 100`.
- Dashed horizontal divider through the centre.
- Shared 0-100 grid rings (4 concentric circles).
- No legend below — axis labels are color-coded.
- Canvas 290 × 320 native, sized to fit inside the `.outfit-info` column without horizontal CSS scaling.

And the chat bubbles render assistant text as proper HTML paragraphs and lists for any handler that uses the `\n\n` paragraph + `• ` bullet convention (StyleAdvisor today; future structured advisors automatically too).

---

### ✅ CLOSED — Merge style + evaluation radar charts into one split polar bar chart (April 9 2026)

Shipped April 9, 2026. The two stacked radar charts on each PDP card have been replaced with a single Nightingale-style split polar bar chart. Top semicircle = 8-axis style archetype profile (purple `#7F77DD`); bottom semicircle = dynamic 5-9 axis fit/evaluation profile (burgundy `#8B3055`, scaled by `analysis_confidence_pct`); dashed horizontal divider through the centre; shared 0-100 grid rings; color-coded legend below the canvas. Test count: **322 passing** (was 321, +1 new smoke test).

Files touched (Step 7 close-out):
- `modules/platform_core/src/platform_core/ui.py` — `buildOutfitCard` had two stacked radar render blocks (~lines 1685-1793 in the prior version). Both removed and replaced with a single 300×272 canvas + `drawProfile(axes, values, color, fillColor, startAngle, span)` function + two calls (top semicircle: archetypes / `Math.PI` start / `Math.PI` span; bottom semicircle: filtered criteria / `0` start / `Math.PI` span). The bottom-semicircle path preserves all of `bef671a`'s context-gating logic verbatim (drop null, drop zero for the 4 context-gated keys). The bottom values are still multiplied by `profileConfPct / 100` so Phase 12B confidence scaling carries through. A small color-coded legend `<div>` is appended below the canvas.
- `tests/test_agentic_application_api_ui.py` — added `test_ui_html_renders_split_polar_bar_chart` smoke test that asserts the new structure is present (`drawProfile`, `CONTEXT_GATED_KEYS`, both semicircle start angles, both colours, legend labels, `setLineDash`, layout constants `pMaxR=78`/`pLabelR=98`) and that the old two-radar scaffolding is fully removed (no `var values = archetypes.map`, no legacy purple `rgba(139, 92, 246, 0.85)`, no legacy burgundy `rgba(111, 47, 69, 0.85)`, no `criteriaRadarDiv`).
- `docs/CURRENT_STATE.md` — this close-out + the executive status line at the top now describes the single chart instead of "dual radar charts".
- `docs/APPLICATION_SPECS.md` — every prior reference to "dual radar charts" / "8 evaluation criteria" / "200px" / two separate canvas blocks has been updated to the split polar bar chart language. The 9 evaluation dimensions (5 always + 4 context-gated) and the per-semicircle layout are now documented in both the "Recommendation Output" and the "PDP Card Layout" sections.
- `docs/DESIGN.md` — the **Outfit PDP card** entry rewritten to describe the split polar bar chart with the actual hex colours (`#7F77DD` / `#8B3055`).

**Risk callouts (none materialised):**
- Canvas width vs PDP card on mobile — chose 300×272 per the spec; verified the rendered HTML contains `max-width: 100%` on the canvas style so it scales down on narrow viewports. If clipping shows up in real testing, fall back to `260×232`.
- Label collisions — at the maximum 9 axes in the bottom semicircle the spec's `gap = Math.min(0.09, sector * 0.15)` keeps adjacent sectors visually distinct. Will revisit if a real turn shows visible crowding.
- Confidence scaling — preserved verbatim (`var confFactor = profileConfPct / 100; criteriaValues = criteria.map(... * confFactor)`).
- Empty bottom semicircle — handled. If `hasCriteriaData` is false, the bottom-semicircle `drawProfile` call is skipped; the top semicircle and the dashed divider still render.

**No backend changes.** The OutfitCard schema, visual evaluator prompt, context-gating rules, and purchase verdict logic from prior fixes are all unchanged. This is purely a rendering-layer change.

**On verifying the new chart:** as before, **hard refresh** (Cmd+Shift+R) any open browser tabs after restarting the staging app — the JS is inlined in the HTML, so already-open tabs keep running the old two-radar code until they re-fetch the page.

---

### P0 — Merge style + evaluation radar charts into one split polar bar chart (April 9 2026) — historical plan retained for reference

**Goal:** replace the two stacked radar charts on each PDP card with a single Nightingale-style split polar bar chart. The top semicircle owns the **style archetype profile** (8 fixed axes); the bottom semicircle owns the **fit / evaluation profile** (5–9 dynamic axes per the existing context-gating rules). A dashed horizontal divider separates them. One canvas, one rendering pass, no toggles or overlays.

**Why:** the two stacked radars take vertical space, force the eye to compare two webs separately, and don't visually relate the user-facing profile (archetypes) to the per-turn evaluation (fit dimensions). One chart with two semicircles makes that relationship explicit, saves vertical space on the PDP card, and aligns the visual language with how a stylist would present "this is how the outfit reads aesthetically vs. how it scores on the technical fit checklist".

**Current state (`platform_core/ui.py:1685-1793`):**
- **Chart A — Style archetype radar** (lines 1685-1723): always 8 axes, purple stroke `rgba(139, 92, 246, 0.85)`, fill `rgba(139, 92, 246, 0.25)`. Reads `classic_pct`, `dramatic_pct`, `romantic_pct`, `natural_pct`, `minimalist_pct`, `creative_pct`, `sporty_pct`, `edgy_pct` from the OutfitCard. Renders into a 200×200 canvas inside an `outfit-radar` div appended to the `info` panel.
- **Chart B — Evaluation criteria radar** (lines 1725-1793): 5-9 axes after the context-gated filter from `bef671a`, burgundy stroke `rgba(111, 47, 69, 0.85)`, fill `rgba(111, 47, 69, 0.22)`. Reads via `buildEvaluationCriteria` (which returns 5 always-evaluated + 4 context-gated dimensions). Multiplies values by `profileConfPct / 100` (Phase 12B confidence scaling). Renders into a second 200×200 canvas appended to the same `info` panel below the first.

**Target state — one canvas, two semicircles:**

| Region | Profile | Axis count | Color | Data source |
|---|---|---|---|---|
| Top semicircle (9→12→3 o'clock) | Style archetypes | always 8 | Purple `#7F77DD` stroke / `rgba(127, 119, 221, 0.38)` fill | Same 8 archetype `_pct` fields |
| Bottom semicircle (3→6→9 o'clock) | Fit / evaluation | dynamic 5-9 | Burgundy `#8B3055` stroke / `rgba(139, 48, 85, 0.35)` fill | Same `buildEvaluationCriteria(...).filter(...)` chain, with the same null + context-gated-zero drop rules from `bef671a` |
| Center | Dashed horizontal divider | n/a | `rgba(0,0,0,0.14)` 0.75px dashed | n/a |
| Background | Concentric grid rings (0/25/50/75/100) | 4 rings | `rgba(0,0,0,0.08)` 0.5px | n/a |
| Below canvas | Color-coded legend | n/a | Two colored chips + labels "Style profile" / "Fit profile" | n/a |

Both profiles are on the same 0-100 scale, so the grid rings are shared. Bottom-semicircle values still get multiplied by `profileConfPct / 100` to preserve Phase 12B confidence scaling.

**Implementation plan (Steps 1-7):**

- **Step 1 — Audit (no code).** Confirm: top is always 8 axes; bottom is 5-9 dynamic; both share the 0-100 scale; the only Python-side change is removing two radar canvas blocks; backend OutfitCard schema is unchanged. Done in this plan section.
- **Step 2 — Replace the two radar canvases with one.** In `ui.py` `buildOutfitCard`, delete both existing radar render blocks (lines 1685-1723 and 1725-1793) and replace with a single `<canvas>` of dimensions `300×272` (per the spec's recommendation for 9-10px labels) wrapped in an `outfit-radar` div. The 300px width is wider than the current 200px — verify it still fits the PDP card's `info` panel width on desktop and mobile; if not, drop to `260×232` and tighten `labelR` accordingly.
- **Step 3 — Layout constants + grid + divider.** Compute `cx = W/2`, `cy = H/2`, `maxR = 78`, `labelR = 98`. Draw 4 concentric grid rings (steps 25/50/75/100 of `maxR`) with `rgba(0,0,0,0.08)` 0.5px stroke. Draw the dashed horizontal divider through `cy` from `cx - maxR - 10` to `cx + maxR + 10` with `setLineDash([4, 4])` and reset the dash pattern with `ctx.save()` / `ctx.restore()`.
- **Step 4 — `drawProfile` function.** Translate the spec's `drawProfile(axes, values, color, fillColor, startAngle, span)` into the inlined JS string. Per axis: compute `midAngle`, draw a filled arc sector from `cx,cy` out to `(value/100) * maxR` (with a 4px floor so empty axes are still visible), draw a 2.5px tip dot, and place a 9.5px label at `labelR` with text alignment derived from `cos`/`sin` of the angle. The label color matches the profile's stroke color so the legend isn't strictly necessary (but we'll add one for accessibility).
- **Step 5 — Wire up data.** Top semicircle call: hardcoded 8-archetype list, values from `outfit[archetype.key] || 0`, color `#7F77DD`, fill `rgba(127, 119, 221, 0.38)`, `startAngle = Math.PI`, `span = Math.PI`. Bottom semicircle call: re-use the existing `buildEvaluationCriteria(...).filter(...)` chain (preserving the null + zero context-gated drops from `bef671a`), multiply each value by `profileConfPct / 100` for confidence scaling, color `#8B3055`, fill `rgba(139, 48, 85, 0.35)`, `startAngle = 0`, `span = Math.PI`. If the filtered criteria array is empty (no fit dimensions to show), skip the bottom-semicircle call entirely — the top still renders alone. The dashed divider is always drawn.
- **Step 6 — Legend.** Append a small legend `<div>` below the canvas inside the `outfit-radar` container. Two color chips with `display: flex`, `gap: 20px`, `justify-content: center`. Use the same colors as the strokes/fills.
- **Step 7 — Tests + docs.** No backend tests change. Add a small smoke test that calls `get_web_ui_html()` and asserts the rendered HTML contains `drawProfile`, `CONTEXT_GATED_KEYS`, and that the old archetype radar code (`var archetypes = [`) is gone (so we know the migration is complete). Update `WORKFLOW_REFERENCE.md` if it mentions the two-chart layout. Close out this P0 in `CURRENT_STATE.md`.

**Files touched:**
- `modules/platform_core/src/platform_core/ui.py` — primary surgery in `buildOutfitCard` between lines ~1685 and ~1793. Net code is roughly the same length but consolidated into one chart.
- `tests/test_agentic_application_api_ui.py` — add a smoke test asserting the new `drawProfile` function string is present and the old `var archetypes = [` block is gone.
- `docs/CURRENT_STATE.md` — close-out.
- `docs/WORKFLOW_REFERENCE.md` — only if it explicitly mentions "two radar charts" anywhere (will grep during Step 7).

**Risk callouts:**
- **Canvas width vs PDP card width.** The current radars are 200px each; the new canvas is 300px. The PDP card's `info` panel is constrained — need to verify on mobile (~360px viewport) that the chart still fits without overflow. Fallback: use 260×232 with `maxR = 70`, `labelR = 90`.
- **Label collisions in the bottom semicircle.** When the dynamic axis count is 5 (the minimum), the bottom labels are well-spaced. When it's 9 (the maximum, which would happen on a turn with full live_context — occasion + weather + needs + a pairing-capable intent), the labels can crowd. The spec's `gap = Math.min(0.09, sector * 0.15)` already handles this by tightening sector gaps; if labels still collide we can drop the font from 9.5px to 9px, or shorten labels (e.g. "Pair" instead of "Pairing").
- **Confidence scaling gotcha.** The current evaluation radar multiplies by `profileConfPct / 100` BEFORE the 0-100 normalization. The new code must do the same — otherwise users with low profile confidence will see the bottom semicircle "deflate" inconsistently with the existing behavior.
- **Empty bottom semicircle case.** If the user has zero filtered fit dimensions (theoretically impossible because the 5 always-evaluated dimensions should always be present, but defensive), the bottom semicircle should be skipped without leaving a half-empty divided canvas. Solution: skip the divider and the bottom-semicircle call when filtered criteria length is 0; the top semicircle renders against the full circle as before.
- **No CSS changes needed.** The existing `.outfit-radar { text-align: center; padding: 8px 0; }` class still works for the new container.

**Test count after this lands:** unchanged (321), unless the new smoke test counts (322).

**This does NOT change:** any backend code, the OutfitCard schema, the visual evaluator prompt, the context-gating rules from the previous fixes. The fix is purely in `ui.py`'s rendering layer.

---

### ✅ CLOSED — Pairing dimension is intent-gated (April 9 2026)

Shipped April 9, 2026. The visual evaluator now scores **5 dimensions always** and **4 dimensions contextually**. Test count: 321 passing (was 319, +2 new tests).

Files touched:
- `prompt/visual_evaluator.md` — moved `pairing_coherence_pct` from "Always evaluate (6)" to "Context-gated (4)" with the new intent-gating rule. Updated the lead paragraph, single-garment framing, Example B, and the closing constraint paragraph to reflect 5 + 4.
- `modules/agentic_application/src/agentic_application/agents/visual_evaluator_agent.py` — `pairing_coherence_pct` added to the `["integer", "null"]` union; parser switched from `_clamp_pct` to `_optional_pct`.
- `modules/agentic_application/src/agentic_application/schemas.py` — `EvaluatedRecommendation.pairing_coherence_pct` and `OutfitCard.pairing_coherence_pct` are now `Optional[int] = None`.
- `modules/platform_core/src/platform_core/api_schemas.py` — mirror change.
- `tests/test_agentic_application.py` — 2 new regression tests (`test_evaluator_omits_pairing_for_garment_evaluation`, `test_evaluator_keeps_pairing_for_outfit_intents`); updated `test_outfit_card_serializes_none_dimensions` and the existing garment_evaluation orchestrator mock to use `pairing_coherence_pct=None`.
- `docs/CURRENT_STATE.md` — this close-out.
- `docs/WORKFLOW_REFERENCE.md` — updated the contextual evaluation table to 5 always + 4 context-gated.

**No frontend code change needed.** The radar filter from the previous fix already drops null dimensions; `pairing_coherence_pct: null` flows through the existing path.

**On the user-reported "occasion=0 / needs=0 still on radar" symptom:** confirmed during this investigation that the backend is correct — the OutfitCard for staging turn `a4818188-8674-4bdc-8cc1-a8f1f9e001c1` has `occasion_pct: None`, `weather_time_pct: None`, `specific_needs_pct: None` exactly as designed. The user's browser tab almost certainly cached the pre-restart `ui.py` JS (the turn was created 6 minutes after the staging restart, which is enough for the orchestrator to be running new code but not enough for an open browser tab to have re-fetched the inlined JS). **Action for the user: hard refresh (Cmd+Shift+R)** to pick up the new filter and the radar will drop the null axes.

---

### P0 — Pairing dimension is intent-gated (April 9 2026)

Discovered April 9, 2026 from user feedback on conversation `7af3ce39-5768-4ceb-9f12-7583130f065d`. The previous fix correctly made `occasion_pct` / `weather_time_pct` / `specific_needs_pct` nullable based on `live_context` inputs, but `pairing_coherence_pct` remained "always evaluated" — including for `garment_evaluation` ("Should I buy this?") turns where the user is judging a single garment in isolation, not pairing anything.

**The right rule:** `pairing_coherence_pct` is meaningful only for intents that actually involve pairing or composing an outfit:

| Intent | Score `pairing_coherence_pct`? | Why |
|---|---|---|
| `occasion_recommendation` | ✅ yes | Multi-piece outfit; pairing coherence is the central question |
| `pairing_request` | ✅ yes | The whole intent is "what goes with this" |
| `outfit_check` | ✅ yes | User is wearing a multi-piece outfit; pairing matters |
| `garment_evaluation` | ❌ no (null) | Single garment in isolation; not pairing anything |
| `style_discovery` | ❌ no (null) | No outfit candidates |
| `explanation_request` | ❌ no (null) | No new outfit being scored |

The previous architecture fix gated 3 dimensions on **`live_context` inputs**. This adds a 4th gating dimension based on **intent**. The mechanism is the same — `pairing_coherence_pct` becomes `Optional[int] = None` and the evaluator returns null for the 3 non-pairing intents. The frontend filter already drops null dimensions from the radar chart, so no UI work needed.

**Note on the user-reported "radar still shows occasion=0 and needs=0" symptom:** I investigated the staging turn and confirmed the backend is correct — `occasion_pct: None`, `weather_time_pct: None`, `specific_needs_pct: None` are stored on the OutfitCard exactly as designed. The orchestrator was running the new contextual-evaluation code (verified via the stored values + the fact that the new `risk_tolerance_pct` and `comfort_boundary_pct` are also present on the card, which only the post-fix code path includes). The user's browser tab almost certainly cached the pre-restart `ui.py` JS — a hard refresh (Cmd+Shift+R) will pick up the new filter and drop the null axes from the radar chart. No backend bug.

**Implementation plan (Steps 1-4, this commit):**

- **Step 1 — Prompt** (`prompt/visual_evaluator.md`): move `pairing_coherence_pct` from "Always evaluate (6)" to "Context-gated (4)". Add the rule: "Score this dimension **only when `intent` is one of `occasion_recommendation`, `outfit_check`, `pairing_request`**. For `garment_evaluation`, `style_discovery`, and `explanation_request`, set `pairing_coherence_pct` to `null`." Update Example B to show `pairing_coherence_pct: null`.
- **Step 2 — Code** (`visual_evaluator_agent.py`, `schemas.py`, `api_schemas.py`):
  - Add `pairing_coherence_pct` to the `["integer", "null"]` union in `_EVAL_JSON_SCHEMA`.
  - Switch the parser line from `_clamp_pct("pairing_coherence_pct")` → `_optional_pct("pairing_coherence_pct")`.
  - Move `pairing_coherence_pct: int = 0` → `pairing_coherence_pct: Optional[int] = None` in `EvaluatedRecommendation`, `OutfitCard` (application), and `OutfitCard` (api mirror).
  - The orchestrator's `_handle_garment_evaluation` OutfitCard construction passes `evaluation.pairing_coherence_pct` straight through — None will propagate naturally.
  - The frontend filter already handles null values; no UI work needed.
- **Step 3 — Tests + docs:** 2 new regression tests asserting (a) the parser preserves None for pairing_coherence_pct when the model returns null, (b) it preserves an int when the model returns a real score. Update `WORKFLOW_REFERENCE.md` contextual-evaluation table to show 5 always + 4 context-gated. Close out this P0 in `CURRENT_STATE.md` with the final file/test list.
- **Step 4 — Run the full suite.** 319 baseline → expect 321 with the new tests, all green.

---

### ✅ CLOSED — Contextual evaluation: omit dimensions when input is absent (April 9 2026)

Shipped April 9, 2026. The visual evaluator initially scored 6 dimensions always and 3 dimensions only when their inputs are present in `live_context`. (A subsequent follow-up the same day moved `pairing_coherence_pct` to context-gated, making it 5 + 4 — see the next closed P0 below.) Test count after this fix: 319 passing (was 313, +6 new regression tests). Verification of the next "Should I buy this?" turn should show:

- The PDP card radar chart only renders **6 axes** (Body / Color / Style / Risk / Comfort / Pairing), not 8 — `occasion_pct`, `weather_time_pct`, and `specific_needs_pct` are dropped because the user didn't supply those inputs.
- The buy/skip verdict is computed from 3 dimensions (body / color / style) instead of the legacy 5 (which included synthetic 0 / 70 defaults).
- The model's `match_score` reflects only the dimensions actually scored.
- A turn that *does* mention an occasion (e.g. "What should I wear to the office tomorrow?") still shows `occasion_pct` on the radar with a real grade.

Files touched (10 total):
- `prompt/visual_evaluator.md` — restructured Evaluation Dimensions into "Always evaluate (6)" + "Context-gated (3 — null when input absent)" sections; added explicit `match_score` rule; added Example B showing the no-context case with `null` values.
- `modules/agentic_application/src/agentic_application/agents/visual_evaluator_agent.py` — `_EVAL_JSON_SCHEMA` uses `["integer", "null"]` union for the 3 fields; new `_optional_pct` parser preserves None instead of coercing to 0.
- `modules/agentic_application/src/agentic_application/schemas.py` — `EvaluatedRecommendation` and `OutfitCard` fields are `Optional[int] = None`.
- `modules/platform_core/src/platform_core/api_schemas.py` — mirror `Optional[int]` change.
- `modules/agentic_application/src/agentic_application/agents/response_formatter.py` — adds `weather_time_pct` to OutfitCard construction (was a pre-existing bug; the formatter never plumbed the field through), passes None through.
- `modules/agentic_application/src/agentic_application/orchestrator.py`:
  - `_handle_garment_evaluation` now plumbs `risk_tolerance_pct`, `comfort_boundary_pct`, and `specific_needs_pct` into the OutfitCard (also pre-existing — the garment_evaluation card was only showing 5 of 9 dimensions before).
  - `_compute_purchase_verdict` averages over `[body, color, style] + filter(None, [occasion, weather])` instead of a fixed 5-dim mean.
- `modules/platform_core/src/platform_core/ui.py` — `buildEvaluationCriteria` result is filtered to drop dimensions where the OutfitCard value is `null`/`undefined` BEFORE the radar geometry calculation, so the chart's vertex count adapts to 5/6/7/8 axes based on what was actually scored.
- `tests/test_agentic_application.py` — 6 new regression tests in `Phase12BBuildingBlockTests`:
  1. `test_evaluator_omits_occasion_when_no_occasion_signal`
  2. `test_evaluator_keeps_all_three_when_inputs_present`
  3. `test_evaluator_handles_missing_context_gated_keys`
  4. `test_purchase_verdict_skips_none_dimensions`
  5. `test_purchase_verdict_with_full_context`
  6. `test_outfit_card_serializes_none_dimensions`
  Plus updated `test_garment_evaluation_does_not_persist_uploaded_item` to mock the new always-on dimensions and the now-Optional context-gated dimensions.
- `docs/CURRENT_STATE.md` — this close-out.
- `docs/WORKFLOW_REFERENCE.md` — rewrote the "No-occasion handling" section to reflect the omit-not-default rule.

**Risk callouts that landed cleanly:**
- OpenAI structured-outputs strict mode does accept the `["integer", "null"]` union when the field is also kept in `required`. No fallback needed.
- Legacy text-only `OutfitEvaluator` still emits `int = 0` for the now-Optional fields. The Pydantic schema accepts that (Optional[int] allows int values). Marked with a comment in `EvaluatedRecommendation` that this path will be retired in Phase 12E.

---

### P0 — Contextual evaluation: omit dimensions when input is absent (April 9 2026)

The current visual evaluator scores 9 dimensions for every candidate. Three of them are context-gated and only meaningful when the user supplies the relevant input — but the prompt today tells the model to **fall back to a default** when input is absent (`occasion_pct=0`, `weather_time_pct≈70`, `specific_needs_pct` neutral). Three concrete failures from this:

1. **`occasion_pct=0` artificially drags down `match_score`** for any recommendation turn where no occasion was named. The model is told "score 0 if no occasion" — that 0 contributes to the user's mental average even though no real evaluation happened.
2. **`weather_time_pct≈70` is fake data on the radar chart.** A 70 from "no weather context" looks identical to a 70 the model derived from the rendering. The user can't tell the difference.
3. **`_compute_purchase_verdict` averages 5 dimensions** including `occasion_pct` and `weather_time_pct`. For a `garment_evaluation` ("should I buy this?") turn with no occasion, two of those five are synthetic neutral defaults — so the buy/skip recommendation is partially built on fake data.

**The right rule:** the evaluator should **always evaluate 6 dimensions** (the user's stable profile signals) and **conditionally evaluate the other 3** only when their inputs are present in `live_context`.

| Dimension | Always or Conditional | Required input |
|---|---|---|
| `body_harmony_pct` | always | profile (always present after onboarding) |
| `color_suitability_pct` | always | derived_interpretations (always present) |
| `style_fit_pct` | always | style_preference (always present) |
| `risk_tolerance_pct` | always | style_preference (always present) |
| `comfort_boundary_pct` | always | style_preference (always present) |
| `pairing_coherence_pct` | always | candidate items (always present) |
| `occasion_pct` | **conditional** | `live_context.occasion_signal` non-null |
| `weather_time_pct` | **conditional** | `live_context.weather_context` OR `time_of_day` non-null |
| `specific_needs_pct` | **conditional** | `live_context.specific_needs` non-empty |

Conditional dimensions are **omitted from the JSON response when their input is absent** — not scored 0, not scored neutral. The PDP card radar chart drops the slice. The purchase verdict averages over only the dimensions that were actually evaluated.

**Implementation plan (Steps 1-9, this commit):**

- **Step 1 — Prompt** (`prompt/visual_evaluator.md`): restructure the Evaluation Dimensions section into "Always evaluate (6)" and "Context-gated (3)". Replace the current default-scoring rules for the 3 conditional dimensions with explicit "OMIT from your JSON if input is absent". Update the example output to show both modes. Tell the model the holistic `match_score` should only reflect dimensions actually scored.
- **Step 2 — Agent schema** (`visual_evaluator_agent.py`): drop the 3 fields from `_EVAL_JSON_SCHEMA["schema"]["required"]`; change their property type to a nullable union (verify OpenAI structured-outputs strict mode accepts it; fall back to `anyOf` or full removal from `properties` if needed). New `_optional_pct` helper in `_to_evaluated_recommendation` that returns `None` when the key is missing or null.
- **Step 3 — Schemas** (`schemas.py`, `platform_core/api_schemas.py`): change `occasion_pct`, `specific_needs_pct`, `weather_time_pct` from `int = 0` to `Optional[int] = None` in `EvaluatedRecommendation`, `OutfitCard`, and the API mirror schema. Other 6 dimensions stay `int = 0`.
- **Step 4 — Response formatter** (`response_formatter.py:240`): audit the propagation chain for any `int(...)` coercion that would convert `None → 0`; pass through unchanged.
- **Step 5 — Purchase verdict** (`orchestrator.py:_compute_purchase_verdict`): rebuild the average over a list of `[body_harmony, color_suitability, style_fit] + [v for v in (occasion_pct, weather_time_pct) if v is not None]`. The verdict thresholds (`>=78 buy`, `>=60 conditional`, else skip) stay the same — they now apply to the actually-evaluated mean.
- **Step 6 — Frontend** (`platform_core/ui.py:buildEvaluationCriteria` + radar render at line 1726): filter the criteria list to drop dimensions where `outfit[c.key] == null` BEFORE the radar geometry calculation. The chart vertex count adapts to 5/6/7/8 dimensions based on what was evaluated. Apply the same filter to both the recommendation branch and the outfit_check branch.
- **Step 7 — Tests:** 6 new regression tests in `Phase12BBuildingBlockTests`:
  1. `test_evaluator_omits_occasion_when_no_occasion_signal`
  2. `test_evaluator_omits_weather_when_no_weather_or_time`
  3. `test_evaluator_omits_specific_needs_when_empty_list`
  4. `test_evaluator_keeps_all_three_when_inputs_present`
  5. `test_purchase_verdict_skips_none_dimensions`
  6. `test_outfit_card_serializes_none_dimensions`
  Plus an audit pass over existing tests that hardcoded values for these 3 dimensions on no-occasion turns.
- **Step 8 — Docs:** close out this P0 with the final file/test list; rewrite the "No-occasion handling" section in `WORKFLOW_REFERENCE.md` to reflect the omit-not-default rule.
- **Step 9 — Run the full test suite.** 313 baseline → expect ~319 with the new tests, all green.

**Risk callouts:**
- OpenAI structured-outputs `strict` mode + nullable fields: if `{"type": ["integer", "null"]}` isn't accepted, fall back to dropping the 3 fields from `properties` entirely so the model genuinely omits them. Verified during Step 2.
- Legacy text-only `OutfitEvaluator` (used as fallback when no person photo) still defaults to `int = 0`. Left as-is with a comment — that path will be retired in Phase 12E reranker calibration.

This is a Phase 12B follow-up: 12B added the visual evaluator with 9 dimensions but did not gate the 3 context-dependent ones on input presence. The fix makes evaluation contextually honest — the user only sees scores for dimensions the model actually evaluated.

---

### ✅ CLOSED — Wardrobe ingestion gated by intent + duplicate-check + PDP thumbnail fix (April 9 2026)

Shipped April 9, 2026 in a single coordinated commit. Test count: 313 passing (was 308, +5 new regression tests). Verification of the next staging "Should I buy this?" turn should show:
- The uploaded garment does NOT appear in `user_wardrobe_items` for `user_03026279ecd6`.
- The assistant message has no "Heads up — your wardrobe already has X" line.
- The PDP card thumbnail of the uploaded garment renders correctly (the image_url starts with `/v1/onboarding/images/local?path=`).
- A `pairing_request` or `outfit_check` upload still persists to the wardrobe (preserves Phase 12D anchor injection).

Files touched:
- `modules/user/src/user/service.py` — added `persist: bool = True` parameter to `save_wardrobe_item` / `save_chat_wardrobe_image`; new `persist_pending_wardrobe_item` method that promotes a pending dict to a real row.
- `modules/agentic_application/src/agentic_application/services/onboarding_gateway.py` — propagates `persist` and exposes `persist_pending_wardrobe_item`.
- `modules/agentic_application/src/agentic_application/orchestrator.py`:
  - Upload now calls `save_uploaded_chat_wardrobe_item(persist=False)` (orchestrator.py:667-705).
  - After the planner returns, conditionally calls `persist_pending_wardrobe_item` only when `intent in {pairing_request, outfit_check}` (orchestrator.py:945-985).
  - `_compute_wardrobe_overlap` now skips any wardrobe row whose id matches `attached_item["id"]` (orchestrator.py:5095-5115).
  - `_attached_item_to_outfit_item` wraps `image_url`/`image_path` with `_browser_safe_image_url` (orchestrator.py:5260-5285).
- `tests/test_agentic_application.py` — 5 new regression tests in `Phase12DAnchorAndEnrichmentTests`:
  1. `test_compute_wardrobe_overlap_excludes_attached_item_id`
  2. `test_compute_wardrobe_overlap_still_finds_real_duplicates`
  3. `test_attached_item_to_outfit_item_uses_browser_safe_image_url`
  4. `test_garment_evaluation_does_not_persist_uploaded_item`
  5. `test_pairing_request_persists_uploaded_item`
- `docs/WORKFLOW_REFERENCE.md` — added "No-occasion handling" subsection under garment_evaluation.

---

### P0 — Wardrobe ingestion gated by intent + duplicate-check + PDP thumbnail fix (April 9 2026)

Discovered April 9, 2026 from manual staging test of `user_03026279ecd6` conversation `db5f01ea-d553-4faf-af6f-08f8c3b6d0cb` ("Should I buy this?" with a charcoal jeans upload). Three independent bugs surfaced from one turn:

1. **Wardrobe ingestion happens unconditionally for any image upload.**
   `orchestrator.process_turn` calls `save_uploaded_chat_wardrobe_item` at lines 667-704 *before* the planner runs, so every upload — including `garment_evaluation` ("should I buy this?") and `style_discovery` turns — gets persisted to `user_wardrobe_items`. The user is asking if they should *buy* the jeans; they don't own them yet, but the row is in their wardrobe by the time the response renders.
2. **False-positive "your wardrobe already has X" duplicate message.**
   `_compute_wardrobe_overlap` at `orchestrator.py:5065` walks `user_context.wardrobe_items` (loaded fresh from the DB after the upload was persisted), finds the just-saved row, and matches it against `attached_item` — i.e. against itself. The user sees "Heads up — your wardrobe already has your Charcoal Jeans" on the very first upload.
3. **PDP card thumbnail of the uploaded garment fails to render.**
   `_attached_item_to_outfit_item` at `orchestrator.py:5229` returns the raw `image_path` (e.g. `data/onboarding/images/wardrobe/abc.jpg`) for the OutfitCard's `image_url`, while the parallel `_wardrobe_item_to_outfit_item` at line 2554 wraps the same value in `_browser_safe_image_url(...)` (which rewrites to `/v1/onboarding/images/local?path=...`). The browser tries to fetch a relative repo path as a URL, fails, and only the try-on render shows.

**Implementation plan (Steps 1-6, this commit):**

- **Step 1 — Split enrich vs persist in the wardrobe gateway.** Add a `persist: bool` parameter (default `True` for backward compat) to `OnboardingGateway.save_uploaded_chat_wardrobe_item` and the underlying `user.service` save path. When `persist=False`: still write the image bytes to disk, still run the 46-attribute enrichment, still return the same dict shape — but skip the `user_wardrobe_items` insert and return `id=None`. In `orchestrator.process_turn`, always call with `persist=False` initially; after the planner returns a `plan_result`, conditionally call a new `OnboardingGateway.persist_chat_wardrobe_item(enriched_dict)` only when `plan_result.intent in {Intent.PAIRING_REQUEST, Intent.OUTFIT_CHECK}`.
- **Step 2 — Defensive overlap exclusion.** `_compute_wardrobe_overlap` now takes `attached_item_id` and skips any wardrobe row whose `id` matches. Belt-and-braces in case a future code path persists before evaluating.
- **Step 3 — Browser-safe image URL on attached items.** `_attached_item_to_outfit_item` wraps `image_url`/`image_path` with `AgenticOrchestrator._browser_safe_image_url(...)`, matching `_wardrobe_item_to_outfit_item`.
- **Step 4 — Regression tests.** Cover (a) `garment_evaluation` with upload does NOT persist + has no "already has" line + has a browser-safe image URL; (b) `pairing_request` and `outfit_check` with upload still persist (preserves Phase 12D anchor injection); (c) `_compute_wardrobe_overlap` excludes the attached item's id.
- **Step 5 — SKIPPED.** A "no occasion specified — graded on general versatility" note in the assistant message would be a UX nice-to-have but is out of scope for this bug fix and would require prompt changes.
- **Step 6 — Docs.** Close out this action item in `CURRENT_STATE.md`, add a "no occasion handling" note to `WORKFLOW_REFERENCE.md` documenting the answer to "what occasion does the evaluator use when none is specified?" (short answer: none — single_garment mode grades on general versatility; recommendation mode scores `occasion_pct=0`; `weather_time_pct` defaults to neutral 65-75).

This is a Phase 12D / Phase 12B follow-up: Phase 12D split intent registry into 7 advisory intents but did not gate wardrobe persistence by intent; Phase 12B's `garment_evaluation_handler` inherited the unconditional save and added the duplicate check on top, producing the cascading false positive; the PDP image bug was latent since the Phase 12D wardrobe-anchor work added `_attached_item_to_outfit_item` without the browser-safe URL helper.

---

### ✅ CLOSED — Wardrobe-anchor try-on now includes the user's uploaded image (Phase 12D follow-up, April 8 2026)

Discovered April 8, 2026 from manual staging test of `user_03026279ecd6` turn `9dff6f7e-9146-4d66-a277-a835e484334d` ("What goes with this pullover for casual night out?" with a chocolate brown pullover upload). The pullover was correctly ingested + enriched and was injected into every paired candidate as the anchor, but the **image** never reached Gemini — `garment_source` on all 3 try-on rows was `"catalog"` and the renders showed a hallucinated brown sweater rather than the user's actual photo.

**Root cause** (two-step):
1. `outfit_assembler._product_to_item` resolved `image_url` only from catalog fields (`images__0__src`, `primary_image_url`, …). Wardrobe rows store the image at `image_path` and leave `image_url=""`, so wardrobe-anchor candidate items got `image_url=""`. It also never set `source`, so `_detect_garment_source` fell through to its `"catalog"` default.
2. `orchestrator._render_candidates_for_visual_eval._render_one` skipped any item whose `image_url` was empty when building `garment_urls`, silently dropping the pullover. Gemini received only the catalog trouser URL + the person photo and hallucinated a sweater from prompt text.

**Fix shipped (3 files, 308 tests passing):**
- `outfit_assembler._product_to_item` now resolves `image_url` from `enriched_data["image_url"]` and `enriched_data["image_path"]` (in addition to catalog fields), and tags wardrobe-shaped rows with `source="wardrobe"` (detected by `image_path` present + no catalog `handle`/`store`).
- `tryon_service.generate_tryon_outfit` dispatches by URL scheme: HTTP(S) → `_download_image`, anything else → `_load_local_image`, so wardrobe `data/...` paths reach Gemini correctly.
- 3 new regression tests in `Phase12DAnchorAndEnrichmentTests` cover (a) wardrobe-anchor `_product_to_item` resolves `image_url` and tags `source`, (b) catalog rows are not mislabelled, (c) the full chain from anchor injection → diversity pass preserves `is_anchor`.

This was a Phase 12D follow-up: 12D fixed wardrobe ingestion enrichment but did not exercise the anchor → render path with a real wardrobe image. Closed by commit landing on April 8, 2026; the next staging test of a pairing-with-upload turn should show `garment_source="mixed"` in `virtual_tryon_images` and renders that contain the user's actual garment.

---

**Phase 12 is complete** as of April 8, 2026 (all sub-phases 12A–12E shipped). See "Phase 12 — Closed" in the Phase 12 section below for the close-out summary, deferred items, and the final test counts.

The next incomplete phase will depend on what staging telemetry (Panels 9-12 in `docs/OPERATIONS.md`) reveals once accumulating real traffic. Likely candidates:
- **Reranker calibration** — once Phase 12E telemetry has 2-4 weeks of data, calibrate the reranker to incorporate feedback signals beyond `assembly_score`
- **True path 1b API** — `wardrobe_item_id` parameter to avoid re-uploading existing wardrobe items
- **Capsule / trip planning return** — re-introduce as a dedicated intent with multi-day recurrence semantics
- **Background re-enrichment worker** — backfill legacy wardrobe rows that were saved with empty fields before the Phase 12D fix

Phase 11A (Design System And Experience Realignment) is functionally complete in code; designer sign-off on `docs/DESIGN_SYSTEM_VALIDATION.md` remains the only open gate there.

Operating note:
- The intent registry is now 7 advisory + feedback + silent wardrobe_ingestion. Anything that references `capsule_or_trip_planning`, `shopping_decision`, `garment_on_me_request`, `virtual_tryon_request`, or `product_browse` as intents is historical and should not be extended.
- Keep `docs/CURRENT_STATE.md` aligned to future runtime changes.

## Phase 12: Re-architecture to Visually-Grounded Evaluation

Status: planned, not started. This phase supersedes several earlier forward-looking items (see "Items Removed from Forward-Looking Plan" at the end of this section). It is a coordinated re-architecture rather than a collection of local fixes, because three issues compound:

1. **Intent taxonomy confusion.** 12 intents ship today, of which 4–5 are really tool calls or workflow operations masquerading as advisory intents. Two intents (`shopping_decision` and `garment_on_me_request`) ask the same underlying question from different framings and have asymmetric handler quality — one has a dedicated agent, the other falls through to inline planner text.
2. **Evaluation is not visually grounded.** The current `OutfitEvaluator` scores candidates from catalog attributes before any try-on render exists. It cannot catch proportion, drape, fit, or on-body color problems that only emerge once a garment is composed onto the user. Try-on today is a decorative bolt-on appended after evaluation.
3. **Wardrobe ingestion is broken at the data-path level.** Per the staging audit of `user_03026279ecd6` conversation `721e1963-c515-4fd4-82d0-f84448c51564`, `save_uploaded_chat_wardrobe_item` returned an attached item with empty title / garment_category / primary_color fields. The planner therefore never saw the garment attributes, and for `garment_on_me_request` the vision-grounded handler was never invoked — the planner produced generic Autumn-palette boilerplate instead of analyzing the actual garment. This is a pre-existing bug that blocks pairing reliability and must be fixed as part of this phase.

### Target Architecture

**Intent taxonomy: 12 → 7 advisory + feedback + silent-save wardrobe_ingestion.**

| New Intent | Replaces / Absorbs | Workflow Shape |
|---|---|---|
| `occasion_recommendation` | absorbs `product_browse` when `target_product_type` is set | architect → catalog_search → assembler → reranker (top 3) → tryon (all 3) → visual evaluator (all 3) → formatter |
| `pairing_request` | same intent, but with a mandatory sub-pipeline for uploaded garments (1a new image → 46-attr vision → embeddings → wardrobe save; 1b existing wardrobe → use stored attributes) | architect (with anchor) → catalog_search → assembler → reranker (top 3) → tryon (all 3) → visual evaluator (all 3) → formatter |
| `garment_evaluation` | merges `shopping_decision` + `garment_on_me_request` + `virtual_tryon_request` | tryon → visual evaluator → formatter. Photo-only input. `purchase_intent: bool` extracted by planner; formatter conditionally renders buy/skip verdict computed deterministically from evaluator scores |
| `outfit_check` | unchanged intent, lean pipeline | visual evaluator on user-provided photo → formatter → [async] outfit decomposition + wardrobe save. **No architect call, no try-on.** Outfit check rates what the user is wearing — it does not redirect to what the system would have recommended instead. |
| `style_discovery` | unchanged intent, new handler | StyleAdvisorAgent → formatter |
| `explanation_request` | unchanged intent, new handler | StyleAdvisorAgent → formatter |
| `feedback_submission` | unchanged | pure tool call, no LLM reasoning |
| `wardrobe_ingestion` | **kept as silent-save variant** | not exposed as a primary advisory intent in the planner prompt; remains in the registry so programmatic / bulk upload flows can dispatch it |

**Intents being removed from the user-facing advisory taxonomy:**
- `capsule_or_trip_planning` — deferred to a later phase; delete `_handle_capsule_or_trip_planning`, registry entry, related prompts, and tests
- `product_browse` — folded into `occasion_recommendation` via a new `target_product_type` field. "Show me shirts" becomes an `occasion_recommendation` with `target_product_type="shirt"` and no occasion_signal; the architect still plans a direction, retrieval still runs, but the candidate shape may be single-garment instead of top+bottom pairs
- `virtual_tryon_request` — absorbed into `garment_evaluation`
- `shopping_decision` — absorbed into `garment_evaluation`
- `garment_on_me_request` — absorbed into `garment_evaluation`

**Planner responsibilities (narrower than today):**
1. Query validation — is the request in scope for a fashion copilot?
2. Intent classification across the 7 advisory intents (+ implicit `feedback_submission` + silent `wardrobe_ingestion`)
3. Entity extraction: `occasion_signal`, `formality_hint`, `time_of_day`, `weather_context`, `target_product_type`, `purchase_intent`, `source_preference`, anchor-garment reference, conversation continuity (`is_followup`, `followup_intent`)
4. Clarification questioning when any required entity is irreducibly ambiguous

The planner **no longer generates inline response text**. Persona and advisory content generation move to `StyleAdvisorAgent` (for `style_discovery` and `explanation_request`) and the response formatter (for everything else).

**Orchestrator responsibilities:**
1. Enrich the planner output with context the planner cannot see: user profile, style preferences, conversation memory, disliked-product suppression, attached-image state, wardrobe contents
2. Reason about which of the four thinking directions matter most for this turn (see below), and pass that reasoning direction into the architect and evaluator prompts as context
3. Dispatch to the correct pipeline and sequence its stages with graceful failure handling
4. Persist turn artifacts and emit telemetry

**The four thinking directions** — these are reasoning axes for the orchestrator, architect, and evaluator, NOT fixed 25% weights. They tell the system what matters per turn:
- Physical features + color (body harmony, proportion, palette match)
- User comfort (risk tolerance, comfort boundaries, personal style alignment)
- Occasion appropriateness (formality, dress code, cultural context)
- Weather and time of day (climate, season, daypart)

The orchestrator should reason about which of these dominates for a given request and propagate that direction into downstream prompts. The concrete evaluator scoring dimension count grows by exactly one: **`weather_time_pct`** is added as a 9th dimension alongside the existing 8.

### Phase 12A — Intent Consolidation and Cleanup

Status: **complete** (verified May 1, 2026 — `intent_registry.py` ships 8 intents and 7 actions, `garment_on_me_vision_route` gone, `_handle_shopping_decision` and `prompt/shopping_decision.md` removed).

Goal: the registry is 7 advisory + feedback + silent `wardrobe_ingestion`, with no behavioral or quality change to users. Pure rename + deletion.

Checklist:
- [x] merge `shopping_decision` + `garment_on_me_request` + `virtual_tryon_request` into a new `Intent.GARMENT_EVALUATION` in `modules/agentic_application/src/agentic_application/intent_registry.py`
- [x] remove `Intent.CAPSULE_OR_TRIP_PLANNING` + its registry metadata, handler (`_handle_capsule_or_trip_planning`), tests, prompt references, and all related stage messages
- [x] remove `Intent.PRODUCT_BROWSE` as a distinct intent; absorb into `Intent.OCCASION_RECOMMENDATION` by adding `target_product_type: Optional[str]` on `CopilotResolvedContext`
- [x] keep `Intent.WARDROBE_INGESTION` in the registry as a silent-save variant; remove it from the user-facing intent list in `prompt/copilot_planner.md` but retain the dispatch path
- [x] update `CopilotActionParameters`: replace `verdict: Optional[str]` with `purchase_intent: bool = False`; add `target_product_type: str = ""`; add `weather_context: str = ""`; add `time_of_day: str = ""`
- [x] update `Action` enum: drop `RUN_SHOPPING_DECISION`, `RUN_VIRTUAL_TRYON`, `RUN_PRODUCT_BROWSE`; add `RUN_GARMENT_EVALUATION`; actions go from 9 → 7
- [x] update `prompt/copilot_planner.md` to classify only the 7 advisory intents and extract the new entities
- [x] update planner JSON schema in `agents/copilot_planner.py` to reflect the new enum values and entity fields
- [x] route the new `garment_evaluation` intent to a temporary shim that calls the existing `OutfitCheckAgent` (the deeper pipeline lands in Phase 12B)
- [x] delete the `garment_on_me_vision_route` override added during the P0 staging bug fix — the merged intent has its own dispatch path
- [x] delete `_handle_shopping_decision`, `prompt/shopping_decision.md`, and `agents/shopping_decision_agent.py` (or rename the agent to `garment_evaluation_agent.py` and keep its scoring logic as reference for Phase 12B)
- [x] update tests that mock removed intents; add tests for the new `garment_evaluation` routing

Success criteria:
- intent registry lists 7 advisory intents + `feedback_submission` + silent `wardrobe_ingestion`
- every existing test passes with the new taxonomy
- no user-visible behavioral change; this is a rename + deletion phase

### Phase 12B — Visually-Grounded Evaluator and Reranker

Status: **complete** (April 8, 2026). Visual evaluator path is gated on the user having a full-body profile photo; legacy text-only `OutfitEvaluator` remains as the fallback for users without one. Phase 12E will tighten the over-generation contract and add operational dashboards.

Goal: evaluation reflects the rendered try-on, not catalog attributes. Explicit reranker prunes candidates before the expensive visual stage.

Checklist:
- [x] introduce an explicit `Reranker` step in the orchestrator pipeline between `OutfitAssembler` and try-on generation (`agents/reranker.py` — **direction-aware round-robin**: picks the top candidate from each direction first, then fills remaining slots by global `assembly_score`; `final_top_n=3`, `pool_top_n=5`)
- [x] merge `OutfitEvaluator` and `OutfitCheckAgent` into a single `VisualEvaluatorAgent` (`agents/visual_evaluator_agent.py`) that takes `(image, candidate_metadata, user_context, live_context, intent, mode)` and produces 9 dim scores + 8 archetype scores + structured notes per candidate. The agent works in three modes: `recommendation` (per-candidate, no overall_verdict), `single_garment` (full output for `garment_evaluation`), `outfit_check` (full output for the user-photo flow)
- [x] add the 9th evaluator dimension `weather_time_pct` to `EvaluatedRecommendation` + `OutfitCard` (internal + api) — appropriateness for stated weather and time of day
- [x] author `prompt/visual_evaluator.md` (combines the strongest pieces of `outfit_evaluator.md` and `outfit_check.md`, names the four thinking directions, single-garment framing, follow-up evaluation rules, weather/time mapping)
- [x] move the evaluator call to AFTER try-on in `_handle_planner_pipeline` for users with a person photo: `assembler → reranker → render top-3 (with over-generation fallback) → VisualEvaluatorAgent (parallel per candidate) → formatter`. Users without a person photo continue on the legacy text-only OutfitEvaluator path.
- [x] render try-on for top-3 candidates in parallel via `_render_candidates_for_visual_eval`; the existing post-format `_attach_tryon_images` cache lookup hits the same renders so OutfitCards still get their try-on images
- [x] graceful failure handling: if a try-on fails the quality gate, the over-generation pool walks the next candidate; if the pool is exhausted, the candidate ships without a tryon path and the visual evaluator falls back to attribute-only scoring on that slot. If the entire visual path raises, the orchestrator falls back to the legacy text-only `OutfitEvaluator`
- [x] rewire `_handle_garment_evaluation` to use: `TryonService → VisualEvaluatorAgent → formatter` with deterministic wardrobe overlap + versatility + verdict gating. Photo-only input. `purchase_intent` flag flows through to the formatter and is the only thing that controls whether the buy/skip verdict block renders
- [x] rewire `_handle_outfit_check` to use `VisualEvaluatorAgent` directly on the user's provided photo (no architect, no try-on; the user is already wearing the outfit in the image). The existing async outfit decomposition + wardrobe save path remains
- [x] update stage emission for the slow pipeline: new stages `reranker`, `visual_evaluation` (with `target_count` and `evaluated_count` context); the legacy text path keeps emitting `outfit_evaluation`. Operator dashboards can distinguish the two paths via `model_call_logs.request_json.evaluator_path`
- [x] response formatter: add deterministic wardrobe overlap check via `AgenticOrchestrator._compute_wardrobe_overlap` (category + color + formality match → strong / moderate / none). Surfaced in `garment_evaluation` metadata + assistant message. No LLM involved
- [x] response formatter: add deterministic wardrobe versatility check via `AgenticOrchestrator._compute_wardrobe_versatility` (counts compatible complementary categories with formality compatibility). Surfaced in metadata
- [x] response formatter: deterministic buy/skip/conditional verdict via `AgenticOrchestrator._compute_purchase_verdict`. Strong wardrobe overlap forces `skip` regardless of scores; otherwise the average of body+color+style+occasion+weather drives the verdict. Only computed when `purchase_intent=true`; suppressed otherwise
- [x] tests added: `test_planner_garment_evaluation_runs_tryon_visual_eval_pipeline`, `test_garment_evaluation_no_image_returns_clarification`, `test_garment_evaluation_strong_wardrobe_overlap_drives_skip_verdict`, `test_garment_evaluation_purchase_intent_false_suppresses_verdict`, plus 12 building-block unit tests in `Phase12BBuildingBlockTests` covering Reranker ordering / pool cap / validation, the four verdict-computation branches, and wardrobe overlap + versatility detection

Success criteria:
- outfit_recommendation / pairing_request: when the user has a full-body photo, top-3 candidates are visually evaluated against rendered try-ons; when they don't, the legacy text evaluator runs and the response still ships
- garment_evaluation produces a visually-grounded assessment plus an optional purchase verdict when the user framed it commercially
- outfit_check uses the visual evaluator on the user's photo with no architect call and no try-on
- all tests in `tests/test_agentic_application.py` pass (100 total — 85 existing + 3 new garment_evaluation flow tests + 12 new building-block unit tests)
- no regressions in the broader suite (3 pre-existing UI HTML failures remain, unchanged from before Phase 12B)

Deferred to Phase 12E:
- assembler "top 5" output contract (currently the assembler returns its full set and the reranker prunes; over-generation walks the same set rather than asking the assembler for more)
- Operations dashboard panels (quality-gate failure rate, evaluator path mix, latency by intent)
- Reranker calibration from staging telemetry once it exists

### Phase 12C — StyleAdvisorAgent, Planner Split, and Entity Additions

Status: **complete** (April 8, 2026). The orchestrator now uses a layered routing model: deterministic topical helpers (collar / neckline / pattern / silhouette / archetype / color) take priority for style_discovery, with `StyleAdvisorAgent` as the LLM fallback for open-ended discovery questions and explanation_request turns that have prior recommendations to reason about.

Goal: the planner becomes a pure router + entity extractor. Style discovery and explanation flow through a dedicated advisor agent. Weather and time enter the prompt chain.

Checklist:
- [x] introduce `modules/agentic_application/src/agentic_application/agents/style_advisor_agent.py` + `prompt/style_advisor.md`
- [x] `StyleAdvisorAgent.advise(mode, query, user_context, plan_resolved_context, plan_action_parameters, conversation_memory, previous_recommendation_focus, profile_confidence_pct)` returns a structured `StyleAdvice` with `assistant_message`, `bullet_points`, `cited_attributes`, `dominant_directions`. Two modes: `discovery` (open-ended) and `explanation` (against a prior recommendation summary). `render_assistant_message()` produces the chat-ready prose + bullets combined output.
- [x] update `prompt/copilot_planner.md` — added a Phase 12C clarification under `respond_directly` explaining that the planner's `assistant_message` for advisory intents is a brief acknowledgment (or empty) and that the orchestrator's downstream advisor produces the actual response. Examples of acceptable acknowledgments included.
- [x] planner JSON schema: `assistant_message` was already optional in the schema; the prompt change tells the planner to leave it empty/short for advisory intents.
- [x] rewire `_handle_style_discovery` to delegate to `StyleAdvisorAgent` when `_detect_style_advice_topic` returns `"general"` (open-ended). Topical questions (collar, color, etc.) continue to use the deterministic Phase 11 helpers.
- [x] rewire `_handle_explanation_request` to delegate to `StyleAdvisorAgent` in `explanation` mode when `previous_recommendations` is present. Advisor receives the prior recommendation's title, colors, categories, occasion fits, and confidence band so it can reason against actual turn artifacts. Falls back to the deterministic explanation summary when no prior recommendation exists or the advisor raises.
- [x] add weather / time-of-day extraction was already done in Phase 12A (`weather_context`, `time_of_day`, `target_product_type` on `CopilotResolvedContext`). Phase 12C plumbs these through the prompts.
- [x] update `prompt/outfit_architect.md` — added a "Thinking Directions" section naming the four directions (physical+color, comfort, occasion, weather/time) with concrete examples of how each one shapes the plan. Architect input section now documents `live_context.weather_context`, `live_context.time_of_day`, and `live_context.target_product_type` as inputs the architect should use.
- [x] update `prompt/visual_evaluator.md` — already authored in Phase 12B with the four thinking directions section. No changes needed here in 12C.

Success criteria:
- planner output for advisory intents contains routing + entities only; the orchestrator + advisor produce the substantive response
- `style_discovery` open-ended questions ("what defines my style?") are answered by `StyleAdvisorAgent` with bullet-pointed structured advice
- `style_discovery` topical questions still use the deterministic Phase 11 helpers (4 existing tests still pass)
- `explanation_request` answers cite the actual prior recommendation title, colors, categories via the advisor when context is available; falls back to the deterministic summary otherwise
- weather / time-of-day flows from planner → architect → visual evaluator end-to-end via the four-thinking-directions sections in each prompt
- 103 tests in `tests/test_agentic_application.py` pass (100 from Phase 12B + 3 new Phase 12C tests covering general delegation, topical fallback preservation, and explanation no-prior-recommendation fallback)
- no regressions in the broader suite (3 pre-existing UI HTML failures remain, unchanged from before Phase 12C)

Files added in Phase 12C:
- `modules/agentic_application/src/agentic_application/agents/style_advisor_agent.py` — new agent class + `StyleAdvice` result wrapper
- `prompt/style_advisor.md` — new prompt with the four thinking directions, mode-specific guidance, and structured JSON schema

Files modified in Phase 12C:
- `orchestrator.py` — `_handle_style_discovery` and `_handle_explanation_request` now route through `StyleAdvisorAgent` when conditions are met; `style_advisor` instantiated in `__init__`; `StyleAdvisorAgent` import added
- `prompt/copilot_planner.md` — `respond_directly` section clarifies that the planner's `assistant_message` is not the final answer for advisory intents
- `prompt/outfit_architect.md` — new "Thinking Directions" section, weather_context / time_of_day / target_product_type inputs documented
- `tests/test_agentic_application.py` — `_build_orchestrator` now patches `StyleAdvisorAgent`; `test_planner_respond_directly_for_explanation_request` updated to assert delegation; 3 new Phase 12C tests added

### Phase 12D — Wardrobe Ingestion Fix and Pairing Upload Subpipeline

Status: **complete** (April 8, 2026). Surfaced a second pre-existing bug along the way (the diversity pass was collapsing all pairing turns to 1 outfit because it didn't exempt the anchor) and fixed both in one phase.

Goal: fix the pre-existing enrichment bug surfaced by the staging audit; make the pairing-request 1a upload path reliable; add an invariant test for anchor handling.

Root cause analysis (from the staging audit of user_03026279ecd6 conversation 721e1963):
- `user/service.py:save_wardrobe_item` wrapped the 46-attribute vision enrichment call in a try/except that **silently swallowed the exception** and inserted the wardrobe row with the original empty `projected` dict (initialized from empty user-supplied fields).
- Downstream, `_attached_item_context` returned an empty string because all the parts were empty, the planner saw only `"Image anchor source: wardrobe image"` with no real attributes, and the architect had no anchor context to plan around. The pairing turn collapsed to a generic response.
- Separately: the `OutfitAssembler._enforce_cross_outfit_diversity` pass treats the anchor product like any other shared item, so all but the first paired candidate were being dropped. Pairing turns were producing 1 outfit instead of 3 — even when enrichment worked. Verified by running the pass against synthetic candidates.

Checklist:
- [x] traced `save_uploaded_chat_wardrobe_item` end-to-end through `onboarding_gateway → user.service → user.repository → wardrobe_enrichment.infer_wardrobe_catalog_attributes`. Located the swallow at `service.py:494-497`.
- [x] fix the enrichment path: added a single retry on transient enrichment failure (handles rate limits / network blips), and when both attempts fail, persist the row with `metadata_json["catalog_attribute_extraction_status"]="failed"` AND surface an `enrichment_status` top-level field on the returned dict so the orchestrator can detect the failure without re-parsing nested JSON.
- [x] orchestrator detects `enrichment_status="failed"` (or empty critical fields, for backwards compatibility with rows saved before the marker existed) and sets `attached_item["enrichment_failed"]=True`.
- [x] before dispatch, when `enrichment_failed=True` AND the intent is anything OTHER than `garment_evaluation`, the orchestrator overrides the action to `ASK_CLARIFICATION` with a user-facing message: *"I couldn't quite read the piece in that photo — could you try a clearer shot, ideally well-lit and showing the full garment? Then I can pair it properly."* `garment_evaluation` is exempt because the visual evaluator works on the image bytes directly and doesn't need attribute enrichment.
- [x] **path 1b finding:** path 1b doesn't exist as a distinct API path. The "select from wardrobe" UI re-uploads the existing item's image as a fresh `image_data` payload. Both 1a and 1b flow through the same `save_wardrobe_item` code path so the fix covers them. A true "look up by wardrobe_item_id without re-saving" path would require a new API field, UI change, and orchestrator branch — flagged as a Phase 12E or later improvement, not blocking.
- [x] **"Attached garment context" text decision:** keep it. After the enrichment fix the appended text reliably contains real garment attributes; it's consumed by the architect via `user_message` (per the architect prompt which explicitly says *"interpret this directly to understand what the user wants"*). Removing it would lose a real signal to the architect.
- [x] **anchor handling unification:** Added invariant test + fixed a pre-existing bug. The diversity pass at `OutfitAssembler._enforce_cross_outfit_diversity` was treating the anchor like any other shared product, so pairing turns with N candidates collapsed to 1 outfit. Fix:
  - `_product_to_item` now propagates the `is_anchor` flag from `enriched_data` to the candidate item.
  - The orchestrator's anchor injection at `_handle_planner_pipeline` sets `enriched_data["is_anchor"]=True` on the synthetic anchor `RetrievedProduct`.
  - The diversity pass exempts items where `is_anchor=True` from the "no repeats across outfits" rule. Non-anchor duplicates are still dropped (the original rule still applies for shared complementary items).
  - Two regression tests lock the invariant in: `test_diversity_pass_keeps_all_pairing_candidates_when_anchor_is_marked` and `test_diversity_pass_still_drops_non_anchor_duplicates`.
- [x] regression test reproducing the staging case: `test_failed_enrichment_surfaces_clarification_for_pairing` simulates the staging bug (gateway returns empty fields with `enrichment_status="failed"`) and asserts the orchestrator returns a clarification asking for a clearer photo, NOT a generic pairing response. Architect must not be called.
- [x] companion test `test_garment_evaluation_proceeds_even_with_failed_enrichment` confirms the garment_evaluation exemption: even with failed enrichment, the visual evaluator runs on the image bytes and the response is a real `recommendation`, not a clarification.

Success criteria:
- the staging bug no longer reproduces: failed enrichment surfaces a user-facing clarification instead of running the pipeline with an empty-attribute anchor
- transient enrichment failures are recovered automatically via the single retry
- pairing turns return up to 3 outfits, not 1, because the diversity pass now exempts anchor products
- non-anchor duplicates are still dropped by the diversity pass (the original "no repeats" rule still works for shared complementary items)
- 107 tests in `tests/test_agentic_application.py` pass (103 from Phase 12C + 4 new Phase 12D tests)
- no regressions in the broader suite (5 pre-existing UI HTML / onboarding HTML failures remain, unchanged from before Phase 12D)

Files modified in Phase 12D:
- `modules/user/src/user/service.py` — `save_wardrobe_item` retries enrichment once, propagates `enrichment_status` and `enrichment_error` to the returned dict
- `modules/agentic_application/src/agentic_application/orchestrator.py` — detect `enrichment_failed` after upload, override action to `ASK_CLARIFICATION` for pairing/recommendation intents (garment_evaluation exempt); mark anchor `RetrievedProduct.enriched_data["is_anchor"]=True` during anchor injection
- `modules/agentic_application/src/agentic_application/agents/outfit_assembler.py` — `_enforce_cross_outfit_diversity` exempts items with `is_anchor=True` from the "no repeats" rule; `_product_to_item` propagates the `is_anchor` flag from `enriched_data`
- `tests/test_agentic_application.py` — new `Phase12DAnchorAndEnrichmentTests` class with 4 regression tests (anchor diversity exemption, non-anchor duplicate handling preserved, failed enrichment clarification, garment_evaluation exemption)

Deferred (not blocking Phase 12D):
- True path 1b: API support for "use wardrobe item by id" without re-uploading (avoids row duplication)
- Background re-enrichment of older wardrobe rows that were saved with empty fields before the Phase 12D fix
- Wardrobe ingestion telemetry dashboard (Phase 12E)

### Phase 12E — Over-generation, Hardening, and Calibration

Status: **complete** (April 8, 2026). Phase 12 is now fully closed out — see "Phase 12 — Closed" summary below.

Goal: harden the Phase 12B pipeline against quality-gate failures; instrument telemetry; document the new pipeline shapes.

Checklist:
- [x] **assembler/reranker contract** — verified that Phase 12B's `Reranker(final_top_n=3, pool_top_n=5)` already provides the over-generation pool. The assembler returns its full set, the reranker prunes to top 5, and `_render_candidates_for_visual_eval` walks the pool with quality-gate fallback to positions 4-5 when slots fail. No code change needed; this item was already covered by the Phase 12B reranker design and is now documented in `docs/WORKFLOW_REFERENCE.md` Phase 12 Summary.
- [x] **retry/fallback logic** — `_render_candidates_for_visual_eval` already walks the over-generation pool when quality-gate failures happen. Phase 12E adds **per-turn metrics** so operations can see how often this fires: `tryon_attempted_count`, `tryon_succeeded_count`, `tryon_quality_gate_failures`, `tryon_overgeneration_used`, `rendered_with_image_count`, `rendered_without_image_count`. These flow into `response.metadata.tryon_stats` and `dependency_validation_events.metadata_json` so Panel 10 (below) can chart them.
- [x] **operational dashboard panels** — added 4 new panels to `docs/OPERATIONS.md` with concrete SQL:
  - **Panel 9** — Visual Evaluator Path Mix: tracks the visual-vs-legacy evaluator path share over the last 7 days. Healthy steady state is `visual ~ 60–80%` and `legacy_text ~ 20–40%`.
  - **Panel 10** — Try-on Quality Gate Health: tracks `tryon_quality_gate_failure_rate_pct` and `turns_using_overgeneration` per day. Healthy steady state is failure rate `< 15%`; alert above 25%.
  - **Panel 11** — Final Response Count Below Target: tracks the share of recommendation turns shipping fewer than 3 outfits because over-generation exhausted the pool. Healthy `< 5%`; page someone above 15%.
  - **Panel 12** — Wardrobe Enrichment Failure Rate: tracks the Phase 12D `wardrobe_enrichment_failed` reason code rate; healthy `< 5%`; spike means the OpenAI vision model is degraded.
  - **Panel 13** — Wardrobe-Anchor Try-on Coverage: tracks `garment_source` mix on `virtual_tryon_images` (`mixed` / `wardrobe` / `catalog`). For pairing-with-upload turns, healthy means `mixed` or `wardrobe`; a `catalog`-only label is the regression signal that the April 8, 2026 wardrobe-anchor fix has been undone.
- [x] **WORKFLOW_REFERENCE.md update** — added a new "Phase 12 Summary" section at the top with the current 7-intent + feedback + silent wardrobe_ingestion taxonomy, current pipeline shapes per intent, key building blocks added in Phase 12, and what stays the same. Marked the obsolete sections (Shopping Decision, Capsule/Trip Planning, Virtual Try-On, Garment-on-Me Query, Product Browse) with REMOVED IN PHASE 12X callouts pointing to the new equivalents. Updated the LLM Model Usage Summary table with Phase 12 component list and per-turn LLM call counts per intent. Updated the Database Write Summary table.
- [x] **end-to-end stage emission tests** — added a new `Phase12EStageEmissionTests` class with 3 tests that capture `stage_callback` events and assert the canonical stage skeleton per intent: lean skeleton for `style_discovery` and `explanation_request` (entry stages only), full pipeline skeleton for `occasion_recommendation` legacy text path (entry + outfit_architect + catalog_search + outfit_assembly + reranker + outfit_evaluation + response_formatting). Locks in the Phase 12 pipeline shapes so a future refactor that changes the order or skips a stage breaks the test loudly.

Success criteria:
- 99th-percentile turns ship 3 outfits with renders → unblocked by Phase 12B's over-generation pool + Phase 12D's anchor diversity exemption + Phase 12E's metrics make this measurable
- operational dashboards make quality-gate failure rate visible → Panel 10 in OPERATIONS.md
- `docs/WORKFLOW_REFERENCE.md` reflects the new pipelines → Phase 12 Summary section + per-section REMOVED callouts
- 110 tests in `tests/test_agentic_application.py` pass (107 from Phase 12D + 3 new Phase 12E stage emission tests)
- no regressions in the broader suite (5 pre-existing UI HTML / onboarding HTML failures remain, unchanged from before any Phase 12 work)

Files modified in Phase 12E:
- `modules/agentic_application/src/agentic_application/orchestrator.py` — `_render_candidates_for_visual_eval` returns `(rendered_list, stats_dict)` tuple instead of a bare list; `_handle_planner_pipeline` captures the stats and surfaces them in `response.metadata.tryon_stats` plus `dependency_validation_events.metadata_json` for the operations dashboard
- `docs/OPERATIONS.md` — 4 new panels (9-12) with concrete SQL
- `docs/WORKFLOW_REFERENCE.md` — Phase 12 Summary at the top, REMOVED callouts on obsolete sections, updated LLM Model Usage Summary and Database Write Summary tables
- `tests/test_agentic_application.py` — new `Phase12EStageEmissionTests` class with 3 stage emission tests

Files NOT modified (intentionally — already done by Phase 12B/D):
- `agents/reranker.py` — already had `final_top_n=3, pool_top_n=5` defaults
- `agents/visual_evaluator_agent.py` — already had per-candidate parallel call pattern
- `agents/outfit_assembler.py` — anchor diversity exemption already landed in Phase 12D

## Phase 12 — Closed

Phase 12 (the re-architecture from 12 → 7 advisory intents + visually-grounded evaluation + planner split + wardrobe ingestion fix + over-generation hardening) is **fully closed out** as of April 8, 2026.

Sub-phase status:
- Phase 12A — Intent Consolidation and Cleanup → complete
- Phase 12B — Visually-Grounded Evaluator and Reranker → complete
- Phase 12C — StyleAdvisorAgent, Planner Split, Entity Additions → complete
- Phase 12D — Wardrobe Ingestion Fix and Pairing Upload Subpipeline → complete
- Phase 12E — Over-generation, Hardening, and Calibration → complete

End-to-end test counts:
- `tests/test_agentic_application.py`: 110 passing (75 pre-Phase-12 + 35 added across Phases 12A-E)
- Broader suite: 284 passing (5 pre-existing UI HTML / onboarding HTML failures unchanged from before Phase 12 work)

Files added across Phase 12 (5 new modules + 2 new prompts):
- `agents/visual_evaluator_agent.py` (Phase 12B)
- `agents/reranker.py` (Phase 12B)
- `agents/style_advisor_agent.py` (Phase 12C)
- `prompt/visual_evaluator.md` (Phase 12B)
- `prompt/style_advisor.md` (Phase 12C)

Files deleted across Phase 12 (2 dead modules):
- `agents/shopping_decision_agent.py` (Phase 12A)
- `prompt/shopping_decision.md` (Phase 12A)

### Items deferred from Phase 12 to a future phase

These were considered during Phase 12E scoping but explicitly punted because they require either real staging telemetry (not yet collected) or non-trivial UI / API surface changes:

1. **True path 1b API** — `wardrobe_item_id` parameter on `/v1/conversations/{id}/turns` so users can select an existing wardrobe item without re-uploading the image. Today the "select from wardrobe" UI re-uploads through the same `image_data` path, creating duplicate wardrobe rows. Affects API contract, web UI, and orchestrator dispatch.
2. **Background re-enrichment** — a worker that walks legacy wardrobe rows saved before Phase 12D's `service.py` retry-and-mark fix and re-runs the enrichment vision call. Today users with sparse legacy wardrobe items get a clarification when they reference one as an anchor; auto-re-enrichment would close the loop.
3. **Reranker calibration from staging telemetry** — incorporate prior-turn feedback, user style preference proximity, and weather/time match as additional reranker signals. Today `assembly_score` is the only signal. Phase 12E added the operations panels (9-12) that provide the inputs once staging traffic accumulates.
4. **Capsule / trip planning return** — Phase 12A removed this intent. Capsule/trip planning will return as a dedicated phase with the right shape (multi-day outfit selection with intentional wardrobe item recurrence).
5. ~~**Three-piece outfit support**~~ — **DONE** (April 10 2026). `three_piece` direction type with `outerwear` role. Architect prompt, JSON schema, assembler `_assemble_three_piece`, directional filters, role-category validation all shipped.
6. **External weather API integration** — Phase 12 extracts weather context from the user message text only. A real weather API call (lat/lon → current conditions) would let the system reason about weather even when the user doesn't mention it.
7. **Splitting OutfitEvaluator and OutfitCheckAgent fully** — Phase 12B added `VisualEvaluatorAgent` as the new path; the legacy `OutfitEvaluator` remains as the no-photo fallback and `OutfitCheckAgent` remains because some tests still mock it. A follow-up phase can delete both once test coverage is fully migrated.

These are recorded here so they don't get re-discovered as "Phase 12 didn't finish X" — they're deliberate punts, not missed items.

### Items Removed From the Forward-Looking Plan

The following items from earlier sections of this document are **superseded by Phase 12** and should not be picked up as standalone work:

- **Phase 3 — "implement `capsule_or_trip_planning` handler"**: SUPERSEDED. The handler and intent are being deleted in Phase 12A.
- **Phase 3 — "implement `shopping_decision` handler"**: SUPERSEDED. Absorbed into `garment_evaluation`.
- **Phase 3 — "implement `garment_on_me_request` handler"**: SUPERSEDED. Absorbed into `garment_evaluation`.
- **Phase 3 — "implement `virtual_tryon_request` handler path"**: SUPERSEDED. Absorbed into `garment_evaluation`.
- **Phase 11 — "trip/capsule catalog-path diversity"**: SUPERSEDED. The capsule handler is being removed.
- **Phase 11 — "architect-level diversity for trip/capsule"**: SUPERSEDED. Same reason.
- **The "12 intents recognized" claim** throughout the document: STALE. Becomes "7 advisory + feedback + silent wardrobe_ingestion" after Phase 12A.
- **The "9 actions" claim** throughout the document: STALE. Becomes 7 after Phase 12A (drop `run_shopping_decision`, `run_virtual_tryon`, `run_product_browse`; add `run_garment_evaluation`).
- **"Outfit evaluator scoring text-only attributes pre-try-on"** claims throughout: SUPERSEDED by Phase 12B visual evaluator. Evaluation post-12B is grounded in the rendered try-on image.

### Not in Scope for Phase 12

- WhatsApp runtime rebuild — separate phase
- External weather API integration — for Phase 12 the planner extracts weather context from the user message or conversation memory; external API is a future enhancement
- Reranker learning from live feedback — comes after staging telemetry lands
- Three-piece outfit support — **DONE** (April 10 2026); `three_piece` direction type shipped
- Alternative embedding models for catalog retrieval — unchanged from current design
- Bulk wardrobe upload UI — `wardrobe_ingestion` remains as silent-save; no new user-facing bulk surface in this phase

### Open Questions Resolved During Phase 12 Scoping

Recorded here so they don't get re-asked during implementation:

1. **Top-N try-on rendering**: render try-on for ALL 3 top candidates in parallel, not just #1. Cost is justified by the visually-grounded evaluation quality gain.
2. **Outfit check architect call**: NO. Outfit check stays lean — vision → formatter. It evaluates what the user is wearing, not what the system would have recommended instead.
3. **Style discovery handler**: delegate to a dedicated `StyleAdvisorAgent`, not to the architect. Clean separation between retrieval planning and stylist advisory.
4. **Bulk wardrobe save**: keep `wardrobe_ingestion` alive as a silent-save variant in the registry; it's just not exposed as a user-facing advisory intent in the planner prompt.
5. **Evaluation dimensions**: the four thinking directions (physical+color, comfort, occasion, weather/time) are reasoning axes for orchestrator and prompt authoring — not fixed scoring weights. The evaluator gains exactly one new scoring dimension: `weather_time_pct`. The existing 8 dimensions stay; total becomes 9.

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
- [x] **Operational dashboards (production-readiness)**: `docs/OPERATIONS.md` defines 14 dashboard panels with concrete SQL — acquisition funnel, daily turn volume by channel, intent mix, pipeline health (empty responses + error rate + catalog-unavailable guardrail hits), repeat / retention, wardrobe & catalog engagement, negative signals (dislikes), confidence drift, evaluator path mix (Panel 9), try-on quality gate health (Panel 10), final response count below target (Panel 11), wardrobe enrichment failure rate (Panel 12), wardrobe-anchor try-on coverage (Panel 13), and non-garment image rate (Panel 14, added April 9, 2026 with the non-garment detection fix). Each panel maps to one operational question and refreshes on the cadence specified in the doc.
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

---

## Phase 13: Outfit Architect Prompt & Schema Remediation

Scope: fix contradictions, close gaps, and tighten the outfit architect system prompt (`prompt/outfit_architect.md`) and its code wrapper (`modules/agentic_application/src/agentic_application/agents/outfit_architect.py`). No new features — this is correctness, consistency, and robustness.

**Status: all items implemented and verified (125/125 tests passing).**

### P0 — Code Bug: Missing `live_context` Fields in Architect Payload

- [x] added `weather_context`, `time_of_day`, `target_product_type` fields to `LiveContext` schema
- [x] wired them in `_build_effective_live_context()` from `CopilotResolvedContext` (both normal and catalog-followup paths)
- [x] `_build_user_payload()` now nests them under a `live_context` key in the architect payload
- [x] prompt Input section updated to document `live_context` as an object with three sub-fields
- [x] 3 regression tests added: fields present when set, null when empty, anchor_garment passthrough

### P0 — Contradictory Direction-Count Rules (Issues 1, 13)

- [x] removed "You MUST create exactly 3 directions for broad occasion requests, one of each structure type"
- [x] removed "For broad requests, use all three structure types (complete + paired + three_piece)"
- [x] occasion-driven structure selection (the table with occasion → appropriate structures) is now the sole authority

### P0 — Input Schema Gaps: Color Fields and `previous_recommendations` (Issues 4, 14)

- [x] documented `BaseColors.value`, `AccentColors.value`, `AvoidColors.value`, `SeasonalColorGroup_additional` in the `derived_interpretations` bullet of the Input section
- [x] documented `previous_recommendations` as a structured list with all 11 fields (title, primary_colors, garment_categories, garment_subtypes, roles, occasion_fits, formality_levels, pattern_types, volume_profiles, fit_types, silhouette_types)

### P1 — Anchor Garment Conflict Resolution (Issues 3, 10)

- [x] added anchor rules 4 and 5: per-category direction structure (top → paired/three_piece without top query; bottom → paired/three_piece without bottom query; outerwear → paired only with both top+bottom; complete → no search)
- [x] explicit "goal is always a complete outfit" rule

### P1 — `retrieval_count` Guidance (Issue 2)

- [x] added `retrieval_count` rules table after the Output schema: 12 broad, 6 single-garment, 8–10 anchor, 10–15 more_options, 12 change_color/similar/full_alternative

### P1 — Query Document Field Completeness (Issue 5)

- [x] added after query document template: "Every field MUST be populated… write `not_applicable` for genuinely irrelevant fields"

### P1 — Follow-Up Intent Tiebreaker (Issue 6)

- [x] added priority ordering: change_color > increase/decrease_formality > increase_boldness > full_alternative > similar_to_previous > more_options

### P1 — Inventory Starvation: Occasion > Count (Issues 8, 16)

- [x] replaced `count < 5` hard-avoid with occasion-first logic: count >= 1 is usable if occasion-appropriate
- [x] added fallback direction rule for count < 3

### P2 — Seasonal Color Group Additional Guidance (Issue 7)

- [x] added inline guidance in query document PROFILE_AND_STYLE section: populate when `SeasonalColorGroup_additional` is present, otherwise rely on primary group

### P2 — Fabric Vocabulary: Semantic Clusters (Issue 9)

- [x] added semantic fabric cluster instruction in the consolidated Occasion Calibration section

### P2 — Style-Stretch Direction (Issue 11)

- [x] added Style-Stretch Direction subsection under Direction Rules: third direction pushes one notch beyond archetype, gated by riskTolerance

### P2 — Prompt Structure Optimization (Issues 12, 15)

- [x] consolidated Sub-Occasion Calibration + Embellishment Reasoning + Occasion-Fabric Coupling into single "Occasion Calibration — Formality, Fabric, and Embellishment" section with one unified reference table
- [x] moved Thinking Directions from after Input to just before Guidelines (near generation point)
- [x] query document format left unchanged — compression requires embedding quality A/B test before committing

### P2 — `DirectionSpec` Comment (Minor)

- [x] updated `schemas.py` comment to `# complete | paired | three_piece`
- [x] regression test added: `test_direction_spec_accepts_three_piece`

---

## Phase 13B: Outfit Architect — Retrieval Quality, Failure Mode Hardening, Ranking Intent

Scope: fix remaining prompt sequencing issues, harden against real-world failure modes (weather-fabric conflict, anchor formality mismatch, embedding noise from filler tokens), add color synonym expansion, and introduce a ranking intent signal for downstream use.

**Status: all items implemented and verified (127/127 tests passing).**

### P0 — Thinking Directions Placement (Issue 1)

- [x] moved Thinking Directions from between Style Archetype Override and Guidelines to between Time-of-Day Color Palette Shift and Direction Rules — now acts as a framing lens before all specific rules

Definition of done:
- Thinking Directions sits immediately before the sections it should frame (Direction Rules, Hard Filters, Query Document Format, etc.)

### P0 — Query Document: Omit Inapplicable Fields (Issues 4, 6)

- [x] replaced "write `not_applicable`" rule with "omit fields that have no physical counterpart"
- [x] added per-role omission guide: bottom queries omit NecklineType, NecklineDepth, ShoulderStructure, SleeveLength; top/outerwear/complete queries populate all fields
- [x] clarified that WaistDefinition, GarmentLength, FitType, VolumeProfile apply to ALL garment categories

### P0 — Fallback Direction Count Tiebreaker (Issue 5)

- [x] added to fallback rule: "When adding a fallback would exceed 3 total directions, replace the lowest-confidence direction with the fallback rather than adding a fourth"

### P1 — Style-Stretch Occasion Guard (Issues 2, 10)

- [x] added guard: fabric/formality/embellishment/AvoidColors not relaxable for stretch; stretch operates in style/silhouette/color space only
- [x] removed "a different fabric family" from the high-risk stretch examples to prevent occasion-fabric conflict

### P1 — Follow-Up Rules: Explicit Field Name Mapping (Issue 3)

- [x] `change_color` rule now references `occasion_fits`, `formality_levels`, `garment_subtypes`, `silhouette_types`, `volume_profiles`, `fit_types`
- [x] `similar_to_previous` rule now references `garment_subtypes`, `primary_colors`, `formality_levels`, `occasion_fits`, `volume_profiles`, `fit_types`, `silhouette_types`

### P1 — Anchor Formality Conflict Resolution (Issue 9)

- [x] added anchor rule 6: shift supporting garments upward in formality to compensate when anchor conflicts with occasion

### P1 — Weather-Fabric Climate Override (Issue 11)

- [x] added Occasion Calibration core rule 5: weather overrides occasion for fabric weight/breathability; examples for hot/humid and cold scenarios; occasion still governs formality and embellishment

### P1 — Color Synonym Expansion (Issue 8)

- [x] added to color coordination rules: PrimaryColor/SecondaryColor fields should use comma-separated synonym lists (e.g., "terracotta, rust, burnt orange, warm brick")

### P2 — Query Document Conciseness (Issue 7)

- [x] added to query document format intro: "Use concise values — single terms or comma-separated lists, not full sentences"

### P2 — `retrieval_count` vs Inventory Depth (Issue 12)

- [x] added: "Do NOT inflate retrieval_count to compensate for low inventory"

### P2 — Ranking Intent Signal (Issue 13)

- [x] added `ranking_bias` field to `ResolvedContextBlock` in `schemas.py` (default: "balanced")
- [x] added `ranking_bias` to `_PLAN_JSON_SCHEMA` in `outfit_architect.py` with enum: conservative, balanced, expressive, formal_first, comfort_first
- [x] added `ranking_bias` to `_parse_plan()` extraction
- [x] added `ranking_bias` to prompt output schema and `resolved_context` rules with guidance on when to set each value
- [x] 2 regression tests added: default/override on ResolvedContextBlock, parse from LLM response
- [x] wire `ranking_bias` into assembler/reranker scoring (May 1, 2026 — `_BIAS_COEFS` table + `_apply_bias_bonus` in assembler; tie-break in reranker; orchestrator passes `combined_context.live.ranking_bias` through. See Open Items Plan section.)

### Post-13B Fix — Direction Differentiation for Outfit Count Regression

**Root cause:** After Phase 13B, outfit count dropped from 3 to 1-2. The conciseness instruction and field omission rules made query documents across directions more formulaic and similar in embedding space. Similar query documents → overlapping product retrieval → the cross-outfit diversity pass (`_enforce_cross_outfit_diversity`, `MAX_PRODUCT_REPEAT_PER_RUN=1`) eliminated most candidates since shared products can only appear in one outfit.

**Fix (prompt-only):**
- [x] added "direction differentiation" rule to Query Document Format: query documents across directions MUST use noticeably different vocabulary for garment subtypes, colors, fabrics, silhouettes. Explains WHY: similar documents → same products → 1 surviving outfit after diversity pass.
- [x] added to Concept-First Planning: "Each direction must be a genuinely different outfit concept — different garment subtypes, different color families, or different silhouette approaches."

### Post-13B Fix — Search Timeout Resilience + Office Sub-Occasion Calibration

**Root cause investigation (staging conversation `b8a5f527`):** "Find me outfits for daily office wear" returned only 1 outfit. Traced the pipeline:
- Architect produced 3 directions correctly (2 paired + 1 three_piece)
- Search returned `product_ids` for all 7 queries, but top queries only surfaced 1 product each
- Reproduced: Supabase vector search RPC (`match_catalog_item_embeddings`) hits statement timeout (error 57014) intermittently when 7 parallel queries run simultaneously against 1000+ row cosine similarity scans
- Search agent catches the exception at `catalog_search_agent.py:150-152` and sets `matches = []` — silently returns 0 products for timed-out queries
- With only 1 top product surviving (the query that didn't timeout), all 3 directions shared it, and `MAX_PRODUCT_REPEAT_PER_RUN=1` eliminated all but 1 candidate

**Two secondary issues found:**
1. The occasion table maps ALL "Office / business" to `paired + three_piece`, but "daily office wear" (smart_casual, repeatable) should lean paired-only — a blazer every day is overdressed
2. All 3 top queries used `GarmentSubtype: shirt` — even with direction differentiation, the same subtype + same filters produces near-identical embeddings

**Fix 1 — Search timeout retry with reduced concurrency:**

- [x] reduced `_MAX_SEARCH_WORKERS` from 4 to 2 in `catalog_search_agent.py`
- [x] added retry loop in `_search_one`: 1 retry after timeout (detects error code 57014 or "timeout" in message), 0.5s delay between attempts
- [x] logs `WARNING` with query_id, attempt number, and timeout flag on each retry

**Fix 2 — Office sub-occasion split in prompt:**

- [x] split "Office / business" row into "Formal office / business meeting" (paired + three_piece) and "Daily office / everyday work" (paired only) in both the direction structure table and the Occasion Calibration formality/fabric table
- [x] added `daily_office` as a valid `occasion_signal` in the `resolved_context` rules with classifier: "daily/everyday/regular/routine" → daily_office; meetings/presentations/clients/interviews → office; generic → default to daily_office
- [x] updated Time-of-Day Inference table for the split

**Fix 3 — Top-role subtype diversification:**

- [x] added "Role-level subtype diversification" rule to Query Document Format: when multiple directions share the same role, vary GarmentSubtype across directions. If the occasion constrains to one subtype, vary color family and silhouette instead.
- [x] **post-staging validation fix:** reinforced that diversification MUST only use subtypes present in `catalog_inventory` with count > 0 — staging showed the LLM chose `polo` (0 items in catalog), wasting direction B entirely. Rule now includes explicit example: "if the catalog carries shirt (758), tshirt (20), sweater (106) but no polo, use shirt/tshirt/sweater, NOT polo"
- [x] strengthened Catalog Awareness: "Never plan for a subtype with zero items" expanded to explain consequence — "the search will return zero results for that query, wasting a direction"

### Onboarding UX Improvements

**Step reorder** — moved images earlier and combined into single screen so users complete the high-friction step sooner:

Old: mobile → otp → name → dob → gender → body → profession → **fullbody** → **headshot** → style → done (10 steps)
New: mobile → otp → name → gender → **images (both)** → dob → body → profession → style → done (9 steps)

Changes:
- [x] reordered `STEP_ORDER` in `user/ui.py` — gender before images (needed for style session gender filtering), images combined into single screen
- [x] merged full-body and headshot into one step (`step-images`) with side-by-side upload slots and per-slot status indicators
- [x] height input changed from cm to **feet + inches** (two inputs), waist from cm to **inches** — converts to cm before API call (`heightCm = ((ft * 12) + inches) * 2.54`)
- [x] added `uploadImageAsync()` helper for sequential upload of both images from the combined screen
- [x] updated all `data-back` indices and `setStep()` targets for the new step order
- [x] updated step count display: "Step X of 9" (was 10)

### Phased Analysis — Early Agent Execution

**Goal:** start analysis agents as soon as their inputs are available, not after full onboarding. The user fills in fields progressively — agents should start as each data dependency is met.

**Prompt analysis:** checked all 3 agent prompts for actual profile field usage:
- Color agent prompt uses `<gender>` and `<age>` as context placeholders. Age is supplementary — skin/hair/eye color classification is age-independent. Can run with gender only.
- Other details agent uses `<gender>` and `<age>`. Gender-aware hair length baseline needs gender; age is supplementary. Can run with gender + age.
- Body type agent uses `<gender>`, `<age>`, `<height>`, `<waist>`. Height/waist are "context only" per prompt, but inform the vision model's frame assessment. Needs all four.

**Phased execution plan:**

| Trigger | Agent(s) to start | Data available | Data missing (passed as empty) |
|---|---|---|---|
| After image upload (step 4) | **color_analysis_headshot** | gender, headshot | age (empty — harmless) |
| After DOB input (step 5) | **other_details_analysis** | gender, age, headshot, full_body | — |
| After profile save (step 7, profession) | **body_type_analysis** + collation + interpretation | gender, age, height, waist, full_body | — |

**Implementation:**

Service layer:
- [x] added `run_single_agent(user_id, agent_name, prompt_context_override)` — runs one agent, persists its output column on the analysis snapshot, does NOT collate/interpret
- [x] added `run_remaining_and_finalize(user_id)` — checks which agents already have output, runs only the missing ones, collates all 3, runs interpretation, marks completed

API layer:
- [x] replaced no-op `start-partial` with real `POST /v1/onboarding/analysis/start-phase1` — starts color agent in daemon thread with gender-only context (age/height/waist empty)
- [x] added `POST /v1/onboarding/analysis/start-phase2` — starts other_details agent in daemon thread with gender + age
- [x] updated `POST /v1/onboarding/analysis/start` to use `run_remaining_and_finalize` — detects phases 1/2 output already on the snapshot and only runs body_type + collation + interpretation

UI layer:
- [x] after image upload → fires `start-phase1` (color agent begins ~30s before it otherwise would)
- [x] after DOB input → fires `start-phase2` (other_details agent begins while user fills measurements + profession)
- [x] after style preference → redirects to main app where `analysis/start` runs body_type + finalization, reusing phase 1/2 output

### Incremental Profile Persistence + Resume Flow

**Problem 1:** Steps 3-6 (name, gender, DOB, body) are held in JS memory and only persisted as a batch at step 7 ("Save Profile"). If the user drops off at step 5 after uploading images, their name and gender are lost despite images being saved to disk.

**Problem 2:** When a returning user re-enters mobile + OTP, the UI starts them at step 3 (name) regardless of existing progress. No pre-fill, no skip-to-incomplete-step, no way to edit already-saved fields.

**Fix 1 — Incremental save:**
- [x] added `PATCH /v1/onboarding/profile/partial` endpoint — `ProfilePartialRequest` with all optional fields, `patch_profile` service + repo methods update only provided fields
- [x] after name step → saves name via PATCH
- [x] after gender step → saves gender via PATCH
- [x] after DOB step → saves date_of_birth via PATCH
- [x] after body step → saves height_cm + waist_cm via PATCH
- [x] after profession step → saves profession + marks `profile_complete=true` via existing POST /profile

**Fix 2 — Resume flow:**
- [x] after OTP verification, UI calls `GET /v1/onboarding/status/{user_id}` (already existed) and now calls `prefillFromStatus()` to populate all form fields with existing values
- [x] `prefillFromStatus()` pre-fills: name, gender (input + chip highlight), DOB, height (reverse-converts cm → ft+in), waist (reverse-converts cm → in), profession (input + chip highlight)
- [x] `determineResumeDestination()` rewritten for new step order: checks each field in sequence (name → gender → images → DOB → height/waist → profession → style) and jumps to first incomplete step
- [x] `onboarding_complete=true` → redirects to main app (processing view)

### Body Type Analysis — Anti-Hedging Calibration

**Problem:** Vision LLMs systematically default to the middle of classification scales ("Medium", "Balanced", "Approximately Equal") to avoid appearing judgmental about body size. Staging validation showed a user with a clearly Solid+Broad frame classified as "Medium and Balanced" — producing wrong FrameStructure → wrong VerticalWeightBias → wrong silhouette recommendations.

**Root cause:** The prompt instruction "independent of actual body weight" was read by the model as permission to downplay visible mass. The "do not make evaluative judgments" rule (meant to prevent comments about attractiveness) was interpreted as "be conservative on body size scales."

**Fix (`prompt/body_type_analysis.md`):**
- [x] added CALIBRATION section naming the center-bias problem explicitly: "Vision models systematically default toward Medium/Balanced — these are NOT safe defaults"
- [x] added concrete calibration examples for VisualWeight (Light through Heavy with visual cues: bone visibility, limb thickness, joint width, frame density) and ArmVolume (Slim through Full)
- [x] added "Accuracy is kindness" framing: misclassifying a Heavy frame as Medium produces recommendations that don't fit or flatter
- [x] reinforced per-attribute instructions on VisualWeight ("do NOT default to Medium"), ArmVolume ("do not downgrade to Medium out of caution"), MidsectionState ("classify what you see")

### FrameStructure Interpreter — Two Bugs Fixed

**Staging investigation** showed the LLM agent output was actually correct (`VisualWeight: Medium-Heavy`, `ArmVolume: Full`) but the deterministic interpreter in `interpreter.py` mapped these to wrong FrameStructure. Two bugs:

**Bug 1 — Height penalty on width_score:** Users with `height_cm <= 160` got a -0.5 width penalty. For this user (160cm, Full arms, Average shoulders): `width_score = 0 + 1 - 0.5 = 0.5` → "Balanced" instead of "Broad". Height doesn't change observed arm volume or shoulder slope — a short person with Full arms IS broad.

**Bug 2 — Label mapping:** `("Solid", "Balanced")` mapped to `"Medium and Balanced"` — should be `"Solid and Balanced"`. A Solid weight band should never produce a "Medium" label. Similarly, `("Light", "Balanced")` mapped to `"Medium and Balanced"` instead of `"Light and Narrow"`.

**Fix (`interpreter.py`):**
- [x] removed height_cm bonus/penalty from width_score calculation — width is determined purely by ShoulderSlope + ArmVolume observations
- [x] fixed label mapping: `("Solid", "Balanced")` → `"Solid and Balanced"`, `("Light", "Balanced")` → `"Light and Narrow"`
- [x] now 5 of 9 combinations produce distinct labels instead of collapsing to "Medium and Balanced"

---

## Color Analysis System Overhaul — 12-Season Typing + Dimension-First Architecture

### Problem Statement

The current system has three structural weaknesses:
1. **Warmth is determined by a single attribute** (HairColorTemperature). Olive-skinned South Asian users with warm-toned hair get misclassified as Autumn when their skin undertone is actually cool/olive.
2. **Draping unconditionally overrides the deterministic analysis.** A 43%-vs-38% draping split throws away a solid attribute-based signal.
3. **4-season bucketing is too coarse.** Two users classified as "Autumn" can have very different coloring (Warm Autumn vs Soft Autumn vs Deep Autumn), but receive identical palettes.

### Architecture Shift

Current: season-first (determine season → derive palette)
Target: dimension-first (compute warmth/depth/contrast/chroma → derive season + sub-season AND expose raw dimensions for direct downstream use)

### Implementation Plan — 3 Phases

---

#### Phase A — Enhanced Color Extraction (prompt changes, zero added latency)

**A1. Add SkinUndertone to color analysis prompt**

File: `prompt/color_analysis_headshot.md`
- [x] added attribute #6: `SkinUndertone` with enum `Warm | Cool | Neutral-Warm | Neutral-Cool | Olive` — instruction focuses on jaw-to-neck area, explicitly ignores hair color, includes Olive detection note for South Asian skin

File: `modules/user/src/user/analysis.py`
- [x] added `SkinUndertone` to `COLOR_HEADSHOT_SPEC.attribute_enums`

**A2. Add SkinChroma to color analysis prompt**

File: `prompt/color_analysis_headshot.md`
- [x] added attribute #7: `SkinChroma` with enum `Muted | Moderate | Clear`

File: `modules/user/src/user/analysis.py`
- [x] added `SkinChroma` to `COLOR_HEADSHOT_SPEC.attribute_enums`

**A3. Rename EyeClarity → EyeChroma**

- [x] renamed in prompt, COLOR_HEADSHOT_SPEC, and JSON response format
- [x] interpreter uses backward-compat fallback: reads "EyeChroma" first, falls back to "EyeClarity" for pre-existing analysis data

---

#### Phase B — Dimension-First Interpreter (code changes, zero API calls)

**B1. Weighted warmth score replacing binary branch**

File: `modules/user/src/user/interpreter.py` — `_derive_seasonal_color_group()`
- [x] implemented weighted warmth from SkinUndertone(×3) + HairTemp(×2) + EyeColor(×1), normalized to ±2
- [x] fallback path for users without SkinUndertone (pre-Phase A): uses HairTemp(×2) + EyeColor(×1) only
- [x] `ambiguous_temperature` flag when |warmth_score| < 0.5 — reduces confidence by 0.10

**B2. Explicit skin-hair contrast score**

File: `modules/user/src/user/interpreter.py`
- [x] added `_derive_skin_hair_contrast()` — computes `abs(skin_depth - hair_depth)`, stores as Low/Medium/High label + numeric score
- [x] registered as `SkinHairContrast` in `derive_interpretations()`

**B3. Chroma-aware season selection**

File: `modules/user/src/user/interpreter.py`
- [x] chroma_score = average of SkinChroma score + EyeChroma score (Muted=0.15, Moderate=0.55, Clear=0.9)
- [x] computed inside `_derive_seasonal_color_group()`, feeds into sub-season assignment and is stored in dimension_profile

**B4. Store dimension profile as first-class output**

- [x] `_derive_color_dimension_profile()` surfaces warmth_score, depth_score, skin_hair_contrast, chroma_score, ambiguous_temperature as `ColorDimensionProfile` derived interpretation
- [x] dimension_profile also attached to SeasonalColorGroup output for direct access

---

#### Phase C — Draping Collaboration + 12 Sub-Seasons

**C1. Draping confidence margin**

File: `modules/user/src/user/draping.py`
- [x] added `_confidence_to_points()`: >0.8→Strong(3), 0.6-0.8→Moderate(2), <0.6→Slight(1)
- [x] added `_compute_confidence_margin()`: sums points for primary season camp vs runner-up across 3 rounds
- [x] `confidence_margin` stored on `DrapingResult` and serialized in `to_dict()`

**C2. Threshold-based draping collaboration**

File: `modules/user/src/user/analysis.py`
- [x] extracted `_apply_draping_collaboration()` shared helper, used in both `run_analysis()` and `run_remaining_and_finalize()`
- [x] threshold `_DRAPING_OVERRIDE_MARGIN = 4`: margin > 4 → draping overrides; margin ≤ 4 + agreement → confidence boosted; margin ≤ 4 + disagreement → deterministic holds, draping stored as secondary_season
- [x] `secondary_season` and `confidence_margin` surfaced as first-class fields on SeasonalColorGroup output

**C3. 12 sub-season assignment**

File: `modules/user/src/user/interpreter.py`
- [x] added `_derive_sub_season()` — scores each candidate sub-season by how extreme the user is on its defining dimension (warmth/depth/chroma), picks the best match
- [x] `_SUB_SEASON_RULES` dict defines all 12 sub-seasons with their dominant dimension and direction (highest/lowest)
- [x] `SUB_SEASON_ADJACENCY` dict defines borrowing relationships (Warm Autumn ↔ Warm Spring, Soft Autumn ↔ Soft Summer, etc.)
- [x] stored as `SubSeason` derived interpretation with `adjacent_sub_seasons` list

**C4. 12 sub-season palettes with dimension-based adjustments**

File: `modules/user/src/user/interpreter.py`
- [x] `SUB_SEASON_PALETTE_MAP`: 12 curated palette tables (4 base + 5 accent + 5 avoid each = 168 color values)
- [x] `SEASON_PALETTE_MAP` now derived from sub-season palettes (backward compat)
- [x] `derive_color_palette()` accepts `sub_season`, `secondary_season`, `dimension_profile`
- [x] boundary blending: confidence < 0.6 or secondary_season → base from primary, accents extended from adjacent, avoid narrowed to intersection

**C5. Store secondary season and confidence margin explicitly**

- [x] `secondary_season` and `confidence_margin` surfaced on SeasonalColorGroup by `_apply_draping_collaboration()`
- [x] architect reads `additional_groups` which now includes secondary season from draping

### Post-Implementation: Migration, Integration, Draping Image Storage

**Migration** (`supabase/migrations/20260411120000_color_analysis_12_season.sql`):
- [x] added columns to `user_interpretation_snapshots`: sub_season (value/confidence/evidence_note), skin_hair_contrast (value/confidence/evidence_note), color_dimension_profile (value/confidence/evidence_note), confidence_margin
- [x] created `draping_overlay_images` table for persisting draping overlay pairs per round (user_id, analysis_snapshot_id, round_number, image_a/b_path, colors, labels, choice, confidence, reasoning, winner)

**Repository integration** (`repository.py`):
- [x] added SubSeason, SkinHairContrast, ColorDimensionProfile to `INTERPRETATION_COLUMN_PREFIXES` — these now persist to typed columns alongside the JSONB collated_output
- [x] added `insert_draping_overlay()` method for persisting draping round images + decisions

**Draping image persistence** (`draping.py`):
- [x] added `_run_round_with_persistence()` — saves overlay images to `data/draping/overlays/{user_id}_r{round}_a/b.jpg` and records paths + round metadata in `draping_overlay_images` table
- [x] `run_draping()` accepts `analysis_snapshot_id` param, passes to each round for DB association
- [x] both callers in `analysis.py` (`run_analysis` and `run_remaining_and_finalize`) now pass `run_id` as analysis_snapshot_id

### Post-Implementation: Integration Gaps

**Gap 1 — Architect prompt:**
- [x] added SubSeason, SkinHairContrast, ColorDimensionProfile to Input section with usage guidance
- [x] updated Visual Direction Reasoning table: all 5 FrameStructure labels now match interpreter output

**Gap 2 — Tests (10 new, 13 total in test_onboarding_interpreter.py):**
- [x] weighted warmth with Olive undertone + Cool undertone overriding warm hair
- [x] ambiguous temperature flag
- [x] sub-season assignment (Deep Autumn, Deep Winter)
- [x] boundary palette blending (accents extended from adjacent)
- [x] SkinHairContrast High + Low
- [x] backward compat (EyeClarity fallback)
- [x] ColorDimensionProfile surfaced with all fields

**Gap 3 — Draping prompt:**
- [x] added Strong/Moderate/Slight reference points to confidence instruction in digital_draping.md

**Gap 4 — Downstream agents:**
- [x] visual_evaluator_agent.py: passes sub_season + skin_hair_contrast to evaluation context
- [x] style_advisor_agent.py: passes sub_season + skin_hair_contrast to advice context

**Gap 5 — effective_seasonal_groups:**
- [x] both callers in analysis.py enrich effective_groups[0] with sub_season value

**Gap 6 — Docs:**
- [x] APPLICATION_SPECS.md: added "Color analysis — 12 sub-season architecture" section
- [x] WORKFLOW_REFERENCE.md: added "Color Analysis Overhaul" table with all changes

**Gap 7 — FrameStructure labels:**
- [x] architect prompt Visual Direction table updated with all 5 valid labels

---

## Remove Digital Draping

**Decision:** Digital draping produces unreliable results — the LLM has a systematic cool-bias at 35% overlay opacity, over-assigns confidence on subtle visual differences, and overrides correct deterministic results. The deterministic interpreter (weighted warmth from SkinUndertone + HairTemp + EyeColor, depth, chroma) is more reliable. Remove draping entirely.

### Removal scope — 10 touchpoints

**Deleted:**
- [x] `modules/user/src/user/draping.py` — entire DigitalDrapingService
- [x] `prompt/digital_draping.md` — draping prompt
- [x] `tests/test_digital_draping.py` — draping tests
- [x] `data/draping/overlays/` — local overlay image files

**Removed from analysis pipeline:**
- [x] `analysis.py`: removed `_apply_draping_collaboration()`, `_DRAPING_OVERRIDE_MARGIN`, all `DigitalDrapingService` imports/calls, `draping_output` from snapshot updates
- [x] `run_analysis()` and `run_remaining_and_finalize()` go straight from collation+interpretation to persistence
- [x] `effective_seasonal_groups` uses source="deterministic" only

**Removed from API + UI:**
- [x] `api.py`: removed `GET /analysis/draping-images/{user_id}` endpoint, removed `data/draping/overlays` from allowed_roots
- [x] `ui.py` (platform_core): removed draping card HTML, `loadDrapingImages()` JS, draping CSS

**Removed from user context builder:**
- [x] `user_context_builder.py`: removed effective_seasonal_groups overlay that could override SeasonalColorGroup with draping. Removed `derive_color_palette` import. Deterministic result from `collated_output` is now the sole authority.

**DB — columns left in place (non-breaking):**
- `user_analysis_snapshots.draping_output` — no longer written, defaults to `{}`
- `draping_overlay_images` table — no longer written, left in place
- `user_interpretation_snapshots` draping columns — no longer written

**All 143 tests passing (130 main + 13 interpreter).**

