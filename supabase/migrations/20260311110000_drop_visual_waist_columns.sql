-- Remove deprecated visual waist outputs from analysis snapshots.

ALTER TABLE IF EXISTS user_analysis_snapshots
  DROP COLUMN IF EXISTS waist_value,
  DROP COLUMN IF EXISTS waist_confidence,
  DROP COLUMN IF EXISTS waist_evidence_note,
  DROP COLUMN IF EXISTS waist_visibility_value,
  DROP COLUMN IF EXISTS waist_visibility_confidence,
  DROP COLUMN IF EXISTS waist_visibility_evidence_note;
