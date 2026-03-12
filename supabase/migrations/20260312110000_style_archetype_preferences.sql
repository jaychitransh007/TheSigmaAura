-- Style archetype preference snapshots and onboarding completion flag.

ALTER TABLE IF EXISTS onboarding_profiles
  ADD COLUMN IF NOT EXISTS style_preference_complete boolean NOT NULL DEFAULT false;

ALTER TABLE IF EXISTS onboarding_profile_snapshots
  ADD COLUMN IF NOT EXISTS style_preference_complete boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS user_style_preference_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES onboarding_profiles(user_id) ON DELETE CASCADE,
  gender text NOT NULL CHECK (gender IN ('male', 'female')),
  primary_archetype text NOT NULL,
  secondary_archetype text,
  blend_ratio_primary int NOT NULL DEFAULT 100,
  blend_ratio_secondary int NOT NULL DEFAULT 0,
  risk_tolerance text NOT NULL DEFAULT '',
  formality_lean text NOT NULL DEFAULT '',
  pattern_type text NOT NULL DEFAULT '',
  comfort_boundaries_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  archetype_scores_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  selected_image_ids_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  selection_count int NOT NULL DEFAULT 0,
  completed_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_style_preference_snapshots_user_created
  ON user_style_preference_snapshots(user_id, created_at DESC);
