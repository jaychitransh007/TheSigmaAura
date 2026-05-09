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

## Catalog content gap — masculine top coverage

**Status:** queued · **Cost:** content task (catalog enrichment) · **Risk:** low

Surfaced May 8 2026 during the turn `9abaf4d4` audit. Masculine `catalog_enriched` carries only 8 subtypes:

| subtype | count |
|---|---|
| trouser | 327 |
| blazer | 315 |
| jeans | 274 |
| track_pants | 41 |
| shorts | 34 |
| kurta | 7 |
| co_ord_set | 1 |
| kurta_set | 1 |

There are zero tshirts / polos / sweatshirts / hoodies / shirts in the masculine catalog. So when a male user asks for "loungewear" or "casual day-out" outfits, the architect emits reasonable subtype guesses (tshirt, hoodie) that retrieval can't satisfy — total products = 0 across all queries. PR #192 (empty-retrieval auto-relaxation) routes around the gap by dropping the subtype filter; PRs #186/#187 route around it by binding `OccasionFit ∈ {very_casual, active}` to find the 39 matching items. Both are workarounds — the underlying gap is content.

**Trigger to act:** when the masculine cohort hits production and we see empty-result rates / auto-relax rates for masculine users above some threshold.

**Acceptance:** at least 50 masculine items each across `tshirt`, `polo_tshirt`, `shirt`, `sweatshirt`, `hoodie` subtypes — enough that browse-by-garment and loungewear-style requests have a real catalog to draw from before relaxation kicks in.

**Note:** this is NOT a latency-optimization task even though it surfaced in latency review. It's content / catalog work. Filed here under general catalog hygiene, not under the sub-3s latency push below.

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

## Phase out `archetypal_preferences` from the composer

**Status:** queued · **Cost:** small · **Risk:** low

Post-PR-#89 the rater no longer reads `archetypal_preferences` — past likes/dislikes flow upstream through the architect's episodic memory (`recent_user_actions`, PR #90). The composer still reads it as a **soft preference** ("when the user has disliked an attribute at least twice, prefer to avoid it" — see `prompt/outfit_composer.md`). This is the last consumer of the aggregate signal.

Two ways to clean up:
1. **Drop the soft preference from the composer**, fall back entirely on episodic memory at the architect (which biases retrieval queries). Smallest code change; bet is the architect's bias is enough.
2. **Switch the composer to also read `recent_user_actions`** (the raw 30-day timeline, not the aggregate). Symmetric with the architect; lets the composer reason on context-dependent patterns the same way.

**Trigger to act:** if (a) Panel 18 (rater unsuitable rate) holds <5% over a stable post-#101 week — meaning episodic memory at the architect is producing acceptable retrieval + composer item selection without needing the aggregate signal — or (b) the `aggregate_archetypal_feedback` repo method becomes a maintenance burden (it has its own catalog_enriched hydration that overlaps with `list_recent_user_actions`).

---
---

# Sub-3s latency push — phased execution plan

**The anchor document for the latency-reduction work.** Replaces the prior pre-launch / launch / post-launch framing with a 5-phase execution plan, each with explicit test gates. We test query response after every phase before progressing.

## Status as of 2026-05-08

| Phase | Status | Notes |
|---|---|---|
| Phase 1 — Operational quick wins | ✅ **SHIPPED + verified** | Rater parallelization, retrieval RPC fix, planner shadow infra (dormant), gpt-5.4 → gpt-5.2 architect/composer swap. ~6s saved per turn. |
| Phase 2 — Caching layer | ✅ **SHIPPED + applied to staging** | All 4 migrations live on Aura-Staging. Hit rate jumped from ~0% (non-deterministic planner output) toward the design target as Phase 4.7+4.11 made engine inputs canonical. |
| Phase 3 — Prompt compression (3.0+3.1+3.2+3.4) | ✅ **SHIPPED** (PR #202, May 8 2026) | MIGRATED sections compressed in architect + composer prompts, `_RECENT_USER_ACTIONS_MAX` 30→20, structured output verified, audit harness (`ops/scripts/audit_prompt_tokens.py`) + budget regression guard. ~2K input tokens off the LLM-fallback path per turn. Aggressive 14K→5K via YAML-row injection (3.3/3.5) deferred to post-4.6. |
| Phase 4 prep (4.1, 4.4, 4.5) | ✅ **SHIPPED** | Composition semantics spec, bootstrap grid YAML loader, MIGRATED prompt markers. |
| Phase 4.7 — Engine implementation | ✅ **SHIPPED** (PR #149) | 6 sub-PRs (4.7a-f) bundled: yaml_loader, reduction, relaxation, engine, render, worked-example tests. Architect stage drops 19s → ~0ms on engine-accepted turns. Verified end-to-end with confidence=1.0 on a real staging query. |
| Phase 4.8 — Quality validator | ✅ **Framework SHIPPED** (PR #149) | `composition/quality.py` + `ops/scripts/composition_quality_eval.py` ready to consume Phase 4.6 eval set. Real comparison run gated on 4.6. |
| Phase 4.9 — Hot-path router | ✅ **SHIPPED** (PR #149) | `composition/router.py` with §9 fall-through gates + `extract_engine_inputs` + `is_engine_acceptable`. Wired into orchestrator. |
| Phase 4.10 — Manual flag rollout | ✅ **Manual flag SHIPPED** (PRs #149, #151) | `AURA_COMPOSITION_ENGINE_ENABLED` bool env var (default false). Bucketed-pct rollout deferred — flip flag for testing; switch to bucket-based ramp once 4.6 calibration data lands. |
| Phase 4.11 — Input canonicalization | ✅ **SHIPPED** (PR #151) | Two-phase canonicalize: exact-match against YAML keys → batched text-embedding-3-small fallback. 256-dim pre-computed embeddings (350KB JSON) co-shipped. Unblocked the engine on real planner output. |
| Phase 4.12 — Observability + operability hardening | ✅ **SHIPPED** (PRs #150, #152, #153, #154) | Pre-flag instrumentation, tool_traces constraint fix, model_call_logs origin stamping, full panel set (21-24) + runbook + `ops/scripts/turn_forensics.py`. |
| Phase 4.2 — Stylist YAML review | 🔒 Blocked on human | Paid consultant pass. Output: revised YAMLs + canonical-schema fixes. |
| Phase 4.6 — Eval set curation | 🔒 Blocked on human | 100-500 hand-curated queries with hand-rated outputs. Gates Phase 4.8 actual run, Phase 1.4 model A/B, Phase 4.10 bucketed ramp. |
| Phase 5 — Composer engine | ✅ **SHIPPED** (PRs #158-#163) | 6 sub-PRs (5a-5f): semantic spec, loader+evaluator, engine, router+flag, quality+shadow, dashboards+runbook. 154 tests added. Engine dormant behind `AURA_COMPOSER_ENGINE_ENABLED`; flag-on validation gated on Phase 4.6 eval set + 4.2 stylist review. |

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
The composition engine (Phase 4) is the architectural endpoint that makes the YAMLs runtime-load-bearing. Phases 1–3 are operational wins that get us most of the way to sub-3s on the common path *before* the engine ships. Phase 5 extends the wins to the composer.

---

## Phase 1 — Operational quick wins (P0, Week 1)

**Goal:** 64s → ~25-30s without architectural changes. All tasks are independent, parallelizable, low-risk.

### 1.1 Parallelize the rater (1 day)

Replace the single 6-outfit `outfit_rater.rate()` call with `asyncio.gather` over 6 parallel calls. Each call rates one outfit independently against the absolute 75-threshold. If composer produces 6 and we pick top 3 (rather than just gate-keep), add a tie-breaking comparative pass (~500ms) after parallel scoring. Verify in production: same scores within tolerance, latency drops from 13.4s to ~2-3s.

### 1.2 Fix retrieval (hours)

Profile the current 2.9s pgvector query — likely missing HNSW index, doing pre-filtering wrong, or re-running embedding model on query without caching. Add HNSW index if absent: `CREATE INDEX ON catalog_item_embeddings USING hnsw (embedding vector_cosine_ops)`. Cache the query embedding model in memory; don't reload per request. Move metadata filters (size, gender, in-stock) to indexed columns; apply at SQL level not Python loop. Expected: retrieval drops from 2.9s to <100ms.

### 1.3 / 1.4 — DROPPED (2026-05-07)

Further planner / architect / composer model-swap work is no longer on the plan.

What stays shipped and in production:
- Planner shadow infrastructure (`AURA_PLANNER_SHADOW_MODEL`, `aura.planner.shadow` logger). Dormant unless the env var is set; not being actively iterated on.
- The `gpt-5.4 → gpt-5.2` architect + composer swap (shipped May 13 2026).
- Env-configurable model strings (`PLANNER_MODEL`, `ARCHITECT_MODEL`, `COMPOSER_MODEL`, `RATER_MODEL`, `STYLE_ADVISOR_MODEL`).

The previously planned next steps — promoting a non-reasoning planner and A/B-ing claude-sonnet-4-7 / gemini-2.5-pro for architect+composer — are not being pursued. The architect path is mostly moot post-engine (Phase 4.7 ships engine-accepted turns at ~0ms architect), and the planner promotion didn't justify the calibration work given the engine's larger end-to-end win. Composer-side latency is now better attacked by Phase 5 (composer engine) than by a model swap.

### Phase 1 test gate

- Cold-path latency p95: ≤30s (from 64s, after 1.1 rater + 1.2 retrieval RPC ship)
- Quality on eval set: ≥95% agreement with current production (deferred until eval set exists)
- No regressions on the 50 hand-picked test queries

> **Note:** streaming card delivery (NDJSON/SSE + frontend) was previously scoped here as 1.5 and later as Phase 6. Both are dropped from the latency push — perceived-latency UX work is no longer planned under this anchor.

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

## Phase 3 — Prompt compression (P1)

**Goal:** shrink architect + composer prompts; reduce cold-path latency on the LLM-fallback path.

**Important context (May 8 2026):** with the architect engine accepting ~70-80% of turns and 7-of-7 follow-up intents engine-friendly, the architect LLM is now a **fallback** path (<30% of turns), not the common path. Compression saves real time on the cases that fall through, but the headline win has shifted from "every turn" to "the hard edge cases."

Phase re-scoped May 8 2026 into a ship-now bundle and a post-4.6 follow-up tier:

### 🟢 Ship-now bundle (3.0 + 3.1 + 3.2 + 3.4)

Low-risk cuts that don't depend on Phase 4.6 ground truth:

#### 3.0 Audit (1 day)
Add token-counting telemetry; one-time measure on 50 production turns; produce per-section breakdown so subsequent cuts target real heavy-hitters, not assumed ones.

#### 3.1 Easy cuts in architect prompt (1-2 days)
Delete the `<!-- MIGRATED -->` sections from `prompt/outfit_architect.md` (Occasion Calibration, BodyShape Visual Direction, Pattern Calibration — all already encoded in YAML and consumed by the engine). Trim translation examples to 2 per category. Cap `recent_user_actions` at 20 (was 30). Cap `conversation_history` to last 2 turns (was 4). Estimated savings: ~3-4K tokens.

#### 3.2 Verify structured output (hours)
Confirm architect's `_PLAN_JSON_SCHEMA` is in use via OpenAI `response_format=json_schema` (already in place per `outfit_architect.py:_PLAN_JSON_SCHEMA`). Trim any redundant in-prompt schema description. Estimated savings: ~500-800 tokens.

#### 3.4 Composer trim (1 day)
Apply the same pattern to `prompt/outfit_composer.md`: drop redundant prose, prune examples. Estimated savings: ~500 tokens.

**Combined target:** architect ~14K → ~9-10K, composer ~3-5K → ~2.5-4K. Aggressive 14K → 5K target deferred to 3.3 + 3.5 (next).

### 🔒 Post-4.6 follow-up tier (3.3 + 3.5)

Gated on Phase 4.6 eval set landing — cannot validate quality regression without ground truth.

#### 3.3 Conditional prompt injection (3-4 days, post-4.6)

Load `outfit_architect_followup.md` ONLY when `is_followup=true`. Same idea for occasion-specific rules — only inject the active occasion's calibration. Saves ~500-1,000 tokens per applicable turn but requires routing logic in the architect agent + per-occasion eval coverage.

#### 3.5 YAML row injection (5-7 days, post-4.6)

Replace the deleted MIGRATED prose with structured per-user YAML row injection (palette for their sub-season, body_frame for their shape, archetype for their style). Adds a per-turn YAML rendering pipeline plus an ongoing YAML↔prompt sync burden. Biggest single token win (~1-2K) but the highest engineering cost AND the highest quality risk on the LLM-fallback path. Worth doing only if (a) 3.0+3.1 prove out the easy cuts hold quality on the eval set and (b) the LLM-fallback rate doesn't drop further (if engine acceptance keeps climbing, the LLM path becomes too rare to justify the YAML-injection investment).

### Phase 3 test gate

- Architect input tokens: ≤5K
- Composer input tokens: ≤4K
- Cold-path architect latency: ~8-10s (with the shipped gpt-5.2 swap stacked)
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

**Goal:** replace `OutfitComposer.compose()` (gpt-5.2, ~12-14s, $0.036/turn — second-largest LLM line post-4.7) with deterministic tuple scoring against `pairing_rules.yaml`. Engine emits up to 6 outfits in the existing `ComposerResult` shape; rater contract unchanged. Spec mirrors Phase 4.7's pattern (composition_semantics.md → composer_semantics.md, pure-function engine, hot-path router with eligibility + acceptance gates, `AURA_COMPOSER_ENGINE_ENABLED` boolean flag, LLM kept as permanent fallback).

### Locked decisions (2026-05-07)

| # | Decision | Rationale |
|---|---|---|
| 1 | **All-or-nothing per turn**, not per-outfit hybrid | Single `ComposerResult.overall_assessment`; hybrid doubles debugging surface. Mirror of architect router. |
| 2 | **Hard violation drops tuple; soft violation = -0.1 score penalty per violation; base score 1.0** | Clean binary; matches architect spec's hard/soft model. If <3 tuples survive across all directions → low-confidence fall-through. No precedence ordering among hard categories needed. |
| 3 | **Hardcode `pairing.py:is_statement()`**, docstring references `scale_balance.statement_definition` as source of truth | Same call architect made on its precedence matrix. Statement definition is a 4-clause OR; rare stylist edits. |
| 4 | **Defer anchor turns** to a follow-up | Pre-engine eligibility gate declines `anchor_present`/`followup_request`/`has_previous_recommendations`/`pool_too_sparse`. Mirror of architect router. Anchor support added post-validation. |
| 5 | **`bridal_specific.triggers_on: [occasion keys]`** new YAML field | Engine matches `formality_hint == 'ceremonial' AND occasion_signal in triggers_on`. Stylist-editable, no hardcoded occasion names in Python. |
| 6 | **Keep LLM `OutfitComposer` as permanent fallback** | Engine target hit rate ≥70%, not 100%. Same as architect pattern. The LLM stays as the permanent fallback path. |

### Sub-PR decomposition — ALL SHIPPED (2026-05-07)

| PR | Lands | Status |
|---|---|---|
| **5a** | `docs/composer_semantics.md` spec | ✅ #158 |
| **5b** | `composition/pairing_loader.py` + `pairing.py`; `bridal_specific.triggers_on` YAML field; 69 unit tests | ✅ #159 |
| **5c** | `composition/composer_engine.py` — `compose_outfits()`; tuple enumeration + scoring + diversity top-K + confidence; 49 tests | ✅ #160 |
| **5d** | `composition/composer_router.py` + `AURA_COMPOSER_ENGINE_ENABLED` flag + orchestrator wiring + `aura_composer_router_decision_total` counter; 17 tests | ✅ #161 |
| **5e** | Quality validator extension (`compare_composer_outputs`) + `ops/scripts/composer_quality_eval.py` + shadow-mode hook on router; 15 tests | ✅ #162 |
| **5f** | Panels 25-28 in OPERATIONS.md + auto-extracted SQL files + A5 runbook + `maxItems: 10` LLM schema cap + spec §9 worked-example tests | ✅ #163 |

Total: 154 new tests across the 6 PRs, 902/902 passing post-5f. Engine is dormant (default-false flag); ready for operational rollout once Phase 4.2 stylist YAML review + Phase 4.6 eval-set ground truth land.

**Composer-side `model_call_logs.model="composer_engine"` origin stamping** — ✅ shipped in PR #180 (Phase 5x.4a). `_resolve_composer_origin_model()` writes a synthetic row stamped `composer_engine` / `cache` on engine and cache paths, mirroring the architect's pattern.

### Phase 5 test gate

- Composer engine hit rate: ≥70% of cache misses
- Engine latency p95: <300ms
- Quality on eval set: ≥85% agreement with LLM composer
- Cold-path composer average: <500ms on engine hit, ~6s on engine miss

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
