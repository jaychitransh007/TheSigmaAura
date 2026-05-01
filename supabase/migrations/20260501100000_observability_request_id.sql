-- Item 2 of the Observability Hardening plan (May 1, 2026).
-- Add request_id column to the three observability tables so logs,
-- traces, and the upstream load-balancer / RUM correlation ID all
-- join on the same key.
--
-- The column is text rather than uuid because:
--   1. Upstream proxies (Cloudflare Ray IDs, etc.) supply non-uuid
--      formats and we want to echo whatever they sent.
--   2. The middleware also generates uuid-shaped values when no
--      header is supplied — a text column accepts both.

ALTER TABLE turn_traces       ADD COLUMN IF NOT EXISTS request_id text;
ALTER TABLE model_call_logs   ADD COLUMN IF NOT EXISTS request_id text;
ALTER TABLE tool_traces       ADD COLUMN IF NOT EXISTS request_id text;

CREATE INDEX IF NOT EXISTS idx_turn_traces_request_id
    ON turn_traces(request_id) WHERE request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_model_call_logs_request_id
    ON model_call_logs(request_id) WHERE request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tool_traces_request_id
    ON tool_traces(request_id) WHERE request_id IS NOT NULL;

COMMENT ON COLUMN turn_traces.request_id IS
    'Correlation ID set by the request_id_middleware (May 1, 2026). Joins to logs and upstream proxy headers.';
COMMENT ON COLUMN model_call_logs.request_id IS
    'Correlation ID set by the request_id_middleware (May 1, 2026).';
COMMENT ON COLUMN tool_traces.request_id IS
    'Correlation ID set by the request_id_middleware (May 1, 2026).';
