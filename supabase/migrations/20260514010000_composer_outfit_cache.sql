-- Phase 2.3 — composer output cache.
--
-- Caches the structured ComposerResult (list of outfits) keyed on the
-- architect direction + retrieval fingerprint + profile cluster +
-- composer prompt version. Hit → skip the composer LLM call entirely
-- (~13s saved on gpt-5.2). Stacks on top of the architect cache from
-- PR #134.
--
-- See docs/phase_2_cache_design.md for the cache-key shape:
--   hash(tenant_id, architect_direction_id, retrieval_fingerprint,
--        profile_cluster, composer_prompt_version)
--
-- The retrieval fingerprint = sha1 of sorted SKU IDs the architect's
-- search returned. Different SKUs → different cache key → no stale
-- catalog references survive a catalog refresh.

create table if not exists composer_outfit_cache (
  cache_key                   text not null,
  tenant_id                   text not null default 'default',

  -- Denormalised key fields for ops dashboards / debugging.
  architect_direction_id      text,
  retrieval_fingerprint       text,
  profile_cluster             text,
  composer_prompt_version     text,
  composer_model              text,

  -- The cached output: a serialised ComposerResult (JSON of the
  -- pydantic model). Application reconstructs the ComposerResult on
  -- cache hit. We do NOT cache `attempt_count` or `raw_response` (set
  -- attempt_count=1 and raw_response='' on the way out so traces
  -- visibly say "this was a single hit, no retries").
  outfits_json                jsonb not null,

  -- Bookkeeping
  created_at                  timestamptz not null default now(),
  last_used_at                timestamptz not null default now(),
  hit_count                   int not null default 0,

  primary key (tenant_id, cache_key)
);

create index if not exists idx_composer_cache_cluster
  on composer_outfit_cache (tenant_id, profile_cluster, last_used_at desc);

create index if not exists idx_composer_cache_last_used_at
  on composer_outfit_cache (last_used_at);

create or replace view composer_cache_metrics as
select
  tenant_id,
  profile_cluster,
  count(*) as entries,
  sum(hit_count) as total_hits,
  avg(extract(epoch from (now() - last_used_at)) / 86400.0) as avg_days_idle
from composer_outfit_cache
group by tenant_id, profile_cluster;
