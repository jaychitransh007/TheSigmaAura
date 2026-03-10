-- User analysis runs and flattened attribute storage

CREATE TABLE IF NOT EXISTS user_analysis_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES onboarding_profiles(user_id) ON DELETE CASCADE,
  status text NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
  model_name text NOT NULL DEFAULT 'gpt-5.4',
  started_at timestamptz,
  completed_at timestamptz,
  error_message text NOT NULL DEFAULT '',
  body_type_output jsonb NOT NULL DEFAULT '{}'::jsonb,
  color_headshot_output jsonb NOT NULL DEFAULT '{}'::jsonb,
  color_veins_output jsonb NOT NULL DEFAULT '{}'::jsonb,
  other_details_output jsonb NOT NULL DEFAULT '{}'::jsonb,
  collated_output jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_analysis_runs_user_created
  ON user_analysis_runs(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS user_analysis_attributes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_run_id uuid NOT NULL REFERENCES user_analysis_runs(id) ON DELETE CASCADE,
  user_id text NOT NULL REFERENCES onboarding_profiles(user_id) ON DELETE CASCADE,
  source_agent text NOT NULL,
  attribute_name text NOT NULL,
  attribute_value text NOT NULL,
  confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  evidence_note text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, attribute_name)
);

CREATE INDEX IF NOT EXISTS idx_user_analysis_attributes_user
  ON user_analysis_attributes(user_id);
