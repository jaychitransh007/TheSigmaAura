-- Structured sentiment history for conversational memory and later adaptation.

CREATE TABLE IF NOT EXISTS user_sentiment_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES users(external_user_id) ON DELETE CASCADE,
  conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
  turn_id uuid REFERENCES conversation_turns(id) ON DELETE SET NULL,
  source_channel text NOT NULL DEFAULT 'web' CHECK (source_channel IN ('web', 'whatsapp')),
  sentiment_source text NOT NULL DEFAULT 'user_message' CHECK (
    sentiment_source IN ('user_message', 'feedback_note', 'system_inference')
  ),
  sentiment_label text NOT NULL CHECK (
    sentiment_label IN (
      'positive',
      'negative',
      'neutral',
      'anxious',
      'frustrated',
      'confident',
      'uncertain'
    )
  ),
  sentiment_score numeric(4,3) NOT NULL DEFAULT 0,
  intensity numeric(4,3) NOT NULL DEFAULT 0,
  cues_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_sentiment_history_user_created
  ON user_sentiment_history(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_sentiment_history_user_label
  ON user_sentiment_history(user_id, sentiment_label, created_at DESC);
