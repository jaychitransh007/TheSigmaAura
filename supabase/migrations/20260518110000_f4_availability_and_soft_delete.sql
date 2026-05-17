-- F.4: real-time inventory state via Shopify products/* webhooks.
--
-- The bootstrap (F.2.2) and daily sync (F.3) walk the merchant's
-- catalog in cursor-based passes — they're authoritative for product
-- existence but lag for inventory changes. The webhooks below land
-- on vibe-app and forward to the engine, which marks catalog rows as
-- unavailable in real time so customer Vibe recommendations don't
-- surface out-of-stock items.
--
--   products/create   → row added (bootstrap-batch path)
--   products/update   → metadata refresh + availability flip
--   products/delete   → soft delete (available_for_sale=false,
--                        deleted_at=now()) so an accidental delete
--                        can be revived without re-running vision
--
-- This migration:
--   1. Adds `available_for_sale boolean` + `deleted_at timestamptz`
--      to catalog_enriched (the source of truth).
--   2. Adds `available_for_sale boolean` to catalog_item_embeddings
--      so the retrieval RPC can filter without a JOIN — the hot
--      path is the per-turn similarity search and we keep it cheap.
--   3. Updates `match_catalog_item_embeddings_v2` to AND in
--      `available_for_sale IS NOT FALSE` so unavailable rows never
--      reach a customer. NULL is treated as available — that keeps
--      pre-F.4 rows working until webhooks populate them.

set local lock_timeout = '5s';
set local statement_timeout = '60s';

-- ── 1. catalog_enriched: source of truth for inventory state ───────

alter table public.catalog_enriched
  add column if not exists available_for_sale boolean not null default true;

alter table public.catalog_enriched
  add column if not exists deleted_at timestamptz null;

comment on column public.catalog_enriched.available_for_sale is
  'F.4: false when products/update webhook reports zero in-stock variants. NULL on legacy rows = treated as available.';
comment on column public.catalog_enriched.deleted_at is
  'F.4: set when products/delete webhook fires. Soft delete — row stays but is filtered out of recommendations.';

-- ── 2. catalog_item_embeddings: filter column for the retrieval RPC

alter table public.catalog_item_embeddings
  add column if not exists available_for_sale boolean not null default true;

-- ── 3. RPC v2: filter out unavailable rows ─────────────────────────
--
-- This drops + recreates the function (CREATE OR REPLACE since the
-- signature is unchanged). The new predicate `IS NOT FALSE` matches
-- both TRUE and NULL — so pre-webhook rows still come back.

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
  IF p_tenant_id IS NULL OR length(trim(p_tenant_id)) = 0 THEN
    RAISE EXCEPTION 'match_catalog_item_embeddings_v2: p_tenant_id is required';
  END IF;

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
      -- F.4: unavailable rows never reach customers. IS NOT FALSE
      -- treats NULL as available so pre-webhook rows survive.
      AND cie.available_for_sale IS NOT FALSE
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
    LIMIT match_count;
END;
$$;
