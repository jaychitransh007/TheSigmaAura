-- Panel 5 — Repeat / Retention
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- second_session_within_14d
WITH first_seen AS (
    SELECT user_id, MIN(created_at) AS first_at
    FROM dependency_validation_events
    WHERE event_type = 'turn_completed'
    GROUP BY user_id
),
second_session AS (
    SELECT
        e.user_id,
        MIN(e.created_at) AS second_at
    FROM dependency_validation_events e
    JOIN first_seen f USING (user_id)
    WHERE event_type = 'turn_completed'
      AND e.created_at >= f.first_at + interval '12 hours'
      AND e.created_at <= f.first_at + interval '14 days'
    GROUP BY e.user_id
)
SELECT
    COUNT(*)                                  AS users_with_first_session,
    COUNT(s.user_id)                          AS users_with_second_session,
    round(
        100.0 * COUNT(s.user_id) / nullif(COUNT(*), 0),
        2
    ) AS second_session_rate_pct
FROM first_seen f
LEFT JOIN second_session s USING (user_id);
