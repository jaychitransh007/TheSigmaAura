-- Distillation traces — full LLM stage I/O for offline training data.
--
-- Coexists with model_call_logs. Different purposes:
--   model_call_logs  → analytics: cost, latency, token counts, sampled bodies.
--                      request_json/response_json there are SUMMARIES (e.g. the
--                      architect logs only {gender, occasion, message, is_followup},
--                      not the 14K-token actual prompt).
--   distillation_traces → supervised tuples for fine-tuning: full input, full
--                         output, no body sampling, plus a back-filled quality_signal
--                         for label propagation from feedback_events.
--
-- The recipe-bootstrap run (Pre-launch Step 3) writes ~50K rows here as a
-- side-effect; that's the v1 distillation training set.
--
-- Multi-tenancy hook: tenant_id column included now (default 'default') to avoid
-- a backfill migration when Shopify multi-tenancy lands.

CREATE TABLE IF NOT EXISTS distillation_traces (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign keys (no FK constraints — turns/conversations may be archived
    -- separately and we want traces to survive for distillation).
    turn_id         UUID NOT NULL,
    conversation_id UUID NOT NULL,

    -- Stage identifier. Matches the call_type values in model_call_logs:
    -- copilot_planner, outfit_architect, catalog_search, outfit_composer,
    -- outfit_rater. Catalog_search is included for retrieval-quality
    -- analysis even though it's not directly distillable.
    stage           TEXT NOT NULL,
    model           TEXT NOT NULL,

    -- The actual payloads. Unsampled — every row gets stored in full so the
    -- distillation training set is complete. PII redaction is applied at
    -- write time via the same pii_redactor used by model_call_logs.
    full_input      JSONB NOT NULL,
    full_output     JSONB,

    -- SHA-256 (truncated 32 hex chars) of canonicalized full_input. Used
    -- for dedup analysis (was this exact input seen before?) and cache-hit
    -- analysis once the recipe cache lands.
    input_hash      TEXT NOT NULL,

    latency_ms      INTEGER,
    status          TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'error')),
    error_message   TEXT,

    -- Back-filled nightly by ops/scripts/backfill_quality_signal.py from
    -- feedback_events + downstream stage acceptance. NULL means not yet
    -- labeled; distillation jobs filter WHERE quality_signal IS NOT NULL.
    quality_signal  JSONB,

    tenant_id       TEXT NOT NULL DEFAULT 'default',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Per-turn lookup (debugging a turn end-to-end).
CREATE INDEX IF NOT EXISTS idx_distillation_traces_turn_created
    ON distillation_traces (turn_id, created_at DESC);

-- Per-stage time-windowed queries (build training set for stage X over last N days).
CREATE INDEX IF NOT EXISTS idx_distillation_traces_stage_created
    ON distillation_traces (stage, created_at DESC);

-- Dedup / cache-hit analysis.
CREATE INDEX IF NOT EXISTS idx_distillation_traces_input_hash
    ON distillation_traces (input_hash);

-- Tenant-scoped queries (forward-compatible with Shopify multi-tenancy).
CREATE INDEX IF NOT EXISTS idx_distillation_traces_tenant_created
    ON distillation_traces (tenant_id, created_at DESC);
