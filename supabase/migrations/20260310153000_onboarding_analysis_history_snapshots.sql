-- Append-only onboarding, analysis, and interpretation snapshots.

CREATE TABLE IF NOT EXISTS onboarding_profile_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES onboarding_profiles(user_id) ON DELETE CASCADE,
  mobile text NOT NULL DEFAULT '',
  otp_last_used_hash text NOT NULL DEFAULT '',
  otp_verified_at timestamptz,
  name text NOT NULL DEFAULT '',
  date_of_birth date,
  gender text
    CHECK (gender IS NULL OR gender IN ('male', 'female', 'non_binary', 'prefer_not_to_say')),
  height_cm numeric(5, 1),
  waist_cm numeric(5, 1),
  profession text
    CHECK (profession IS NULL OR profession IN (
      'software_engineer', 'doctor', 'lawyer', 'teacher', 'designer',
      'architect', 'business_finance', 'marketing', 'artist', 'student',
      'entrepreneur', 'homemaker', 'other'
    )),
  profile_complete boolean NOT NULL DEFAULT false,
  onboarding_complete boolean NOT NULL DEFAULT false,
  has_full_body_image boolean NOT NULL DEFAULT false,
  has_headshot_image boolean NOT NULL DEFAULT false,
  has_veins_image boolean NOT NULL DEFAULT false,
  full_body_encrypted_filename text NOT NULL DEFAULT '',
  headshot_encrypted_filename text NOT NULL DEFAULT '',
  veins_encrypted_filename text NOT NULL DEFAULT '',
  snapshot_reason text NOT NULL DEFAULT 'state_change'
    CHECK (snapshot_reason IN ('created', 'otp_verified', 'profile_saved', 'image_uploaded', 'onboarding_completed', 'state_change')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_onboarding_profile_snapshots_user_created
  ON onboarding_profile_snapshots(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS user_analysis_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_run_id uuid NOT NULL REFERENCES user_analysis_runs(id) ON DELETE CASCADE,
  user_id text NOT NULL REFERENCES onboarding_profiles(user_id) ON DELETE CASCADE,
  model_name text NOT NULL DEFAULT 'gpt-5.4',
  status text NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
  error_message text NOT NULL DEFAULT '',
  waist_value text NOT NULL DEFAULT '',
  waist_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  waist_evidence_note text NOT NULL DEFAULT '',
  shoulder_to_hip_ratio_value text NOT NULL DEFAULT '',
  shoulder_to_hip_ratio_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  shoulder_to_hip_ratio_evidence_note text NOT NULL DEFAULT '',
  torso_to_leg_ratio_value text NOT NULL DEFAULT '',
  torso_to_leg_ratio_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  torso_to_leg_ratio_evidence_note text NOT NULL DEFAULT '',
  body_shape_value text NOT NULL DEFAULT '',
  body_shape_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  body_shape_evidence_note text NOT NULL DEFAULT '',
  visual_weight_value text NOT NULL DEFAULT '',
  visual_weight_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  visual_weight_evidence_note text NOT NULL DEFAULT '',
  vertical_proportion_value text NOT NULL DEFAULT '',
  vertical_proportion_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  vertical_proportion_evidence_note text NOT NULL DEFAULT '',
  arm_volume_value text NOT NULL DEFAULT '',
  arm_volume_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  arm_volume_evidence_note text NOT NULL DEFAULT '',
  midsection_state_value text NOT NULL DEFAULT '',
  midsection_state_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  midsection_state_evidence_note text NOT NULL DEFAULT '',
  waist_visibility_value text NOT NULL DEFAULT '',
  waist_visibility_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  waist_visibility_evidence_note text NOT NULL DEFAULT '',
  bust_volume_value text NOT NULL DEFAULT '',
  bust_volume_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  bust_volume_evidence_note text NOT NULL DEFAULT '',
  skin_surface_color_value text NOT NULL DEFAULT '',
  skin_surface_color_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  skin_surface_color_evidence_note text NOT NULL DEFAULT '',
  hair_color_value text NOT NULL DEFAULT '',
  hair_color_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  hair_color_evidence_note text NOT NULL DEFAULT '',
  hair_color_temperature_value text NOT NULL DEFAULT '',
  hair_color_temperature_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  hair_color_temperature_evidence_note text NOT NULL DEFAULT '',
  eye_color_value text NOT NULL DEFAULT '',
  eye_color_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  eye_color_evidence_note text NOT NULL DEFAULT '',
  eye_clarity_value text NOT NULL DEFAULT '',
  eye_clarity_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  eye_clarity_evidence_note text NOT NULL DEFAULT '',
  skin_undertone_value text NOT NULL DEFAULT '',
  skin_undertone_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  skin_undertone_evidence_note text NOT NULL DEFAULT '',
  face_shape_value text NOT NULL DEFAULT '',
  face_shape_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  face_shape_evidence_note text NOT NULL DEFAULT '',
  neck_length_value text NOT NULL DEFAULT '',
  neck_length_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  neck_length_evidence_note text NOT NULL DEFAULT '',
  hair_length_value text NOT NULL DEFAULT '',
  hair_length_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  hair_length_evidence_note text NOT NULL DEFAULT '',
  jawline_definition_value text NOT NULL DEFAULT '',
  jawline_definition_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  jawline_definition_evidence_note text NOT NULL DEFAULT '',
  shoulder_slope_value text NOT NULL DEFAULT '',
  shoulder_slope_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  shoulder_slope_evidence_note text NOT NULL DEFAULT '',
  body_type_output jsonb NOT NULL DEFAULT '{}'::jsonb,
  color_headshot_output jsonb NOT NULL DEFAULT '{}'::jsonb,
  color_veins_output jsonb NOT NULL DEFAULT '{}'::jsonb,
  other_details_output jsonb NOT NULL DEFAULT '{}'::jsonb,
  collated_output jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_analysis_snapshots_user_created
  ON user_analysis_snapshots(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS user_interpretation_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_run_id uuid NOT NULL REFERENCES user_analysis_runs(id) ON DELETE CASCADE,
  user_id text NOT NULL REFERENCES onboarding_profiles(user_id) ON DELETE CASCADE,
  seasonal_color_group_value text NOT NULL DEFAULT '',
  seasonal_color_group_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  seasonal_color_group_evidence_note text NOT NULL DEFAULT '',
  contrast_level_value text NOT NULL DEFAULT '',
  contrast_level_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  contrast_level_evidence_note text NOT NULL DEFAULT '',
  frame_structure_value text NOT NULL DEFAULT '',
  frame_structure_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  frame_structure_evidence_note text NOT NULL DEFAULT '',
  waist_size_band_value text NOT NULL DEFAULT '',
  waist_size_band_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  waist_size_band_evidence_note text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_interpretation_snapshots_user_created
  ON user_interpretation_snapshots(user_id, created_at DESC);
