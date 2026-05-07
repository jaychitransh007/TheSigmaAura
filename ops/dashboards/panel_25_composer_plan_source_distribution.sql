-- Panel 25 — Composer Plan-Source Distribution
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- composer_plan_source_distribution_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    CASE
        WHEN model = 'cache'           THEN 'cache'
        WHEN model = 'composer_engine' THEN 'engine'
        ELSE                                'llm'
    END                            AS plan_source,
    COUNT(*)                       AS rows,
    AVG(latency_ms)::int           AS avg_latency_ms,
    SUM(prompt_tokens + completion_tokens) AS total_tokens
FROM model_call_logs
WHERE call_type = 'outfit_composer'
  AND status = 'ok'
  AND created_at >= now() - interval '7 days'
GROUP BY 1, 2
ORDER BY 1 DESC, 2;
