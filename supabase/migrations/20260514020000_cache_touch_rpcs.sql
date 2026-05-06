-- Phase 2 review (PR #134): atomic touch RPCs for the cache repos.
--
-- The application-side touch() in ArchitectCacheRepository /
-- ComposerCacheRepository previously only refreshed last_used_at —
-- the docstring claimed it also bumped hit_count, but PostgREST's
-- table API can't do server-side increments. Adding two thin RPCs
-- (one per cache table) so touch() can atomically:
--   1. UPDATE last_used_at = now()
--   2. UPDATE hit_count = hit_count + 1
-- in one round trip, no read-modify-write race.
--
-- The repos call these via the RPC method on SupabaseRestClient.
-- If the RPC is missing for any reason, the repo's exception handler
-- swallows the error — touch is best-effort metrics, not load-
-- bearing.

create or replace function architect_cache_touch(
  p_tenant_id text,
  p_cache_key text
)
returns void
language sql
as $$
  update architect_direction_cache
  set
    last_used_at = now(),
    hit_count = hit_count + 1
  where tenant_id = p_tenant_id
    and cache_key = p_cache_key;
$$;

create or replace function composer_cache_touch(
  p_tenant_id text,
  p_cache_key text
)
returns void
language sql
as $$
  update composer_outfit_cache
  set
    last_used_at = now(),
    hit_count = hit_count + 1
  where tenant_id = p_tenant_id
    and cache_key = p_cache_key;
$$;
