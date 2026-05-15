-- Phase A.1 — Shopify mapping columns + Phase A.2 backfill on
-- catalog_enriched. Unblocks B.8 (GID capture) which unblocks D.C.7
-- (Add to Cart wiring).
--
-- All columns are additive and nullable. shopify_product_id and
-- shopify_variant_ids start NULL on every row; B.8's capture script
-- reads Shopify Admin API and populates them by matching
-- vibe.source_product_id metafield → catalog_enriched.product_id.
--
-- tenant_id is backfilled here to TheSigmaVibe's locked value on
-- every row that was imported to Shopify (i.e., has a price).
-- Rows without a price were dropped from the import (1,065 of the
-- 14,242) and don't need a tenant stamp.
--
-- shopify_variant_ids is jsonb keyed by size:
--   {"XS": "gid://shopify/ProductVariant/...",
--    "S":  "gid://shopify/ProductVariant/...",
--    ...}

alter table public.catalog_enriched
  add column if not exists tenant_id text null,
  add column if not exists shopify_product_id text null,
  add column if not exists shopify_variant_ids jsonb null,
  add column if not exists image_hash text null;

create index if not exists idx_catalog_enriched_tenant_id
  on public.catalog_enriched (tenant_id);

create index if not exists idx_catalog_enriched_shopify_product_id
  on public.catalog_enriched (shopify_product_id)
  where shopify_product_id is not null;

-- A.2 backfill: stamp the locked TheSigmaVibe tenant_id on every row
-- that corresponds to a product imported to Shopify.
update public.catalog_enriched
   set tenant_id = 't_Oq0BSHnewiEAAAAAagWWlmnV-0sJmcGk'
 where tenant_id is null
   and price is not null;
