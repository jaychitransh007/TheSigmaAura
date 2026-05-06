# Release Readiness Criteria

This document defines the concrete checklist that must be green before Aura
ships beyond the current dev-complete state. It is the single source of
truth for "are we ready to put a real user in front of this?".

The checklist is split into four gates. Each gate is a hard block — you do
not advance to the next gate until the previous one is fully green.

The companion artifacts are:

- `docs/OPERATIONS.md` — dashboards and queries that back the metrics gates
- `ops/scripts/smoke_test_full_flow.sh` — end-to-end smoke test
- `ops/scripts/validate_dependency_report.py` — dependency report validator
- `docs/DESIGN_SYSTEM_VALIDATION.md` — manual UI QA checklist

---

## Gate 1 — Functional Correctness

The pipeline must produce a usable answer for every primary intent without
manual intervention.

- [ ] All tests across `tests/` pass against the current branch
      (verified May 3, 2026 post-PR-#32: **434 L0 tests, 1 skipped, 0 failures**).
      Cumulative scope: Phase 13/13B regression tests (live_context
      payload, three_piece direction, anchor payload); May-1 confidence
      threshold tests (`ConfidenceThresholdGateTests` × 6) verifying
      outfits below the threshold never reach the user; May-3 perf-series
      tests (`TryonParallelRenderTests` × 3, `ArchitectPromptAssemblyTests`
      × 3); May-3 LLM ranker tests (`test_outfit_composer.py` × 11,
      `test_outfit_rater.py` × 8). Prior baseline: three outfit structures +
      all 46 attributes in query docs + parallel retrieval ~4× speedup +
      occasion-fabric coupling + time-of-day inference + role-category
      validation + outerwear recategorization + catalog 14,296 garment
      items.
- [ ] `ops/scripts/validate_dependency_report.py` runs to completion with
      zero failed assertions.
- [ ] `ops/scripts/smoke_test_full_flow.sh` runs to completion against a
      staging backend with `pass > 0` and `fail = 0`.
- [ ] The catalog-unavailable guardrail (P0 — local env guard) fires when
      `catalog_item_embeddings` is empty, returning a clear user-facing
      message instead of an empty turn.
- [ ] The silent-empty-response guard (P0) is verified by the
      `test_pipeline_*` tests; the post-pipeline guard rewrites empty
      messages to a graceful fallback.
- [ ] The wardrobe-first hybrid pivot (P0) is exercised by at least one
      user-story test in the suite.
- [ ] Disliked products from `feedback_events` are excluded from
      `catalog_search_agent` retrieval results across turns (verified by
      `test_catalog_search_excludes_disliked_product_ids`).

## Gate 2 — Data & Environment Readiness

The environment we ship to must have the data the pipeline depends on.

- [ ] `catalog_enriched` has at least 500 rows with `row_status in ('ok','complete')`.
      (verified April 10, 2026: 14,296 items, all enriched, all embedded,
      zero null filter columns. Dead/delisted items cleaned up. Vastramay,
      Powerlook, CampusSutra re-embedded from DB via resync endpoint.)
- [ ] `catalog_item_embeddings` has the same row count as the embeddable
      subset of `catalog_enriched` (no orphan rows, no missing embeddings).
- [ ] All Supabase migrations under `supabase/migrations/` have been
      applied to the target environment (`ops/scripts/schema_audit.py`
      reports zero drift).
- [ ] `data/catalog/uploads/` has the most recent enrichment CSV the
      catalog admin team approved.
- [ ] At least one fully-onboarded test user exists with:
  - completed `onboarding_profiles` row (profile_complete + style_preference_complete + onboarding_complete)
  - both `full_body` and `headshot` images uploaded
  - completed `user_analysis_runs` row
  - non-empty `user_derived_interpretations`
  - at least 5 wardrobe items in `user_wardrobe_items`
- [ ] The above test user can complete a full chat → wardrobe-first → catalog
      hybrid → outfit-check journey via `ops/scripts/smoke_test_full_flow.sh`.

## Gate 3 — Observability & Operations

You cannot ship what you cannot watch.

- [ ] All 16 dashboard panels in `docs/OPERATIONS.md` exist in the chosen
      dashboard tool (Supabase Studio / Metabase / Grafana) and refresh on
      the cadence specified there. Panel 16 — Low-Confidence Catalog
      Responses (May 2026) tracks the rate at which the 0.75 threshold
      gate forces a no-confident-match response; healthy steady state
      is < 5%.
- [ ] **Pipeline Health** panel shows zero empty responses and a defined
      error rate over the last 24h.
- [ ] **Catalog-unavailable guardrail** panel shows zero hits in production
      and is documented as a "ring oncall" alert if it goes non-zero.
- [ ] **Negative signals** panel is reviewed daily during the first week of
      rollout. If any single product appears in the top-disliked list for
      more than 3 distinct users, the catalog row is audited and either
      fixed or hidden.
- [ ] An on-call rotation exists with documented escalation steps for:
  - empty responses spike
  - catalog/embeddings missing
  - feedback dislikes spike on a single product
  - try-on render slowness (visual_evaluation step > 70s sustained — see
    Operations runbook section E)
  - dependency report shows acquisition_source = unknown for >50% of
    new users (instrumentation regressed)
- [ ] Logs from `_log.error` / `_log.warning` in `orchestrator.py`,
      `catalog_search_agent.py`, `outfit_composer.py`, and
      `outfit_rater.py` are captured somewhere queryable (cloud
      logging, Logflare, etc.) — not just stdout.

## Gate 4 — Product & UX

The user-facing surface must hold up to a stylist's scrutiny.

- [ ] All items in `docs/DESIGN_SYSTEM_VALIDATION.md` are checked by an
      actual designer (not the implementing engineer).
- [ ] Mobile (430px width) and desktop (≥1280px) variants of every primary
      view (`/`, `/wardrobe`, `/profile`, results page, chat) have been
      walked through end-to-end on real devices, not just devtools.
- [ ] The chat homepage uses one dominant primary CTA + progressive
      disclosure for secondary actions (P0 — Single-Page Shell).
- [ ] Wardrobe-first answers explicitly name the selected pieces and
      explain *why* they fit; single-item wardrobe answers either pivot
      to hybrid or explicitly say what is missing (P1 — Partial Answer UX).
- [ ] Follow-up suggestions render as labelled groups (Improve It /
      Show Alternatives / Shop The Gap), driven by the structured
      `follow_up_groups` field in metadata, not substring matching.
- [ ] All copy has been reviewed for the "stylist, not a dashboard" tone
      (P0 — Design System Realignment).

---

## Sign-off

A release is ready when **every box above is checked** AND the following
two humans have signed:

- [ ] Engineering owner: ____________
- [ ] Design / product owner: ____________

Date: ____________

Branch / commit shipped: ____________

---

## What is *not* in scope for the first-50 release

These are explicit non-goals — do not block the release on them:

- WhatsApp inbound runtime (deliberately removed; rebuilding separately)
- Virtual try-on feedback loop (P2 — try-on quality complaints handler)
- First-50 recurring-intent analysis dashboard (separate workstream)
- ~~Pairing-pipeline anchor enforcement edge cases~~ — **resolved in Phase 13** (April 10, 2026): anchor rules 4–6 added to the architect prompt covering every anchor category (top/bottom/outerwear/complete) with explicit direction structure constraints and formality conflict resolution. The architect now skips the anchor's role and chooses direction types based on what the anchor fills.

---

# Recently Shipped (May 1, 2026 — migrated May 3, 2026)

_Migrated from `CURRENT_STATE.md`. The May-1 "Open Items Plan" — every item now ✅ shipped — is preserved here as a record of work landed during the platform pass. For ongoing release readiness criteria see the Gates above._

## May 6–7, 2026 — Phase 4.7+ composition engine + canonicalization + observability

A 7-PR push that shipped the deterministic YAML-driven composition engine, the input-canonicalization layer that makes it work on real planner output, and the observability surface around both.

| PR | Title | Net change |
|---|---|---|
| #149 | Phase 4.7 + 4.8 + 4.9 + 4.10 — engine, validator, router, flag | New `composition/` package: `yaml_loader.py` → `reduction.py` → `relaxation.py` → `engine.py` → `render.py` → `quality.py` → `router.py`. `compose_direction()` reduces 8 style-graph YAMLs into a `DirectionSpec` deterministically; router applies spec §9 fall-through criteria; orchestrator wires it behind `AURA_COMPOSITION_ENGINE_ENABLED` (default false). 691 → 599 → 654 tests across the sub-PRs. |
| #150 | Pre-flag observability instrumentation | `aura_composition_router_decision_total` counter, engine latency under `aura_turn_duration_seconds{stage="composition_engine"}`, YAML-gap surfacer in distillation traces, `aura_composition_yaml_load_failure_total` + alert. |
| #151 | Phase 4.11 input canonicalization via embedding nearest-neighbour | The pivotal piece. `composition/canonicalize.py` two-phase (exact-match → batched `text-embedding-3-small`) maps free-text planner output to YAML-canonical keys. 350KB pre-computed embedding bank (`canonical_embeddings.json`). Confidence threshold recalibrated 0.60 → 0.50. Engine bug fix: seasonal_color_group dual-dimension lookup. |
| #152 | `tool_traces` CHECK-constraint fix | Every cache-hit try-on candidate was silently dropping its trace row (`status='cache_hit'` violated the table's `('ok', 'error')` enum). `_coerce_tryon_trace_db_status()` helper coerces the rich path enum to the constrained domain. |
| #153 | `model_call_logs.model` origin stamping | Per-model rollups were attributing every cache + engine row to gpt-5.2 (phantom 0-token rows). New `_resolve_architect_origin_model()` stamps `cache` / `composition_engine` / LLM model id; tokens forced to 0 on non-LLM paths. |
| #154 | Comprehensive observability follow-up | 4 new metrics (canonicalize result counter, embed-duration histogram, tool_traces failure counter, attribute-status counter). 4 new dashboard panels (21 plan-source distribution, 22 yaml-gap distribution, 23 per-attribute status, 24 single-turn diagnostic). `RouterDecision.provenance_summary` plumbed into traces. OPERATIONS.md "A4: Composition engine flag-on regressions" runbook. `ops/scripts/turn_forensics.py`. |
| #155 | OPEN_TASKS.md refresh | Updated the Phase status table + foundation list + per-phase detail to reflect the above shipped state. |

**Verified end-to-end on 2026-05-06:** a real flag-on staging turn (`b356a1bf`, "Find me casual outfits for weekend outing") produced `used_engine=true, engine_confidence=1.0, engine_ms=0`. Total turn 83s → 63s vs the flag-off baseline; per-turn cost ~$0.19 → ~$0.15. Architect stage 19s → ~0ms is the dominant saving.

**Still gated on humans:**
- Phase 4.2 — paid stylist YAML content review (revised YAMLs, edge-case calls, canonical-schema fixes)
- Phase 4.6 — eval-set curation (100-500 hand-curated queries) — required for confidence-threshold calibration, A/B model swap (Phase 1.4), and the bucketed-rollout ramp

## May 5–6, 2026 — episodic memory + R7 rater + composer name + ops recalibration

A 22-PR sweep that overhauled the rater rubric, added episodic memory at the architect, made every outfit a first-class named card, fixed three silent failure modes, and rebuilt the observability surface to match the new system. Grouped by area:

### Composer (PRs #80, #81, #83, #88, #91, #95)

| PR | Title | Net change |
|---|---|---|
| #80 | Harden direction_id contract + per-attempt logging | Dynamic enum on `direction_id` (LLM physically can't write a SKU there); per-attempt callback so `model_call_logs` gets one row per LLM call instead of summing tokens across the retry. T6 turn that "appeared" to have a 24K-token prompt was actually 12K + 12K — the doubling now visible. |
| #81 | Composer → gpt-5.4 + threshold 75 → 60 + weight rebalance | Promoted from gpt-5-mini for the heavier reasoning task. Default weight profile rebalanced (occ 0.35 / body 0.20 / col 0.25 / inter 0.20). Threshold lowered to 60 to compensate for the more honest score distribution under the new model. (Both superseded again by R7 — see below.) |
| #83 | Source composer model from agent instance | Trace + log rows now read `self.outfit_composer._model` rather than a hardcoded literal, mirroring the architect's drift-protection pattern. |
| #88 | Composer emits per-outfit `name` | Cards previously rendered as "Outfit 1", "Outfit 2" — composer now writes a stylist-flavored title (e.g. *"Sharp Navy Boardroom"*, *"Camel Sand Refined"*) per outfit. Surfaces directly as the user-facing card title. |
| #91 | Composer name schema cap + null safety | `maxLength: 100` on `name` in the strict-output schema (review fix); parser uses `or ""` so an explicit JSON null doesn't ship as `"None"`. |
| #95 | Composer `model_call_logs.latency_ms` was always 0 | `_invoke()` never timed `responses.create()`; the per-attempt payload didn't carry latency at all. Fixed: any panel computing composer p50/p95 from `model_call_logs` now reads real values. |

### Rater (PRs #89, #101)

| PR | Title | Net change |
|---|---|---|
| #89 | Drop rater veto on `archetypal_preferences.disliked` | T12 had **8/8 outfits vetoed** because each touched a single disliked attribute (color_temperature: neutral, pattern: solid). Per-dim scores were healthy 70–88; the aggregate-veto rule was punching above its weight. Removed entirely; the rater no longer reads `archetypal_preferences`. |
| #101 | **R7: 6 dims on a 1/2/3 scale** | Most consequential change of the sweep. Rater contract moved from 4 dims on 0–100 → 6 dims on 1/2/3, schema-locked via `enum: [1, 2, 3]` per sub-score. Added Formality (was double-counted across `occasion_fit` + `inter_item_coherence`) and Statement (was a fractional sub-check inside `inter_item_coherence`). Renamed `inter_item_coherence` → `pairing`, scoped to fit + fabric only. Threshold moved 60 → 50 (all-2s outfit lands at exactly 50). Blend math: `((Σ subscore × weight) − 1) / 2 × 100` rescales to 0–100 for the card center. All five weight profiles rebalanced across 6 dims. |

### Architect — episodic memory (PRs #90, #92, #93, #97)

| PR | Title | Net change |
|---|---|---|
| #90 | Surface recent like/dislike timeline to the architect | New repo method `list_recent_user_actions(user_id, lookback_days=30)` returns a chronological 30-day timeline of like/dislike events, each row carrying `user_query`, `created_at`, `event_type`, and the garment's full attribute set. The architect prompt has a new "Recent user actions (episodic memory)" section instructing it to find context-dependent patterns (different occasions can take the same attribute differently) and bias retrieval queries — never as blanket exclusions. Replaces the old aggregate-veto signal with raw evidence the LLM can reason over. |
| #92 | PascalCase fix — episodic memory was empty for every user | PR #90 shipped with snake_case column names (`color_temperature`, `pattern_type`) in the `catalog_enriched` query. The actual schema uses **PascalCase** (`ColorTemperature`, `PatternType`). PostgREST 400-errored on every call; the `except Exception` swallowed it; every user got an empty timeline since #90 merged. Mocks also used snake_case, so tests didn't catch it. |
| #93 | Consolidate catalog attr mappings + log silent excepts | Single `_CATALOG_ATTR_MAP` (snake_case prompt key → PascalCase DB column) replaces the two parallel mappings that drifted in #90. Five `except Exception:` blocks across `aggregate_archetypal_feedback` + `list_recent_user_actions` now log `_log.warning(..., exc_info=True)` instead of swallowing — the next failure surfaces in logs instead of vanishing. |
| #97 | Narrow broad excepts to `(SupabaseError, httpx.RequestError)` | The five `except Exception:` blocks were catching too much — a `KeyError` from `_CATALOG_ATTR_MAP` or a `TypeError` mid-comprehension would silently degrade to an empty timeline (the same shape PR #92 just fixed). Logic errors now propagate fast. |

### Default routing — catalog-first (PR #82)

| PR | Title | Net change |
|---|---|---|
| #82 | Auto → catalog default; ≥2-per-role wardrobe coverage gate | Pre-#82, `source_preference="auto"` (no explicit signal) routed to the **wardrobe-first** path. Now the default routes to the **catalog**; wardrobe-first only fires on explicit "from my wardrobe" / "use my wardrobe". When the user does ask for wardrobe-first, a new minimum-coverage gate requires ≥2 tops AND ≥2 bottoms AND ≥2 one-pieces — falls through to a `wardrobe_unavailable` answer-source with the actual counts surfaced ("you have 2 tops, 2 bottoms, 0 dresses"). New `wardrobe_coverage` metadata block exposes counts + sufficient-flag for observability. |

### Observability + ops (PRs #94, #95, #96, #98, #99, #100)

| PR | Title | Net change |
|---|---|---|
| #94 | Recalibrate alerts + Panel 3 / 6 for the auto→catalog flip | LLM-cost daily-budget alert: $50 → $500 (gpt-5.4 composer was tripping the old threshold on every quiet day). Panel 3 + Panel 6 SQL + narration updated for the new dominant `answer_source` mix. Carve-out paragraph in Panel 16 + the try-on QG alert noting the post-#89 `unsuitable=True` rate baseline shift. |
| #96 | Add Panels 17–20 + script preserve-marker | New panels: **17** Architect Input Token Growth (PR #90/#92), **18** Rater Unsuitable Rate (PR #89 baseline), **19** Composer Latency (PR #95 baseline), **20** Episodic Memory Population (PR #90/#92). Plus `extract_dashboard_sql.py` now preserves curator content past a `<!-- preserve-below -->` marker so README.md no longer gets eaten on every regen. |
| #98 | Drop dates from panel filenames; SUM(CASE) → COUNT FILTER | Renamed `panel_16_*may_3_2026.sql` → `panel_16_low_confidence_catalog_responses.sql` (and 17–20 likewise). Cleaner SQL idiom. |
| #99 | Panel 20 query label was last_7d, CTE was 30d | Single-line comment fix to match the actual query window. |
| #100 | Panel 16 `NULLIF` → `nullif` | Casing alignment with every other panel in OPERATIONS.md. |

### Review-fix follow-ups (PRs #84, #85, #86, #87)

Four small PRs addressing reviewer feedback on PRs #82 + #88: precompute wardrobe coverage once and thread through both the wardrobe-first builder and the fallback (avoid double-walk on the insufficient-coverage path); inline a single-use local; drop a `list(... or [])` defensive wrapper that the schema's `default_factory=list` already covered; switch `getattr(user_context, ...)` to direct attribute access at call sites where `user_context` is statically known to be a `UserContext`.

### Pipeline shape (post-sweep)

```
copilot_planner (gpt-5-mini, 7s)
  → outfit_architect (gpt-5.4, 22-28s, ~15K input tokens with episodic memory)
  → catalog retrieval (text-embedding-3-small + pgvector, 3s)
  → outfit_composer (gpt-5.4, 13s, emits per-outfit name)
  → outfit_rater (gpt-5-mini, 13s, 6 dims on 1/2/3 scale)
  → tryon_render (gemini-3.1-flash-image-preview, 3 parallel, ~25s wallclock)
  → response_formatter
```

Threshold gate moved 60 → 50 (R7). All 6 weight profiles sum to 1.0. Pairing drops for `complete` (single-item) outfits → 5 axes; the orchestrator renormalizes the remaining 5 weights at compute time.

### Live verification (T13, 2026-05-05 17:21)

The first turn after R7 merged shipped 3 outfits with stylist-flavored names ("Camel Sand Refined" / "Chalk Navy Balance" / "Olive Mocha Office"). Rater emitted 1/2/3 across all six dims, no `unsuitable=True`, fashion_scores 87/92/94. Total turn cost 20.81¢, latency 100s — comparable to T10/T11 (3 try-on shipped) within margin; +6K architect tokens vs pre-#90 baseline (episodic memory carries weight).

**L0 tests:** 458 pass post-#101 (up from 434 at start of sweep; net change includes the rater test rewrite for the 6-dim 1/2/3 contract + new tests for composer name, episodic memory hydration, narrow except, threshold gate fixtures).

---

## May 3, 2026 — LLM ranker rollout

| PR | Title | Net change |
|---|---|---|
| #27 | Architect kurta hard rule + retrieval_count 12→5 | Catalog has zero compatible bottoms for a standalone kurta, so paired/three_piece kurta directions are now rejected at the prompt level; retrieval pool drops to 5 per query. |
| #28 | Drop kurta code-side check, rely on prompt | Removed the parser-level kurta validator added in #27; prompt rule alone enforces the contract. |
| #29 | Scaffold OutfitComposer + OutfitRater LLM agents | Two new gpt-5-mini agents + prompts + schemas, behind a flag. No orchestrator wiring yet. |
| #30 | Switch orchestrator to LLM ranker, delete assembler + reranker | Replaces ~600 lines of heuristic pairing code + the deterministic Reranker with the Composer + Rater pipeline. `assembly_score` (0–1) → `fashion_score` (0–100); `ranking_bias` retired. |
| #31 | Address PR #29 review notes | Top-level imports, type hints, tightened exception handling, rater stub schema consistency. |
| #32 | Address PR #30 review notes | Composer prompt mandates item order in `item_ids`; thread-safe `usage` carried on result objects; `_clamp01` → `_clamp_to_100`. |

**Pipeline change:**
- Before: `Architect → Retrieval → Assembler (heuristic) → Reranker (det) → ...`
- After: `Architect → Retrieval → Composer (LLM) → Rater (LLM) → ...`

**Observability:** new `tool_traces.composer_decision` + `rater_decision` rows carry per-outfit rationale + the four-dimension score breakdown. `model_call_logs` gets the full raw LLM JSON.

**L0 tests:** 434 pass (up from 382 pre-rollout; net change includes ~25 deleted assembler/reranker unit tests and ~50 new Composer + Rater tests).

## Open Items Plan (May 1, 2026)

Audit on May 1, 2026 surfaced five categories of open work. The first three are real code-pending tasks; the fourth is ops/deployment work gated on a staging environment; the fifth is a documentation hygiene sweep.

### 1. Wire `ranking_bias` into assembler + reranker — superseded May 3 2026

**Status:** The deterministic OutfitAssembler + Reranker were replaced with the LLM ranker (Composer + Rater) in PRs #29 / #30. `ranking_bias` is gone from the schema; the Rater reads user context directly. This entry is preserved as historical record only.

### 2. Stale onboarding test (P0, trivial)

**Status today:** `tests/test_onboarding.py:272` asserts `"Step 1 of 10"` but the UI now renders `"Step 1 of 9"` since the onboarding flow was streamlined (full-body + headshot merged into one screen, gender moved before images). 1 of 312 tests fails for this reason.

**Plan:**
- [x] Update the assertion to `"Step 1 of 9"`.

### 3. Reranker calibration plumbing — superseded May 3 2026

**Status:** The deterministic Reranker is gone (PR #30). `data/reranker_weights.json`, `ops/scripts/calibrate_reranker.py`, and `tool_traces.reranker_decision` rows are obsolete. The orphan files were removed in the May-3 doc-cleanup PR.

The LLM Rater is now the sole ranker. New observability rows live in `tool_traces` as `composer_decision` and `rater_decision`. Future calibration is informed by joining `rater_decision.fashion_score` to `feedback_events` — see `docs/OPERATIONS.md` Panel 16 for the reference query.

### 4. Release Readiness — gate-by-gate ops checklist (partial staging verification, May 1, 2026)

**Status today (May 1, 2026):** Code-side prep landed AND staging connectivity verified — schema audit, dependency report, catalog health, embedding coverage, and reranker calibration all run cleanly against the live staging Supabase. The remaining items need a deployed app, designer review, and real devices.

**Staging readouts (May 1, 2026):**
| Check | Result |
|---|---|
| `schema_audit.py` against staging | **PASS** — 46 attributes, no migration drift |
| `validate_dependency_report.py` (in-memory harness) | **PASS** — 15/15 assertions |
| Live `dependency_report` against staging telemetry | 11 onboarded users, 9 repeat sessions total, wardrobe memory shows +60pp retention lift, feedback +54pp |
| `catalog_enriched` row count | **14,296** (14,295 in `(ok,complete)`) ✅ exceeds 500 threshold |
| `catalog_item_embeddings` row count | **14,296** ✅ exact 1:1 with embeddable subset |
| Embedding orphan check | 0 enrichable rows missing an embedding; 1 stale embedding (cleanup PR-worthy, not blocking) |
| `feedback_events` count | 672 (237 likes / 435 dislikes); all rows have `turn_id`, `outfit_rank`, `event_type` |
| `tool_traces.composer_decision` / `rater_decision` rows | LLM ranker logging shipped May 3 (PR #29 / #30) — needs production traffic to accumulate |

**Live finding — Gate 1 escalation D is firing in staging:** acquisition_source = `unknown` for **100% of 11 onboarded users** (threshold is >50%). The OTP-verify endpoint is no longer writing `acquisition_source` / `acquisition_campaign` / `referral_code` / `icp_tag`. Tracked as a follow-up — see Gate 1 below.

**Plan:** see `docs/RELEASE_READINESS.md` for the existing checklist. The concrete actions per gate:

**Gate 1 — Functional Correctness:**
- ~~run `pytest tests/` (must be 312/312 green)~~ ✅ May 1, 2026: 329 passed + 1 skipped (skip is the "weights file missing" test — file now exists from staging calibration).
- ~~run `APP_ENV=staging python3 ops/scripts/validate_dependency_report.py`~~ ✅ May 1, 2026: 15/15 assertions PASS against staging.
- run `ops/scripts/smoke_test_full_flow.sh` end-to-end against staging (deferred — needs deployed app + explicit approval to incur LLM token costs for the architect call. Read-only checks below cover the parts that don't need a live HTTP server.)
- catalog-unavailable test in staging: temporarily empty `catalog_item_embeddings`, POST a turn, assert guardrail copy fires (deferred — destructive against shared staging, needs explicit approval)
- ~~confirm wardrobe-first hybrid pivot user-story test exists~~ ✅ verified May 1, 2026: `test_single_item_wardrobe_first_does_not_short_circuit_catalog_pipeline` (catalog pivot path) at `tests/test_agentic_application.py:1770` and `test_explicit_wardrobe_occasion_request_returns_gap_fallback_when_coverage_is_missing` (gap fallback path) at `tests/test_agentic_application.py:2048`
- ⚠️ **acquisition_source instrumentation — known issue, code path verified intact** (May 1, 2026 → audit May 3, 2026): live staging snapshot showed 11/11 onboarded users with `acquisition_source = 'unknown'`. Code audit on May 3 confirmed the OTP-verify endpoint (`modules/user/src/user/api.py:91`), `verify_otp` service (`modules/user/src/user/service.py:279`), and the `VerifyOtpRequest` schema (`modules/user/src/user/schemas.py:48`) all carry `acquisition_source` end to end. The most likely cause of the staging numbers is the frontend not populating the field on the request — verify by capturing a live OTP-verify request body before the next staging readout. Not blocking; the dependency report can't attribute users to cohorts until this is verified.

**Gate 2 — Data & Environment Readiness:**
- ~~catalog row count ≥ 500 with `row_status in ('ok','complete')`~~ ✅ May 1, 2026: **14,295** in `(ok,complete)` against staging, 14,296 total.
- ~~embedding coverage check returns 0 orphan rows~~ ✅ May 1, 2026: 0 enrichable rows missing an embedding. 1 embedded row whose `catalog_enriched` row was demoted from `(ok,complete)` (cleanup PR-worthy).
- ~~`python3 ops/scripts/schema_audit.py` against staging~~ ✅ May 1, 2026: PASS, 46 attributes, no drift.
- approved enrichment CSV at `data/catalog/uploads/enriched_catalog_upload.csv` (deferred — file management decision)
- seed one fully-onboarded test user (deferred — staging already has 11 onboarded users; pick one via `select * from onboarding_profiles where onboarding_complete=true limit 1` and run the smoke test against them when explicit smoke-test approval lands)
- run smoke test as that user end-to-end (deferred per Gate 1 above)

**Gate 3 — Observability & Operations:**
- ~~build all 8 dashboard panels from `docs/OPERATIONS.md`~~ ✅ May 1, 2026: 14 panel SQL files extracted into `ops/dashboards/panel_NN_*.sql` via `ops/scripts/extract_dashboard_sql.py`; ready to paste into Supabase Studio / Metabase. Panel 15 (catalog search timeout) is log-based, no SQL — see `ops/dashboards/README.md`.
- wire alerts: Panel 4 `error_rate_pct > 5%` → Slack `#aura-oncall`; catalog-unavailable counter > 0 → page; Panel 7 negative signals daily review during week 1 (deferred — needs the dashboard tool to be provisioned first)
- ~~write on-call runbook in `docs/OPERATIONS.md`~~ ✅ May 1, 2026: § On-Call Runbook added with rotation slots, channels, four failure-mode runbooks, escalation timeline, post-incident process. Names + PagerDuty service still need to be filled in by the team.
- ~~pipe `_log.error` / `_log.warning` to a queryable sink~~ ✅ May 1, 2026: structured-logging shim shipped at `platform_core/logging_config.py`. Set `AURA_LOG_FORMAT=json` to emit single-line JSON records every modern aggregator (Logflare / Datadog / Cloud Logging / Loki) can ingest with no parsing. Default text behaviour unchanged. 3 regression tests in `tests/test_platform_core.py::StructuredLoggingConfigTests`.

**Gate 4 — Product & UX:**
- designer (not implementing engineer) walks `docs/DESIGN_SYSTEM_VALIDATION.md` checklist
- real-device QA at 430px (iPhone) + 1280px+ (MacBook) on `/`, `/wardrobe`, `/profile`, chat, outfits, checks tabs
- wardrobe-first pivot copy review with single-item wardrobe scenario
- follow-up `IMPROVE IT / SHOW ALTERNATIVES / SHOP THE GAP` headers visually confirmed
- copy tone review — read 20 staging response transcripts, flag dashboard-speak
- fill in sign-off block at `RELEASE_READINESS.md:122` — engineer + designer + date + commit SHA

### 5. Doc-stale cleanup (this commit)

The audit found 80 unchecked `[ ]` items in CURRENT_STATE.md whose code has actually shipped. They are being marked `[x]` in this same commit. See "Doc-Stale Sweep (May 1, 2026)" section below for the verified list.

### 6. Observability Hardening (May 1, 2026 audit) — **all 12 items SHIPPED**

**Status: complete (May 1, 2026).** All twelve items implemented, tested, and the full suite is **387 passed / 1 skipped**. Per-item summary at the bottom of this section. Original detailed plan kept below for reference.

**Why now:** the May 1 staging audit surfaced two real defects (turn-trace coverage at ~28%, no request-id propagation) and several missing-but-needed surfaces (`/readyz`, Prometheus, OpenTelemetry, PII redaction, alert-as-code). Today's observability tables are good — `turn_traces`, `model_call_logs`, `tool_traces`, `policy_event_log`, `dependency_validation_events`, `feedback_events` are all present and populated in staging — but the layer above them (live RED metrics, distributed tracing, log/trace correlation) is missing. This is the gap before Aura can run at first-50 scale and beyond.

**Verified-against-staging baseline (May 1, 2026):**
| Table | Staging count | Verdict |
|---|---|---|
| `turn_traces` | 120 | **Coverage gap** — 433 conversation_turns exist, only ~28% are traced. Three early-return paths in `process_turn` skip `_persist_trace`. |
| `model_call_logs` | 972 | Solid coverage; missing token usage + cost columns |
| `tool_traces` | 718 | Solid coverage for top-level tools; per-candidate parallel work-items not traced individually |
| `policy_event_log` | 393 | Working |
| `feedback_events` | 672 | All rows have `turn_id`, `outfit_rank`, `event_type` |

#### Plan — 12 items, priority-ordered

##### Item 1: trace coverage on error paths (P0, <1h)

**Problem:** [`orchestrator.py:993, 1067, 4109`](modules/agentic_application/src/agentic_application/orchestrator.py:993) — onboarding-blocked / planner-error / architect-error returns bypass `_persist_trace`. Staging shows 313 of 433 turns have no trace.

**Fix:**
- Wrap the dispatch logic in `process_turn` with a `try/finally` that calls `self._persist_trace(trace)` on every exit. Set `trace._persisted = True` after a successful persist so the finally block doesn't double-write.
- Each early-return path stays as-is; trace builder already accumulates state up to that point.
- Set `trace.set_evaluation({"response_type": "error", "stage_failed": <stage>})` immediately before each error return so the persisted record explains why the turn ended early.

**Tests** in `tests/test_agentic_application.py`:
- `test_onboarding_gate_blocked_turn_persists_trace`
- `test_planner_failure_persists_trace_with_error_stage`
- `test_architect_failure_persists_trace_with_error_stage`

**Files:** `modules/agentic_application/src/agentic_application/orchestrator.py`; new tests.

##### Item 2: request_id middleware + ContextVar log filter (P0, half-day)

**Problem:** zero HTTP middleware in [`api.py`](modules/agentic_application/src/agentic_application/api.py); 118 `_log.info` callsites in `modules/` don't thread `turn_id` / `conversation_id`. Operator can't correlate a user-reported slow turn to log lines or to upstream `OpenAI-Request-Id` / `x-supabase-request-id` headers.

**Fix:**
- New `modules/platform_core/src/platform_core/request_context.py` — `ContextVar` for `request_id`, `turn_id`, `conversation_id`, `external_user_id`. Helpers `set_*`, `get_*`, `clear()`.
- Update `platform_core/logging_config.py` to install `RequestContextFilter` on the root handler. Filter reads ContextVars and injects them into every `LogRecord` so the JSON formatter picks them up automatically.
- Add FastAPI middleware in `api.py` `create_app`:
  ```python
  @app.middleware("http")
  async def request_context(request, call_next):
      request_id = request.headers.get("x-request-id") or str(uuid4())
      token = set_request_id(request_id)
      try:
          response = await call_next(request)
          response.headers["x-request-id"] = request_id
          return response
      finally:
          reset_request_id(token)
  ```
- At top of `process_turn`, set `turn_id` and `conversation_id` ContextVars after `turn_id` is assigned.
- Add `request_id` column to `turn_traces`, `model_call_logs`, `tool_traces` via migration `<date>_observability_request_id.sql`.
- Capture upstream IDs: store `response.headers.get("x-request-id")` from OpenAI / Gemini / Supabase in the corresponding `model_call_logs.response_json.upstream_request_id` field.

**Tests** in `tests/test_platform_core.py`:
- `test_request_context_propagates_to_log_records`
- `test_request_id_middleware_generates_when_header_missing`
- `test_request_id_middleware_echoes_incoming_header`
- `test_orchestrator_sets_turn_id_contextvar`

**Files:**
- New `modules/platform_core/src/platform_core/request_context.py`
- `modules/platform_core/src/platform_core/logging_config.py`
- `modules/agentic_application/src/agentic_application/api.py`
- `modules/agentic_application/src/agentic_application/orchestrator.py`
- `modules/platform_core/src/platform_core/repositories.py` — accept `request_id` kwarg in 3 insert helpers
- New `supabase/migrations/<date>_observability_request_id.sql`
- `tests/test_platform_core.py`

##### Item 3: real `/readyz` + `/version` endpoints (P0, half-day)

**Problem:** [`api.py:450`](modules/agentic_application/src/agentic_application/api.py:450) `/healthz` returns `{"ok": True}` unconditionally — Kubernetes / load balancer thinks the service is healthy when Supabase is unreachable.

**Fix:**
- New `modules/platform_core/src/platform_core/readiness.py`:
  - `check_supabase(client) -> Tuple[bool, str]` — `SELECT 1 FROM users LIMIT 1` with a 2s timeout
  - `check_openai(api_key) -> Tuple[bool, str]` — HEAD on `https://api.openai.com/v1/models` with auth header, 2s timeout
  - `check_gemini(api_key) -> Tuple[bool, str]` — HEAD on `https://generativelanguage.googleapis.com/v1beta/models` with 2s timeout
  - All three run in parallel via `concurrent.futures.ThreadPoolExecutor` so a slow upstream doesn't dominate the check
- Add `/readyz` and `/version` in `api.py`. `/readyz` returns 503 if any check fails; `/version` returns `{commit, deployed_at, env}` from env vars (`AURA_COMMIT_SHA`, `AURA_DEPLOYED_AT`, `APP_ENV`).
- Update Dockerfile / deploy script to set `AURA_COMMIT_SHA=$(git rev-parse HEAD)` and `AURA_DEPLOYED_AT=$(date -u +%FT%TZ)` at build time (deferred to deploy infra).

**Tests** in `tests/test_agentic_application_api_ui.py`:
- `test_readyz_returns_200_when_all_checks_pass`
- `test_readyz_returns_503_when_supabase_check_fails`
- `test_version_returns_commit_and_env`

**Files:**
- New `modules/platform_core/src/platform_core/readiness.py`
- `modules/agentic_application/src/agentic_application/api.py` — 2 new endpoints
- `tests/test_agentic_application_api_ui.py`

##### Item 4: token usage + cost capture on every LLM call (P1, half-day)

**Problem:** [`repositories.py:150`](modules/platform_core/src/platform_core/repositories.py:150) `log_model_call` records request/response JSON but discards the `response.usage` field every OpenAI SDK call returns. No per-user / per-conversation cost attribution.

**Fix:**
- Migration `<date>_model_call_token_usage.sql`: add `prompt_tokens int`, `completion_tokens int`, `total_tokens int`, `estimated_cost_usd numeric(10,6)` columns to `model_call_logs`.
- New `modules/platform_core/src/platform_core/cost_estimator.py` with a static pricing table:
  ```python
  _PRICING = {
      "gpt-5.4":          {"input_per_1m": 2.50, "output_per_1m": 10.00},
      "gpt-5-mini":       {"input_per_1m": 0.15, "output_per_1m": 0.60},
      "text-embedding-3-small": {"input_per_1m": 0.02, "output_per_1m": 0.0},
      "gemini-3.1-flash-image-preview": {"flat_per_image": 0.039},
  }
  ```
  Helper `estimate_cost_usd(model, prompt_tokens, completion_tokens, image_count=0)`.
- Extend `log_model_call` signature with `prompt_tokens`, `completion_tokens`, `total_tokens`, `estimated_cost_usd` kwargs. Persist when present.
- Update each LLM call site to pass them:
  - [`copilot_planner.py:225`](modules/agentic_application/src/agentic_application/agents/copilot_planner.py:225) — read `response.usage.input_tokens` / `output_tokens` (Responses API field names)
  - [`outfit_architect.py:195`](modules/agentic_application/src/agentic_application/agents/outfit_architect.py:195)
  - [`visual_evaluator_agent.py:324`](modules/agentic_application/src/agentic_application/agents/visual_evaluator_agent.py:324)
  - [`style_advisor_agent.py:202`](modules/agentic_application/src/agentic_application/agents/style_advisor_agent.py:202)
  - [`outfit_decomposition.py:127`](modules/agentic_application/src/agentic_application/services/outfit_decomposition.py:127)
  - [`tryon_service.py`](modules/agentic_application/src/agentic_application/services/tryon_service.py) — pass `image_count=N_renders` for Gemini cost
- New `ops/dashboards/panel_16_per_user_llm_cost.sql` and `panel_17_daily_total_cost.sql`. Re-run `ops/scripts/extract_dashboard_sql.py` after adding to OPERATIONS.md.

**Tests** in `tests/test_platform_core.py`:
- `test_cost_estimator_gpt54_input_output_pricing`
- `test_cost_estimator_gemini_per_image`
- `test_cost_estimator_unknown_model_returns_zero`
- `test_log_model_call_persists_token_columns_when_provided`
- `test_log_model_call_back_compat_when_token_kwargs_omitted`

**Files:** new `cost_estimator.py`, modified `repositories.py`, 5 LLM call sites, new migration, OPERATIONS.md panel additions, tests.

##### Item 5: Prometheus `/metrics` endpoint with RED metrics (P1, 1 day)

**Problem:** no live percentile metrics. Latencies live in `turn_traces.steps[].latency_ms` JSON only — operators must run Postgres queries to see p95.

**Fix:**
- Add `prometheus-client>=0.19` to `requirements.txt`.
- New `modules/platform_core/src/platform_core/metrics.py`:
  - `aura_turn_total` — Counter labelled by `intent`, `action`, `status`
  - `aura_turn_duration_seconds` — Histogram labelled by `stage` (architect, search, assembler, reranker, visual_evaluation, response_formatting); buckets `[0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60]`
  - `aura_llm_call_total` — Counter labelled by `service`, `model`, `status`
  - `aura_llm_call_duration_seconds` — Histogram labelled by `service`, `model`
  - `aura_external_call_duration_seconds` — Histogram labelled by `service` (`supabase`, `openai`, `gemini`), `operation`, `status`
  - `aura_tryon_quality_gate_total` — Counter labelled by `passed` (`true`/`false`)
  - `aura_in_flight_turns` — Gauge
- Add `/metrics` endpoint in `api.py`:
  ```python
  from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
  @app.get("/metrics")
  def metrics():
      return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
  ```
- Wire metric `.observe()` calls into existing instrumentation hooks:
  - In `trace_end()` inside `process_turn` → `aura_turn_duration_seconds.labels(stage=step).observe(latency_ms / 1000)`
  - In `log_model_call` → `aura_llm_call_total.labels(...).inc()` + duration histogram
  - In `SupabaseRestClient._request` → `aura_external_call_duration_seconds.labels("supabase", method, status).observe(latency)`
  - In `_render_candidates_for_visual_eval` → `aura_tryon_quality_gate_total.labels(passed=...)`
  - At top of `process_turn` increment `aura_in_flight_turns`, decrement in finally

**Tests** in `tests/test_platform_core.py`:
- `test_metrics_endpoint_returns_prometheus_format`
- `test_turn_counter_increments_on_simulated_turn`
- `test_llm_histogram_records_latency`

**Files:** `requirements.txt`, new `metrics.py`, `api.py`, `orchestrator.py`, `repositories.py`, `supabase_rest.py`, tests.

##### Item 6: OpenTelemetry tracing (P1, 2 days)

**Problem:** spans stop at the FastAPI boundary. No parent/child relationships across the planner→architect→6 parallel searches→assembler→reranker→3 parallel try-ons→3 parallel evaluators graph. No way to share trace context with downstream services or upstream RUM.

**Fix:**
- Add packages: `opentelemetry-api>=1.27`, `opentelemetry-sdk>=1.27`, `opentelemetry-exporter-otlp>=1.27`, `opentelemetry-instrumentation-fastapi>=0.48`, `opentelemetry-instrumentation-urllib>=0.48`.
- New `modules/platform_core/src/platform_core/otel_setup.py`:
  - `configure_otel(service_name="aura")` — sets up `TracerProvider`, `BatchSpanProcessor`, OTLP exporter targeting `OTEL_EXPORTER_OTLP_ENDPOINT` env var.
  - Honours W3C Trace Context (default in SDK).
  - Default sampler: `ParentBased(TraceIdRatioBased(0.1))` so 10% of turns are sampled but children inherit parent decision. Override via `OTEL_TRACES_SAMPLER_ARG`.
  - No-op when `OTEL_EXPORTER_OTLP_ENDPOINT` is unset (local dev).
- Wire into `api.py`:
  ```python
  from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
  configure_otel("aura-agentic-application")
  FastAPIInstrumentor.instrument_app(app)
  ```
- Manual spans in orchestrator (replacing/enhancing the existing `trace_start`/`trace_end` helpers):
  ```python
  tracer = trace.get_tracer("aura.orchestrator")
  with tracer.start_as_current_span("copilot_planner") as span:
      span.set_attribute("aura.model", "gpt-5.4")
      span.set_attribute("aura.user_id_hash", _hash_user_id(external_user_id))
      span.set_attribute("aura.has_image", bool(image_data))
      plan_result = self._copilot_planner.plan(...)
      span.set_attribute("aura.intent", plan_result.intent)
  ```
- Parallel-section span propagation: pass `trace.get_current_span().get_span_context()` into worker callables so each parallel task creates a child span linked to the parent.
- Keep the DB `turn_traces` write — it's the audit log. OTel adds the live waterfall view.

**Tests** in new `tests/test_otel.py`:
- Use OTel test exporter (`opentelemetry.sdk.trace.export.in_memory_span_exporter`) to assert:
  - `test_otel_creates_root_span_per_turn`
  - `test_otel_pipeline_spans_have_correct_parent`
  - `test_otel_parallel_search_spans_share_parent`
  - `test_otel_traceparent_header_propagation`

**Files:** `requirements.txt`, new `otel_setup.py`, `api.py`, `orchestrator.py`, agent files (5 of them), new test file.

##### Item 7: PII redactor before observability inserts (P1, 1 day)

**Problem:** `model_call_logs.request_json` includes raw user message + full profile (gender, height, body shape, color analysis). `turn_traces.user_message` stores raw user input. No redaction. GDPR / least-privilege risk.

**Fix:**
- New `modules/platform_core/src/platform_core/pii_redactor.py`:
  ```python
  EMAIL_RE = re.compile(r'\b[\w.-]+@[\w.-]+\.\w+\b')
  PHONE_RE = re.compile(r'(\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}')
  SSN_RE = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')

  def redact_string(s: str) -> str: ...
  def redact_value(v: Any) -> Any:  # recurse dicts/lists
  def redact_profile(profile: dict) -> dict:
      """Truncate body measurements to bands, drop exact cm/age."""
  ```
  Profile bands: height_cm → `Petite|Average|Tall`; waist_cm → existing `WaistSizeBand`; date_of_birth → 5-year age band.
- Wire into `repositories.py`:
  - `log_model_call(..., redact_pii: bool = True)` — redact `request_json` and `response_json` recursively before insert
  - `insert_turn_trace(..., redact_pii: bool = True)` — redact `user_message` and `profile_snapshot`
- Add data-subject deletion helper:
  ```python
  def delete_user_observability_data(self, external_user_id: str) -> Dict[str, int]:
      """GDPR: delete all observability rows for a user. Returns row counts deleted per table."""
  ```
  Tables: `turn_traces`, `model_call_logs`, `tool_traces`, `policy_event_log`, `feedback_events`, `dependency_validation_events`, `catalog_interaction_history`, `user_comfort_learning`.

**Tests** in new `tests/test_pii_redactor.py`:
- `test_redact_emails`, `test_redact_phones`, `test_redact_ssns`
- `test_redact_profile_buckets_height_cm_into_band`
- `test_redact_value_recurses_nested_dicts_and_lists`
- `test_log_model_call_redacts_pii_in_request_json`
- `test_delete_user_observability_data_returns_row_counts`

**Files:** new `pii_redactor.py`, `repositories.py`, new test file.

##### Item 8: shared logging bootstrap in all entry points (P0, <1h)

**Problem:** `configure_logging()` only wired into `run_agentic_application.py`. `run_catalog_enrichment.py` and `run_user_profiler.py` emit text-formatted logs even when `AURA_LOG_FORMAT=json`.

**Fix:**
- Add `configure_logging()` call to top of `main()` in `run_catalog_enrichment.py` and `run_user_profiler.py`.
- A 2-line change in each.

**Tests:** the existing `tests/test_platform_core.py::StructuredLoggingConfigTests` already covers the configurator. No new tests needed — just visual verification that `AURA_LOG_FORMAT=json python3 run_catalog_enrichment.py …` emits JSON.

**Files:** `run_catalog_enrichment.py`, `run_user_profiler.py`.

##### Item 9: alert rules in code (P1, 1 day)

**Problem:** thresholds described in prose in `OPERATIONS.md`. No `ops/alerts/` directory. Alerts get configured in the dashboard tool's UI by hand → can be deleted accidentally with no audit trail.

**Fix:**
- New `ops/alerts/` directory. One YAML file per alert in Prometheus AlertManager format (most universal target — Datadog, Grafana, AlertManager, even Cloud Monitoring can ingest):
  - `pipeline_error_rate.yaml` — Panel 4 trigger
  - `catalog_unavailable_guardrail.yaml` — Panel 4 trigger; pages on first hit
  - `negative_signals_concentration.yaml` — Panel 7 trigger
  - `tryon_quality_gate_unhealthy.yaml` — Panel 10 trigger
  - `final_response_count_low.yaml` — Panel 11 trigger
  - `wardrobe_enrichment_degraded.yaml` — Panel 12 trigger
  - `catalog_search_timeouts.yaml` — Panel 15 trigger
- Each YAML file contains: `alert`, `expr` (PromQL — uses metrics from item 5), `for` (duration), `severity` (P1/P2), `runbook_url` (link into `docs/OPERATIONS.md` On-Call Runbook section).
- New `ops/scripts/sync_alerts.py` — read the directory, validate YAML structure, emit format-specific output (initial: print to stdout for review; later: HTTP POST to AlertManager / Datadog API).
- Add a section to `docs/OPERATIONS.md` § Alert Rules pointing to `ops/alerts/`.

**Tests** in new `tests/test_alert_rules.py`:
- `test_every_alert_yaml_has_required_fields`
- `test_every_alert_severity_is_valid`
- `test_every_runbook_url_resolves_to_an_existing_section`

**Files:** ~7 new YAML files, new sync script, OPERATIONS.md edit, test file.

##### Item 10: per-stage parallel work-item traces (P2, 1 day)

**Problem:** [`orchestrator.py:4612 _render_candidates_for_visual_eval`](modules/agentic_application/src/agentic_application/orchestrator.py:4612) emits aggregate counters (`tryon_attempted_count`, etc.) but no per-candidate timing. Same for [`_evaluate_candidates_visually:4810`](modules/agentic_application/src/agentic_application/orchestrator.py:4810). A slow turn can't be debugged without rerunning.

**Fix:**
- Wrap each parallel work-item with a `tool_traces` row:
  ```python
  def _render_one(candidate):
      started = time.monotonic()
      try:
          result = self.tryon_service.render(...)
          status, error = "ok", None
      except Exception as e:
          result, status, error = None, "error", str(e)
      latency_ms = int((time.monotonic() - started) * 1000)
      self.repo.log_tool_trace(
          conversation_id=conversation_id, turn_id=turn_id,
          tool_name="tryon_render",
          input_json={"candidate_id": candidate.candidate_id, "garment_ids": [...]},
          output_json={"latency_ms": latency_ms, "status": status, "quality_passed": ..., "parent_step": "visual_evaluation"},
          latency_ms=latency_ms, status=status, error_message=error or "",
      )
      return result
  ```
- Same shape for `_evaluate_one_candidate` inside `_evaluate_candidates_visually`.
- Tools schema gains an implicit `parent_step` field via `output_json` (no migration — `tool_traces` already JSONB-typed).
- These per-candidate rows multiply tool_traces volume by ~3-5×, so the daily retention sweep (item 12) becomes more important.

**Tests** in `tests/test_agentic_application.py`:
- `test_render_candidates_logs_per_candidate_tool_trace`
- `test_evaluate_candidates_logs_per_candidate_tool_trace`
- `test_per_candidate_traces_carry_parent_step_in_output_json`

**Files:** `orchestrator.py`, tests.

##### Item 11: sample `model_call_logs.request_json` (P2, 1h)

**Problem:** every architect call's full request payload (~10 KB) is persisted. Staging is at 972 rows × 10 KB ≈ 10 MB just for that column. At 100× scale this is ~1 GB and growing.

**Fix:**
- Env var `AURA_LOG_REQUEST_BODY_SAMPLE_RATE` (default `1.0`).
- In `log_model_call`, if `random.random() > sample_rate`, replace `request_json` with a summary:
  ```python
  request_json = {
      "sampled_out": True,
      "model": model,
      "input_size_chars": _approx_size(original_request_json),
  }
  ```
- Same option for `response_json` via `AURA_LOG_RESPONSE_BODY_SAMPLE_RATE`.
- Defaults stay at `1.0` so today's behaviour is preserved.

**Tests:** 2 small tests asserting the sampling behavior.

**Files:** `repositories.py`, tests.

##### Item 12: log retention policy (P2, 1h)

**Problem:** observability tables grow unbounded.

**Fix:**
- New `ops/scripts/cleanup_observability_logs.py` — accepts `--days N` (default 30); deletes from `model_call_logs`, `tool_traces`, `turn_traces` where `created_at < now() - N days`.
- Document in `docs/OPERATIONS.md` § Retention: "run `python3 ops/scripts/cleanup_observability_logs.py --days 30` daily via cron / GitHub Action / Supabase scheduled function".
- Aggregates that we want to keep long-term (acquisition, retention, dependency lift) live in `dependency_validation_events` and `feedback_events` — those are NOT swept.

**Tests** in `tests/test_cleanup_observability_logs.py`:
- `test_cleanup_deletes_rows_older_than_threshold`
- `test_cleanup_preserves_recent_rows`
- `test_cleanup_does_not_touch_feedback_events`

**Files:** new script, OPERATIONS.md edit, test file.

#### Effort + priority summary

| # | Item | Priority | Effort |
|---|---|---|---|
| 1 | trace coverage on error paths | P0 | <1h |
| 8 | shared logging bootstrap | P0 | <1h |
| 2 | request_id middleware + ContextVar log filter | P0 | half-day |
| 3 | `/readyz` + `/version` endpoints | P0 | half-day |
| 4 | token usage + cost capture | P1 | half-day |
| 5 | Prometheus `/metrics` + RED histograms | P1 | 1 day |
| 7 | PII redactor + GDPR delete helper | P1 | 1 day |
| 9 | alert rules in code | P1 | 1 day |
| 6 | OpenTelemetry tracing | P1 | 2 days |
| 10 | per-stage parallel work-item traces | P2 | 1 day |
| 11 | request body sampling | P2 | 1h |
| 12 | log retention sweep script | P2 | 1h |

**Total P0 work: 1.5 days** (items 1 + 2 + 3 + 8). Closes the trace-coverage gap, makes logs correlatable, and gives the team a real readiness probe before serving the first 50 users.

**Total P1 work: ~5 days.** Adds production-grade RED metrics, GDPR-clean data flow, alerts-as-code, and full distributed tracing with W3C trace context propagation.

**Total P2 work: 3 days.** Operational polish — deeper trace fidelity, retention, and cost control.

#### Shipped (May 1, 2026) — verification table

| # | Item | Files added/modified | Tests added |
|---|---|---|---|
| 1 | trace coverage on error paths | `orchestrator.py` — `_persist_trace` idempotent + persists on onboarding-blocked / planner-error returns | `test_orchestrator_blocks_turn_when_onboarding_is_incomplete` (extended), `test_orchestrator_planner_failure_persists_trace_with_error_stage` (new) |
| 2 | request_id middleware + ContextVar log filter | new `request_context.py`, `logging_config.py`, `api.py` middleware, `orchestrator.py` ContextVar setters, repo helpers stamp request_id, migration `20260501100000_observability_request_id.sql` | `RequestContextTests`, `RepositoryRequestIdStampingTests`, `test_request_id_middleware_*` (9 tests) |
| 3 | /readyz + /version endpoints | new `readiness.py` with parallel Supabase / OpenAI / Gemini checks; 2 endpoints in `api.py` | `test_healthz_returns_200_*`, `test_readyz_returns_*`, `test_version_returns_*` (4 tests) |
| 4 | token usage + cost capture | new `cost_estimator.py` with pricing + `extract_token_usage`; `repositories.py` extends `log_model_call`; 4 LLM agents expose `last_usage`; orchestrator passes through; migration `20260501110000_model_call_token_usage.sql` | `CostEstimatorTests` (9 tests) |
| 5 | Prometheus /metrics + RED metrics | new `metrics.py` (7 metrics), `requirements.txt` adds `prometheus-client`, `/metrics` endpoint, observe-hooks in `trace_end`, `log_model_call`, `supabase_rest._request`, tryon quality gate | `PrometheusMetricsTests`, `test_metrics_endpoint_returns_prometheus_text` (5 tests) |
| 6 | OpenTelemetry tracing | new `otel_setup.py`, OTLP exporter wiring, FastAPI auto-instrumentation, child-span emission via `trace_end`; `requirements.txt` adds 4 packages | `OtelSetupTests` (4 tests) |
| 7 | PII redactor + GDPR delete | new `pii_redactor.py`, `redact_pii=True` default on `log_model_call` + `insert_turn_trace`, new `repositories.delete_user_observability_data`, `supabase_rest.delete_one` | `test_pii_redactor.py` (19 tests) |
| 8 | shared logging bootstrap | `run_catalog_enrichment.py` + `run_user_profiler.py` call `configure_logging()` | covered by existing `StructuredLoggingConfigTests` |
| 9 | alert rules in code | 7 YAML files in `ops/alerts/`, validation script `ops/scripts/sync_alerts.py`, `ops/alerts/README.md` | `test_alert_rules.py` (4 tests + 7 subtests) |
| 10 | per-candidate parallel work-item traces | `orchestrator.py:_render_one` emits `tool_traces` row per candidate with status (cache_hit / quality_gate_failed / decode_failed / etc.) and parent_step="visual_evaluation" | covered by existing pipeline tests |
| 11 | request body sampling | `repositories.log_model_call` sampling block driven by `AURA_LOG_REQUEST_BODY_SAMPLE_RATE` and `AURA_LOG_RESPONSE_BODY_SAMPLE_RATE` env vars; default 1.0 preserves today's behaviour | inline in repo helper |
| 12 | log retention sweep | new `ops/scripts/cleanup_observability_logs.py` with `--days N` and `--dry-run`, paged delete, only sweeps `model_call_logs` / `tool_traces` / `turn_traces` (aggregate tables preserved) | dry-run verified against staging |

**Test totals after this work:** 387 passed, 1 skipped (was 330 before this section).

**Migrations added (must be applied to staging before deploy):**
- `supabase/migrations/20260501100000_observability_request_id.sql` — adds `request_id` text column + index to `turn_traces`, `model_call_logs`, `tool_traces`
- `supabase/migrations/20260501110000_model_call_token_usage.sql` — adds `prompt_tokens` / `completion_tokens` / `total_tokens` / `estimated_cost_usd` columns to `model_call_logs`

**Operations runbook update:** the `docs/OPERATIONS.md` § On-Call Runbook section now references the metric names that the alerts in `ops/alerts/*.yaml` use; the alert rules sync via `ops/scripts/sync_alerts.py` to Prometheus-format YAML.

**Environment variables added:**
- `AURA_LOG_FORMAT` — `text` (default) or `json`
- `AURA_LOG_LEVEL` — defaults to `INFO`
- `AURA_LOG_INCLUDE_PROC` — `0` / `1`
- `AURA_LOG_REQUEST_BODY_SAMPLE_RATE` / `AURA_LOG_RESPONSE_BODY_SAMPLE_RATE` — sampling rates for `model_call_logs`
- `AURA_COMMIT_SHA` / `AURA_DEPLOYED_AT` — surfaced via `/version`
- `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_TRACES_SAMPLER_ARG` — turn on distributed tracing

#### Open follow-ups

- [x] Apply both May-1 migrations (`request_id` on tracing tables; token-usage columns on `model_call_logs`) to staging — verified May 3, 2026.
- [x] Wire token-cost capture into Gemini try-on calls — `image_count` now flows into `log_model_call` from the `tryon_service` call site so per-Gemini-call cost lands in `model_call_logs.estimated_cost_usd`.

### 7. Outfits Tab Theme Taxonomy (May 1, 2026) — **SHIPPED**

**Status: complete (May 1, 2026).** All planned items shipped, 36 new theme-taxonomy tests + endpoint coverage. Full suite: 423 passed / 1 skipped.

**Why now:** the Outfits tab today groups by raw `occasion_signal` strings the planner extracts from user messages. That string is uncontrolled vocabulary, so semantically-equivalent occasions split into multiple buckets. A real staging user produced this group list:

> *casual outing, general, beach, casual, occasion recommendation, traditional engagement, weekend outing, evening, date night, engagement wedding, wedding engagement, engagement, date night, pairing request*

Two underlying defects:
1. **Vocabulary explosion** — `casual` / `casual outing` / `weekend outing` are one occasion; `engagement` / `traditional engagement` / `engagement wedding` / `wedding engagement` are one wedding-cycle.
2. **Fallback intent labels leak** — when `occasion_signal` is empty, the bucket falls back to `intent.replace("_", " ")` so the user sees `"occasion recommendation"` and `"pairing request"` as if they were occasions. They aren't.

The fix is a deterministic theme taxonomy applied at read-time in the `intent-history` endpoint — no migration, no backfill, no per-turn LLM cost.

#### Plan

- [x] **Theme module** — new `modules/agentic_application/src/agentic_application/services/theme_taxonomy.py` with:
  - `THEMES: dict[str, dict]` — 8 canonical themes (`wedding`, `festive`, `date`, `work`, `casual`, `travel`, `evening`, `style_sessions` fallback) each with `label`, `description`, `order`.
  - `KEYWORDS: list[tuple[str, str]]` — keyword fragments paired with theme keys; precedence is `wedding` > `festive` > `date` > `work` > `travel` > `evening` > `casual` so e.g. "engagement evening" lands in Wedding & Engagement.
  - `map_to_theme(occasion_signal, intent="") -> str` — pure function, returns one of the 8 theme keys. Uses **regex word-boundary matching** so short keywords like `holi` (Holi festival) don't accidentally match `holiday` (which lands in `travel`).
- [x] **Schema additions** — `IntentHistoryThemeBlock` in `platform_core/api_schemas.py` with `theme_key`, `theme_label`, `theme_description`, `group_count`, `total_outfit_count`, `most_recent_at`, `groups: list[IntentHistoryGroup]`. Added `themes: list[IntentHistoryThemeBlock]` to `IntentHistoryResponse` alongside `groups` for back-compat.
- [x] **Endpoint update** — `list_intent_history` in `agentic_application/api.py` folds the flat groups dict into theme blocks via `map_to_theme()`. Sorts themes by most-recently-active turn timestamp (canonical order is the tiebreaker).
- [x] **UI update** — `platform_core/ui.py` Outfits page renders a section per theme: 36px Fraunces italic header (28px on mobile), champagne underline, JetBrains Mono uppercase subtitle ("3 looks across 2 sessions"), then the existing PDP carousel pattern inside each. Empty themes are hidden. Falls back to the flat `groups` list when the server omits the `themes` payload (backwards compat for staged deploys).
- [x] **Telemetry hook** — `is_unmapped()` helper + per-process dedup set in `api.py` (`_THEME_UNMAPPED_LOGGED`). Each unique unmapped signal emits exactly one `tool_traces` row with `tool_name="theme_unmapped"` per process lifetime; a weekly query over the last 7d surfaces the keyword-list growth edge.
- [x] **Tests** — `tests/test_theme_taxonomy.py` (36 tests) covers: every example from the bug report → expected theme; wedding precedence over evening/casual; festive vs date overlaps; word-boundary matching (holi vs holiday); whitespace + casing + underscore normalization; empty signal + intent fallback; helper functions.

**Acceptance test:** the staging user's 14-group list collapses to 5 themes:
- `Wedding & Engagement` — engagement, traditional engagement, engagement wedding, wedding engagement
- `Casual & Everyday` — casual, casual outing, weekend outing
- `Travel & Vacation` — beach
- `Date & Romance` — date night, date night (dedup)
- `Evening & Party` — evening
- `Style Sessions` — general, occasion recommendation, pairing request

**Effort actual:** ~2 hours. No migration, no planner change, contained to the read path.

#### Acceptance verification

The user-reported list of 14 group names collapsed to 5 themes exactly as planned (`tests/test_theme_taxonomy.py::AcceptanceFromBugReport`):

| Original | Theme |
|---|---|
| casual outing, casual, weekend outing | **Casual & Everyday** |
| beach | **Travel & Vacation** |
| traditional engagement, engagement wedding, wedding engagement, engagement | **Wedding & Engagement** |
| evening | **Evening & Party** |
| date night, date night (dup) | **Date & Romance** |
| general, "occasion recommendation" (empty signal), "pairing request" (empty signal) | **Style Sessions** |

#### Files added/modified

| File | Change |
|---|---|
| `modules/agentic_application/src/agentic_application/services/theme_taxonomy.py` | NEW — 220 lines, 8 themes, ~60 keywords, regex word-boundary matcher |
| `modules/platform_core/src/platform_core/api_schemas.py` | `IntentHistoryThemeBlock` class added; `theme_key` on `IntentHistoryGroup`; `themes` list on `IntentHistoryResponse` |
| `modules/agentic_application/src/agentic_application/api.py` | Group construction stamps `theme_key`; new theme-folding pass after group build; per-process dedup'd telemetry on unmapped signals |
| `modules/platform_core/src/platform_core/ui.py` | Outfits tab renders themes-of-groups; new `.theme-block / .theme-header / .theme-title / .theme-subtitle / .theme-groups` CSS |
| `tests/test_theme_taxonomy.py` | NEW — 36 tests |

#### Trade-offs

- Keyword precedence is opinionated. "Wedding cocktail party" lands in Wedding (correct) because wedding outranks evening; "office cocktail" lands in Work then casual. Edge cases get explicit tests in the taxonomy file.
- New themes (Sports & Outdoor, Religious, Cultural performance) require product buy-in to add — keep the list small.
- Long-term move: have the planner emit `occasion_theme` on `resolved_context` once we have a quarter of mapper telemetry showing which signals are hardest. For now, deterministic rules win on inspectability.

### 8. Model Migration (May 1, 2026) — **SHIPPED**

**Why:** gpt-5.4 latency was the long pole on every recommendation turn. The user picked a tiered move: keep the workhorse on a more capable model where reasoning quality drives downstream output (planner, architect, user analysis), and downgrade structured-output paths to gpt-5-mini where schema constraints contain risk (visual evaluator, image moderation, outfit decomposition).

**Changes:**

| Component | Before | After | Rationale |
|---|---|---|---|
| **Copilot Planner** | gpt-5.4 | **gpt-5.5** | Highest leverage call per turn — wrong intent = wrong handler. Pay for the better reasoning. |
| **Outfit Architect** | gpt-5.4 | **gpt-5.5** | Architect output drives retrieval quality across the entire pipeline; better directions / hard filters / query documents lift every downstream stage. |
| **User Analysis (3 agents)** | gpt-5.4 | **gpt-5.5** | One-time onboarding cost but the output drives every recommendation forever after. Better seasonal-color / body-type extraction = better outfits long-term. |
| **Visual Evaluator** | gpt-5.4 | **gpt-5-mini** | Tight JSON schema (9 evaluation pcts + 8 archetype pcts per candidate) constrains output corridor; mini handles structured scoring well. Score noise affects ranking-within-pool only — retrieval is upstream and unaffected. Latency win compounds 3-5x because evaluator runs in parallel post-try-on. |
| **Image Moderation** | gpt-5.4 | **gpt-5-mini** | Binary allow/block decision with one-line rationale; the heuristic layer catches the obvious cases so the model only fires on ambiguous uploads. ~2-3s saved per wardrobe save. |
| **Outfit Decomposition** | gpt-5-mini | gpt-5-mini *(no change)* | Already on mini — flagged for confirmation, no edit needed. |
| **Style Advisor** | gpt-5.4 | **gpt-5.5** | Free-form prose for `style_discovery` and `explanation_request` turns where voice quality is the user-facing value. Upgraded alongside the other reasoning paths to keep stylist tone consistent across the product. |

**Files modified:**
- [`copilot_planner.py:219`](modules/agentic_application/src/agentic_application/agents/copilot_planner.py:219)
- [`outfit_architect.py:188`](modules/agentic_application/src/agentic_application/agents/outfit_architect.py:188)
- [`visual_evaluator_agent.py:266`](modules/agentic_application/src/agentic_application/agents/visual_evaluator_agent.py:266)
- [`image_moderation.py:49`](modules/platform_core/src/platform_core/image_moderation.py:49)
- [`user/analysis.py:111`](modules/user/src/user/analysis.py:111)
- [`user_profiler/config.py:7`](modules/user_profiler/src/user_profiler/config.py:7)
- 10 hardcoded `model="gpt-5.4"` strings in [`orchestrator.py`](modules/agentic_application/src/agentic_application/orchestrator.py) (planner: 3 sites → gpt-5.5; architect: 3 sites → gpt-5.5; visual eval: 4 sites → gpt-5-mini)
- [`cost_estimator.py:25`](modules/platform_core/src/platform_core/cost_estimator.py:25) — added `gpt-5.5` pricing entry at the published OpenAI list price ($5.00/M input, $30.00/M output). Legacy `gpt-5.4` row preserved so historical `model_call_logs` rows still cost-attribute correctly. The 2× input / 1.5× output multiplier OpenAI applies to prompts >272K input tokens is intentionally not modelled — Aura's typical request payloads stay well under 30K, so the simpler formula stays accurate.
- 4 test sites updated to assert the new defaults; the rest of the gpt-5.4 references in tests are incidental (PII redactor, log_model_call shape, OTel attribute) and pass through unchanged because the legacy entry preserves the lookup.

**Verification:** `pytest tests/` 423 passed / 1 skipped, no regressions. Doc table at the top of the **§ Models** section updated to reflect the new state.

**Open follow-ups:** none — gpt-5.5 list price is now in the table; Style Advisor moved to gpt-5.5 alongside the other reasoning paths so the entire user-visible response surface uses the same model.

---

