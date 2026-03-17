create table if not exists public.catalog_jobs (
  id              uuid primary key default gen_random_uuid(),
  job_type        text not null,
  status          text not null default 'pending',
  params_json     jsonb not null default '{}'::jsonb,
  processed_rows  integer,
  saved_rows      integer,
  missing_url_rows integer,
  error_message   text,
  started_at      timestamptz,
  completed_at    timestamptz,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists idx_catalog_jobs_type    on public.catalog_jobs (job_type);
create index if not exists idx_catalog_jobs_status  on public.catalog_jobs (status);
create index if not exists idx_catalog_jobs_created on public.catalog_jobs (created_at desc);
