-- Panel 33 — Cache Hit-Rate by Stage (LLM caches)
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- Per-stage hit rate from model_call_logs over the last 7 days.
-- cache hits stamp model='cache'; LLM runs stamp the model id.
-- Filters by call_type so each row maps to exactly one stage.
WITH stage_decisions AS (
    SELECT
        call_type AS stage,
        CASE WHEN model = 'cache' THEN 'hit' ELSE 'miss' END AS outcome,
        created_at::date AS day
    FROM model_call_logs
    WHERE call_type IN ('copilot_planner', 'outfit_architect', 'outfit_composer')
      AND created_at >= NOW() - INTERVAL '7 days'
      AND status = 'ok'
)
SELECT
    stage,
    COUNT(*)                                         AS total_calls,
    COUNT(*) FILTER (WHERE outcome = 'hit')          AS cache_hits,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE outcome = 'hit')
        / NULLIF(COUNT(*), 0),
        1
    )                                                AS hit_rate_pct
FROM stage_decisions
GROUP BY stage
ORDER BY stage;
