-- Panel 34 — Try-on Cache Hit-Rate
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- Try-on cache hit rate over the last 7 days.
-- Each row in model_call_logs is one render attempt; the call_type
-- distinguishes hit from miss.
WITH tryon_decisions AS (
    SELECT
        CASE
            WHEN call_type = 'virtual_tryon_cache_hit' THEN 'hit'
            WHEN call_type = 'virtual_tryon'           THEN 'miss'
            ELSE 'other'
        END AS outcome,
        created_at::date AS day
    FROM model_call_logs
    WHERE call_type IN ('virtual_tryon', 'virtual_tryon_cache_hit')
      AND created_at >= NOW() - INTERVAL '7 days'
)
SELECT
    day,
    COUNT(*)                                  AS total_renders,
    COUNT(*) FILTER (WHERE outcome = 'hit')   AS cache_hits,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE outcome = 'hit')
        / NULLIF(COUNT(*), 0),
        1
    )                                         AS hit_rate_pct
FROM tryon_decisions
GROUP BY day
ORDER BY day DESC;
