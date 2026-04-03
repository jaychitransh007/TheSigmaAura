-- Persist virtual try-on images with garment mapping for cache reuse.

CREATE TABLE IF NOT EXISTS virtual_tryon_images (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES onboarding_profiles(user_id) ON DELETE CASCADE,
  conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
  turn_id uuid REFERENCES conversation_turns(id) ON DELETE SET NULL,
  outfit_rank int,
  garment_ids text[] NOT NULL DEFAULT '{}',
  garment_source text NOT NULL DEFAULT 'catalog'
    CHECK (garment_source IN ('catalog', 'wardrobe', 'mixed')),
  person_image_path text NOT NULL,
  encrypted_filename text NOT NULL,
  file_path text NOT NULL,
  mime_type text NOT NULL DEFAULT 'image/png',
  file_size_bytes int NOT NULL DEFAULT 0,
  generation_model text NOT NULL DEFAULT 'gemini-3.1-flash-image-preview',
  quality_score_pct int,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_tryon_user_created ON virtual_tryon_images(user_id, created_at DESC);
CREATE INDEX idx_tryon_garment_ids ON virtual_tryon_images USING gin(garment_ids);
