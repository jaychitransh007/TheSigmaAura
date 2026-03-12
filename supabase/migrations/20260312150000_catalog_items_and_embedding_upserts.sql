create table if not exists catalog_items (
  id uuid primary key default gen_random_uuid(),
  catalog_row_id text not null,
  product_id text not null unique,
  title text not null default '',
  description text not null default '',
  price numeric,
  primary_image_url text not null default '',
  secondary_image_url text not null default '',
  product_url text not null default '',
  row_status text not null default '',
  error_reason text not null default '',
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_catalog_items_row_status on catalog_items(row_status);
create index if not exists idx_catalog_items_title on catalog_items(title);

create unique index if not exists uq_catalog_item_embeddings_identity
  on catalog_item_embeddings(product_id, embedding_model, embedding_dimensions);
