-- Phase 1.2 review follow-up — addresses PR #123 review feedback.
--
-- ## What changed
--
-- JSONB `?` operator instead of expanding arrays with
-- `jsonb_array_elements_text` + `ANY` for the array-valued filters
-- (`garment_category`, `garment_subtype`, `styling_completeness`).
-- The `?` operator avoids materialising the array as a row set —
-- semantically identical for text element membership, faster.
--
-- ## What did NOT change (and why)
--
-- The reviewer suggested moving the GUC sets from `SET LOCAL` inside
-- the function body to a `SET` clause in the function definition. We
-- tried that and Supabase rejects it:
--
--     ERROR: permission denied to set parameter "hnsw.iterative_scan"
--
-- The function-level `SET` clause requires role-level privileges to
-- set the parameter ahead of function execution; the `postgres` role
-- on Supabase doesn't have that for pgvector's GUCs. `SET LOCAL`
-- inside the body works because it only sets the parameter for the
-- current transaction — a weaker permission requirement.
--
-- The defensive `BEGIN ... EXCEPTION when undefined_object` wrapper
-- around the SET LOCALs is also retained for forward-compat: if a
-- future Supabase upgrade swaps pgvector for a fork or downgrades the
-- extension, the function still serves correct (if slower) results
-- via inline HNSW + post-filter rather than erroring out.

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
          and filter->'garment_category' ? cie.garment_category)
      or (jsonb_typeof(filter->'garment_category') <> 'array'
          and cie.garment_category = filter->>'garment_category')
    )
    and (
      (filter ? 'garment_subtype') is false
      or (jsonb_typeof(filter->'garment_subtype') = 'array'
          and filter->'garment_subtype' ? cie.garment_subtype)
      or (jsonb_typeof(filter->'garment_subtype') <> 'array'
          and cie.garment_subtype = filter->>'garment_subtype')
    )
    and (
      (filter ? 'styling_completeness') is false
      or (jsonb_typeof(filter->'styling_completeness') = 'array'
          and filter->'styling_completeness' ? cie.styling_completeness)
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
