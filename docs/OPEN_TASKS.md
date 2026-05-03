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

## Pipeline latency — 4m31s end-to-end on `daily office wear` turn

**Status:** queued · **Cost:** dev time only · **Risk:** medium

Turn `86a0a95f-ae12-4cea-9b03-238b30d50b27` (May 3, 2026 — "Find me an outfit to buy for daily office wear") shipped successfully but took **4m31s end-to-end**. The dominant stages:

| Stage | Latency | Model |
|---|---|---|
| outfit_rater | 72.9s | gpt-5-mini |
| outfit_composer | 72.0s | gpt-5-mini |
| visual_evaluation | 64.3s | gpt-5-mini (×3 candidates) |
| outfit_architect | 37.5s | gpt-5.5 |

70+ second gpt-5-mini calls are abnormal — should be 5-10s each. Hypotheses to investigate:
1. **Composer retry-on-hallucination firing too often.** The 16K total tokens for one Composer turn suggests two attempts. Look at `tool_traces.composer_decision` for retry-fire rate.
2. **Long output tokens (10 outfits × full rationale).** Trim the Composer's `up to 10 outfits` cap to 5–6 if the speedup justifies it.
3. **gpt-5-mini queue depth at the provider.** Check whether latency spikes correlate with time-of-day or burst traffic.

**Trigger to act:** more than two production turns over 60s wallclock, OR the operations p95-latency dashboard crosses 30s.

---

## Per-turn cost too high — $0.29 on a single recommendation

**Status:** queued · **Cost:** dev time only · **Risk:** low

Same turn as above billed $0.29 USD. Breakdown:

| Call | Cost | % of turn |
|---|---|---|
| outfit_architect (gpt-5.5) | $0.127 | 43% |
| virtual_tryon ×3 (Gemini) | $0.117 | 40% |
| copilot_planner (gpt-5.5) | $0.041 | 14% |
| Everything else (Composer, Rater, visual_eval, embedding) | $0.012 | 4% |

The architect alone pays nearly half the bill (10.5K tokens at gpt-5.5 pricing). Two angles to attack:

- **Architect prompt size.** PR #29 trimmed it to 4.8K tokens but it can shrink further — anchor + follow-up modules are conditionally appended; review if the base prompt has dead sections.
- **Try-on render count.** 3 × Gemini renders at $0.039 each. If the LLM Rater's `fashion_score` is highly predictive of which outfits would render well, render only the top 1 first and over-render only on visual-eval failure.

**Trigger to act:** $0.30+/turn average sustained, or the LLM-cost-budget alert fires.

---

## Misleading `virtual_tryon` stage emit at end of pipeline

**Status:** queued · **Cost:** small (telemetry-only, doc + rename) · **Risk:** none

The `turn_traces.steps[]` shows `visual_evaluation` finishing BEFORE `virtual_tryon`, which reads as "we evaluated outfits before rendering try-ons." Reality: the actual Gemini renders happen INSIDE the `visual_evaluation` stage (via `_render_candidates_for_visual_eval`). The `virtual_tryon` emit at line 5229 of `orchestrator.py` is a post-formatting `_attach_tryon_images()` cache-lookup step — not a render. That's why its latency is 462ms (cache hits) while the actual renders sum to ~80s inside `visual_evaluation`.

Two cleanup options:
- **Rename** the late stage from `virtual_tryon` to `attach_tryon_images` so dashboards stop misreading "try-on takes 462ms".
- **Restructure** so try-on render gets its own stage emit BEFORE `visual_evaluation` and the steps[] timeline reads chronologically: `... → tryon_render → visual_evaluation → response_formatting`.

Renaming is the quick fix; restructuring is the right fix.

---

## Visual evaluator scope reduction — overlap with the LLM Rater

**Status:** queued · **Cost:** small · **Risk:** medium (UI dependency)

Since PR #30, the Composer + Rater LLM ranker scores outfits on `occasion_fit`, `body_harmony`, `color_harmony`, `archetype_match` (text-only, pre-render). The visual evaluator independently scores 5+4 dimensions from the rendered try-on image (post-render, vision-grounded). Some of these overlap.

Three trim options to consider, in increasing aggressiveness:
- **(a) Drop the 4 context-gated dimensions** from the visual evaluator (occasion_fit, weather_time, specific_needs, pairing_coherence) since they overlap with Rater. Keep the 5 always-evaluated (body, color, style, risk, comfort) — those need vision grounding.
- **(b) Run visual_evaluator on top-1 only,** not all 3 candidates. Saves 2/3 of the cost + latency.
- **(c) Drop visual_evaluator entirely.** Wire the Rater's 4 dim scores to the radar chart on the PDP card. Most aggressive — saves 64s of pipeline time AND $0.0025/turn AND simplifies the code path. Cost: lose the post-render image check (Gemini render artifacts won't get caught) AND the radar chart loses 5 dims it currently shows (need to redesign).

**Trigger:** if pipeline latency follow-up confirms visual_eval is the slowest cuttable stage, OR if Rater quality is good enough that the post-render check is rarely catching anything.

---

## Cost rollup gap — `outfit_check` and `garment_evaluation` handlers

**Status:** queued · **Cost:** small · **Risk:** none

PR #38 wired `total_cost_usd` rollup for the recommendation pipeline (planner, architect, composer, rater, visual_evaluator, virtual_tryon, catalog_embedding). Two other handler paths still log to `model_call_logs` but their cost doesn't roll up to `turn_traces.evaluation.total_cost_usd`:

- `_handle_outfit_check` — visual evaluator on the user's photo (`orchestrator.py:5862`)
- `_handle_garment_evaluation` — try-on + visual evaluator on a garment upload (`orchestrator.py:6304`)

Wire each `repo.log_model_call(...)` callsite there with `trace.add_model_cost_from_row(...)` — same pattern PR #38 used in the recommendation flow. Each handler signature also needs a `trace: Optional[TurnTraceBuilder] = None` parameter threaded from `process_turn`.

**Trigger:** when ops needs per-turn cost on outfit_check / garment_evaluation paths (likely when those flows hit ≥10% of weekly volume).
