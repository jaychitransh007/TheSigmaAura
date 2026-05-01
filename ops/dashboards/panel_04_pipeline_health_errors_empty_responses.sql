-- Panel 4 — Pipeline Health (Errors & Empty Responses)
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- pipeline_error_rate_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) FILTER (WHERE assistant_message IS NULL OR assistant_message = '') AS empty_responses,
    COUNT(*) FILTER (WHERE resolved_context_json ? 'error')                     AS error_responses,
    COUNT(*)                                                                    AS total_turns,
    round(
        100.0 * COUNT(*) FILTER (WHERE resolved_context_json ? 'error')::numeric
        / nullif(COUNT(*), 0),
        2
    ) AS error_rate_pct
FROM conversation_turns
WHERE created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1 DESC;

-- catalog_unavailable_guardrail_hits
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) AS guardrail_hits
FROM conversation_turns
WHERE created_at >= now() - interval '7 days'
  AND resolved_context_json->>'error' = 'catalog_unavailable'
GROUP BY 1
ORDER BY 1 DESC;
