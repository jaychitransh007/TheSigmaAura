-- Panel 11 — Final Response Count Below Target (Phase 12E)
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- response_count_below_target_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) FILTER (
        WHERE (metadata_json->>'outfit_count')::int < 3
          AND primary_intent IN ('occasion_recommendation', 'pairing_request')
    ) AS sub_target_turns,
    COUNT(*) FILTER (
        WHERE primary_intent IN ('occasion_recommendation', 'pairing_request')
    ) AS recommendation_turns,
    round(
        100.0 * COUNT(*) FILTER (
            WHERE (metadata_json->>'outfit_count')::int < 3
              AND primary_intent IN ('occasion_recommendation', 'pairing_request')
        )::numeric / nullif(COUNT(*) FILTER (
            WHERE primary_intent IN ('occasion_recommendation', 'pairing_request')
        ), 0),
        2
    ) AS sub_target_share_pct
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1 DESC;
