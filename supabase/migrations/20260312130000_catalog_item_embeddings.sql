create extension if not exists vector;

create table if not exists catalog_item_embeddings (
  id uuid primary key default gen_random_uuid(),
  catalog_row_id text not null,
  product_id text not null,
  embedding_model text not null,
  embedding_dimensions int not null default 1536,
  document_text text not null,
  metadata_json jsonb not null default '{}'::jsonb,
  garment_category text,
  garment_subtype text,
  styling_completeness text,
  gender_expression text,
  formality_level text,
  occasion_fit text,
  time_of_day text,
  primary_color text,
  price numeric,
  embedding vector(1536) not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_catalog_item_embeddings_product_model
  on catalog_item_embeddings(product_id, embedding_model, embedding_dimensions);

create index if not exists idx_catalog_item_embeddings_filters
  on catalog_item_embeddings(garment_category, garment_subtype, styling_completeness, gender_expression, formality_level, occasion_fit, time_of_day);

create index if not exists idx_catalog_item_embeddings_embedding
  on catalog_item_embeddings using hnsw (embedding vector_cosine_ops);

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
language sql
as $$
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
  where ((filter ? 'garment_category') is false or cie.garment_category = filter->>'garment_category')
    and ((filter ? 'garment_subtype') is false or cie.garment_subtype = filter->>'garment_subtype')
    and ((filter ? 'styling_completeness') is false or cie.styling_completeness = filter->>'styling_completeness')
    and ((filter ? 'gender_expression') is false or cie.gender_expression = filter->>'gender_expression')
    and ((filter ? 'formality_level') is false or cie.formality_level = filter->>'formality_level')
    and ((filter ? 'occasion_fit') is false or cie.occasion_fit = filter->>'occasion_fit')
    and ((filter ? 'time_of_day') is false or cie.time_of_day = filter->>'time_of_day')
    and ((filter ? 'primary_color') is false or cie.primary_color = filter->>'primary_color')
  order by cie.embedding <=> query_embedding
  limit greatest(match_count, 1);
$$;
