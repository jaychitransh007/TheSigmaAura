-- Phase 2.2 — architect output cache.
--
-- Caches the structured `direction` object the OutfitArchitect emits,
-- keyed on a hash of (tenant_id, intent, profile_cluster, occasion,
-- calendar_season, formality, weather_context, style_goal,
-- time_of_day, architect_prompt_version). Cache hit → orchestrator
-- skips the architect LLM call entirely (~19s saved on gpt-5.2).
--
-- See docs/phase_2_cache_design.md for the cache-key shape and the
-- "why these fields and not others" decisions.
--
-- Multi-tenancy: tenant_id is in both the row column AND the cache_key
-- hash (belt-and-suspenders isolation). Single-tenant today; everything
-- stamps tenant_id='default'.
--
-- TTL: 14 days, refreshed on access via last_used_at. A daily cron
-- (ops/scripts/prune_stale_cache.py, future 2.5 follow-up) will purge
-- stale entries. Until that cron exists, expired entries just hang
-- around — they're never SERVED because the application-side filter
-- checks last_used_at, so correctness is unaffected.

create table if not exists architect_direction_cache (
  cache_key                   text not null,
  tenant_id                   text not null default 'default',

  -- Denormalised key fields for ops dashboards / debugging. Not used
  -- for cache lookup (cache_key is the hash) but invaluable when
  -- slicing hit-rate by cluster or chasing why a particular outfit
  -- got served from cache.
  intent                      text,
  profile_cluster             text,    -- e.g. 'feminine|autumn|hourglass'
  occasion_signal             text,
  calendar_season             text,
  formality_hint              text,
  weather_context             text,
  style_goal                  text,
  time_of_day                 text,
  architect_prompt_version    text,
  architect_model             text,    -- model that generated this entry — useful when prompt_version stays the same but the model swap changed quality

  -- The cached output: a serialised RecommendationPlan (JSON of the
  -- pydantic model). Application reconstructs the plan from this on
  -- cache hit. We do NOT cache the plan_source field — we always set
  -- it to 'cache' on the way out so trace logs make hit/miss obvious.
  direction_json              jsonb not null,

  -- Bookkeeping
  created_at                  timestamptz not null default now(),
  last_used_at                timestamptz not null default now(),
  hit_count                   int not null default 0,

  primary key (tenant_id, cache_key)
);

-- Hot path: lookup by tenant + key (covered by the PK above).

-- Ops queries: hit-rate by cluster, recent activity by cluster.
create index if not exists idx_architect_cache_cluster
  on architect_direction_cache (tenant_id, profile_cluster, last_used_at desc);

-- TTL pruning: scan oldest entries first.
create index if not exists idx_architect_cache_last_used_at
  on architect_direction_cache (last_used_at);

-- ── Metrics view: hit rate + popularity by cluster ──────────────
-- Cheap to query; the dashboard script joins this against
-- model_call_logs to compute the hit-rate denominator (total turns).
-- Update last_used_at on hit so this view stays representative
-- without needing a separate hit-event table.
create or replace view architect_cache_metrics as
select
  tenant_id,
  profile_cluster,
  intent,
  count(*) as entries,
  sum(hit_count) as total_hits,
  -- Average days since each entry was last used; useful to spot
  -- clusters where the cache populates but never gets revisited.
  avg(extract(epoch from (now() - last_used_at)) / 86400.0) as avg_days_idle
from architect_direction_cache
group by tenant_id, profile_cluster, intent;
