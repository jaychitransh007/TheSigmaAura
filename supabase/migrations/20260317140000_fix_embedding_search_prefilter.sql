-- Fix: HNSW index causes post-filter elimination of valid matches.
-- Pre-filter rows in a CTE so the vector sort runs on the filtered subset
-- using exact (non-index) distance calculation. Fine for <50K rows.

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
  return query
    with filtered as materialized (
      select *
      from catalog_item_embeddings cie
      where ((filter ? 'garment_category') is false or cie.garment_category = filter->>'garment_category')
        and ((filter ? 'garment_subtype') is false or cie.garment_subtype = filter->>'garment_subtype')
        and ((filter ? 'styling_completeness') is false or cie.styling_completeness = filter->>'styling_completeness')
        and ((filter ? 'gender_expression') is false or cie.gender_expression = filter->>'gender_expression')
        and ((filter ? 'formality_level') is false or cie.formality_level = filter->>'formality_level')
        and ((filter ? 'occasion_fit') is false or cie.occasion_fit = filter->>'occasion_fit')
        and ((filter ? 'time_of_day') is false or cie.time_of_day = filter->>'time_of_day')
        and ((filter ? 'primary_color') is false or cie.primary_color = filter->>'primary_color')
    )
    select
      f.id,
      f.catalog_row_id,
      f.product_id,
      f.document_text,
      f.metadata_json,
      f.garment_category,
      f.garment_subtype,
      f.styling_completeness,
      f.gender_expression,
      f.formality_level,
      f.occasion_fit,
      f.time_of_day,
      f.primary_color,
      f.price,
      1 - (f.embedding <=> query_embedding) as similarity
    from filtered f
    order by f.embedding <=> query_embedding
    limit greatest(match_count, 1);
end;
$$;
