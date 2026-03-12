-- Add deterministic height category interpretation columns.

ALTER TABLE IF EXISTS user_interpretation_snapshots
  ADD COLUMN IF NOT EXISTS height_category_value text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS height_category_confidence numeric(4, 3) NOT NULL DEFAULT 0.0,
  ADD COLUMN IF NOT EXISTS height_category_evidence_note text NOT NULL DEFAULT '';
