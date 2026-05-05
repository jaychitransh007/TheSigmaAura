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

## Telemetry follow-up — visual_eval on-demand uptake

**Status:** queued · **Cost:** dev time only · **Risk:** none

May 5, 2026 shipped the on-demand visual_evaluator: default recommendation cards carry Rater-only dims with `visual_evaluation_status="pending"`, and a "Get a deeper read" CTA on each card calls `POST /v1/turns/{turn_id}/outfits/{rank}/visual-eval` to populate the full 17-dim radar lazily. Outfit_check + garment_evaluation handlers still run the evaluator inline (the user's photo upload IS the intent signal there).

What we need to learn from production:

- **Click-through rate.** New event `visual_evaluator_on_demand` shows up in `model_call_logs` whenever the CTA fires. Wire a panel that reports clicks/turn over a rolling 7-day window. Hypothesis: if <5% of shipped cards get clicked, the post-render check is rarely catching anything → schedule a follow-up to consider dropping `visual_evaluator` entirely (option c). If >30%, the deeper read is genuinely valued → invest in richer Rater output so the default card carries more signal too.
- **Time-to-click.** Distribution would tell us whether users decide quickly (signal: card content is missing something) or slowly (signal: idle scrutiny). Use as a sanity check on the CTA copy.
- **Re-click on cached cards.** If users return to the same turn and re-click, the cache should hit and the eval shouldn't re-run. Verify via the idempotent path in `run_on_demand_visual_eval`.

**Trigger:** review the dashboard ~4 weeks after rollout (around June 2, 2026).

---

## Eval + observability — planner moved to gpt-5-mini (May 5, 2026)

**Status:** queued · **Cost:** dev time only · **Risk:** medium (routing accuracy regression would be user-visible)

May 5, 2026 swapped CopilotPlanner from `gpt-5.5` → `gpt-5-mini` ([copilot_planner.py:220](modules/agentic_application/src/agentic_application/agents/copilot_planner.py:220)) on the argument that strict-JSON-schema enums make the planner's task structurally similar to other gpt-5-mini callers (Composer, Rater, visual_evaluator), and the architecture-grade reasoning (body × palette × occasion → catalog queries) lives downstream in OutfitArchitect, which stays on gpt-5.5. Pricing ratio is ~33× (gpt-5.5 input $5/M, gpt-5-mini input $0.15/M) so the planner line item should drop from ~$0.041/turn → ~$0.001/turn — meaningful given planner runs on every turn including non-recommendation ones.

**The change shipped without an offline eval first.** Validating it as production data accumulates:

1. **Offline routing-accuracy eval.** Pull ~200 historical planner inputs from `tool_traces` (across all 8 intents). Run each through both `gpt-5.5` and `gpt-5-mini` with the existing prompt. Compare:
   - Intent label match rate (gate ≥95%)
   - Action label match rate (gate ≥98% — action drives dispatch, miss = wrong handler ships)
   - `purchase_intent` / `target_piece` / `is_followup` accuracy
   - Subjective spot-check on `assistant_message` tone (50 samples by hand — this is the only stylist-voice text the user sees on advisor intents before the StyleAdvisor takes over)

   Scaffold this as a new mode of `ops/scripts/run_agentic_eval.py` (model-comparison mode). If gpt-5-mini misses on routing fields, revert and instead trim the planner prompt.

2. **Production observability — planner-failure rate.** Wire a Grafana panel for the rolling 7-day rate of `clarification` actions and `error` paths attributed to the planner. A spike post-May-5 = mini misclassifying.

3. **Production observability — `purchase_intent` accuracy proxy.** When the planner sets `purchase_intent=true` on a `garment_evaluation` and the user dismisses the buy/skip verdict block without engaging, that's a soft signal of misclassification. Track engagement vs dismissal rate before vs after the swap.

**Trigger to act on item 1:** within 1 week of merge, while the gpt-5.5 baseline is still fresh in production traces. Items 2–3 are ongoing — no specific trigger, just wire the panels and watch.

**Rollback path:** swap the default in [copilot_planner.py:220](modules/agentic_application/src/agentic_application/agents/copilot_planner.py:220) back to `"gpt-5.5"`; the orchestrator's log/trace sites read from `self._copilot_planner._model` so they pick up the change automatically. One-line revert.

