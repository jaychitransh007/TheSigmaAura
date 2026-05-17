-- F.2.0 + F.2.1: multi-tenant catalog retrieval.
--
-- Spike F.2.1 (docs/spikes/F21_pgvector_tenant_filter.md) confirmed HNSW
-- iterative scan keeps the index as the driver across every tenant
-- selectivity level we tested (down to 0.035% / 5 rows). Simple in-place
-- migration is safe: add `tenant_id` to `catalog_item_embeddings`,
-- btree-index it, and add a tenant_id predicate to the retrieval RPC.
-- No per-tenant partial HNSW indexes needed at current scale.
--
-- This migration is reversible: the new `match_catalog_item_embeddings_v2`
-- RPC ships alongside the existing 3-arg RPC. Callers are migrated to v2
-- in the same PR. The v1 RPC stays until the next migration drops it,
-- so the migration can be deployed without a brief "all retrieval down"
-- window.

-- Bump per-statement timeout for this migration. The backfill UPDATE
-- joins catalog_item_embeddings (~14K) to catalog_enriched (~13K) on
-- product_id; default pooler timeout (30s) cancelled it on first run.
-- 5 minutes is generous — actual measured runtime is ~10-20s.
SET LOCAL statement_timeout = '5min';

-- ──────────────────────────────────────────────────────────────────────
-- tenants table — opaque tenant_id keyed off Shopify shop domain. The
-- vibe-app's install flow upserts a row on first OAuth (F.2.2). Engine
-- code looks up tenant_id by shop_domain on every retrieval-bearing
-- request.
-- ──────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tenants (
  tenant_id text PRIMARY KEY,
  shopify_shop_domain text NOT NULL,
  shopify_shop_gid text,
  installed_at timestamptz NOT NULL DEFAULT now(),
  -- bootstrap_status drives the merchant-admin sync-progress UI (F.2.4).
  -- Values: 'pending' (just installed, sync not started) → 'syncing'
  -- (catalog ingestion in progress) → 'ready' (all products enriched +
  -- embedded). 'failed' is terminal until manual re-trigger.
  bootstrap_status text NOT NULL DEFAULT 'pending',
  bootstrap_completed_at timestamptz,
  -- Cached counts maintained by the install + daily sync. Source of
  -- truth is catalog_item_embeddings + catalog_enriched but these are
  -- cheap reads for the admin UI.
  product_count integer NOT NULL DEFAULT 0,
  last_sync_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT tenants_shop_domain_unique UNIQUE (shopify_shop_domain),
  CONSTRAINT tenants_bootstrap_status_check
    CHECK (bootstrap_status IN ('pending', 'syncing', 'ready', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_tenants_shop_domain
  ON tenants(shopify_shop_domain);

-- Seed TheSigmaVibe so the existing 13,177 catalog rows have a tenant
-- entry to point at. The tenant_id matches what's already in
-- catalog_enriched.tenant_id (A.2 backfill, 2026-05-15).
INSERT INTO tenants (tenant_id, shopify_shop_domain, bootstrap_status, bootstrap_completed_at, product_count)
VALUES (
  't_Oq0BSHnewiEAAAAAagWWlmnV-0sJmcGk',
  'q8pery-95.myshopify.com',
  'ready',
  '2026-05-15T00:00:00Z',
  13177
)
ON CONFLICT (tenant_id) DO NOTHING;

-- ──────────────────────────────────────────────────────────────────────
-- catalog_item_embeddings.tenant_id — add column, backfill from
-- catalog_enriched.tenant_id (joined on product_id), enforce NOT NULL,
-- index for the predicate's pre-filter.
-- ──────────────────────────────────────────────────────────────────────

ALTER TABLE catalog_item_embeddings
  ADD COLUMN IF NOT EXISTS tenant_id text;

-- Backfill from catalog_enriched. Every catalog_item_embeddings row was
-- produced from a catalog_enriched row in the same ingestion pipeline,
-- so the join is total. Batched in chunks of 2,000 rows so each
-- statement stays under any pooler-side timeout even if the planner
-- picks a slow plan, and so a partial completion is resumable on
-- retry (the WHERE tenant_id IS NULL guard skips already-backfilled
-- rows).
DO $$
DECLARE
  batch_size constant int := 2000;
  rows_updated int;
  total_updated int := 0;
BEGIN
  LOOP
    WITH next_batch AS (
      SELECT cie.id, ce.tenant_id AS src_tenant_id
      FROM catalog_item_embeddings cie
      JOIN catalog_enriched ce
        ON cie.product_id = ce.product_id
      WHERE cie.tenant_id IS NULL
        AND ce.tenant_id IS NOT NULL
      LIMIT batch_size
    )
    UPDATE catalog_item_embeddings cie
    SET tenant_id = next_batch.src_tenant_id
    FROM next_batch
    WHERE cie.id = next_batch.id;

    GET DIAGNOSTICS rows_updated = ROW_COUNT;
    total_updated := total_updated + rows_updated;
    EXIT WHEN rows_updated = 0;
    RAISE NOTICE 'F.2.1 backfill: % rows updated so far', total_updated;
  END LOOP;
  RAISE NOTICE 'F.2.1 backfill: complete, % total rows', total_updated;
END $$;

-- Catch-all for legacy embedding rows that don't have a matching
-- catalog_enriched.tenant_id. Two known sources of these:
--   1. Pre-Shopify-import test data (predates A.2's 2026-05-15
--      backfill on catalog_enriched). Under the single-tenant world
--      they were implicitly part of TheSigmaVibe's retrieval pool.
--   2. Embeddings whose catalog_enriched row has price IS NULL —
--      A.2's WHERE clause filtered those out (only priced rows got
--      tenant_id). Same provenance — TheSigmaVibe.
-- Assigning them to TheSigmaVibe preserves the pre-migration
-- recommendation behavior exactly; the engine's pool of products
-- for TheSigmaVibe's tenant_id stays identical to today's full pool.
-- A future cleanup PR can audit and remove genuinely-stale rows.
UPDATE catalog_item_embeddings
SET tenant_id = 't_Oq0BSHnewiEAAAAAagWWlmnV-0sJmcGk'
WHERE tenant_id IS NULL;

-- Safety check: after both passes, every row must have a tenant_id.
-- The ALTER COLUMN ... SET NOT NULL below would catch this too but
-- a named exception makes the migration-push failure message clearer.
DO $$
DECLARE
  unbackfilled_count integer;
BEGIN
  SELECT count(*) INTO unbackfilled_count
  FROM catalog_item_embeddings
  WHERE tenant_id IS NULL;
  IF unbackfilled_count > 0 THEN
    RAISE EXCEPTION 'F.2.1 backfill incomplete: % rows in catalog_item_embeddings still have NULL tenant_id. Investigate before retrying.', unbackfilled_count;
  END IF;
END $$;

ALTER TABLE catalog_item_embeddings
  ALTER COLUMN tenant_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_catalog_item_embeddings_tenant
  ON catalog_item_embeddings(tenant_id);

-- ──────────────────────────────────────────────────────────────────────
-- match_catalog_item_embeddings_v2 — v2 of the RPC with p_tenant_id as
-- the required first positional parameter. Implementation mirrors the
-- May-13 iterative-HNSW rewrite (relaxed_order + max_scan_tuples=20000)
-- plus the new tenant predicate.
--
-- The previous 3-arg RPC stays in the schema so existing callers don't
-- break during deploy. A follow-up migration drops it once every caller
-- is on v2.
-- ──────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION match_catalog_item_embeddings_v2(
  p_tenant_id text,
  query_embedding vector(1536),
  match_count int DEFAULT 10,
  filter jsonb DEFAULT '{}'::jsonb
)
RETURNS TABLE (
  id uuid,
  catalog_row_id text,
  product_id text,
  document_text text,
  metadata_json jsonb,
  garment_category text,
  garment_subtype text,
  styling_completeness text,
  gender_expression text,
  formality_level text,
  occasion_fit text,
  time_of_day text,
  primary_color text,
  price numeric,
  similarity double precision
)
LANGUAGE plpgsql
AS $$
BEGIN
  -- Fail loud if the caller forgot tenant_id. NULL or empty string
  -- would otherwise silently return zero rows (the WHERE predicate
  -- never matches), which looks like "the catalog has nothing" to the
  -- engine — a worse bug than an explicit failure.
  IF p_tenant_id IS NULL OR length(trim(p_tenant_id)) = 0 THEN
    RAISE EXCEPTION 'match_catalog_item_embeddings_v2: p_tenant_id is required';
  END IF;

  -- Iterative HNSW scan: fetch nearest neighbors from the index, apply
  -- WHERE (including the new tenant_id predicate), continue iterating
  -- until match_count rows pass or max_scan_tuples is reached. Spike
  -- F.2.1 validated max_scan_tuples=20000 is sufficient for 0.035%
  -- selectivity (5 rows / 14,242).
  BEGIN
    SET LOCAL hnsw.iterative_scan = relaxed_order;
    SET LOCAL hnsw.max_scan_tuples = 20000;
  EXCEPTION
    WHEN undefined_object THEN
      RAISE NOTICE 'pgvector iterative_scan unavailable; falling back to inline HNSW scan';
  END;

  RETURN QUERY
    SELECT
      cie.id,
      cie.catalog_row_id,
      cie.product_id,
      cie.document_text,
      cie.metadata_json,
      cie.garment_category,
      cie.garment_subtype,
      cie.styling_completeness,
      cie.gender_expression,
      cie.formality_level,
      cie.occasion_fit,
      cie.time_of_day,
      cie.primary_color,
      cie.price,
      1 - (cie.embedding <=> query_embedding) AS similarity
    FROM catalog_item_embeddings cie
    WHERE cie.tenant_id = p_tenant_id
      AND (
        (filter ? 'garment_category') IS FALSE
        OR (jsonb_typeof(filter->'garment_category') = 'array'
            AND cie.garment_category = ANY(SELECT jsonb_array_elements_text(filter->'garment_category')))
        OR (jsonb_typeof(filter->'garment_category') <> 'array'
            AND cie.garment_category = filter->>'garment_category')
      )
      AND (
        (filter ? 'garment_subtype') IS FALSE
        OR (jsonb_typeof(filter->'garment_subtype') = 'array'
            AND cie.garment_subtype = ANY(SELECT jsonb_array_elements_text(filter->'garment_subtype')))
        OR (jsonb_typeof(filter->'garment_subtype') <> 'array'
            AND cie.garment_subtype = filter->>'garment_subtype')
      )
      AND (
        (filter ? 'styling_completeness') IS FALSE
        OR (jsonb_typeof(filter->'styling_completeness') = 'array'
            AND cie.styling_completeness = ANY(SELECT jsonb_array_elements_text(filter->'styling_completeness')))
        OR (jsonb_typeof(filter->'styling_completeness') <> 'array'
            AND cie.styling_completeness = filter->>'styling_completeness')
      )
      AND ((filter ? 'gender_expression') IS FALSE OR cie.gender_expression = filter->>'gender_expression')
      AND ((filter ? 'formality_level') IS FALSE OR cie.formality_level = filter->>'formality_level')
      AND ((filter ? 'occasion_fit') IS FALSE OR cie.occasion_fit = filter->>'occasion_fit')
      AND ((filter ? 'time_of_day') IS FALSE OR cie.time_of_day = filter->>'time_of_day')
      AND ((filter ? 'primary_color') IS FALSE OR cie.primary_color = filter->>'primary_color')
    ORDER BY cie.embedding <=> query_embedding
    LIMIT greatest(match_count, 1);
END;
$$;

-- updated_at trigger on tenants so admin UI shows fresh state
CREATE OR REPLACE FUNCTION tenants_touch_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_tenants_touch_updated_at ON tenants;
CREATE TRIGGER trg_tenants_touch_updated_at
  BEFORE UPDATE ON tenants
  FOR EACH ROW EXECUTE FUNCTION tenants_touch_updated_at();
