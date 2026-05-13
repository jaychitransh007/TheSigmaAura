-- Panel 36 — Retrieval Empty After Relaxation
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- retrieval_empty_after_relaxation_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) AS turns,
    COUNT(*) FILTER (
        WHERE metadata_json->>'retrieval_relaxation_outcome' = 'exhausted'
          AND (metadata_json->>'retrieval_total_products')::int = 0
    ) AS retrieval_empty_after_relaxation,
    COUNT(*) FILTER (
        WHERE metadata_json->>'answer_source' = 'catalog_low_confidence'
    ) AS low_conf_total,
    round(
        100.0 * COUNT(*) FILTER (
            WHERE metadata_json->>'retrieval_relaxation_outcome' = 'exhausted'
              AND (metadata_json->>'retrieval_total_products')::int = 0
        )::numeric
        / nullif(COUNT(*), 0),
        3
    ) AS empty_after_relax_pct
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND primary_intent IN ('occasion_recommendation', 'pairing_request')
  AND created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1 DESC;
