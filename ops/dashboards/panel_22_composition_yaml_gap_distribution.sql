-- Panel 22 — Composition YAML-Gap Distribution
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- composition_yaml_gap_top_n_last_30d
WITH gaps AS (
    SELECT
        gap_value AS gap,
        created_at::date AS day
    FROM distillation_traces,
         jsonb_array_elements_text(
             COALESCE(full_output -> 'router_decision' -> 'yaml_gaps', '[]'::jsonb)
         ) AS gap_value
    WHERE stage = 'outfit_architect'
      AND created_at >= now() - interval '30 days'
)
SELECT
    gap,
    COUNT(*) AS occurrences,
    COUNT(DISTINCT day) AS days_seen,
    MIN(day) AS first_seen,
    MAX(day) AS last_seen
FROM gaps
GROUP BY gap
ORDER BY occurrences DESC
LIMIT 30;
