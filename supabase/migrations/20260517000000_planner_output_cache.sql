-- Phase 2 follow-up — copilot_planner output cache.
--
-- Phase 2.2 (architect cache, May 14 2026) shipped a cache for the
-- outfit_architect stage but explicitly skipped the planner — at the
-- time, the architect was the 19s dominant LLM hop and the planner
-- was less than 4s on gpt-5.5. The May 11 2026 latency review (turn
-- f735f414) flagged the planner as the second-largest non-tryon
-- LLM stage at 7.7s on gpt-5-mini (6K input / 322 output). On repeat
-- and paraphrased queries — the long tail of "Dress me for X" /
-- "Show me Y outfits" — those 7.7s repeat verbatim. A cache hit
-- here drops the stage to ~50ms (lookup + parse).
--
-- See docs/phase_2_cache_design.md for the cache-key philosophy.
-- The planner cache key extends the architect's "profile_cluster +
-- canonical context" pattern with the planner's load-bearing
-- discriminators:
--
--   hash(
--     tenant_id,                       'default' today
--     user_message,                    normalised + length-capped
--     profile_cluster,                 96 buckets — same as architect
--     previous_intent,                 follow-up classification signal
--     previous_occasion,               follow-up disambiguation signal
--     has_attached_image,              changes intent path
--     has_person_image,                profile-readiness flag
--     wardrobe_count_bucket,           coarse {0, 1-5, 6-20, 21+}
--     planner_prompt_version,          SHA of prompt/copilot_planner.md
--   )
--
-- DELIBERATELY EXCLUDED from the key:
--   - conversation_history[-4:] — high-variance text; load-bearing
--     signals are captured via previous_intent + previous_occasion
--     abstractions. Including it would fragment the cache and
--     defeat the purpose.
--   - recent_user_actions timeline — episodic memory shifts but
--     the planner's intent classification doesn't depend on it
--     (the architect's reduction does, downstream of the planner).
--
-- TTL: 14 days, refreshed on access via last_used_at (mirrors
-- architect cache TTL).
--
-- Multi-tenancy: tenant_id is in both the row column AND the
-- cache_key hash (belt-and-suspenders isolation).

create table if not exists planner_output_cache (
  cache_key                   text not null,
  tenant_id                   text not null default 'default',

  -- Denormalised key fields for ops dashboards / debugging. Not used
  -- for cache lookup (cache_key is the hash) but invaluable for
  -- slicing hit-rate by cluster or chasing why a query got served
  -- from cache.
  user_message_preview        text,    -- first 120 chars; full text is in user_message_norm
  user_message_norm           text,    -- post-normalisation message used in the hash
  profile_cluster             text,    -- e.g. 'feminine|autumn|hourglass'
  previous_intent             text,
  previous_occasion           text,
  has_attached_image          boolean,
  has_person_image            boolean,
  wardrobe_count_bucket       text,    -- '0' | '1-5' | '6-20' | '21+'
  planner_prompt_version      text,
  planner_model               text,    -- model that generated this entry — correlate cache hit rate with model swaps

  -- The cached output: a serialised CopilotPlanResult (JSON of the
  -- pydantic model). Application reconstructs the result on cache
  -- hit. The result includes intent, intent_confidence, action,
  -- assistant_message, follow_up_suggestions, resolved_context,
  -- action_parameters.
  plan_result_json            jsonb not null,

  -- Bookkeeping
  created_at                  timestamptz not null default now(),
  last_used_at                timestamptz not null default now(),
  hit_count                   int not null default 0,

  primary key (tenant_id, cache_key)
);

-- Hot path: lookup by tenant + key (covered by the PK above).

-- Ops queries: hit-rate by cluster, recent activity by cluster.
create index if not exists idx_planner_cache_cluster
  on planner_output_cache (tenant_id, profile_cluster, last_used_at desc);

-- TTL pruning: scan oldest entries first.
create index if not exists idx_planner_cache_last_used_at
  on planner_output_cache (last_used_at);

-- ── Metrics view: hit rate + popularity by cluster ──────────────
-- Mirrors architect_cache_metrics. Dashboard joins against
-- model_call_logs (call_type='copilot_planner') to compute the
-- hit-rate denominator.
create or replace view planner_cache_metrics as
select
  tenant_id,
  profile_cluster,
  count(*) as entries,
  sum(hit_count) as total_hits,
  avg(extract(epoch from (now() - last_used_at)) / 86400.0) as avg_days_idle
from planner_output_cache
group by tenant_id, profile_cluster;

-- ── Atomic touch RPC (mirrors architect_cache_touch) ────────────
create or replace function planner_cache_touch(
  p_tenant_id text,
  p_cache_key text
)
returns void
language sql
as $$
  update planner_output_cache
  set
    last_used_at = now(),
    hit_count = hit_count + 1
  where tenant_id = p_tenant_id
    and cache_key = p_cache_key;
$$;
