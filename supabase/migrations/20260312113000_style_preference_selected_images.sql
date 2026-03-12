ALTER TABLE IF EXISTS user_style_preference_snapshots
  ADD COLUMN IF NOT EXISTS selected_images_json jsonb NOT NULL DEFAULT '{}'::jsonb;
