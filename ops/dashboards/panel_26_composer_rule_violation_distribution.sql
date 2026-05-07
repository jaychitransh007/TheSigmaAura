-- Panel 26 — Composer Rule-Violation Distribution
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- composer_drop_reason_distribution_last_30d
WITH reasons AS (
    SELECT
        kv.key  AS drop_reason,
        kv.value::int AS count,
        created_at::date AS day
    FROM distillation_traces,
         jsonb_each_text(
             COALESCE(
                 full_output -> 'composer_router_decision' -> 'provenance_summary' -> 'dropped_by_reason',
                 '{}'::jsonb
             )
         ) AS kv
    WHERE stage = 'outfit_composer'
      AND created_at >= now() - interval '30 days'
)
SELECT
    drop_reason,
    SUM(count)        AS total_drops,
    COUNT(DISTINCT day) AS days_seen,
    MIN(day)          AS first_seen,
    MAX(day)          AS last_seen
FROM reasons
GROUP BY drop_reason
ORDER BY total_drops DESC
LIMIT 30;
