-- Panel 23 — Composition Per-Attribute Status
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- composition_attribute_status_last_30d
WITH entries AS (
    SELECT
        status,
        attribute,
        created_at::date AS day
    FROM distillation_traces,
         jsonb_each(
             COALESCE(full_output -> 'router_decision' -> 'provenance_summary', '{}'::jsonb)
         ) AS s(status, attrs),
         jsonb_array_elements_text(attrs) AS attribute
    WHERE stage = 'outfit_architect'
      AND created_at >= now() - interval '30 days'
)
SELECT
    status,
    attribute,
    COUNT(*) AS occurrences,
    COUNT(DISTINCT day) AS days_seen
FROM entries
GROUP BY status, attribute
ORDER BY status, occurrences DESC;
