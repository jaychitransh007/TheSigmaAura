-- Panel 20 — Episodic Memory Population
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- episodic_memory_population_rate_last_7d
WITH recent_users AS (
    SELECT DISTINCT user_id
    FROM dependency_validation_events
    WHERE event_type = 'turn_completed'
      AND created_at >= now() - interval '30 days'
),
users_with_feedback AS (
    SELECT DISTINCT user_id
    FROM feedback_events
    WHERE event_type IN ('like', 'dislike')
      AND created_at >= now() - interval '30 days'
)
SELECT
    (SELECT COUNT(*) FROM recent_users)                                AS recent_active_users,
    (SELECT COUNT(*) FROM users_with_feedback)                         AS users_with_episodic_signal,
    round(
        100.0 * (SELECT COUNT(*) FROM users_with_feedback)::numeric
        / nullif((SELECT COUNT(*) FROM recent_users), 0),
        2
    ) AS population_pct;
