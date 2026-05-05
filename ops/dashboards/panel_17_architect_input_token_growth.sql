-- Panel 17 — Architect Input Token Growth
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- architect_prompt_tokens_p50_p95_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) AS calls,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY prompt_tokens) AS p50,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY prompt_tokens) AS p95,
    MAX(prompt_tokens) AS p_max
FROM model_call_logs
WHERE call_type = 'outfit_architect'
  AND created_at >= now() - interval '7 days'
  AND prompt_tokens IS NOT NULL
GROUP BY 1
ORDER BY 1 DESC;
