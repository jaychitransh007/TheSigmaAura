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
---

# Sub-3s latency push (May 6 revision — pre-launch / launch / post-launch)

The original P0/P1/P2 sequencing assumed the slow pipeline would ship to friendly users for trace collection, then optimize. That breaks because 60–70s pre-tryon latency makes shipping unviable. Replaced with **pre-launch (offline cache build) → launch (closed alpha, narrow scope) → post-launch (cold-path optimization)** ordering.

Cache (recipe library) is the launch unlock, NOT fine-tuning. The slow pipeline is the teacher; the cache is the precomputed lookup. Fine-tuning is a post-launch optimization for the rare cache miss.

---

## Pre-launch Step 1 — Trace schema + writer

**Status:** ✓ **shipped May 6, 2026 (PR #109)** · **Cost:** ~½ dev day · **Risk:** low

Implementation note: while surveying the codebase, I confirmed that `model_call_logs` already exists but stores only hand-built summaries in `request_json` (the architect logs `{gender, occasion, message, is_followup}` — not the 14K-token actual prompt). That's fine for cost/latency analytics but unusable for fine-tuning. Resolution: a separate `distillation_traces` table coexists with `model_call_logs`, captures full I/O at every stage call site, and never samples bodies. The original "traces unblock distillation" framing still holds — this is just the right table shape.

What landed:
- Migration `20260506120000_distillation_traces.sql` — table + 4 indexes (turn, stage, input_hash, tenant). `tenant_id TEXT NOT NULL DEFAULT 'default'` from day one (multi-tenancy hook).
- `Repositories.log_distillation_trace` — mirrors `log_tool_trace` style; reuses the same `pii_redactor`.
- `record_stage_trace` context manager in `platform_core/distillation_traces.py` — wraps a stage call, swallows writer failures so a Supabase hiccup never fails a turn. Plus `to_jsonable()` helper.
- Wired into 5 stage call sites in `orchestrator.py`: copilot_planner, outfit_architect, catalog_search, outfit_composer, outfit_rater.
- `ops/scripts/backfill_quality_signal.py` — idempotent skeleton joining traces to `feedback_events`. Manual run for now; cron is a follow-up.
- 13 unit tests in `tests/test_distillation_traces.py`. Full suite passes (471/471).

Acceptance checked: every turn writes one row per stage ✓; sample queries pull (input, output, latency) ✓; back-fill skeleton runnable manually ✓.

Follow-ups: cron-wire the back-fill script; expand `quality_signal` beyond user feedback to include downstream stage acceptance + implicit signals (these unblock once real traffic accumulates).

---

## Pre-launch Step 2 — Synthetic intent grid + profile sampling

**Status:** ✓ **shipped May 6, 2026 (PR pending)** · **Cost:** ~½ dev day · **Risk:** medium (coverage decisions)

What landed:
- `modules/agentic_application/src/agentic_application/recipes/profiles.py` — synthetic profile pool (12 archetypes × 2 genders, with first-pass coverage of all 24 base combos plus weighted sampling toward production-frequent archetypes; deterministic seed).
- `modules/agentic_application/src/agentic_application/recipes/grid.py` — curated 31-occasion taxonomy (work_mode, social_casual, night_out, formal_events, festive, beach_vacation, dating, wedding_vibes), grid enumerator, cost estimator, coverage-filter Protocol.
- `ops/scripts/generate_bootstrap_grid.py` — deterministic generator. Without `--with-coverage` runs offline; produces grid CSV + profile pool JSON + cost estimate.
- `ops/data/bootstrap_grid.csv` (5,424 cells), `ops/data/bootstrap_profile_pool.json` (75 profiles) — committed for review; regeneratable byte-identically with `--seed=42`.
- 23 unit tests covering profile determinism, grid enumeration, occasion-season exclusion, cost scaling, coverage filter caching.

**Important finding on the budget:** the original $10–20K LLM-spend estimate (and $1–2/cell rate) was off by ~20×. Actual per-cell cost from the May 6 cost re-baseline is ~$0.09/cell (architect $0.053 + composer $0.036 + rater + planner). The 5,424-cell grid estimates to **~$542 total**. This means either (a) keep the conservative budget for safety margin, or (b) expand the grid 5–10× to get richer coverage. Step 3 should make this call before kicking off the bootstrap run.

Acceptance checked: grid file enumerated and reviewed ✓ (`bootstrap_grid.csv` in `ops/data/`); coverage analysis runnable but requires Supabase access (Protocol mockable in tests, real run deferred to bootstrap pipeline); estimated cost within budget ✓ (~$542 vs $10–20K cap).

---

## Pre-launch Step 2 (original spec, kept for reference)

**Status:** superseded by the shipped version above · **Cost:** ~1 dev week · **Risk:** medium (coverage decisions)

Define which (intent × archetype × occasion × season) cells the bootstrap will populate. Coverage decisions made here dictate launch alpha scope — cells outside the grid become "we don't cover that yet" graceful refusals at launch.

Build:
1. **Intent enumeration:** primary on `occasion_recommendation` (most traffic); secondary on `pairing_request` and `garment_evaluation`; lower coverage on the tail.
2. **Archetype enumeration:** 8 style archetypes from existing taxonomy.
3. **Occasion enumeration:** ~25–40 canonical occasions curated from current `prompt/outfit_architect.md` + market research (office, wedding-guest, dinner-date, weekend-brunch, etc.).
4. **Season + climate enumeration:** 4 seasons × climate variants (humid/dry/temperate).
5. **Profile sampling:** 50–100 synthetic user profiles spanning (body_type × palette × archetype × budget) used as architect inputs during bootstrap so recipes capture profile-conditional variation.
6. **Catalog feasibility filter:** drop cells where `catalog_enriched` has <100 SKUs matching slot specs (skip "evening gowns" if you have 12).
7. **Output:** `bootstrap_grid.csv` with ~5,000–10,000 cells, cost-estimated.

**Trigger:** parallel to Step 1.

**Acceptance:** grid file enumerated and reviewed; coverage analysis confirms each cell has feasible catalog support; estimated bootstrap cost ($1–2/cell × cell count) within $10–20K budget.

---

## Pre-launch Step 3 — Recipe bootstrap runner

**Status:** queued · **Cost:** ~2 dev weeks + ~$500–$3K LLM spend (revised down from $10–20K based on Step 2 cost finding — see updated Step 2 above) · **Risk:** medium

The bootstrap. For each grid cell, run the existing slow pipeline (architect → composer) and normalize output into a recipe row.

Build:
1. New module `modules/agentic_application/src/agentic_application/recipes/` (schema, library, lookup).
2. Postgres `recipes` table: `(recipe_id, intent, archetype, occasion, season, style_axis, slot_specs JSONB, source_trace_ids UUID[], tenant_id NOT NULL DEFAULT 'default', created_at)`.
3. Bootstrap script `ops/scripts/generate_recipes.py`:
   - Iterates grid from Step 2 with concurrency (10–20 workers, rate-limit aware).
   - For each cell: synthetic user_context + occasion → `OutfitArchitect.plan()` → `OutfitComposer.compose()` → extract catalog-independent slot specs from composer output.
   - Writes recipe row + backreference to source trace IDs (for distillation later).
   - Resumable checkpoints every 100 cells.
4. Cost monitor with kill-switch at $25K spend.
5. Quality sampling: 20 random recipes per 1K generated get a manual sanity-check before continuing.

Multi-tenancy hook: recipes catalog-independent by design ("structured navy blazer, formality 3-4" — never product_ids).

**Trigger:** Steps 1 + 2 must land first.

**Acceptance:** ≥5K recipes covering high-frequency intent × archetype × occasion combos; lookup by (intent, archetype, occasion, season) returns recipe in <50ms; bootstrap traces populate the traces table.

---

## Pre-launch Step 4 — Feasibility index against current catalog

**Status:** queued · **Cost:** ~1.5 dev weeks · **Risk:** low

For each recipe slot, precompute the top-K catalog products that fill it. Without this, recipes are abstract and can't be served.

Build:
1. New module `modules/catalog/src/catalog/feasibility/`.
2. Postgres `recipe_slot_candidates` table: `(recipe_id, slot_index, product_id, score, tenant_id NOT NULL DEFAULT 'default')`, indexed on `(recipe_id, slot_index, score DESC)`.
3. Builder: embed slot spec text via existing `text-embedding-3-small`, run cosine search against `catalog_item_embeddings`, store top-50 product_ids per slot with scores.
4. Refresh: re-run on `catalog_enriched` change (manual today; webhook-driven post multi-tenant launch).
5. Coverage report: flags recipes with <10 viable candidates per slot for redesign or removal from launch grid.

**Trigger:** Step 3 must populate recipes.

**Acceptance:** every recipe has top-50 candidates per slot; lookup `(recipe_id, slot_index) → ranked product_ids` returns in <20ms; coverage report identifies slot-level gaps.

---

## Pre-launch Step 5 — Manual eval set curation

**Status:** queued · **Cost:** ~1–2 dev weeks human curation · **Risk:** low

The ground-truth set used to validate cache quality before launch. **NOT training data — eval data only.**

Build:
1. Pick 100–500 representative test queries spanning the launch grid (mix of common, edge, novel).
2. Run the slow pipeline against each, capture full outputs (architect plan + 6 composed outfits + rater scores + try-on for top 3).
3. Hand-rate each output on the same 6 axes the rater uses (occasion fit, body harmony, color harmony, archetype match, formality, statement).
4. Store as `eval_set.jsonl` versioned in repo (`tests/eval/`).
5. Eval harness `ops/scripts/eval_cache_quality.py` runs queries against the cache and diffs outputs vs eval set.

**Trigger:** parallel with Steps 3–4 (independent of cache build).

**Acceptance:** ≥100 hand-rated cases with full ratings; eval harness produces a per-case quality-delta report (cache vs slow pipeline); inter-rater agreement spot-checked on ≥20 cases by a second reviewer.

---

## Pre-launch Step 6 — Hot-path router and assembly

**Status:** queued · **Cost:** ~2 dev weeks · **Risk:** medium

The mechanism that produces sub-3s. New module `modules/agentic_application/src/agentic_application/hot_path.py`. `process_turn` becomes a router: hot path on cache hit; fall through to existing orchestrator (cold path) on miss.

Hot-path flow:
1. Fast intent classifier → `(intent, archetype, occasion, season)` keys (Step 7).
2. Recipe lookup → recipe_id.
3. Feasibility lookup → product_ids per slot.
4. Diverse-sample assembly → 6 outfit candidates via cheap deterministic compat (item-attribute pair scoring).
5. Existence verification → confirm product_ids still in `catalog_enriched`.
6. Lightweight rater → deterministic 6-axis score (cosine to archetype centroid + palette match + role coverage).
7. Return cards.

Cache miss → cold path (existing orchestrator) + write-back (Launch Step 2).

**Trigger:** Steps 3 + 4 must be populated.

**Acceptance:** pre-tryon p95 <3s on cache hits; cache miss fallback to cold path is transparent; deterministic rater agrees with LLM rater ≥85% on Step 5 eval set.

---

## Pre-launch Step 7 — Fast intent classifier

**Status:** queued · **Cost:** ~3 dev days · **Risk:** low

The 7.1s copilot_planner is the hot-path entry point. Replace with gpt-5-mini + prompt caching for ~500–800ms classification, no model change. Distillation to a fine-tuned encoder (~50ms) deferred to post-launch.

Build:
1. Move planner system prompt to a stable cacheable prefix.
2. Switch to gpt-5-mini with `prompt_cache_key` set per (system_prompt_version, intent_registry_version).
3. Wire as the entry point of the hot-path router.

**Trigger:** parallel to Step 6.

**Acceptance:** planner stage p95 <800ms; intent classification ≥90% agreement with current planner on Step 5 eval set.

---

## Pre-launch Step 8 — Quality validation gate

**Status:** queued · **Cost:** ~3 dev days · **Risk:** low

Before launch, run the eval harness against the full hot-path. Validates cache outputs match slow-pipeline outputs on quality dimensions.

Build:
1. Run hot-path against the 100–500 eval queries from Step 5.
2. Diff per-axis ratings (cache outfit ratings vs hand-rated ground truth).
3. Generate launch-readiness report: per (intent × occasion) cell, agreement rate.
4. Cells below threshold (e.g., <80% per-axis agreement) excluded from the launch alpha scope — those cells fall back to the cold path with refusal UI (Launch Step 3).

**Trigger:** Steps 3, 4, 5 must be done.

**Acceptance:** report identifies launch-ready cells; ≥80% of high-frequency cells pass quality gate; failing cells excluded from launch grid; report committed to repo for audit.

---

## Launch Step 1 — Per-stage budget caps + cold-path safety net

**Status:** queued (Launch phase) · **Cost:** ~2 dev days · **Risk:** low

Wraps the cold path that's still there for cache misses. Originally Pre-launch P0; moved to Launch because the slow pipeline is offline-only during pre-launch (no users yet).

Wrap each stage in `process_turn` with timeout + deterministic fallback:
- Architect over budget → use closest-matching cached recipe via fuzzy intent/occasion match.
- Composer over budget → top-K from retrieval with diversity.
- Rater over budget → cheap deterministic score (cosine to archetype centroid + palette match).

Initial budgets: planner 1.5s, architect 4s, composer 2s, rater 1.5s. Tune from p50 traces.

**Trigger:** before opening alpha to users.

**Acceptance:** synthetic slow-stage tests confirm fallback fires at budget; zero hard errors on stage timeout; cold-path total p95 bounded by sum of budgets (~9s).

---

## Launch Step 2 — Cold-path write-back to recipe library

**Status:** queued (Launch phase) · **Cost:** ~3 dev days · **Risk:** low

When the hot path misses and the cold path produces a successful outfit, normalize the cold-path output into a recipe and insert it into the library. Future similar requests hit the cache.

Build:
1. Recipe-extraction logic: takes architect plan + composed outfits → catalog-independent slot specs (same normalization as Step 3 bootstrap).
2. Write to `recipes` + `recipe_slot_candidates` tables.
3. Quality gate: only write back if cold-path output passed the rater threshold (current `_RECOMMENDATION_FASHION_THRESHOLD`).
4. Source attribution: tag with `source='cold_path'` so post-launch analysis can compare bootstrap vs organic recipes.

**Trigger:** Launch Step 1 done.

**Acceptance:** cold-path successes write back to cache; subsequent identical requests hit the cache; organic-vs-bootstrap recipe count tracked in dashboard.

---

## Launch Step 3 — Out-of-scope graceful refusal UI

**Status:** queued (Launch phase) · **Cost:** ~3 dev days · **Risk:** low

For requests outside cached scope (where cold-path quality gate fails or no recipe match exists), the UI must respond honestly rather than serve a slow degraded result. Critical for protecting the alpha experience.

Build:
1. Cold-path quality gate: predicted match score below threshold → refusal path.
2. Refusal copy + alternative suggestions in [ui.py](modules/agentic_application/src/agentic_application/ui.py): "Aura is still learning [X] occasions — try [Y] instead" with quick-reply chips for in-scope alternatives.
3. Telemetry: refusal events logged with intent + occasion so post-launch grid expansion targets actual misses.

**Trigger:** before opening alpha.

**Acceptance:** out-of-scope queries show refusal UI, not slow degraded outfits; refusals logged + dashboarded; in-scope alternative chips correctly map to launch grid cells.

---

## Launch Step 4 — Closed alpha onboarding + dashboard

**Status:** queued (Launch phase) · **Cost:** ~1 dev week · **Risk:** medium (UX decisions)

Define alpha scope and observability for the first 5–15 friendly users.

Build:
1. **Launch grid:** cells from Pre-launch Step 8 quality gate that pass.
2. **Onboarding:** existing flow + a "what Aura covers" page setting expectations on supported intents/occasions.
3. **Feedback collection:** existing per-card thumbs + textarea — no new build.
4. **Internal dashboard:** cache hit rate, cold-path rate, refusal rate, p95 pre-tryon latency, user feedback per cell.
5. **Manual user review cadence:** weekly review of refusals + low-rated outputs to drive grid expansion.

**Trigger:** Launch Steps 1–3 done.

**Acceptance:** 5–15 alpha users onboarded; production traces accumulating; dashboard live; cache hit rate ≥60% on alpha traffic by week 2; weekly review producing concrete grid-expansion candidates.

---

## Post-launch — Distilled rater (cold-path optimization)

**Status:** queued (Post-launch) · **Cost:** ~3 dev weeks + ~$2K compute · **Risk:** medium

Cold-path stage with cleanest distillation profile — fixed 6-axis schema, structured output, abundant supervision. Fine-tune a 3–8B model (Qwen2.5-7B or similar, single A10/L4 serving) on accumulated rater traces (synthetic from Pre-launch Step 3 + real from Launch). Confidence-gated fallback to gpt-5-mini.

New module `modules/style_engine/distilled/`. Serving via vLLM or equivalent.

**Trigger:** ≥10K rater traces accumulated (synthetic bootstrap counts; ~immediately after Pre-launch Step 3 completes for v1, refined post-launch with real traces).

**Acceptance:** distilled rater p95 <600ms; ≥90% agreement with gpt-5-mini on held-out replay; no quality regression on Pre-launch Step 5 eval set.

---

## Post-launch — Graph composer (cold-path optimization)

**Status:** queued (Post-launch) · **Cost:** ~4 dev weeks · **Risk:** medium-high

The 13.3s composer is the slowest survivable cold-path stage. Replace with learned compatibility graph + top-K diverse sampling.

Build:
1. Pairwise compat training set from rater traces (`(item_a, item_b) → compat_score` from 6-axis aggregate).
2. Compat model: LightGBM over enrichment attributes, or small MLP over item embeddings + attribute features.
3. Catalog compat projection (single tenant today, tenant_id-aware shape).
4. Graph composer: top-K search with diversity constraints (max 1 outfit per direction, palette spread, role coverage).

Multi-tenancy hook: compat model can train on aggregated traces across tenants (with opt-out) when platform goes multi-tenant.

**Trigger:** after distilled rater ships (compat training depends on rater output volume).

**Acceptance:** graph composer p95 <300ms; human eval on 100 held-out turns shows quality on par with LLM composer; cold-path total pre-tryon p95 <5s.

---

## Post-launch — SSE try-on streaming

**Status:** parked (Post-launch) · **Cost:** ~1 dev week · **Risk:** low

Cards return immediately with try-on placeholders; new endpoint `GET /v1/turns/{turn_id}/tryon/stream` (SSE) streams images as they render. Frontend updates in [ui.py](modules/agentic_application/src/agentic_application/ui.py) consume the stream.

Addresses *perceived* end-to-end latency (cards in <3s, try-ons follow over 10–30s); not part of the pre-tryon push.

**Trigger:** after pre-tryon p95 reliably <3s in production (Pre-launch + Launch stable), or if user perceived-latency complaints surface earlier.

**Acceptance:** cards visible <3s; try-on images stream in over the following 10–30s.

---

## Post-launch — Pre-warm renders for predicted recipes

**Status:** parked (Post-launch — sub-task of SSE streaming) · **Cost:** ~1 dev week + ongoing Gemini compute · **Risk:** low

Predict each user's likely outfits from profile + recent activity, render try-ons in the background, write to existing try-on cache. Hot path checks try-on cache before returning cards; hit → inline image; miss → SSE streaming fallback. The path to try-on inside the 3s budget on cache hit.

Build:
1. Pre-warm worker `ops/scripts/tryon_prewarm.py` — for each active user, pulls their top-N most-likely (intent, occasion, archetype) recipe cells based on profile + `recent_user_actions`, resolves to garment sets via the feasibility index, renders Gemini try-on, writes to the existing try-on cache.
2. Hot-path tryon cache check before returning cards.
3. Per-user pre-warm budget cap (max 10 renders/user/day) to prevent runaway Gemini cost.
4. Heuristic ranking initially (top-5 cells by `recent_user_actions` frequency); upgrade to a small `(user, recipe) → likelihood` model later.

**Why not cross-user fan-out.** "Render once per garment set, composite onto each user" amortizes Gemini cost across users requesting the same outfit. But `gemini-3.1-flash-image-preview` renders garment-on-body in a single forward pass; can't separate the rendered garment from the body without losing body-conforming drape ([tryon_service.py:18–44](modules/agentic_application/src/agentic_application/services/tryon_service.py:18)). Doing this properly requires a two-stage diffusion pipeline (research project) or classical CV warping (visible quality regression). Park as a "if try-on cost becomes a wall at scale" lever; not actionable today.

**Trigger:** after Pre-launch Steps 3 + 4 (recipe + feasibility) AND SSE streaming live.

**Acceptance:** ≥50% of try-on requests hit the pre-warm cache on real traffic; pre-warm cost stays under per-tenant Gemini budget; no quality regression vs request-time renders.

---

## Cross-cutting — Multi-tenancy data hooks

**Status:** parked (guidance applied to all Pre-launch + Launch work) · **Cost:** trivial if done now; expensive to retrofit · **Risk:** low

Multi-tenancy is deferred from this latency push, but five hooks are zero-cost now and save a painful migration when Shopify multi-tenancy lands:

1. Every new table (`traces`, `recipes`, `recipe_slot_candidates`, future compat tables) includes `tenant_id TEXT NOT NULL DEFAULT 'default'`.
2. Recipes stay catalog-independent ("structured navy blazer, formality 3-4" — never product_ids). Keeps the recipe library reusable across tenants.
3. Prompts stay catalog-neutral (no "Aura's catalog" or brand-specific framing). Lets per-tenant prompt overlays slot in cleanly later.
4. Logs and traces tag with `tenant_id` from day one.
5. **Do not** migrate user-scoped tables (`users`, `conversations`, `feedback_events`) — that's a real migration owed when multi-tenancy actually ships, not now.

**Trigger:** apply continuously to all Pre-launch + Launch work above.

**Acceptance:** no new table created without `tenant_id`; no recipe references SKUs; no prompt references catalog identity; user-scoped tables left alone.
