-- Policy and guardrail event log for blocked / allowed / escalated enforcement decisions.

CREATE TABLE IF NOT EXISTS policy_event_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text REFERENCES users(external_user_id) ON DELETE CASCADE,
  conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
  turn_id uuid REFERENCES conversation_turns(id) ON DELETE SET NULL,
  source_channel text NOT NULL DEFAULT 'web' CHECK (source_channel IN ('web', 'whatsapp')),
  policy_event_type text NOT NULL,
  input_class text NOT NULL,
  reason_code text NOT NULL,
  decision text NOT NULL CHECK (decision IN ('blocked', 'allowed', 'escalated')),
  rule_source text NOT NULL DEFAULT 'rule',
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_policy_event_log_user_created
  ON policy_event_log(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_policy_event_log_decision_created
  ON policy_event_log(decision, created_at DESC);
