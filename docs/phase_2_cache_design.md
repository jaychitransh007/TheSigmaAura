# Phase 2 Cache — Design

**Status:** decisions locked May 13 2026. Revised after PR #131 review (May 13 2026 evening) — see "Revision history" at the bottom.

> **Update 2026-05-07:** the cache infrastructure shipped (PRs #131-#136) but sat at ~0% hit rate because the upstream planner emitted non-deterministic `occasion_signal` / `style_goal` values — same user query produced different cache keys. **Phase 4.7 + 4.11 (composition engine + input canonicalization, PRs #149 + #151) made engine inputs canonical**, so identical user queries now resolve to byte-identical cache keys when the engine accepts. Note that engine plans themselves intentionally bypass the architect cache during the manual flag-on phase (cohort-leak avoidance — see PR #149); LLM-fallback turns continue to use the cache. The original cache-hit-rate projections in this doc apply to the LLM fallback path; engine acceptance becomes the new "hit" path with sub-millisecond latency that doesn't need caching.

Locks the cluster-key shape, prompt-versioning approach, and multi-tenancy posture so 2.1 / 2.2 / 2.3 don't relitigate them mid-PR.

---

## Goal

Cache the *output* of the architect and composer keyed on slow-moving user attributes plus per-turn signals. Hit → skip the LLM call entirely (~32s saved on the architect+composer combined stage post-Phase-1.4). Miss → run the LLM and populate the cache. Hit rate grows organically as alpha traffic accumulates.

Per the [OPEN_TASKS Phase 2 plan](OPEN_TASKS.md), expected hit rate ramp: 0% day 1, ~30% by day 7, ~70% by week 4.

---

## Profile cluster — 3 dimensions, 96 buckets

The cluster captures the **slow-moving** parts of `UserContext` that materially shape the architect's output. Per-turn variables (intent, occasion, formality, weather, style_goal, time_of_day, calendar_season) live in the full cache key, not the cluster.

| Dimension | Source | Values | Cardinality |
|---|---|---|---|
| `gender` | `UserContext.gender` | feminine, masculine, unisex | **3** |
| `season_group_broad` | `derived_interpretations.SeasonalColorGroup` collapsed to broad season | spring, summer, autumn, winter | **4** |
| `body_shape` | `analysis_attributes.BodyShape` | pear, hourglass, apple, inverted_triangle, rectangle, diamond, trapezoid, unknown | **8** |

**Total buckets:** 3 × 4 × 8 = **96**.

### Why these three (and not others)

- `gender` — drives garment_category eligibility (top/bottom/dress) and most-different sub-segment of catalog. Highest leverage.
- `season_group_broad` — drives palette eligibility; collapsed from 12 sub-seasons to 4 broad seasons because sub-season nuance is preserved in the architect's *prompt input* (not stripped) — the cluster just buckets at coarse granularity for hit-rate purposes.
- `body_shape` — primary driver of silhouette/volume/structural-focus reasoning per [outfit_architect.md:368-380](../prompt/outfit_architect.md). The prompt explicitly says "BodyShape priority" over FrameStructure when they conflict on width signals. Caching at body-shape granularity prevents the cache-pollution risk where Pear and Inverted Triangle users would share cached outputs (PR #131 review).

### Why NOT these

- `frame_structure` (slim/medium/sturdy) — was the original 3rd dim in the 36-bucket version. Replaced with `body_shape` after PR #131 review pointed out the architect prompt prioritises BodyShape. They correlate (slim users skew Pear/Rectangle, sturdy users skew Inverted Triangle/Apple) so keeping both adds buckets without much new signal. Add back as a 4th dim if quality regresses on hit and the cluster needs finer slicing.
- `archetype` — dropped from data model May 2026 (per project_overview memory).
- `risk_tolerance` (conservative/balanced/expressive) — drops some "user prefers bold" signal. Add later if hit-rate dashboard shows under-served clusters where risk_tolerance variance matters.
- `HeightCategory` (short/medium/tall) — affects fit/proportion advice but lower leverage than body_shape. Skip; revisit if rater scores diverge by height within a cluster.
- `ContrastLevel` — already captured (loosely) in `season_group_broad` via the seasonal palette structure.
- `profile_richness` — affects how the architect *uses* its inputs, not what those inputs *are*. Don't bucket on it.

### Cost: lower hit rate at maturity

Going from 36 → 96 buckets means ~2.7× more cache slots, so hit-rate ramp slows proportionally:

| Window | 36-bucket (was) | 96-bucket (now) |
|---|---|---|
| Day 7 | ~30% | ~15% |
| Week 4 | ~70% | ~50% |
| Steady state | ~80% | ~60-65% |

Acceptable trade: cache pollution risk is fundamental (wrong silhouette guidance) while slower hit-rate ramp is just slower compounding savings.

### Refinement plan

If hit rate is too low or quality regressions appear:
1. Don't merge buckets globally — only collapse clusters that show high traffic AND identical output across body shapes (e.g., gender-neutral occasions where body shape doesn't differentiate).
2. Add `risk_tolerance` or `HeightCategory` only to clusters where rater scores diverge across users in the same bucket.

---

## Full cache keys

### Architect cache key

```
hash(
  tenant_id,                       # 'default' today; here for isolation when multi-tenancy lands
  intent,                          # ~6 values (planner-emitted)
  profile_cluster,                 # 96 buckets (above)
  occasion_signal,                 # ~45 values (from occasion.yaml)
  calendar_season,                 # 4 values (computed from current date)
  formality_hint,                  # ~5 values (planner-emitted)
  weather_context,                 # from live_context — affects fabric/layering/coverage
  style_goal,                      # from live_context — drives directional vocabulary
  time_of_day,                     # from live_context — affects palette depth + formality
  architect_prompt_version,        # SHA1 hex of base prompt + all assembled fragments
)
```

- `intent` and `formality_hint` come straight from `CopilotResolvedContext` (planner output).
- `calendar_season` is a Python helper: month → spring/summer/autumn/winter (Northern Hemisphere; revisit if/when we serve users elsewhere).
- `occasion_signal` is normalized to lowercase canonical form before hashing.
- `weather_context` / `style_goal` / `time_of_day` come from `LiveContext`. The architect prompt explicitly conditions on these ([outfit_architect.md:107, 153, 353, 440](../prompt/outfit_architect.md)) — without them the cache would serve sunny-day outfits on rainy days, "edgy" outputs to users who said "minimalist", etc. (PR #131 review).
- `tenant_id` is included for **strict isolation under multi-tenancy** even though values are catalog-independent today. Different tenants may interpret the same intent/occasion semantically differently; explicit tenant in the hash prevents cross-tenant cache pollution (PR #131 review).
- `style_goal` is free-text; normalize via lowercase + collapse-whitespace + truncate to 80 chars before hashing. Identical phrasings collapse to the same bucket; long tail of unique phrasings each get their own slot (this is fine — they're long-tail by definition).

**Why these and not the full UserContext:** the cluster captures stable user attributes; the rest of UserContext (analysis_attributes beyond BodyShape, derived_interpretations beyond SeasonalColorGroup, conversation_memory, previous_recommendations, user_message verbatim) varies per turn and is too granular to cache. The architect re-derives those on cache miss; on cache hit we accept that the cached direction is "good enough" for any user in the cluster sending this intent+occasion+formality+live_context.

### Composer cache key

```
hash(
  tenant_id,                       # same isolation rationale as architect
  architect_direction_id,          # SHA1 of the cached architect output
  retrieval_result_fingerprint,    # SHA1 of sorted SKU id list
  profile_cluster,                 # same 96 buckets
  composer_prompt_version,         # same versioning approach as architect
)
```

- `architect_direction_id` ties composer cache to the specific architect output (cached or fresh). The architect_direction_id transitively encodes intent/occasion/formality/weather/style_goal/time_of_day because those went into the architect cache key — so we don't need to repeat them in the composer key.
- `retrieval_result_fingerprint` = `sha1(sorted(retrieved_sku_ids))`. Different SKUs → different cache key. Prevents stale outfits when the catalog changes.
- `profile_cluster` is included even though the architect direction already implicitly carries it: the composer applies *its own* body-harmony reasoning ([outfit_composer.md:190-277](../prompt/outfit_composer.md) uses BodyShape, WaistSizeBand, etc.) on top of the architect direction. Different body shapes within the same direction will pick different items for harmony — explicit cluster in the key prevents that pollution (PR #131 review).
- `tenant_id` for the same isolation reason as the architect cache.

---

## Prompt versioning — hash all assembled fragments on startup

**Decision:** hash the **concatenation of every prompt fragment** (base + all conditionally-appended modules) at process startup. Use the first 8 hex chars of `sha1(...)` as the version string.

```python
# at module load in outfit_architect.py
import hashlib

_PROMPT_BASE = _load_prompt()                       # outfit_architect.md
_PROMPT_ANCHOR = _load_module("anchor")             # outfit_architect_anchor.md
_PROMPT_FOLLOWUP = _load_module("followup")         # outfit_architect_followup.md

_PROMPT_PARTS = [_PROMPT_BASE, _PROMPT_ANCHOR, _PROMPT_FOLLOWUP]
PROMPT_VERSION = hashlib.sha1(
    "\n---\n".join(p or "" for p in _PROMPT_PARTS).encode()
).hexdigest()[:8]
```

### Why hash, not explicit `version: 1` field

| | Hash on startup | Explicit version field |
|---|---|---|
| Auto-invalidates on prompt edit | ✅ | ❌ requires human bump |
| Debuggable in logs | ⚠️ 8-char hex (`a3f1c2b9`) | ✅ readable (`v1`) |
| Risk of forgetting to bump | ✅ none | ❌ silent staleness |
| Migration impact | ✅ first deploy → all entries miss → re-populate | same |

### Why include the modular fragments (PR #131 review)

The architect (and any future composer fragments) appends modules conditionally at request time via `_assemble_system_prompt`:

- `outfit_architect_anchor.md` — appended when `combined_context.live.anchor_garment` is set (pairing-with-piece queries).
- `outfit_architect_followup.md` — appended when conversation history or previous_recommendations exist (follow-up turns).

Originally PROMPT_VERSION hashed only the base. If a reviewer edits `outfit_architect_anchor.md` to fix a pairing-rule bug, the base hash doesn't change → existing pairing-query cache entries serve outputs from the OLD anchor module. Fix: include all fragments in the hash. A change to ANY of the loaded prompt files invalidates the entire cache space, which is the safer default. (PR #131 review.)

The composer currently has no fragments but the same pattern applies if any are added later — make the assembly + hash logic centralised so `composer_prompt_version` automatically picks up new fragments.

---

## Multi-tenancy hooks

Per the [OPEN_TASKS cross-cutting section](OPEN_TASKS.md#cross-cutting--multi-tenancy-data-hooks):

1. **`architect_direction_cache` and `composer_outfit_cache` tables get `tenant_id TEXT NOT NULL DEFAULT 'default'`** — included in the migration. Single-line addition, painful retrofit later.
2. **`tenant_id` is included in the cache-key hash** (not just stored as a column). Even with catalog-independent values, different tenants may semantically interpret the same intent or occasion differently — a `wedding` direction tuned for an Indian-urban catalog wouldn't be appropriate for a hypothetical Western workwear tenant. Belt-and-suspenders isolation prevents cross-tenant cache pollution at the lookup layer, not just the WHERE-clause layer (PR #131 review).
3. **Cache values stay catalog-independent.**
   - Architect cache stores the structured `direction` object (silhouettes, formality, palette guidance) — never product_ids.
   - Composer cache stores the structured `outfit` objects keyed by `composer_id` and item attributes — but the items themselves come from the retrieval step, not the cache. The fingerprint already enforces this: different SKUs → different cache key → no stale catalog references.
4. **Cluster key stays catalog-neutral.** Profile cluster is derived from `UserContext`, not from any catalog state.

The cache is not multi-tenant-aware in *behavior* (single tenant today; everything stamps `tenant_id='default'`), but the schema and key shape support it from day 1 — a future migration to per-tenant retrieval just plumbs `tenant_id` from the request context into the key construction.

---

## TTL + invalidation

- **TTL:** 14 days. Refreshed on access (`last_used_at` column). Entries idle for 14 days get pruned by a daily cron (`ops/scripts/prune_stale_cache.py`, 2.5 follow-up). Most clusters hit the active-set quickly; long-tail clusters expire and re-populate as needed.
- **Prompt-version invalidation:** included in the cache key. Prompt edit → new hash → new key space → old entries become unreachable + expire via TTL. No explicit DELETE needed.
- **No manual invalidation API.** If we later need ops-time invalidation (e.g., a bad architect direction gets cached and we want to nuke it), add an admin endpoint then. Until then keep it simple.

---

## Test gate (revised from OPEN_TASKS.md)

Original gate assumed Phase 1 landed cold-path at ~25s. Phase 1.4 actually lands at ~47s pre-tryon (post gpt-5.2 swap). The 96-bucket cluster (post PR #131 review) further slows hit-rate ramp. Realistic Phase 2 expectations:

- Cache hit rate after 1 week of alpha traffic: ≥15%
- Cache hits: <100ms architect + composer combined latency
- Cache misses: same as Phase 1.4 baseline (~47s pre-tryon)
- Quality unchanged on cache hits (cached output identical to fresh LLM output for the same key — verified by sampling 20 cluster hits in week 2)
- **p95 across mixed traffic: ≤47s by week 1, ≤35s by week 4** (down from "≤15s" in the original doc, further loosened from the 36-bucket revision after the cluster expanded to 96 buckets)

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

---

## Revision history

**May 13 2026 (initial)** — PR #131 merged the first cut. 36-bucket cluster (`gender × season × frame_class`); architect cache key with intent/cluster/occasion/season/formality; prompt versioning hashed only the base; tenant_id stored in column but not in hash.

**May 13 2026 (revision after PR #131 review)**:
- Cluster expanded `36 → 96` buckets — `frame_class (3)` replaced by `body_shape (8)`. The architect prompt explicitly prioritises BodyShape over FrameStructure ([outfit_architect.md:380](../prompt/outfit_architect.md)) so the cluster key has to capture body_shape; otherwise Pear and Inverted Triangle users would share cached outputs.
- **Architect cache key gained 4 fields**: `tenant_id`, `weather_context`, `style_goal`, `time_of_day`. The architect prompt explicitly conditions on weather/time-of-day/style_goal — without them in the key, the cache would serve sunny-day outfits on rainy days, "edgy" outputs to "minimalist" requests, etc.
- **Composer cache key gained `tenant_id`** and a clarifying note about why `profile_cluster` is included even when `architect_direction_id` already encodes it (the composer applies its own body-harmony reasoning on top of the direction).
- **Prompt versioning** now hashes the base + all conditionally-loaded modules (`outfit_architect_anchor.md`, `outfit_architect_followup.md`). Editing a fragment without bumping the base would otherwise serve stale cache entries.
- **`tenant_id` in the hash** (not just in the column WHERE clause) for belt-and-suspenders cross-tenant isolation.
- Test gate further loosened: hit-rate ramp slows ~2.7× with the bigger cluster, so `≤15%` (week 1) / `~50%` (week 4) is the realistic mid-Phase-2 expectation.

Code reflecting this revision is shipped in the same PR as this doc edit (`agentic_application/cache/profile_cluster.py` + tests). 2.2 / 2.3 implementations will use these revised keys from the start.

Reviewers should challenge any of the locked decisions above before code starts.
