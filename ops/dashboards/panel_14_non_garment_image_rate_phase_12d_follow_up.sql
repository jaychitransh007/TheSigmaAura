-- Panel 14 — Non-Garment Image Rate (Phase 12D follow-up)
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- non_garment_image_rate_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) FILTER (
        WHERE 'non_garment_image' = ANY(
            ARRAY(
                SELECT jsonb_array_elements_text(
                    coalesce(resolved_context_json->'response_metadata'->'intent_reason_codes', '[]'::jsonb)
                )
            )
        )
    ) AS non_garment_turns,
    COUNT(*) FILTER (
        WHERE resolved_context_json->'intent_classification'->>'primary_intent' IN (
            'pairing_request', 'occasion_recommendation', 'outfit_check'
        )
    ) AS image_capable_turns
FROM conversation_turns
WHERE created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1 DESC;
