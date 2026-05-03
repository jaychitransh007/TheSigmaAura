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

## Catalog vocabulary consolidation — Phase 3 of the May-3 occasion-tag refactor

**Status:** parked · **Cost:** small if no vision re-run · **Risk:** low

Once Phase 2 lands, the catalog still has a few intrinsic-attribute columns with rare or near-duplicate values worth consolidating:

- `GarmentSubtype`: merge `pants` (107 rows) → `trouser`; merge `jeggings` (9) → `jeans`; drop / re-tag the rare values with ≤5 items (`dungarees`, `ethnic_set`, `tracksuit`, `kaftan`, `leggings`, `poncho`).
- `GenderExpression`: merge `androgynous` (12 rows) → `unisex`.
- `TimeOfDay`: merge `night` (8 rows) → `evening`.
- Drop the single `(null)` row across each categorical field (or fix it).

Pure SQL `UPDATE` migration — no LLM calls, no embedding changes.

**Trigger to do this:** if the architect's `target_garment_subtypes` start producing zero-result hard-filter queries on the rare subtypes, or if a future migration audit flags the inconsistency.

---

## Reranker calibration curve fit

**Status:** data-blocked · **Cost:** ~1 day of dev when data is ready · **Risk:** low

The plumbing landed May 1, 2026: `reranker_decision` rows in `tool_traces`, `data/reranker_weights.json` loader, and the skeleton `ops/scripts/calibrate_reranker.py`. The skeleton runs against staging today and emits default weights + observability metrics (rank-position like-rate spread).

The full Ridge fit replacing those defaults needs **≥200 labelled turns** to be statistically meaningful. Until staging traffic accumulates that volume, the script intentionally keeps emitting defaults.

**Trigger to do this:** when `tool_traces` has ≥200 rows where `tool_name='reranker_decision'` AND `feedback_events` joins to those turns.
