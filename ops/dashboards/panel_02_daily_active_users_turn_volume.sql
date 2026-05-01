-- Panel 2 — Daily Active Users / Turn Volume
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- daily_turn_volume_by_channel
SELECT
    date_trunc('day', created_at) AS day,
    coalesce(source_channel, 'web') AS channel,
    COUNT(*)                       AS turns,
    COUNT(DISTINCT user_id)        AS active_users
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND created_at >= now() - interval '30 days'
GROUP BY 1, 2
ORDER BY 1 DESC, 2;
