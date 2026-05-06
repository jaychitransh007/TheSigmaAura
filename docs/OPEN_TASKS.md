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
