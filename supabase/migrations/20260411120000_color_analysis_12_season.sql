-- Phase: Color Analysis Overhaul — 12-season typing + dimension-first architecture
--
-- Adds columns for new derived interpretations (SubSeason, SkinHairContrast,
-- ColorDimensionProfile) and a confidence_margin field. Also adds a table
-- for draping overlay image persistence.

-- 1. New interpretation columns on user_interpretation_snapshots
ALTER TABLE user_interpretation_snapshots
  ADD COLUMN IF NOT EXISTS sub_season_value text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS sub_season_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  ADD COLUMN IF NOT EXISTS sub_season_evidence_note text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS skin_hair_contrast_value text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS skin_hair_contrast_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  ADD COLUMN IF NOT EXISTS skin_hair_contrast_evidence_note text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS color_dimension_profile_value text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS color_dimension_profile_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  ADD COLUMN IF NOT EXISTS color_dimension_profile_evidence_note text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS confidence_margin integer NOT NULL DEFAULT 0;

-- 2. Draping overlay images — store the generated overlay pairs for audit/display
CREATE TABLE IF NOT EXISTS draping_overlay_images (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES onboarding_profiles(user_id) ON DELETE CASCADE,
  analysis_snapshot_id uuid REFERENCES user_analysis_snapshots(id) ON DELETE SET NULL,
  round_number integer NOT NULL,
  round_question text NOT NULL DEFAULT '',
  image_a_path text NOT NULL DEFAULT '',
  image_b_path text NOT NULL DEFAULT '',
  color_a text NOT NULL DEFAULT '',
  color_b text NOT NULL DEFAULT '',
  label_a text NOT NULL DEFAULT '',
  label_b text NOT NULL DEFAULT '',
  choice text NOT NULL DEFAULT '',
  confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  reasoning text NOT NULL DEFAULT '',
  winner_label text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_draping_overlay_user ON draping_overlay_images(user_id, created_at DESC);
