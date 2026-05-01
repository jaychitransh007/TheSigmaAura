-- Panel 9 — Visual Evaluator Path Mix (Phase 12B+)
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- evaluator_path_mix_last_7d
SELECT
    coalesce(metadata_json->>'evaluator_path', 'unknown') AS evaluator_path,
    COUNT(*) AS turns,
    round(
        100.0 * COUNT(*) / sum(COUNT(*)) OVER (),
        2
    ) AS share_pct
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND primary_intent IN ('occasion_recommendation', 'pairing_request')
  AND created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY turns DESC;
