-- Panel 10 — Try-on Quality Gate Health (Phase 12E)
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- tryon_quality_gate_failure_rate_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    sum( (metadata_json->'tryon_stats'->>'tryon_attempted_count')::int )    AS attempts,
    sum( (metadata_json->'tryon_stats'->>'tryon_succeeded_count')::int )    AS successes,
    sum( (metadata_json->'tryon_stats'->>'tryon_quality_gate_failures')::int ) AS quality_gate_failures,
    sum( (metadata_json->'tryon_stats'->>'tryon_overgeneration_used')::int )  AS turns_using_overgeneration,
    round(
        100.0 * sum( (metadata_json->'tryon_stats'->>'tryon_quality_gate_failures')::int )::numeric
        / nullif(sum( (metadata_json->'tryon_stats'->>'tryon_attempted_count')::int ), 0),
        2
    ) AS quality_gate_failure_rate_pct
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND created_at >= now() - interval '7 days'
  AND metadata_json ? 'tryon_stats'
GROUP BY 1
ORDER BY 1 DESC;
