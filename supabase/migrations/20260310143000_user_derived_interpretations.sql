-- Deterministic user interpretation outputs derived from analysis attributes

CREATE TABLE IF NOT EXISTS user_derived_interpretations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_run_id uuid NOT NULL REFERENCES user_analysis_runs(id) ON DELETE CASCADE,
  user_id text NOT NULL REFERENCES onboarding_profiles(user_id) ON DELETE CASCADE,
  interpretation_name text NOT NULL,
  interpretation_value text NOT NULL,
  confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  evidence_note text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, interpretation_name)
);

CREATE INDEX IF NOT EXISTS idx_user_derived_interpretations_user
  ON user_derived_interpretations(user_id);
