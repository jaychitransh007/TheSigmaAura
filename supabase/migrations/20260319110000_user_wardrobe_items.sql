-- User wardrobe memory: persisted owned-item store for wardrobe-first reasoning

CREATE TABLE IF NOT EXISTS user_wardrobe_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES onboarding_profiles(user_id) ON DELETE CASCADE,
  source text NOT NULL CHECK (source IN ('onboarding', 'chat', 'manual', 'inferred')),
  title text NOT NULL DEFAULT '',
  description text NOT NULL DEFAULT '',
  image_url text NOT NULL DEFAULT '',
  image_path text NOT NULL DEFAULT '',
  garment_category text NOT NULL DEFAULT '',
  garment_subtype text NOT NULL DEFAULT '',
  primary_color text NOT NULL DEFAULT '',
  secondary_color text NOT NULL DEFAULT '',
  pattern_type text NOT NULL DEFAULT '',
  formality_level text NOT NULL DEFAULT '',
  occasion_fit text NOT NULL DEFAULT '',
  brand text NOT NULL DEFAULT '',
  notes text NOT NULL DEFAULT '',
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_worn_at timestamptz,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_wardrobe_items_user_created
  ON user_wardrobe_items(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_wardrobe_items_user_active
  ON user_wardrobe_items(user_id, is_active);

CREATE INDEX IF NOT EXISTS idx_user_wardrobe_items_user_category
  ON user_wardrobe_items(user_id, garment_category, garment_subtype);
