-- Panel 3 — Intent Mix
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- intent_distribution_last_7d
SELECT
    primary_intent,
    COUNT(*) AS turns
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY turns DESC;

-- answer_source_mix_last_7d
SELECT
    coalesce(metadata_json->>'answer_source', 'unknown') AS answer_source,
    COUNT(*) AS turns
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY turns DESC;
