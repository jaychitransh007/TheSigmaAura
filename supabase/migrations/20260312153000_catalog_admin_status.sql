create or replace function catalog_admin_status()
returns table (
  catalog_enriched_count bigint,
  catalog_embeddings_count bigint,
  embedded_product_count bigint
)
language plpgsql
as $$
begin
  catalog_enriched_count := case
    when to_regclass('public.catalog_enriched') is null then 0
    else (select count(*) from public.catalog_enriched)
  end;

  catalog_embeddings_count := case
    when to_regclass('public.catalog_item_embeddings') is null then 0
    else (select count(*) from public.catalog_item_embeddings)
  end;

  embedded_product_count := case
    when to_regclass('public.catalog_item_embeddings') is null then 0
    else (select count(distinct product_id) from public.catalog_item_embeddings)
  end;

  return next;
end;
$$;
