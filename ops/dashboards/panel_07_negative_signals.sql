-- Panel 7 — Negative Signals
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- dislike_volume_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) AS dislikes,
    COUNT(DISTINCT user_id) AS users_disliking,
    COUNT(DISTINCT garment_id) AS unique_disliked_products
FROM feedback_events
WHERE event_type = 'dislike'
  AND created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1 DESC;

-- top_disliked_products
SELECT
    garment_id,
    COUNT(*)              AS dislike_count,
    COUNT(DISTINCT user_id) AS distinct_users
FROM feedback_events
WHERE event_type = 'dislike'
  AND created_at >= now() - interval '14 days'
GROUP BY garment_id
ORDER BY dislike_count DESC
LIMIT 20;
