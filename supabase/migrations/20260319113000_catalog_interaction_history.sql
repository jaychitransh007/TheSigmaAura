-- Catalog interaction history for behavioral memory and later ranking signals

CREATE TABLE IF NOT EXISTS catalog_interaction_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES users(external_user_id) ON DELETE CASCADE,
  conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
  turn_id uuid REFERENCES conversation_turns(id) ON DELETE SET NULL,
  product_id text NOT NULL,
  interaction_type text NOT NULL CHECK (
    interaction_type IN (
      'view',
      'click',
      'save',
      'dismiss',
      'buy_skip_request',
      'buy',
      'skip'
    )
  ),
  source_channel text NOT NULL DEFAULT 'web' CHECK (source_channel IN ('web', 'whatsapp')),
  source_surface text NOT NULL DEFAULT 'chat',
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_catalog_interaction_user_created
  ON catalog_interaction_history(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_catalog_interaction_user_type
  ON catalog_interaction_history(user_id, interaction_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_catalog_interaction_product
  ON catalog_interaction_history(product_id, created_at DESC);
