-- Phase 1: Agentic Fashion Commerce schema additions
-- Adds mode routing, autonomy, checkout-prep tables, and profile fields.

-- 1. users: canonical profile and update timestamp
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS profile_json jsonb NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS profile_updated_at timestamptz;

-- 2. conversation_turns: mode routing and autonomy
ALTER TABLE conversation_turns
  ADD COLUMN IF NOT EXISTS mode_preference text,
  ADD COLUMN IF NOT EXISTS resolved_mode text
    CHECK (resolved_mode IS NULL OR resolved_mode IN ('garment', 'outfit')),
  ADD COLUMN IF NOT EXISTS autonomy_level text
    CHECK (autonomy_level IS NULL OR autonomy_level IN ('suggest', 'prepare'));

-- 3. recommendation_runs: resolved mode and style constraints
ALTER TABLE recommendation_runs
  ADD COLUMN IF NOT EXISTS resolved_mode text
    CHECK (resolved_mode IS NULL OR resolved_mode IN ('garment', 'outfit')),
  ADD COLUMN IF NOT EXISTS requested_garment_types_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS style_constraints_json jsonb NOT NULL DEFAULT '{}'::jsonb;

-- 4. checkout_preparations
CREATE TABLE IF NOT EXISTS checkout_preparations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL REFERENCES conversations(id),
  turn_id uuid REFERENCES conversation_turns(id),
  recommendation_run_id uuid NOT NULL REFERENCES recommendation_runs(id),
  user_id uuid NOT NULL REFERENCES users(id),
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'ready', 'needs_user_action', 'failed')),
  cart_payload_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  pricing_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  validation_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  checkout_ref text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_checkout_preps_conversation
  ON checkout_preparations(conversation_id);
CREATE INDEX IF NOT EXISTS idx_checkout_preps_user
  ON checkout_preparations(user_id);

-- 5. checkout_preparation_items
CREATE TABLE IF NOT EXISTS checkout_preparation_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  checkout_preparation_id uuid NOT NULL REFERENCES checkout_preparations(id),
  rank int NOT NULL,
  garment_id text NOT NULL,
  title text NOT NULL DEFAULT '',
  qty int NOT NULL DEFAULT 1,
  unit_price int NOT NULL DEFAULT 0,
  discount int NOT NULL DEFAULT 0,
  final_price int NOT NULL DEFAULT 0,
  meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (checkout_preparation_id, rank)
);

CREATE INDEX IF NOT EXISTS idx_checkout_prep_items_prep_id
  ON checkout_preparation_items(checkout_preparation_id);
