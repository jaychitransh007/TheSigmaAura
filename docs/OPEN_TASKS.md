# Open Tasks

This file is the running list of known follow-ups: not blocking any release today, but worth tracking so they don't get lost. Each entry is a one-paragraph brief — enough to remember the context, not a full plan.

When a task is picked up, replace the brief with a link to the PR/branch. When it's done, delete the entry (the git history of this file is the audit trail).

For per-PR record of what's already shipped, see `RELEASE_READINESS.md` § Recently Shipped.

The bottom half of this file is the **Sub-3s latency push** — the anchor execution plan we work from. All operations and development going forward thread through that plan.

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
- **Architect prompt size.** Episodic memory adds ~3K tokens per power user (Panel 17). Tighten `_RECENT_USER_ACTIONS_MAX` from 30 → 20 if Panel 17 p95 stays >14K. (This is now also Phase 3.4 of the latency push below.)

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

# Sub-3s latency push — phased execution plan

**The anchor document for the latency-reduction work.** Replaces the prior pre-launch / launch / post-launch framing with a 7-phase execution plan, each with explicit test gates. We test query response after every phase before progressing.

## Status as of 2026-05-07

| Phase | Status | Notes |
|---|---|---|
| Phase 1 — Operational quick wins | ✅ **SHIPPED + verified** | Rater parallelization, retrieval RPC fix, planner shadow infra (dormant), gpt-5.4 → gpt-5.2 architect/composer swap. ~6s saved per turn. |
| Phase 2 — Caching layer | ✅ **SHIPPED + applied to staging** | All 4 migrations live on Aura-Staging. Hit rate jumped from ~0% (non-deterministic planner output) toward the design target as Phase 4.7+4.11 made engine inputs canonical. |
| Phase 3 — Prompt compression | ⏸ Not started | ~1.5 weeks. Realistic ~10s win on architect, ~7s on composer. **Mostly moot for engine-accepted turns** (engine path has no architect LLM call); still relevant for the LLM-fallback path. |
| Phase 4 prep (4.1, 4.4, 4.5) | ✅ **SHIPPED** | Composition semantics spec, bootstrap grid YAML loader, MIGRATED prompt markers. |
| Phase 4.7 — Engine implementation | ✅ **SHIPPED** (PR #149) | 6 sub-PRs (4.7a-f) bundled: yaml_loader, reduction, relaxation, engine, render, worked-example tests. Architect stage drops 19s → ~0ms on engine-accepted turns. Verified end-to-end with confidence=1.0 on a real staging query. |
| Phase 4.8 — Quality validator | ✅ **Framework SHIPPED** (PR #149) | `composition/quality.py` + `ops/scripts/composition_quality_eval.py` ready to consume Phase 4.6 eval set. Real comparison run gated on 4.6. |
| Phase 4.9 — Hot-path router | ✅ **SHIPPED** (PR #149) | `composition/router.py` with §9 fall-through gates + `extract_engine_inputs` + `is_engine_acceptable`. Wired into orchestrator. |
| Phase 4.10 — Manual flag rollout | ✅ **Manual flag SHIPPED** (PRs #149, #151) | `AURA_COMPOSITION_ENGINE_ENABLED` bool env var (default false). Bucketed-pct rollout deferred — flip flag for testing; switch to bucket-based ramp once 4.6 calibration data lands. |
| Phase 4.11 — Input canonicalization | ✅ **SHIPPED** (PR #151) | Two-phase canonicalize: exact-match against YAML keys → batched text-embedding-3-small fallback. 256-dim pre-computed embeddings (350KB JSON) co-shipped. Unblocked the engine on real planner output. |
| Phase 4.12 — Observability + operability hardening | ✅ **SHIPPED** (PRs #150, #152, #153, #154) | Pre-flag instrumentation, tool_traces constraint fix, model_call_logs origin stamping, full panel set (21-24) + runbook + `ops/scripts/turn_forensics.py`. |
| Phase 4.2 — Stylist YAML review | 🔒 Blocked on human | Paid consultant pass. Output: revised YAMLs + canonical-schema fixes. |
| Phase 4.6 — Eval set curation | 🔒 Blocked on human | 100-500 hand-curated queries with hand-rated outputs. Gates Phase 4.8 actual run, Phase 1.4 model A/B, Phase 4.10 bucketed ramp. |
| Phase 5 — Composer engine | ⏸ Not started | Same pattern as 4.7 for the composer. Composer is the next-biggest LLM cost (~$0.04/turn) and second-longest stage (~12-14s). |
| Phase 6 — Streaming delivery | ⏸ Not started | ~2-3 weeks. Cards visible <3s on cache hit, <8s on miss. UX win independent of cache hit rate. |
| Phase 7 — Distillation | ⏸ Months 4+, gated on 10K+ traces | distillation_traces table live since May 2026, accumulating data. |

**Production model lineup:** architect + composer on **gpt-5.2** (was gpt-5.4); planner + rater on **gpt-5-mini**; style advisor on **gpt-5.4**. All five env-configurable via `PLANNER_MODEL`, `ARCHITECT_MODEL`, `COMPOSER_MODEL`, `RATER_MODEL`, `STYLE_ADVISOR_MODEL`.

**See also:** `docs/composition_semantics.md` for the Phase 4 engine spec; `~/.claude/projects/.../memory/project_phase_2_4_status.md` for full handoff context.

**Foundation already shipped:**
- **PR #109** — `distillation_traces` table + `record_stage_trace` context manager wired into 5 stages (production-ready trace pipeline; full I/O captured per turn for future distillation training).
- **PR #110** — bootstrap intent grid + synthetic profile pool (5,424 cells, regenerable via `ops/scripts/generate_bootstrap_grid.py`; available as Phase 4 input). Phase 4.4: generator reads from `occasion.yaml` directly — drift vector eliminated.
- **PRs #111–#117** — 8-file style graph (~5,500 lines of Indian-urban fashion knowledge as YAMLs) covering body_frame (M+F), archetype, palette, occasion, weather, query_structure, pairing_rules. Plus 2 reusable validators (`ops/scripts/validate_style_graph_yaml.py`, `validate_style_graph_conflicts.py`).

**Phase 4 engine + operability — shipped 2026-05-06 / 2026-05-07:**
- **PR #149** — composition engine (Phases 4.7a-4.7f bundled: yaml_loader, reduction, relaxation, engine, render, worked-example tests) + Phase 4.8 quality-validator framework + Phase 4.9 hot-path router + Phase 4.10 boolean feature flag.
- **PR #150** — pre-flag observability: router decision counter, engine latency histogram, YAML gap surfacer, YAML-load-failure alert.
- **PR #151** — Phase 4.11 input canonicalization layer + canonical_embeddings.json artifact + bug fix for seasonal_color_group dual-dimension lookup.
- **PR #152** — `tool_traces` CHECK-constraint coercion fix (cache_hit / skipped_no_urls were tripping the DB; observability data was being silently dropped).
- **PR #153** — `model_call_logs.model` origin stamping (`cache` / `composition_engine` / LLM model id) so per-model rollups stay honest on engine-served turns.
- **PR #154** — comprehensive observability follow-up: 4 new metrics (canonicalize result counter, embed-duration histogram, tool_traces failure counter, attribute-status counter), 4 new dashboard panels (21-24), provenance summary plumbed into traces, OPERATIONS.md "A4: Composition engine flag-on regressions" runbook, `ops/scripts/turn_forensics.py`.

A real flag-on staging turn (`b356a1bf`, 2026-05-06) confirmed the win: architect stage 19s → ~0ms, total turn 83s → 63s, $0.04/turn cheaper, engine accepted at confidence 1.0.

These foundations remain available; their consumers (the composition engine in Phase 4, the cache layer in Phase 2) ship below.

**Strategic context:**
The composition engine (Phase 4) is the architectural endpoint that makes the YAMLs runtime-load-bearing. Phases 1–3 are operational wins that get us most of the way to sub-3s on the common path *before* the engine ships. Phases 5–7 extend the wins to the cold path and post-launch optimization.

---

## Phase 1 — Operational quick wins (P0, Week 1)

**Goal:** 64s → ~25-30s without architectural changes. All tasks are independent, parallelizable, low-risk.

### 1.1 Parallelize the rater (1 day)

Replace the single 6-outfit `outfit_rater.rate()` call with `asyncio.gather` over 6 parallel calls. Each call rates one outfit independently against the absolute 75-threshold. If composer produces 6 and we pick top 3 (rather than just gate-keep), add a tie-breaking comparative pass (~500ms) after parallel scoring. Verify in production: same scores within tolerance, latency drops from 13.4s to ~2-3s.

### 1.2 Fix retrieval (hours)

Profile the current 2.9s pgvector query — likely missing HNSW index, doing pre-filtering wrong, or re-running embedding model on query without caching. Add HNSW index if absent: `CREATE INDEX ON catalog_item_embeddings USING hnsw (embedding vector_cosine_ops)`. Cache the query embedding model in memory; don't reload per request. Move metadata filters (size, gender, in-stock) to indexed columns; apply at SQL level not Python loop. Expected: retrieval drops from 2.9s to <100ms.

### 1.3 Switch planner to fast non-reasoning model (1-2 days)

Pick provider: `claude-haiku-4-5` (recommended for conversational handling) or `gpt-4.1-nano` (cheapest). Build shadow mode: keep `gpt-5-mini` as production planner; call new model in parallel; log both. Run shadow for 2-3 days on real traffic. Manually review 50-100 disagreements; identify systematic errors. Calibrate confidence threshold based on actual error rates. Add hard-rule fallback triggers: schema validation failures, incoherent intent/action combos, multi-clause conditional messages, follow-up patterns ("more X", "different from"). Promote new model to production with fallback to `gpt-5-mini` reasoning for low-confidence. Expected: 7.1s → <500ms.

**Status (May 13 2026):** shadow infrastructure shipped. Set `AURA_PLANNER_SHADOW_MODEL=gpt-4.1-nano` (or any OpenAI model id) in the deploy env to enable. Production response is unaffected; shadow runs in a daemon thread after the production response returns and writes a structured log line via the `aura.planner.shadow` logger (`shadow_compare` event with `intent_match`, `action_match`, latency comparison, both confidences, and the user message snippet). Add `claude-haiku-4-5` shadow vendor adapter when ready to evaluate that path. Promotion to production (with low-confidence fallback to `gpt-5-mini`) blocked on 2-3 days of accumulated traffic + manual review of 50-100 disagreements.

### 1.4 Switch architect + composer to faster reasoning model (2-3 days)

A/B test `claude-sonnet-4-7` and `gemini-2.5-pro` against `gpt-5.4` on the eval set (Phase 4.6). Score outputs against held-out cases and against the existing rater's judgment as proxy. Pick winner; ship config change. Expected: architect 27.6s → ~12-15s; composer 13.3s → ~6-8s.

**Status (May 13 2026):** blocked on Phase 4.6 eval set (100-500 hand-curated representative queries). Without the eval, we'd be A/B-ing against the existing rater's judgment of itself, which closes the loop. Once Phase 4.6 lands, this task is a config-flip + comparison run. Carry into Phase 4 sequencing if Phase 4.6 ships before the rest of Phase 1 lands; otherwise gate this on eval completion.

### Phase 1 test gate

- Cold-path latency p95: ≤30s (from 64s, after 1.1 rater + 1.2 retrieval RPC ship)
- Quality on eval set: ≥95% agreement with current production (deferred until eval set exists)
- No regressions on the 50 hand-picked test queries

> **Note:** streaming card delivery (NDJSON/SSE + frontend) was previously listed here as 1.5. Moved to **Phase 6** so the Phase 1 push focuses purely on real-latency wins, not perceived-latency UX. Phase 6 now owns all streaming work (cards + try-on).

---

## Phase 2 — Caching layer (P0, Weeks 2-3)

**Goal:** cache architect + composer outputs keyed on profile cluster. Hit rate grows organically from real traffic. Replaces the bootstrap-then-cache plan from the earlier draft — runtime cache is lighter weight and learns from real distribution.

### 2.1 Define profile clustering function (2 days)

~20-50 buckets across `(body_frame_class × archetype × palette_class × gender × formality_lean)` for cache key generation. Coarse buckets to start; refine if hit rate too low. Don't over-engineer.

### 2.2 Build architect output cache (3-4 days)

Postgres table `architect_direction_cache` with JSONB output. Cache key: hash of `(intent, profile_cluster, occasion, season, formality, architect_prompt_version)`. TTL 7-14 days; invalidation on `architect_prompt_version` bump. Wrap architect call: hit → skip architect entirely; miss → run architect → cache the output. Expected hit rate: 0% on day 1, ~40% by day 7, ~70% by week 4 as cache populates.

### 2.3 Build composer output cache (2-3 days)

Same pattern as 2.2 with key: hash of `(architect_direction, retrieval_result_fingerprint, profile_cluster, composer_prompt_version)`. Fingerprint retrieval results by sorted SKU IDs (different SKUs = different cache key, prevents stale outfits).

### 2.4 Cache invalidation strategy (included in 2.2, 2.3)

Invalidate on prompt-version bump (the `architect_prompt_version`, `composer_prompt_version` in cache keys handle this automatically). No per-entry TTL needed beyond default. Keep entries for 7-14 days; refresh on access.

### 2.5 Cache hit/miss metrics dashboard (1 day)

Monitor hit rate by cluster. Surface low-hit clusters as "needs more traffic" or "clustering too granular". Track cache miss latency to confirm Phase 1 baseline holds.

### Phase 2 test gate

- Cache hit rate after 1 week of alpha traffic: ≥30%
- Cache hits: <100ms architect + composer combined latency
- Cache misses: same as Phase 1 baseline (~25s on cold path)
- Quality unchanged on cache hits (cached output = original architect/composer output)
- p95 across mixed traffic: ≤15s

---

## Phase 3 — Prompt compression (P1, Weeks 3-4, parallel with Phase 2)

**Goal:** shrink architect + composer prompts; further reduce cold-path latency on cache miss.

### 3.1 Audit architect 14K input (1 day)

Categorize tokens by source: static fashion knowledge (~3-4K, replaceable with YAML row injection), catalog summary (~2-3K, per-request keep), user profile (~1-2K, per-request keep), output format spec (~1-2K, replaceable with structured output / constrained JSON), few-shot examples (~3-4K, filter to only relevant archetype/occasion examples per request).

### 3.2 Compress architect prompt (3-4 days)

Inject relevant YAML rows for *this user* (palette for their sub-season, body_frame for their shape, archetype for their style) instead of generic prose. Use OpenAI `response_format` or Anthropic tool-calling for structured output, removing in-prompt format examples. Target: 14K → 4-5K input tokens, same model from Phase 1.4.

### 3.3 Compress composer prompt (2-3 days)

Same approach: identify static fashion knowledge in prompt, replace with `pairing_rules.yaml` injection. Filter few-shot examples to relevant ones for the architect direction.

### 3.4 Cap `_RECENT_USER_ACTIONS_MAX` 30 → 20 (hours)

Saves ~2K input tokens. Trigger if Panel 17 p95 stays >14K input tokens. (Cross-references the per-turn cost re-baseline task above.)

### Phase 3 test gate

- Architect input tokens: ≤5K
- Composer input tokens: ≤4K
- Cold-path architect latency: ~8-10s (with Phase 1.4 model swap stacked)
- Quality regression on eval set: <2%
- Cache hits (~60-70%): <100ms
- Cache misses: ~25-30s p95 (down from ~50s)

---

## Phase 4 — Composition engine for architect (P0 strategic, Weeks 5-7)

**Goal:** replace architect with YAML-driven composition on the common path. The architectural endpoint that makes the 8 YAMLs runtime-load-bearing.

### Pre-work (Week 4, parallel with Phase 2/3)

#### 4.1 Composition semantics spec (3-5 days)

Write `docs/composition_semantics.md` covering:
- Empty-intersection handling (most common case across 7 mappings)
- Soft vs hard constraint distinction
- Weighted preferences within `flatters` lists (currently flat — need ordering or explicit weights)
- Conflict precedence: 28 pair relationships including BodyShape > FrameStructure, SubSeason > individual color attrs, etc.
- Worked examples for each conflict type

#### 4.2 Stylist review of 8 YAMLs (1-2 weeks, parallel)

Paid consultant pass focused on edge cases: Diamond body type (genuinely tricky), `off_shoulder` workarounds (canonical schema gap), regional festival variants (Onam, Navratri day-color sequence by year), bridal vs non-bridal calls, Indian fabric pairing rules. Output: revised YAMLs + list of canonical-schema fixes needed.

#### 4.3 Add `hard:` / `soft:` distinction to YAML schema (2 days)

Extend the 8 YAMLs with constraint-type markers; update validators (`ops/scripts/validate_style_graph_yaml.py`). Migrate existing entries (most defaults: physical-frame is hard, archetype is soft).

#### 4.4 Refactor bootstrap grid generator (1 day)

Update `ops/scripts/generate_bootstrap_grid.py` to read occasion list from `knowledge/style_graph/occasion.yaml` (currently has 31; YAML has 45+). Eliminates the stale-grid drift vector flagged in PR #114.

#### 4.5 Begin one-way prompt → YAML migration (ongoing)

Add `MIGRATED:` markers in `prompt/outfit_architect.md` next to rules now in YAML. New rules go to YAML directly. Once composition engine ships and replaces the architect, the prompt's migrated sections get pruned. **Decision committed: one-way migration — no dual updates.**

#### 4.6 Manual eval set curation (1-2 weeks human curation, parallel)

100-500 representative test queries spanning the launch grid (mix of common, edge, novel). Run the slow pipeline against each; capture full outputs (architect plan + 6 composed outfits + rater scores + try-on for top 3). Hand-rate each output on the same 6 axes the rater uses. Store as `eval_set.jsonl` versioned in `tests/eval/`. Inter-rater agreement spot-checked on ≥20 cases by a second reviewer.

This is **not** training data — it's the eval ground truth used for Phase 4.8 quality validation, Phase 5.4 composer A/B testing, and ongoing regression detection.

### Engine work (Weeks 5-6)

#### 4.7 Implement composition engine — ✅ SHIPPED (PR #149)

Bundled all six sub-PRs (4.7a–4.7f) into a single merge: yaml_loader → reduction → relaxation → engine → render → worked-example tests. Module `modules/agentic_application/src/agentic_application/composition/`. Reads 8 YAMLs from `knowledge/style_graph/`. Applies intersect/union semantics with precedence rules from `docs/composition_semantics.md` (PR #144 + #147). Empty-intersection fallback per spec §3.2; on full failure, falls through to LLM architect via the router (4.9).

Verified end-to-end on 2026-05-06: architect stage 19s → ~0ms on engine-accepted turns; engine itself runs in <1ms wall-clock; confidence=1.0 on a real staging "casual outfits for weekend outing" query.

#### 4.8 Quality validator — ✅ FRAMEWORK SHIPPED (PR #149)

`composition/quality.py` implements `compare_queries`, `compare_directions`, `compare_plans`, `aggregate_eval` — pure-function comparators with token Jaccard on `query_document`, set Jaccard on `(key, value)` hard-filter items, role-based query pairing, direction_id-based pairing, median-not-mean reduction. `ops/scripts/composition_quality_eval.py` is the CLI driver; reads an eval JSONL, runs engine + LLM per cell, emits markdown.

**Real run gated on Phase 4.6** (eval set curation). Until then the framework sits dormant.

#### 4.9 Hot-path router — ✅ SHIPPED (PR #149)

`composition/router.py:route_recommendation_plan()` encodes spec §9 fall-through criteria (`confidence < 0.50` per the recalibration in PR #151, `no_direction`, `yaml_gap`, `excessive_widening`, `needs_disambiguation`) plus pre-engine eligibility gates (`anchor_present`, `followup_request`, `has_previous_recommendations`). Returns a `RouterDecision` envelope with `used_engine`, `fallback_reason`, `engine_confidence`, `yaml_gaps`, `engine_ms`, `provenance_summary` — wired into the orchestrator's cache-miss path.

### Cutover

#### 4.10 Manual flag rollout — ✅ SHIPPED (PRs #149, #151); bucketed ramp deferred

Single boolean env var `AURA_COMPOSITION_ENGINE_ENABLED` (default false). The earlier int-percent rollout machinery (`is_user_in_rollout_bucket` SHA-256 mod-100) was reverted in favor of the simpler flag for manual testing — bucketed ramp comes back as its own change once Phase 4.6 calibration data tells us where to start the percentage curve.

Engine plans intentionally do NOT write to the architect cache during flag-on testing (the cache key is profile/cluster-scoped, not user-scoped, so cached engine plans would persist across flag-on/flag-off transitions and leak the engine path into control traffic). LLM plans cache normally.

#### 4.11 Input canonicalization — ✅ SHIPPED (PR #151)

The pivotal piece that made the engine actually work on real planner output. Two-phase: (1) exact-match against YAML keys (cheap, no API call), (2) batched `text-embedding-3-small` call for non-matching values, nearest-neighbour cosine ≥ 0.50 wins. Below threshold → keep raw value (engine flags YAML gap → router falls through to LLM cleanly).

Pre-computed `composition/canonical_embeddings.json` (350KB, 256-dim, 85 keys × 5 axes) ships in-repo so production cold starts don't need an API call. Regenerated by `ops/scripts/build_canonical_embeddings.py` when YAMLs change. `aura_composition_canonicalize_result_total{axis, result}` counter (PR #154) tracks per-axis hit rate.

Confidence threshold dropped from spec §8's 0.60 to 0.50 because (a) downstream composer + rater rerank by score so an engine plan that's "merely passable" still surfaces good outfits, (b) at 0.60 the engine almost always fell through on real Indian inputs (4-5 of ~35 attributes typically need relaxation, accumulating penalties below the threshold). YAML gaps still always trigger fallback regardless of threshold via the explicit `has_yaml_gap` branch.

Bundled bug fix: engine's `seasonal_color_group` lookup now tries both `palette.SubSeason` (12-entry) and `palette.SeasonalColorGroup` (4-entry) before flagging a gap — profile data sometimes stores the 4-entry form (`Autumn`) instead of the 12-entry form (`Soft Autumn`).

#### 4.12 Observability + operability hardening — ✅ SHIPPED (PRs #150, #152, #153, #154)

- **PR #150** — pre-flag observability: `aura_composition_router_decision_total{used_engine, fallback_reason}` counter, engine latency under `aura_turn_duration_seconds{stage="composition_engine"}`, YAML gap metadata in `distillation_traces.full_output.router_decision`, `aura_composition_yaml_load_failure_total` counter + alert.
- **PR #152** — `tool_traces` CHECK-constraint fix: helper `_coerce_tryon_trace_db_status()` maps the rich path enum (`cache_hit`/`skipped_no_urls`/`tryon_failed`/...) to the constrained `'ok'`/`'error'` domain. Every cache-hit try-on previously dropped its trace row silently.
- **PR #153** — `model_call_logs.model` origin stamping: `_resolve_architect_origin_model()` picks `cache` / `composition_engine` / LLM model id; non-LLM paths force token columns to 0 (prevents stale `last_usage` bleed from prior turns).
- **PR #154** — comprehensive follow-up: 4 new metrics (`aura_composition_canonicalize_result_total`, `aura_composition_canonicalize_duration_seconds`, `aura_tool_traces_insert_failure_total`, `aura_composition_attribute_status_total`); 4 new dashboard panels (21 plan-source distribution, 22 yaml-gap distribution, 23 per-attribute status, 24 single-turn diagnostic); panel_17 patched to exclude sentinel rows; `RouterDecision.provenance_summary` plumbed into traces; OPERATIONS.md "A4: Composition engine flag-on regressions" runbook (env-var-didn't-export, yaml_gap dominance, YAML-load failure); `ops/scripts/turn_forensics.py` codifies the per-turn comparison report.

### Phase 4 follow-ups (not yet shipped, post-flag-on)

- **Confidence threshold + per-axis canonicalize threshold tuning.** 0.50 floor was a calibration guess; expected to tighten/loosen per axis once Phase 4.6 ground truth + a few hundred engine-accepted turns of telemetry land. Panels 22 + 23 are the read-out.
- **Run `composition_quality_eval.py` against the 4.6 eval set** when the eval JSONL exists — produces the engine-vs-LLM divergence report (markdown). Validates whether engine plans hold quality vs LLM on representative traffic.
- **Architect `model_call_logs.request_json` cleanup on engine path.** Cosmetic: engine-path rows still emit a `reasoning_effort` field that's irrelevant when no LLM call ran. Filter or rename for clarity.
- **Bucketed rollout machinery** restoration after flag-on validation. The SHA-256 mod-100 bucket function lives in git history and can be restored when Phase 4.6 + a stylist-vetted threshold give us the data to ramp.

### Phase 4 test gate

| Criterion | Target | Status |
|---|---|---|
| Engine handles ≥80% of cache-miss requests without LLM fallback | post-rollout target | needs traffic + 4.6 calibration |
| Engine latency p95: <500ms | <500ms | ✅ verified ~0ms on the one staging turn (sub-1ms compose_direction; ~150ms canonicalize embed call) |
| Quality on eval set: ≥90% agreement with LLM architect | ≥90% | gated on 4.6 + `composition_quality_eval.py` run |
| Cold-path architect avg: <2s on engine hit, ~10s on engine miss | hit/miss target | ✅ verified ~2s engine-stage on the staging turn (mostly trace-write + cache-touch overhead; LLM never ran) |
| Cache layer <100ms on cache hit regardless of origin | <100ms | architect cache untouched; behavior unchanged |

---

## Phase 5 — Composition engine for composer (P1, Weeks 8-10)

**Goal:** replace composer with `pairing_rules.yaml` + constrained graph search.

### 5.1 Pairing rules engine spec (3-5 days)

formality_alignment matrix application; color_story enforcement (5 harmony types); pattern_mixing logic (single, dual with constraints); scale_balance (statement-piece-per-outfit rule); bridal exception logic; anchor-driven rules for `pairing_request` intent.

### 5.2 Compatibility scoring against catalog (1 week)

Score `(top × bottom × outerwear)` tuples in the retrieved pool against `pairing_rules.yaml` constraints. Use enrichment attributes (formality, color, pattern, scale) as scoring inputs.

### 5.3 Diverse outfit assembly (3-5 days)

Top-K with diversity constraints: max 1 outfit per direction, palette spread, role coverage. Output 6 candidates for the rater (matching current contract).

### 5.4 A/B test against LLM composer (parallel)

Run both on eval set; rate outputs. Identify specific failure modes of the engine for stylist review.

### 5.5 Production rollout (1 week)

Feature flag rollout: 10% → 50% → 100%.

### Phase 5 test gate

- Composer engine hit rate: ≥70% of cache misses
- Engine latency p95: <300ms
- Quality on eval set: ≥85% agreement with LLM composer
- Cold-path composer average: <500ms on engine hit, ~6s on engine miss

---

## Phase 6 — Streaming delivery: cards + try-on (P1, Weeks 8-10, parallel with Phase 5)

**Goal:** decouple rendering from total-pipeline wall time. Cards visible <3s as the composer/rater finalizes them; try-on streams in 10-30s after. Real latency unchanged from Phase 1-5; perceived latency drops dramatically.

This phase is intentionally last in the active push because perceived-latency wins should layer on top of an already-fast real-latency pipeline — streaming a 60s pipeline into the UI just spreads the wait. After Phases 1-5 land, the cold-path is ~25-30s and the cache-hit path is <500ms; streaming converts those into <3s first-card-visible across the board.

### 6.1 NDJSON/SSE recommendation endpoint (1-2 days)

Refactor the recommendation endpoint to stream NDJSON or SSE. Server-side: emit each composed+rated card as soon as it's ready instead of buffering all 6. Skeleton states render on the frontend within <100ms of request submission. Real latency unchanged; perceived latency drops to first-card-visible (~3s on cache hit, <8s on cache miss after Phase 1-5).

### 6.2 Frontend card streaming consumer (1-2 days)

Update `modules/agentic_application/src/agentic_application/ui.py` to consume the streamed cards as they arrive. Each card renders independently; try-on starts loading on each card the moment it renders, doesn't block visibility of others.

### 6.3 SSE try-on streaming endpoint (3-5 days)

New endpoint `GET /v1/turns/{turn_id}/tryon/stream`. Server-side: as each Gemini render completes, push to the SSE channel. Token-based authentication.

### 6.4 Frontend try-on SSE consumer (2-3 days)

Cards render with try-on placeholders (from 6.2). SSE updates from 6.3 fill in try-on images as they complete.

### 6.5 Pre-warm worker for predicted recipes (1 week)

`ops/scripts/tryon_prewarm.py`. For each active user, predict top-N likely recipe cells based on profile + `recent_user_actions`. Resolve to garment sets via Phase 4 composition engine. Render Gemini try-on; write to existing try-on cache. Per-user pre-warm budget cap (max 10 renders/user/day) to prevent runaway Gemini cost.

**Why not cross-user fan-out.** "Render once per garment set, composite onto each user" is not actionable — `gemini-3.1-flash-image-preview` renders garment-on-body in a single forward pass; can't separate the rendered garment from the body without losing body-conforming drape ([tryon_service.py:18–44](modules/agentic_application/src/agentic_application/services/tryon_service.py#L18-L44)). Doing that properly requires a two-stage diffusion pipeline (research project) or classical CV warping (visible quality regression).

### Phase 6 test gate

- First card visible p95: <3s on cache hit, <8s on cache miss
- Try-on images stream in 10-30s after card visibility
- Pre-warm cache hit rate: ≥40% on alpha traffic by week 4
- No regression in real-latency p95 from Phase 5 baseline

---

## Phase 7 — Distillation (P2, Months 4+, gated on data)

**Goal:** distill slow LLM stages on accumulated trace data. Final cold-path optimization.

**Trigger:** ≥10K rater traces accumulated. Synthetic bootstrap counts; real traces preferred for refinement.

### 7.1 Distilled rater (3 weeks + ~$2K compute)

Fine-tune 3-8B model (Qwen2.5-7B / similar) on 6-axis hexagon traces from `distillation_traces`. Single A10/L4 serving via vLLM. Confidence-gated fallback to gpt-5-mini on low-confidence cases. New module `modules/style_engine/distilled/`.

### 7.2 Distilled architect / composer for novel cases (3-4 weeks)

For cases where Phase 4 + 5 composition engines fall through. Fine-tune small model on cache-miss outputs once 10K+ traces exist. Confidence-gated; if low confidence, fall through to current LLM (already faster from Phase 1+3).

### 7.3 Cold-path replacement (2 weeks)

Distilled models become the LLM-fallback path. gpt-5-class models reserved for very-low-confidence cases only.

### Phase 7 test gate

- Distilled rater p95: <600ms; ≥90% agreement with gpt-5-mini
- Cold-path total p95: <5s
- All paths sub-3s p95 across alpha traffic

---

## Launch readiness (P0, after Phase 4 + 6)

Items needed before opening the first alpha cohort. Slot in alongside Phase 4/5/6 work — small, independent.

### LR.1 Per-stage budget caps + cold-path safety net (2 days)

Wrap each stage in `process_turn` with timeout + deterministic fallback:
- Architect over budget → use closest-matching cached entry via fuzzy intent/occasion match
- Composer over budget → top-K from retrieval with diversity
- Rater over budget → cheap deterministic score (cosine to archetype centroid + palette match)

Initial budgets: planner 1.5s, architect 4s, composer 2s, rater 1.5s. Tune from p50 traces. **Acceptance:** synthetic slow-stage tests confirm fallback fires at budget; zero hard errors on stage timeout.

### LR.2 Out-of-scope graceful refusal UI (3 days)

For requests outside cached scope where composition engine has low confidence AND cold-path quality gate fails: "Aura is still learning [X] occasions — try [Y] instead" with quick-reply chips for in-scope alternatives. Telemetry: refusal events logged with intent + occasion so post-launch grid expansion targets actual misses.

### LR.3 Closed alpha onboarding + dashboard (1 week)

Define alpha scope: cells from Phase 4 quality gate that pass. Onboarding: existing flow + a "what Aura covers" page setting expectations on supported intents/occasions. Internal dashboard: cache hit rate, cold-path rate, refusal rate, p95 pre-tryon latency, user feedback per cell. Manual user review cadence: weekly review of refusals + low-rated outputs to drive grid expansion.

**Acceptance:** 5–15 alpha users onboarded; production traces accumulating; dashboard live; cache hit rate ≥60% on alpha traffic by week 2.

---

## Cross-cutting — Multi-tenancy data hooks

**Status:** parked (guidance applied to all phase work) · **Cost:** trivial if done now; expensive to retrofit · **Risk:** low

Multi-tenancy is deferred from this latency push, but five hooks are zero-cost now and save a painful migration when Shopify multi-tenancy lands:

1. Every new table (caches, future compat tables) includes `tenant_id TEXT NOT NULL DEFAULT 'default'`.
2. Cached architect / composer outputs stay catalog-independent ("structured navy blazer, formality 3-4" — never product_ids). Keeps cache reusable across tenants.
3. Prompts stay catalog-neutral (no "Aura's catalog" or brand-specific framing). Lets per-tenant prompt overlays slot in cleanly later.
4. Logs and traces tag with `tenant_id` from day one.
5. **Do not** migrate user-scoped tables (`users`, `conversations`, `feedback_events`) — that's a real migration owed when multi-tenancy actually ships, not now.

**Trigger:** apply continuously to all phase work above.

**Acceptance:** no new table created without `tenant_id`; no cached output references SKUs; no prompt references catalog identity; user-scoped tables left alone.

---

## End-state latency budget

After Phase 5 (estimated Week 10):

| Path | Frequency | Latency p95 |
|---|---|---|
| Cache hit (warm) | ~70% | <500ms |
| Cache miss → engine compose | ~25% | <2s |
| Cache miss → engine miss → LLM fallback | ~5% | ~10s |
| **Average user experience** | — | **2-3s** |

After Phase 7 (months later):
- All paths sub-3s p95
- LLM only for genuine novelty (<2% of traffic)
