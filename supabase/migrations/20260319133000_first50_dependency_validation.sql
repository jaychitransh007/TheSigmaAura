-- First-50 dependency validation instrumentation.

ALTER TABLE onboarding_profiles
  ADD COLUMN IF NOT EXISTS acquisition_source text NOT NULL DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS acquisition_campaign text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS referral_code text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS icp_tag text NOT NULL DEFAULT '';

ALTER TABLE onboarding_profile_snapshots
  ADD COLUMN IF NOT EXISTS acquisition_source text NOT NULL DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS acquisition_campaign text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS referral_code text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS icp_tag text NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS dependency_validation_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES users(external_user_id) ON DELETE CASCADE,
  conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
  turn_id uuid REFERENCES conversation_turns(id) ON DELETE SET NULL,
  source_channel text NOT NULL DEFAULT 'web' CHECK (source_channel IN ('web', 'whatsapp')),
  event_type text NOT NULL,
  primary_intent text NOT NULL DEFAULT '',
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dependency_validation_events_user_created
  ON dependency_validation_events(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_dependency_validation_events_type_created
  ON dependency_validation_events(event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_dependency_validation_events_channel_created
  ON dependency_validation_events(source_channel, created_at DESC);
