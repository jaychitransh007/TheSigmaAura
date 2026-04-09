-- Turn Traces — unified per-turn observability record
--
-- One row per conversation turn, capturing the full lifecycle:
-- input → intent → context snapshot → step-by-step workflow (model,
-- summarized I/O, latency, status) → final evaluation → user's
-- subsequent response signal → end-to-end latency.
--
-- Complements (does NOT replace) the existing scattered signals in
-- model_call_logs, tool_traces, dependency_validation_events,
-- feedback_events, and conversation_turns.resolved_context_json.
-- The trace is a queryable single-row summary designed so that
-- debugging a turn, finding slow steps, and correlating user
-- satisfaction with pipeline shape are all single-table queries.

CREATE TABLE IF NOT EXISTS turn_traces (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign keys
    turn_id         UUID NOT NULL UNIQUE,
    conversation_id UUID NOT NULL,
    user_id         TEXT NOT NULL,

    -- 1. Input
    user_message    TEXT NOT NULL DEFAULT '',
    has_image       BOOLEAN DEFAULT FALSE,
    image_classification JSONB DEFAULT '{}',

    -- 2. Intent
    primary_intent  TEXT NOT NULL DEFAULT '',
    intent_confidence REAL DEFAULT 0,
    action          TEXT NOT NULL DEFAULT '',
    reason_codes    TEXT[] DEFAULT '{}',

    -- 3. Context snapshot
    profile_snapshot JSONB DEFAULT '{}',
    query_entities   JSONB DEFAULT '{}',

    -- 4-6, 9. Workflow steps (model, I/O summary, latency, status)
    steps           JSONB DEFAULT '[]',

    -- 7. Final evaluation summary
    evaluation      JSONB DEFAULT '{}',

    -- 8. User response (filled retroactively)
    user_response   JSONB DEFAULT '{}',

    -- 10. Overall response time
    total_latency_ms INTEGER,

    -- Timestamps
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Indexes for the common query patterns from the design doc
CREATE INDEX IF NOT EXISTS idx_turn_traces_conversation_id ON turn_traces (conversation_id);
CREATE INDEX IF NOT EXISTS idx_turn_traces_user_id ON turn_traces (user_id);
CREATE INDEX IF NOT EXISTS idx_turn_traces_primary_intent ON turn_traces (primary_intent);
CREATE INDEX IF NOT EXISTS idx_turn_traces_created_at ON turn_traces (created_at DESC);
