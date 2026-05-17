-- F.2.2b: track vision-enrichment batches per tenant.
--
-- Background: bootstrap (F.2.2) inserts new products with
-- row_status='pending_enrichment' and NULL vision attribute columns
-- (GarmentCategory, FabricDrape, etc.). F.2.2b runs the vision pipeline
-- against those rows asynchronously via the OpenAI Batch API.
--
-- The Batch API has a 24h completion SLA — we submit a request, poll
-- for completion, then ingest the structured output. This migration
-- adds:
--
--   1. `tenant_enrichment_batches` — one row per submitted OpenAI batch
--      keyed by `openai_batch_id`. Tracks lifecycle from
--      submitted → completed (output ingested) | failed | expired.
--
--   2. `catalog_enriched.vision_batch_id` — back-reference from the
--      catalog row to the batch it's enrolled in. Ensures the
--      "find rows to submit" query can exclude rows already in-flight
--      (vision_batch_id IS NOT NULL means a batch is processing them).
--
-- Cost-bearing invariant (user-stated, 2026-05-18): vision enrichment
-- must NEVER re-run on a row that's already been enriched. We enforce
-- this with TWO predicates on the "find pending" query:
--
--   row_status = 'pending_enrichment'    -- not yet enriched
--   AND vision_batch_id IS NULL          -- not in-flight in some batch
--
-- A successful batch ingestion moves rows to row_status='ok' (the
-- existing enrichment terminal state used by ops scripts). A failed
-- or expired batch resets vision_batch_id to NULL on its rows so the
-- next submit picks them up — see CatalogVisionEnrichmentService.

set local lock_timeout = '5s';
set local statement_timeout = '60s';

-- ── 1. Per-tenant batch tracking table ─────────────────────────────

create table if not exists public.tenant_enrichment_batches (
  id                bigserial primary key,
  tenant_id         text not null references public.tenants(tenant_id),
  openai_batch_id   text not null unique,
  -- Lifecycle: 'submitted' → 'completed' | 'failed' | 'expired'.
  -- 'completed' specifically means "output downloaded + parsed +
  -- applied to catalog_enriched", not just "OpenAI says done".
  status            text not null
                    check (status in ('submitted', 'completed', 'failed', 'expired')),
  row_count         integer not null default 0,
  -- The OpenAI input + output file ids — kept for debugging / re-ingestion.
  input_file_id     text null,
  output_file_id    text null,
  error_file_id     text null,
  error             text null,
  submitted_at      timestamptz not null default now(),
  completed_at      timestamptz null
);

comment on table public.tenant_enrichment_batches is
  'F.2.2b: tracks OpenAI Batch API submissions for vision enrichment per tenant. Lifecycle: submitted → completed/failed/expired.';

create index if not exists idx_tenant_enrichment_batches_status
  on public.tenant_enrichment_batches (status, submitted_at);

create index if not exists idx_tenant_enrichment_batches_tenant
  on public.tenant_enrichment_batches (tenant_id, submitted_at desc);

-- ── 2. catalog_enriched.vision_batch_id back-reference ────────────

alter table public.catalog_enriched
  add column if not exists vision_batch_id bigint null
  references public.tenant_enrichment_batches(id);

-- Partial index for "find pending rows in this tenant" — the hot
-- query the submit endpoint runs. Only indexes rows that are actually
-- candidates (pending_enrichment + no batch yet) so it stays small
-- even as the catalog grows.
create index if not exists idx_catalog_enriched_pending_vision
  on public.catalog_enriched (tenant_id)
  where row_status = 'pending_enrichment' and vision_batch_id is null;
