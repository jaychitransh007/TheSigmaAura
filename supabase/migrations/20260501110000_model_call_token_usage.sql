-- Item 4 of the Observability Hardening plan (May 1, 2026).
-- Capture per-call token counts and estimated USD cost on every LLM
-- call so per-user / per-conversation cost attribution works without
-- re-parsing JSON columns.

ALTER TABLE model_call_logs
    ADD COLUMN IF NOT EXISTS prompt_tokens int,
    ADD COLUMN IF NOT EXISTS completion_tokens int,
    ADD COLUMN IF NOT EXISTS total_tokens int,
    ADD COLUMN IF NOT EXISTS estimated_cost_usd numeric(12, 6);

CREATE INDEX IF NOT EXISTS idx_model_call_logs_created_at_cost
    ON model_call_logs(created_at DESC)
    WHERE estimated_cost_usd IS NOT NULL;

COMMENT ON COLUMN model_call_logs.prompt_tokens IS
    'Input tokens charged by the provider. May 1, 2026.';
COMMENT ON COLUMN model_call_logs.completion_tokens IS
    'Output tokens generated. May 1, 2026.';
COMMENT ON COLUMN model_call_logs.total_tokens IS
    'Sum of prompt + completion. Independently captured from provider response.';
COMMENT ON COLUMN model_call_logs.estimated_cost_usd IS
    'Cost in USD per the platform_core.cost_estimator pricing table at insert time.';
