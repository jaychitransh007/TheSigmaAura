-- Digital Draping & Comfort Learning tables and columns

-- 1a. Add draping output to analysis snapshots
ALTER TABLE user_analysis_snapshots
  ADD COLUMN draping_output jsonb NOT NULL DEFAULT '{}'::jsonb;

-- 1b. Add draping columns to interpretation snapshots
ALTER TABLE user_interpretation_snapshots
  ADD COLUMN seasonal_color_distribution jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN seasonal_color_groups_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN seasonal_color_source text NOT NULL DEFAULT 'deterministic',
  ADD COLUMN draping_chain_log jsonb NOT NULL DEFAULT '[]'::jsonb;

-- 1c. Effective seasonal groups (source of truth for per-request pipeline)
CREATE TABLE user_effective_seasonal_groups (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES onboarding_profiles(user_id) ON DELETE CASCADE,
  seasonal_groups jsonb NOT NULL DEFAULT '[]'::jsonb,
  source text NOT NULL CHECK (source IN ('draping', 'deterministic', 'comfort_learning')),
  superseded_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_effective_seasonal_user ON user_effective_seasonal_groups(user_id, created_at DESC);

-- 1d. Comfort learning signals
CREATE TABLE user_comfort_learning (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES onboarding_profiles(user_id) ON DELETE CASCADE,
  signal_type text NOT NULL CHECK (signal_type IN ('low_intent', 'high_intent')),
  signal_source text NOT NULL CHECK (signal_source IN ('color_request', 'outfit_like')),
  detected_seasonal_direction text NOT NULL,
  garment_id text,
  conversation_id uuid,
  turn_id uuid,
  feedback_event_id uuid,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_comfort_learning_user ON user_comfort_learning(user_id, created_at DESC);
CREATE INDEX idx_comfort_learning_user_signal ON user_comfort_learning(user_id, signal_type, detected_seasonal_direction);
