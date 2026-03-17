-- Make recommendation_run_id nullable (agentic pipeline does not use run IDs)
ALTER TABLE feedback_events ALTER COLUMN recommendation_run_id DROP NOT NULL;

-- Add turn-level correlation columns for outfit feedback
ALTER TABLE feedback_events ADD COLUMN IF NOT EXISTS turn_id uuid REFERENCES conversation_turns(id) ON DELETE CASCADE;
ALTER TABLE feedback_events ADD COLUMN IF NOT EXISTS outfit_rank int;
