create or replace function catalog_admin_status()
returns table (
  catalog_enriched_count bigint,
  catalog_embeddings_count bigint,
  embedded_product_count bigint
)
language sql
as $$
  select
    (select count(*) from catalog_enriched) as catalog_enriched_count,
    (select count(*) from catalog_item_embeddings) as catalog_embeddings_count,
    (select count(distinct product_id) from catalog_item_embeddings) as embedded_product_count
$$;
