-- Panel 16 — Low-Confidence Catalog Responses
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- low_confidence_catalog_response_rate_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) FILTER (WHERE metadata_json->>'answer_source' = 'catalog_low_confidence') AS low_conf_turns,
    COUNT(*) AS total_turns,
    round(
        100.0 * COUNT(*) FILTER (WHERE metadata_json->>'answer_source' = 'catalog_low_confidence')::numeric
        / nullif(COUNT(*), 0),
        2
    ) AS low_conf_rate_pct,
    round(avg((metadata_json->>'low_confidence_top_match_score')::numeric), 3) AS avg_top_match_score_when_blocked
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND primary_intent IN ('occasion_recommendation', 'pairing_request')
  AND created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1 DESC;
