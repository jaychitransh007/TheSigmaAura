# Open Tasks

This file is the running list of known follow-ups: not blocking any release today, but worth tracking so they don't get lost. Each entry is a one-paragraph brief — enough to remember the context, not a full plan.

When a task is picked up, replace the brief with a link to the PR/branch. When it's done, delete the entry (the git history of this file is the audit trail).

For per-PR record of what's already shipped, see `RELEASE_READINESS.md` § Recently Shipped.

---

## Catalog vocabulary cleanup — Phase 2 of the May-3 occasion-tag refactor

**Status:** queued · **Cost:** small (~$3 + 1 hour) · **Risk:** low

Phase 1 (May 3, 2026) stopped the architect from emitting `OccasionFit` / `OccasionSignal` / `FormalitySignalStrength` in query documents — the catalog still carries them on every row but they no longer pollute the architect's queries. That gives most of the latency / score-quality win without a catalog re-run.

Phase 2 finishes the cleanup on the catalog side:
1. Drop `OccasionFit`, `OccasionSignal`, `FormalitySignalStrength` from the text that gets fed into `text-embedding-3-small`. The columns can stay in the table for historical compatibility but they stop contributing to the embedding vector.
2. Re-run `ops/scripts/embed_catalog.py` (or equivalent) over the existing 14,296 enriched rows. Vision enrichment is **not** re-run — only the embedding text changes.
3. Verify on a handful of test queries (daily-office, date-night, wedding-engagement) that cosine similarity scores stabilize at or above today's post-Phase-1 baseline.

**Trigger to do this:** if the daily-office / casual-occasion confidence-gate failure rate stays elevated after Phase 1 ships, or if Panel 16 in `OPERATIONS.md` shows >5% `catalog_low_confidence` rate sustained.

**Cost:** ~14,296 items × ~500–2,000 tokens × $0.02/1M ≈ $3–5. Re-embed takes 30–60 minutes depending on rate limits. No vision API calls.

---

## Catalog vocabulary consolidation — rare-value cleanup (Phase 3 follow-up)

**Status:** parked · **Cost:** small · **Risk:** low

Phase 3 (May 3, 2026) consolidated the four near-duplicate values: `pants`→`trouser` (107), `jeggings`→`jeans` (9), `androgynous`→`unisex` (12), `night`→`evening` (8). Architect vocabulary list updated to match.

What's left: the rare values with ≤5 rows each — `poncho` (5), `leggings` (4), `kaftan` (4), `tracksuit` (3), `ethnic_set` (2), `dungarees` (1). Each is a per-row content decision (re-tag to nearest valid subtype, or drop the row entirely from `catalog_item_embeddings`). Not vocabulary cleanup — content cleanup. Defer until a content reviewer can decide row by row.

**Trigger to do this:** if any of the rare subtypes appears in `tool_traces.composer_decision` outputs (i.e., the LLM ranker actually picks one) or surfaces in a user complaint.

---

## Catalog `OccasionFit` column — keep for now

**Status:** decided (May 3, 2026) — **keep populating, do not drop**

`OccasionFit` is no longer read by retrieval (Option A in PR #20 stripped user-side sections from the architect's query_document; the LLM ranker doesn't filter on it either). But `build_catalog_document()` still emits it in the metadata dict and the `occasion_fit` SQL column on `catalog_item_embeddings` is still populated.

**Decision:** keep. Cost of populating is negligible (a single field write per enrichment), and dropping the column would force a migration + a downstream impact audit (response payloads, CSV exports, ops dashboards may all reference `occasion_fit`). The cleaner schema is not worth the churn until we have a concrete second use for the schema slot. Revisit only if there's a load-bearing reason.

---

## Per-turn cost re-baseline (May 6, 2026)

**Status:** queued · **Cost:** dev time only · **Risk:** low

Pre-PR-#81 baseline was $0.029/turn (gpt-5-mini composer + gpt-5.5 planner). Post-sweep (PR #81 → #101) T13 came in at **$0.208/turn** when 3 outfits ship — driven by:

| Call | Cost | % of turn | Notes |
|---|---|---|---|
| virtual_tryon × 3 (Gemini) | $0.117 | 56% | Single biggest line; sequential renders. |
| outfit_architect (gpt-5.4) | $0.053 | 25% | +56% vs pre-#90 ($0.034) due to ~6K extra input tokens from episodic memory. |
| outfit_composer (gpt-5.4) | $0.036 | 17% | New since #81 — was ~$0.0015 on gpt-5-mini. |
| outfit_rater (gpt-5-mini) | $0.001 | 1% | Smallest line; 6 dims on 1/2/3 keeps tokens tight. |
| copilot_planner (gpt-5-mini) | $0.001 | 1% | |

Two angles to attack if the cost panel says we need to:
- **Try-on render count.** 3 sequential Gemini renders dominate. Render only the top 1 inline and over-render lazily on a "Get a deeper read" CTA — but that CTA was removed in V2; revisit only if the cost lever justifies bringing it back.
- **Architect prompt size.** Episodic memory adds ~3K tokens per power user (Panel 17). Tighten `_RECENT_USER_ACTIONS_MAX` from 30 → 20 if Panel 17 p95 stays >14K.

**Trigger to act:** the LLM-cost-budget alert fires (currently $500/day — see PR #94), OR Panel 17 p95 stabilises above 14K input tokens.

---

## Phase out `archetypal_preferences` from the composer

**Status:** queued · **Cost:** small · **Risk:** low

Post-PR-#89 the rater no longer reads `archetypal_preferences` — past likes/dislikes flow upstream through the architect's episodic memory (`recent_user_actions`, PR #90). The composer still reads it as a **soft preference** ("when the user has disliked an attribute at least twice, prefer to avoid it" — see `prompt/outfit_composer.md`). This is the last consumer of the aggregate signal.

Two ways to clean up:
1. **Drop the soft preference from the composer**, fall back entirely on episodic memory at the architect (which biases retrieval queries). Smallest code change; bet is the architect's bias is enough.
2. **Switch the composer to also read `recent_user_actions`** (the raw 30-day timeline, not the aggregate). Symmetric with the architect; lets the composer reason on context-dependent patterns the same way.

**Trigger to act:** if (a) Panel 18 (rater unsuitable rate) holds <5% over a stable post-#101 week — meaning episodic memory at the architect is producing acceptable retrieval + composer item selection without needing the aggregate signal — or (b) the `aggregate_archetypal_feedback` repo method becomes a maintenance burden (it has its own catalog_enriched hydration that overlaps with `list_recent_user_actions`).

---

## Hard cap on composer outfit count at the schema level

**Status:** queued · **Cost:** trivial (~5-line schema change + 1 test) · **Risk:** none

The composer's "up to 10 outfits" is enforced **conventionally** via the prompt (`prompt/outfit_composer.md:3, 20`); the JSON schema does not carry `maxItems: 10` on the `outfits` array. Production usually sees 6–8 outfits per turn (T13: 6) so the cap is honoured today, but a future prompt tweak that drops the "up to 10" copy would silently lift the ceiling and the parser would happily accept N outfits.

Two-line fix: add `"maxItems": 10` to the `outfits` array property in `_build_composer_json_schema` (LLM physically can't emit an 11th under strict structured output), plus a parser-level `kept[:10]` belt against future schema-rule changes.

**Trigger:** any prompt edit to `outfit_composer.md` that touches the "up to 10 outfits" line, OR a single production turn observed with >10 outfits in `tool_traces.composer_decision`.

---

## R7 calibration replay — once 7 days of post-#101 traffic accumulate

**Status:** queued · **Cost:** ~½ dev day · **Risk:** none (offline replay)

PR #101 shifted the rater from 4 dims on 0–100 to 6 dims on 1/2/3. Threshold moved 60 → 50 to land on "every dim is at least neutral". The new bands need empirical validation:

1. **Panel 18 baseline.** Pull 7 days of `tool_traces.rater_decision` post-#101 and compute the steady-state `unsuitable=True` rate. Healthy band per OPERATIONS.md is 0–5%; needs real numbers to confirm.
2. **Panel 16 baseline shift.** PR #89 + #101 should have lowered `catalog_low_confidence` rate vs the pre-#89 baseline (when the rater veto was driving outfits below threshold). Compare 7-day rolling rates pre + post.
3. **Score distribution check.** Are sub-scores actually using all three values {1, 2, 3}? If 95% of outputs are 2s, the prompt's calibration anchors aren't biting and the scale collapsed back to a binary. Histogram the sub-score values per dim to confirm.
4. **Spot-check 50 turns by hand.** Read each outfit's six sub-scores + rationale and check they add up to a coherent stylist judgment. Catches drift the per-dim aggregates miss.

**Trigger:** ~7 days post-#101 (around 2026-05-12).

**Acceptance:** `unsuitable_pct` <5% sustained, `catalog_low_confidence_pct` no worse than pre-#89, sub-score distributions show meaningful spread across {1, 2, 3} on every dim.

---

## Architect quality replay — style-preference removal validation (May 2026)

**Status:** queued · **Cost:** ~1 dev day + ~$1 in OpenAI calls · **Risk:** none (offline replay)

The May 2026 style-preference removal stopped feeding `primaryArchetype` / `secondaryArchetype` / `formalityLean` / `patternType` to the architect, replacing the archetype-based "third direction stretch" logic with a `risk_tolerance`-driven scale and adding new pattern-scale + pattern-contrast rules grounded in `FrameStructure` + `SkinHairContrast`. The plan called for a PR-0 empirical replay against historical production turns to validate that quality holds — this was deferred at merge because staging only had 2 `composer_decision` rows in 30 days (insufficient sample).

**To do once production traffic accumulates:**

Build `ops/scripts/architect_replay_eval.py` that:
1. Pulls ~100 historical recommendation turns from `tool_traces.composer_decision` joined to the architect input from `model_call_logs.request_json`.
2. Re-runs `OutfitArchitect.plan(...)` with the OLD payload (carrying the now-deleted `style_preference` block) vs the NEW payload (carrying only `risk_tolerance` + `recent_user_actions`).
3. Diffs the two architect outputs per turn:
   - `directions[]` count + `direction_type` distribution
   - `query_document` text similarity (jaccard or embedding cosine)
   - `hard_filters` set differences
   - `retrieval_count`
4. Emits a markdown report sliced by intent (occasion_recommendation / pairing_request) and by whether the user had high vs low style-preference completeness in the OLD model.

**Trigger to act:** when production has 100+ recommendation turns post-rollout, OR if the `catalog_low_confidence` rate spikes meaningfully — that would be a signal the new architect output is producing weaker queries.

**Acceptance criteria for "quality holds":** median turn produces ≥0.85 cosine similarity on query_document text, AND identical hard_filter set on ≥80% of turns. If those hold, the removal is validated.

---

## Sub-3s latency: distillation-ready trace schema (P0 — unblocks all distillation)

**Status:** queued · **Cost:** ~3 dev days · **Risk:** low

Pre-tryon latency today is 64s (planner 7.1s + architect 27.6s + retrieval 2.9s + composer 13.3s + rater 13.4s). Distilling any of those stages onto smaller/faster models requires supervised data, but `tool_traces` today captures decisions, not the input/output/latency/quality tuples a fine-tuning pipeline needs.

Add a `traces` table: `(turn_id, stage, model, input_hash, input_blob, output_blob, latency_ms, quality_signal, tenant_id NOT NULL DEFAULT 'default', created_at)`. Wire `record_stage_trace()` into the five stage call sites in [orchestrator.py](modules/agentic_application/src/agentic_application/orchestrator.py). Backfill from `session_context_json` where possible.

Multi-tenancy hook: `tenant_id` column included now to avoid a backfill migration when Shopify multi-tenancy lands.

**Trigger:** start immediately. Every distillation task downstream is gated on ≥10K traces per stage; the data flywheel must run during the recipe-cache build, not after.

**Acceptance:** every recommendation turn writes one row per stage; sample query pulls (input, output, latency, quality) tuples ready for fine-tuning.

---

## Sub-3s latency: per-stage budget caps + graceful degradation (P0)

**Status:** queued · **Cost:** ~2 dev days · **Risk:** low

Today architect at 27.6s and rater at 13.4s are hard floors — nothing fires when a stage runs long, and architect failure returns an error to the user (per APPLICATION_SPECS.md "architect failure returns error to user (no silent degradation)"). A budget cap per stage immediately bounds worst-case pre-tryon latency, even before the recipe cache lands.

Wrap each stage in `process_turn` ([orchestrator.py](modules/agentic_application/src/agentic_application/orchestrator.py)) with a timeout + deterministic fallback:
- Planner over budget → last-turn intent or default.
- Architect over budget → default occasion shell (precursor to recipe lookup; even a hardcoded "office_casual" plan beats 27s).
- Composer over budget → top-K from retrieval with diversity.
- Rater over budget → cheap deterministic score (cosine to archetype centroid + palette match).

Initial budgets: planner 1.5s, architect 4s, composer 2s, rater 1.5s. Tune from p50 traces once Task above lands.

**Trigger:** start in parallel with trace work. Caps the worst-case pre-tryon latency immediately, before any cache work.

**Acceptance:** synthetic slow-stage tests confirm fallback fires at budget; production p99 pre-tryon time reflects budget ceilings; zero hard errors on stage timeout.

---

## Sub-3s latency: recipe library + offline bootstrap (P1 — primary lever)

**Status:** queued · **Cost:** ~3 dev weeks + $10–20K LLM spend · **Risk:** medium

The single biggest lever for pre-tryon latency. A recipe is a catalog-independent outfit specification: `(intent, archetype, occasion, season) → [slot_specs]`, where each slot is "structured navy blazer, formality 3-4, fit:tailored" — never a SKU. Recipes are precomputed offline; at request time the hot path looks one up and resolves slots to products via the feasibility index (next task), bypassing the LLM architect + composer entirely.

Build:
1. New module `modules/agentic_application/src/agentic_application/recipes/` (schema, library, lookup).
2. Postgres `recipes` table: `(recipe_id, intent, archetype, occasion, season, style_axis, slot_specs JSONB, tenant_id NOT NULL DEFAULT 'default', created_at)`.
3. Bootstrap script `ops/scripts/generate_recipes.py` runs the current slow architect + composer pipeline against a synthetic intent grid (~5–10K combinations of intent × archetype × occasion × season) and normalizes outputs into recipe rows.

Multi-tenancy hook: recipes are catalog-independent by design; the same library serves any tenant whose catalog can resolve the slots.

**Trigger:** P1, after trace pipeline + budget caps ship. Bootstrap should run once trace logging is live so the bootstrap itself populates the trace table.

**Acceptance:** ≥5K recipes covering top intent × archetype × occasion combos; `(intent, archetype, occasion, season)` lookup returns a recipe in <50ms.

---

## Sub-3s latency: per-recipe feasibility index (P1)

**Status:** queued · **Cost:** ~1.5 dev weeks · **Risk:** low

A recipe is useless without knowing which catalog products fill its slots. Precompute, per `(recipe_id, slot_index)`, the top-K `catalog_enriched` product_ids ranked by slot-spec match. Refresh on `catalog_enriched` change (today: enrichment job; future: Shopify webhooks).

Build:
1. New module `modules/catalog/src/catalog/feasibility/` (builder + lookup).
2. Postgres `recipe_slot_candidates` table: `(recipe_id, slot_index, product_id, score, tenant_id NOT NULL DEFAULT 'default')`, indexed on `(recipe_id, slot_index, score DESC)`.
3. Builder embeds each slot's spec text, runs cosine search against `catalog_item_embeddings`, stores top-50 product_ids with scores per slot.

**Trigger:** P1, immediately after recipe library is populated. Required for hot-path assembly.

**Acceptance:** every recipe has top-50 candidates per slot; `(recipe_id, slot_index) → ranked product_ids` returns in <20ms.

---

## Sub-3s latency: hot-path router and assembly (P1 — sub-3s wins here)

**Status:** queued · **Cost:** ~2 dev weeks · **Risk:** medium

The actual mechanism that produces sub-3s. New module `modules/agentic_application/src/agentic_application/hot_path.py`. `process_turn` becomes a router: hot path on cache hit; fall through to the existing orchestrator (now the cold path) on miss.

Hot-path flow:
1. Fast intent classifier → `(intent, archetype, occasion, season)` keys (next task).
2. Recipe lookup → recipe_id.
3. Feasibility lookup → product_ids per slot.
4. Diverse-sample assembly → 6 outfit candidates via cheap deterministic compat (item-attribute pair scoring).
5. Existence verification → confirm product_ids still in `catalog_enriched`.
6. Lightweight rater → deterministic 6-axis score (cosine to archetype centroid + palette match + role coverage).
7. Return cards.

Cache miss: route to existing orchestrator, wrap result, write back into recipe library on success so future similar turns hit cache.

**Trigger:** P1, after recipe + feasibility tables populate.

**Acceptance:** cache hit rate ≥40% on real or replayed traffic; pre-tryon p95 <3s on cache hits; cache miss fallback to cold path is transparent.

---

## Sub-3s latency: fast intent classifier (P1)

**Status:** queued · **Cost:** ~3 dev days (gpt-5-mini path) or ~3 dev weeks (distilled encoder) · **Risk:** low

The 7.1s copilot_planner is overkill for what's essentially a ~10-class classifier with slot extraction. Two paths:

- **A. gpt-5-mini with prompt caching.** OpenAI prompt caching cuts ~90% off cached prefix tokens; the planner's stable system prompt lands a ~7s call at ~500–800ms with no model change. Ships in days.
- **B. Fine-tuned encoder.** ~50ms on CPU, no API cost. Needs ~5K labeled traces from the trace pipeline above.

Ship A in P1 alongside the recipe cache; migrate to B in P2 once traces accumulate.

**Trigger:** P1, parallel to hot-path router. Router needs intent classification at the front.

**Acceptance:** planner stage p95 <800ms (Path A) or <100ms (Path B); intent quality matches current planner on held-out replay.

---

## Sub-3s latency: distilled rater (P2 — cold path)

**Status:** queued · **Cost:** ~3 dev weeks + ~$2K compute · **Risk:** medium

Cold-path stage with the cleanest distillation profile — fixed 6-axis schema, structured output, abundant supervision in trace logs. Fine-tune a 3–8B model (Qwen2.5-7B or similar, single A10/L4 serving) on accumulated rater traces. Confidence-gated fallback to gpt-5-mini on low confidence.

New module `modules/style_engine/distilled/`. Serving via vLLM or equivalent.

**Trigger:** P2, after ≥10K rater traces accumulate (~2–3 months post-trace-pipeline launch).

**Acceptance:** distilled rater p95 <600ms; ≥90% agreement with gpt-5-mini on held-out replay; no quality regression on 6-axis hexagon vs current production.

---

## Sub-3s latency: graph composer (P2 — cold path)

**Status:** queued · **Cost:** ~4 dev weeks · **Risk:** medium-high

The 13.3s composer is the slowest survivable cold-path stage. Replace with a learned compatibility graph + top-K diverse sampling.

Build:
1. Pairwise compat training set from rater traces (`(item_a, item_b) → compat_score` from 6-axis aggregate).
2. Compat model: LightGBM over enrichment attributes, or small MLP over item embeddings + attribute features.
3. Catalog compat projection (single tenant today, tenant_id-aware shape).
4. Graph composer: top-K search with diversity constraints (max 1 outfit per direction, palette spread, role coverage).

Multi-tenancy hook: compat model can train on aggregated traces across tenants (with opt-out) when platform goes multi-tenant.

**Trigger:** P2, after distilled rater ships (compat training depends on rater trace volume).

**Acceptance:** graph composer p95 <300ms; human eval on 100 held-out turns shows quality on par with LLM composer; cold-path total pre-tryon p95 <5s.

---

## Try-on perceived latency: SSE streaming (P3 — deferred per May 6 plan)

**Status:** parked · **Cost:** ~1 dev week · **Risk:** low

Originally proposed as a P0 perceived-latency win (cards in <3s, try-ons stream over the next 10–30s) but **deprioritized: pre-tryon latency reduction (P0–P2 above) takes precedence per the May 6 plan revision.** This work addresses only perceived end-to-end latency, not the actual pre-tryon pipeline.

When picked up: new endpoint `GET /v1/turns/{turn_id}/tryon/stream` (SSE) streams images as they render; cards return immediately with placeholders. Frontend updates in [ui.py](modules/agentic_application/src/agentic_application/ui.py) consume the stream.

**Trigger:** after pre-tryon p95 is reliably <3s in production (i.e., P0 + P1 stable), or if user perceived-latency complaints surface earlier.

**Acceptance:** cards visible <3s; try-on images stream in over the following 10–30s.

---

## Multi-tenancy: design hooks while building the latency stack (P3 — deferred, but apply now)

**Status:** parked (guidance only — applies to current work) · **Cost:** trivial if done now; expensive to retrofit · **Risk:** low

Multi-tenancy is deferred from this latency push, but five hooks are zero-cost now and save a painful migration when Shopify multi-tenancy lands:

1. Every new table (`traces`, `recipes`, `recipe_slot_candidates`, future compat tables) includes `tenant_id TEXT NOT NULL DEFAULT 'default'`.
2. Recipes stay catalog-independent ("structured navy blazer, formality 3-4" — never product_ids). Keeps the recipe library reusable across tenants.
3. Prompts stay catalog-neutral (no "Aura's catalog" or brand-specific framing). Lets per-tenant prompt overlays slot in cleanly later.
4. Logs and traces tag with `tenant_id` from day one.
5. **Do not** migrate user-scoped tables (`users`, `conversations`, `feedback_events`) — that's a real migration owed when multi-tenancy actually ships, not now.

**Trigger:** apply continuously to all P0–P2 work above. Items 1–4 are constraints on current task implementation; item 5 is a guard against premature scope.

**Acceptance:** no new table created without `tenant_id`; no recipe references SKUs; no prompt references catalog identity; user-scoped tables left alone.

---

## Try-on perceived latency: pre-warm renders for predicted recipes (P3 — sub-task of SSE streaming)

**Status:** parked · **Cost:** ~1 dev week + ongoing Gemini compute · **Risk:** low

Try-on cache key today is `(user_image, garment_id_set)` — a hit only happens when the same user re-requests the exact same outfit. Two users asking for the same office-classic outfit each pay full freight (~20s + ~4¢ each). At any scale this means try-on can never sit inside the 3s response budget on its own.

**The pragmatic fix** (the only path that doesn't require a new try-on model): predict each user's likely outfits from their profile + recent activity, render those try-ons in the background, and let the hot path check the try-on cache *before* returning. When the recipe the hot path picks matches a pre-rendered outfit for that user → try-on is an instant cache hit and ships inside the 3s budget. When it misses → fall back to SSE streaming (the parent P3 task).

Build:
1. Pre-warm worker `ops/scripts/tryon_prewarm.py` — for each active user, pull their top-N most-likely (intent, occasion, archetype) recipe cells based on profile + `recent_user_actions`, resolve to garment sets via the feasibility index, render Gemini try-on, write to the existing try-on cache.
2. Hot path checks try-on cache before returning cards; cache hit → inline image; miss → return cards with placeholders and stream via SSE.
3. Per-user pre-warm budget cap (e.g., max 10 renders/user/day) to prevent runaway Gemini cost.
4. Ranking signal: start with a heuristic (top-5 cells weighted by frequency in `recent_user_actions`); upgrade to a small `(user, recipe) → likelihood` model later once trace data accumulates.

**Why not the cross-user fan-out alternative.** A theoretically cheaper approach is "render once per garment set, composite onto each user" — Gemini cost amortizes across all users requesting the same outfit. But `gemini-3.1-flash-image-preview` renders garment-on-body in a single forward pass; you can't separate the rendered garment from the body it was rendered on without losing the body-conforming drape that makes the output look right ([tryon_service.py:18–44](modules/agentic_application/src/agentic_application/services/tryon_service.py:18)). Doing this properly requires a two-stage diffusion pipeline (research project) or classical CV warping (visible quality regression). Park as a "if try-on cost becomes a wall at scale" lever; not actionable today.

**Trigger:** after P1 recipe cache + feasibility index are in production (predictions need a recipe taxonomy to point at) AND SSE streaming is live (provides the fallback on cache miss).

**Acceptance:** ≥50% of try-on requests hit the pre-warm cache on real traffic; pre-warm cost stays under the per-tenant Gemini budget; no quality regression vs request-time renders (same model, same cache table).
