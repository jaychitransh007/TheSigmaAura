-- Confidence history snapshots for profile and recommendation state over time.

CREATE TABLE IF NOT EXISTS confidence_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES users(external_user_id) ON DELETE CASCADE,
  conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
  turn_id uuid REFERENCES conversation_turns(id) ON DELETE SET NULL,
  source_channel text NOT NULL DEFAULT 'web' CHECK (source_channel IN ('web', 'whatsapp')),
  confidence_type text NOT NULL CHECK (confidence_type IN ('profile', 'recommendation')),
  score_pct int NOT NULL CHECK (score_pct >= 0 AND score_pct <= 100),
  factors_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_confidence_history_user_created
  ON confidence_history(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_confidence_history_user_type
  ON confidence_history(user_id, confidence_type, created_at DESC);
