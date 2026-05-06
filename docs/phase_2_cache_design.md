# Phase 2 Cache — Design

**Status:** decisions locked May 13 2026. Code starts after this doc merges.

Locks the cluster-key shape, prompt-versioning approach, and multi-tenancy posture so 2.1 / 2.2 / 2.3 don't relitigate them mid-PR.

---

## Goal

Cache the *output* of the architect and composer keyed on slow-moving user attributes plus per-turn signals. Hit → skip the LLM call entirely (~32s saved on the architect+composer combined stage post-Phase-1.4). Miss → run the LLM and populate the cache. Hit rate grows organically as alpha traffic accumulates.

Per the [OPEN_TASKS Phase 2 plan](OPEN_TASKS.md), expected hit rate ramp: 0% day 1, ~30% by day 7, ~70% by week 4.

---

## Profile cluster — 3 dimensions, 36 buckets

The cluster captures the **slow-moving** parts of `UserContext` that materially shape the architect's output. Per-turn variables (intent, occasion, formality, season) live in the full cache key, not the cluster.

| Dimension | Source | Values | Cardinality |
|---|---|---|---|
| `gender` | `UserContext.gender` | feminine, masculine, unisex | **3** |
| `season_group_broad` | `derived_interpretations.SeasonalColorGroup` collapsed to broad season | spring, summer, autumn, winter | **4** |
| `frame_structure` | `derived_interpretations.FrameStructure` | slim, medium, sturdy | **3** |

**Total buckets:** 3 × 4 × 3 = **36**.

### Why these three (and not others)

- `gender` — drives garment_category eligibility (top/bottom/dress) and most-different sub-segment of catalog. Highest leverage.
- `season_group_broad` — drives palette eligibility; collapsed from 12 sub-seasons to 4 broad seasons because sub-season nuance is preserved in the architect's *prompt input* (not stripped) — the cluster just buckets at coarse granularity for hit-rate purposes. A "Light Spring" user and a "Bright Spring" user can share architect directions like "soft pastels" because the architect re-derives sub-season from the full input on cache *miss*. On *hit* we accept that nuance is folded into the broader cluster.
- `frame_structure` — drives silhouette + fit recommendations. Three coarse buckets (slim/medium/sturdy) is enough to differentiate "drape vs structure" advice.

### Why NOT these

- `archetype` — dropped from data model May 2026 (per project_overview memory).
- `risk_tolerance` (conservative/balanced/expressive) — only one of the three retained style preferences. Dropping it loses some "user prefers bold" signal but most outfits cleared the rater regardless of risk_tolerance in baseline data. Add later if hit-rate dashboard shows under-served clusters where risk_tolerance variance matters.
- `HeightCategory` (short/medium/tall) — affects fit/proportion advice but lower leverage than frame_structure. Skip; revisit if rater scores diverge by height within a cluster.
- `ContrastLevel` — already captured (loosely) in `season_group_broad` via the seasonal palette structure.
- `profile_richness` — affects how the architect *uses* its inputs (more guesses on minimal profiles), not what those inputs *are*. Don't bucket on it.

### Refinement plan

If hit rate is too low or quality regressions appear, refine by:
1. Splitting the largest bucket (likely `feminine × autumn × medium`) using `risk_tolerance` or `HeightCategory`.
2. Don't add dimensions globally — only split clusters that show low hit rate AND high traffic. Keeps total bucket count growing slowly.

---

## Full cache keys

### Architect cache key

```
hash(
  intent,                          # ~6 values (planner-emitted)
  profile_cluster,                 # 36 buckets (above)
  occasion_signal,                 # ~45 values (from occasion.yaml)
  calendar_season,                 # 4 values (computed from current date)
  formality_hint,                  # ~5 values (planner-emitted)
  architect_prompt_version,        # SHA1 hex prefix of prompt text
)
```

- `intent` and `formality_hint` come straight from `CopilotResolvedContext` (planner output).
- `calendar_season` is a Python helper: month → spring/summer/autumn/winter (Northern Hemisphere; revisit if/when we serve users elsewhere).
- `occasion_signal` is normalized to lowercase canonical form before hashing.

**Why these and not the full UserContext:** the cluster captures stable user attributes; the rest of UserContext (analysis_attributes, derived_interpretations beyond cluster keys, conversation_memory, previous_recommendations, user_message verbatim) varies per turn and is too granular to cache. The architect re-derives those on cache miss; on cache hit we accept that the cached direction is "good enough" for any user in the cluster sending this intent+occasion+formality.

### Composer cache key

```
hash(
  architect_direction_id,          # SHA1 of the cached architect output
  retrieval_result_fingerprint,    # SHA1 of sorted SKU id list
  profile_cluster,                 # same 36 buckets
  composer_prompt_version,         # same versioning approach as architect
)
```

- `architect_direction_id` ties composer cache to the specific architect output (cached or fresh).
- `retrieval_result_fingerprint` = `sha1(sorted(retrieved_sku_ids))`. Different SKUs → different cache key. Prevents stale outfits when the catalog changes.
- `profile_cluster` is included because the composer also conditions on user attributes (body harmony, color palette).

---

## Prompt versioning — hash on startup

**Decision:** hash the prompt text at process startup. Use the first 8 hex chars of `sha1(prompt_text)` as the version string.

```python
# at module load in outfit_architect.py / outfit_composer.py
import hashlib
_PROMPT_TEXT = _load_prompt()
PROMPT_VERSION = hashlib.sha1(_PROMPT_TEXT.encode()).hexdigest()[:8]
```

### Why hash, not explicit `version: 1` field

| | Hash on startup | Explicit version field |
|---|---|---|
| Auto-invalidates on prompt edit | ✅ | ❌ requires human bump |
| Debuggable in logs | ⚠️ 8-char hex (`a3f1c2b9`) | ✅ readable (`v1`) |
| Risk of forgetting to bump | ✅ none | ❌ silent staleness |
| Migration impact | ✅ first deploy → all entries miss → re-populate | same |

Hash wins on the safety-critical axis (no human discipline → no silent staleness → no quality regression from stale cache hitting a new prompt). The 8-char hex shows up in every log line; copy-paste to grep.

### Versioned prompts in catalog

Both `prompt/outfit_architect.md` and `prompt/outfit_composer.md` are read-once at module load. Hash captures the loaded text. If we later add prompt fragments that get composed at request time (e.g., per-occasion injections from `knowledge/style_graph/`), the hash also needs to cover those injections — but that's a Phase 4 problem (composition engine) and not in scope for Phase 2.

---

## Multi-tenancy hooks

Per the [OPEN_TASKS cross-cutting section](OPEN_TASKS.md#cross-cutting--multi-tenancy-data-hooks):

1. **`architect_direction_cache` and `composer_outfit_cache` tables get `tenant_id TEXT NOT NULL DEFAULT 'default'`** — included in the migration. Single-line addition, painful retrofit later.
2. **Cache values stay catalog-independent.**
   - Architect cache stores the structured `direction` object (silhouettes, formality, palette guidance) — never product_ids.
   - Composer cache stores the structured `outfit` objects keyed by `composer_id` and item attributes — but the items themselves come from the retrieval step, not the cache. The fingerprint already enforces this: different SKUs → different cache key → no stale catalog references.
3. **Cluster key stays catalog-neutral.** Profile cluster is derived from `UserContext`, not from any catalog state.

The cache is not multi-tenant-aware in *behavior* (single tenant today), but the schema supports it from day 1 — a future migration to per-tenant retrieval just adds `tenant_id = $1` to lookups.

---

## TTL + invalidation

- **TTL:** 14 days. Refreshed on access (`last_used_at` column). Entries idle for 14 days get pruned by a daily cron (`ops/scripts/prune_stale_cache.py`, 2.5 follow-up). Most clusters hit the active-set quickly; long-tail clusters expire and re-populate as needed.
- **Prompt-version invalidation:** included in the cache key. Prompt edit → new hash → new key space → old entries become unreachable + expire via TTL. No explicit DELETE needed.
- **No manual invalidation API.** If we later need ops-time invalidation (e.g., a bad architect direction gets cached and we want to nuke it), add an admin endpoint then. Until then keep it simple.

---

## Test gate (revised from OPEN_TASKS.md)

Original gate assumed Phase 1 landed cold-path at ~25s. Phase 1.4 actually lands at ~47s pre-tryon (post gpt-5.2 swap). Realistic Phase 2 expectations:

- Cache hit rate after 1 week of alpha traffic: ≥30%
- Cache hits: <100ms architect + composer combined latency
- Cache misses: same as Phase 1.4 baseline (~47s pre-tryon)
- Quality unchanged on cache hits (cached output identical to fresh LLM output for the same key — verified by sampling 20 cluster hits in week 2)
- **p95 across mixed traffic: ≤45s by week 1, ≤30s by week 4** (down from "≤15s" in the original doc, which was based on optimistic Phase 1 assumptions)

OPEN_TASKS.md will be updated to match these numbers in the same PR series.

---

## What this design does NOT cover

- **Embedding cache.** The OpenAI embedding API call (3-8s, highly variable) runs on every cache hit because retrieval still needs the embedded query. A separate `query_text → embedding` cache could shave ~3-5s per turn. Out of Phase 2 scope; logging it as a Phase 3 candidate (prompt compression's neighbor: cache the embedded *query texts* the architect emits).
- **Rater cache.** The rater always runs (~6.5s) because it scores the specific outfit slate, which depends on retrieval results that vary per turn. Caching rater output requires the retrieval-fingerprint trick same as composer — easy to add later if rater latency stays meaningful.
- **Try-on cache.** Already exists pre-Phase-2 (`virtual_tryon_cache_hit` rows in production traces). Cached by garment IDs, not by user/intent. Untouched.

---

## Build order

1. **2.1** profile clustering function (this design lockable in code)
2. **2.2** architect cache (migration + wrapper) ← biggest single PR
3. **2.5** metrics dashboard (ship before 2.3 so we watch hit rate populate)
4. **2.3** composer cache (builds on 2.2 patterns)
5. **2.4** invalidation strategy is folded into 2.2/2.3, not a separate PR
6. Test-gate verification after 1 week of alpha traffic

Reviewers should challenge any of the locked decisions above before code starts.
