-- Weighted retrieval — engine-resolved hard attrs penalize non-matching
-- items rather than excluding them.
--
-- ## Why
--
-- The architect engine already reduces per-attribute "flatters" lists
-- (e.g., SleeveLength: [three_quarter, full] when weather is high-altitude).
-- Today those constraints only flow into the query_document text;
-- pgvector cosine similarity is fuzzy enough that items violating
-- them can still come back in the top-K, and the composer engine
-- doesn't re-check (its rules are inter-slot pairing, not per-item
-- constraint validation).
--
-- Result: a "Manali trip" query can surface a short-sleeve shirt,
-- because it text-matched well even though the engine knew long
-- sleeves were required.
--
-- This migration extends `match_catalog_item_embeddings` with a
-- `hard_attrs jsonb` parameter — a map of attribute → list of
-- engine-acceptable values for HARD-tier sources (per
-- composition_semantics.md §3.3). Items violating those constraints
-- get a per-violation penalty added to their cosine distance,
-- pushing them down the ORDER BY without removing them. If the pool
-- is sparse and the only available items violate, they STILL come
-- back — graceful degradation, no risk of pool collapse, no
-- per-axis rule code at the application layer.
--
-- Soft attributes (archetype, risk_tolerance, style_goal, time_of_day
-- — see §3.3) stay in query_document text only; cosine similarity
-- handles them.
--
-- ## Backward compatibility
--
-- The new param defaults to `'{}'::jsonb`; existing callers that
-- don't pass it get identical behavior (penalty term evaluates to
-- zero). Hard equality filters in the existing `filter` param
-- (gender_expression, formality_level, etc.) remain unchanged.

create or replace function match_catalog_item_embeddings(
  query_embedding vector(1536),
  match_count int default 10,
  filter jsonb default '{}'::jsonb,
  hard_attrs jsonb default '{}'::jsonb,
  hard_penalty double precision default 0.30
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
    -- Weighted ORDER BY: cosine distance + per-violation penalty.
    -- The correlated subquery counts how many hard_attrs entries the
    -- item violates. An entry is a "violation" iff:
    --   - the item's metadata_json carries that attribute key
    --   - AND the value is NOT in the engine-resolved allowed list
    -- Items that LACK the attribute key carry no penalty (no opinion).
    -- Items where the engine resolved no constraints (hard_attrs={})
    -- evaluate the subquery to 0, leaving cosine the only signal.
    order by
      (cie.embedding <=> query_embedding)
      + hard_penalty * coalesce((
          select count(*)
          from jsonb_each(hard_attrs) as h(attr_name, allowed_values)
          where cie.metadata_json ? h.attr_name
            and jsonb_typeof(h.allowed_values) = 'array'
            and not (h.allowed_values ? (cie.metadata_json->>h.attr_name))
        ), 0)
    limit greatest(match_count, 1);
end;
$$;
