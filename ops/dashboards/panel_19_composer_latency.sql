-- Panel 19 — Composer Latency
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- composer_latency_p50_p95_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    call_type, -- 'outfit_composer' (first attempt) vs 'outfit_composer_retry1'
    COUNT(*) AS calls,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms,
    MAX(latency_ms) AS p_max_ms
FROM model_call_logs
WHERE call_type LIKE 'outfit_composer%'
  AND created_at >= now() - interval '7 days'
  AND latency_ms IS NOT NULL
  AND latency_ms > 0  -- exclude pre-PR-#95 zero-rows when reading historical data
GROUP BY 1, 2
ORDER BY 1 DESC, 2;
