-- Phase 1.2 latency push: rewrite match_catalog_item_embeddings to use
-- pgvector's iterative HNSW scan. Replaces the MATERIALIZED CTE pattern
-- that defeated the HNSW index entirely (cause of the 2.9s retrieval
-- baseline observed in production traces).
--
-- History of this RPC:
--   * 20260312130000 (original) — inline WHERE + ORDER BY + LIMIT.
--     HNSW used, fast, but post-filter elimination lost valid matches
--     under restrictive filters (returned <match_count rows).
--   * 20260317140000 ("fix prefilter") — `with filtered as MATERIALIZED`
--     forced full filtered scan + exact sort. Correct (always returns
--     match_count rows when available) but bypassed HNSW entirely. With
--     filter selectivity dropping to ~5-15% (~700-2000 rows) and 7
--     queries per turn fanned 2-at-a-time, this drove retrieval to 2.9s.
--   * 20260409140000, 20260410000000 — added multi-value array support
--     for garment_subtype, garment_category, styling_completeness.
--     Kept the materialized CTE.
--
-- This migration: keep the multi-value array support; switch to inline
-- WHERE + ORDER BY + LIMIT against the table directly so the planner
-- can pick HNSW; set `hnsw.iterative_scan = relaxed_order` at function
-- scope so HNSW iteratively over-fetches until enough rows pass the
-- filter (solves the original post-filter elimination problem without
-- losing the index speedup). Also bump `hnsw.max_scan_tuples` to allow
-- enough iterations for restrictive filters.
--
-- Requires pgvector >= 0.8. If the GUCs are unrecognized, the function
-- will error with a clear message at first call — easy to roll back.

create or replace function match_catalog_item_embeddings(
  query_embedding vector(1536),
  match_count int default 10,
  filter jsonb default '{}'::jsonb
)
returns table (
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
language plpgsql
as $$
begin
  -- Iterative HNSW scan: fetch nearest neighbors from the index, apply
  -- WHERE, and continue iterating until we have match_count rows or
  -- exhaust max_scan_tuples. `relaxed_order` is faster than
  -- `strict_order` and acceptable here — top-N order within the
  -- returned set may diverge slightly from exact KNN, but downstream
  -- ranking uses the similarity score, not position.
  --
  -- Wrapped in BEGIN/EXCEPTION because the GUCs only exist in pgvector
  -- >= 0.8. On older versions the SET fails with "unrecognized
  -- configuration parameter"; we catch that, log a NOTICE, and run the
  -- query without iterative_scan. The fallback path is still faster
  -- than the materialized-CTE pattern (HNSW is engaged by the inline
  -- ORDER BY ... <=> ... LIMIT) but may return <match_count rows under
  -- very restrictive filters. Worth it: forward-compatible without
  -- requiring a hard pgvector version gate at migration time.
  begin
    set local hnsw.iterative_scan = relaxed_order;
    set local hnsw.max_scan_tuples = 20000;
  exception
    when undefined_object then
      raise notice 'pgvector iterative_scan unavailable; falling back to inline HNSW scan';
  end;

  return query
    select
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
      1 - (cie.embedding <=> query_embedding) as similarity
    from catalog_item_embeddings cie
    where (
      (filter ? 'garment_category') is false
      or (jsonb_typeof(filter->'garment_category') = 'array'
          and cie.garment_category = any(select jsonb_array_elements_text(filter->'garment_category')))
      or (jsonb_typeof(filter->'garment_category') <> 'array'
          and cie.garment_category = filter->>'garment_category')
    )
    and (
      (filter ? 'garment_subtype') is false
      or (jsonb_typeof(filter->'garment_subtype') = 'array'
          and cie.garment_subtype = any(select jsonb_array_elements_text(filter->'garment_subtype')))
      or (jsonb_typeof(filter->'garment_subtype') <> 'array'
          and cie.garment_subtype = filter->>'garment_subtype')
    )
    and (
      (filter ? 'styling_completeness') is false
      or (jsonb_typeof(filter->'styling_completeness') = 'array'
          and cie.styling_completeness = any(select jsonb_array_elements_text(filter->'styling_completeness')))
      or (jsonb_typeof(filter->'styling_completeness') <> 'array'
          and cie.styling_completeness = filter->>'styling_completeness')
    )
    and ((filter ? 'gender_expression') is false or cie.gender_expression = filter->>'gender_expression')
    and ((filter ? 'formality_level') is false or cie.formality_level = filter->>'formality_level')
    and ((filter ? 'occasion_fit') is false or cie.occasion_fit = filter->>'occasion_fit')
    and ((filter ? 'time_of_day') is false or cie.time_of_day = filter->>'time_of_day')
    and ((filter ? 'primary_color') is false or cie.primary_color = filter->>'primary_color')
    order by cie.embedding <=> query_embedding
    limit greatest(match_count, 1);
end;
$$;
