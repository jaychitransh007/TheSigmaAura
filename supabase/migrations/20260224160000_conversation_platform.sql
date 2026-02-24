create extension if not exists pgcrypto;

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  external_user_id text not null unique,
  default_gender text check (default_gender in ('male', 'female')),
  default_age text check (default_age in ('18_24', '25_30', '30_35')),
  consent_flags_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  status text not null default 'active' check (status in ('active', 'archived')),
  session_context_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists conversation_turns (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  user_message text not null,
  assistant_message text,
  resolved_context_json jsonb not null default '{}'::jsonb,
  profile_snapshot_id uuid,
  recommendation_run_id uuid,
  created_at timestamptz not null default now()
);

create table if not exists media_assets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  conversation_id uuid references conversations(id) on delete set null,
  source_type text not null check (source_type in ('upload', 'url', 'file')),
  source_ref text,
  storage_url text not null,
  sha256 char(64),
  mime_type text,
  width int,
  height int,
  created_at timestamptz not null default now()
);

create table if not exists profile_snapshots (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  conversation_id uuid not null references conversations(id) on delete cascade,
  source_turn_id uuid references conversation_turns(id) on delete set null,
  profile_json jsonb not null,
  gender text not null check (gender in ('male', 'female')),
  age text not null check (age in ('18_24', '25_30', '30_35')),
  confidence_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists context_snapshots (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  source_turn_id uuid references conversation_turns(id) on delete set null,
  occasion text not null check (occasion in ('work_mode', 'social_casual', 'night_out', 'formal_events', 'festive', 'beach_vacation', 'dating', 'wedding_vibes')),
  archetype text not null check (archetype in ('classic', 'minimalist', 'modern_professional', 'romantic', 'glamorous', 'dramatic', 'creative', 'natural', 'sporty', 'trend_forward', 'bohemian', 'edgy')),
  raw_text text,
  created_at timestamptz not null default now()
);

create table if not exists recommendation_runs (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  turn_id uuid not null references conversation_turns(id) on delete cascade,
  profile_snapshot_id uuid not null references profile_snapshots(id) on delete restrict,
  context_snapshot_id uuid not null references context_snapshots(id) on delete restrict,
  strictness text not null check (strictness in ('safe', 'balanced', 'bold')),
  hard_filter_profile text not null check (hard_filter_profile in ('rl_ready_minimal', 'legacy')),
  candidate_count int not null default 0,
  returned_count int not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists recommendation_items (
  id uuid primary key default gen_random_uuid(),
  recommendation_run_id uuid not null references recommendation_runs(id) on delete cascade,
  rank int not null,
  garment_id text not null,
  title text not null,
  image_url text,
  score numeric(10, 6) not null,
  max_score numeric(10, 6),
  compatibility_confidence numeric(10, 6),
  flags_json jsonb not null default '[]'::jsonb,
  reasons_json jsonb not null default '[]'::jsonb,
  unique (recommendation_run_id, rank)
);

create table if not exists feedback_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  conversation_id uuid not null references conversations(id) on delete cascade,
  recommendation_run_id uuid not null references recommendation_runs(id) on delete cascade,
  garment_id text not null,
  event_type text not null check (event_type in ('like', 'share', 'buy', 'skip')),
  reward_value int not null,
  notes text,
  created_at timestamptz not null default now()
);

create table if not exists model_call_logs (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid references conversations(id) on delete set null,
  turn_id uuid references conversation_turns(id) on delete set null,
  service text not null,
  call_type text not null,
  model text not null,
  request_json jsonb not null,
  response_json jsonb,
  reasoning_notes_json jsonb not null default '[]'::jsonb,
  latency_ms int,
  status text not null default 'ok' check (status in ('ok', 'error')),
  error_message text,
  created_at timestamptz not null default now()
);

create table if not exists tool_traces (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid references conversations(id) on delete set null,
  turn_id uuid references conversation_turns(id) on delete set null,
  tool_name text not null,
  input_json jsonb not null,
  output_json jsonb,
  latency_ms int,
  status text not null default 'ok' check (status in ('ok', 'error')),
  error_message text,
  created_at timestamptz not null default now()
);

create index if not exists idx_conversations_user_id on conversations(user_id);
create index if not exists idx_turns_conversation_created on conversation_turns(conversation_id, created_at desc);
create index if not exists idx_profile_user_created on profile_snapshots(user_id, created_at desc);
create index if not exists idx_reco_items_run_rank on recommendation_items(recommendation_run_id, rank);
create index if not exists idx_feedback_user_created on feedback_events(user_id, created_at desc);
create index if not exists idx_model_calls_model_created on model_call_logs(model, created_at desc);
create index if not exists idx_tool_traces_turn_created on tool_traces(turn_id, created_at desc);
