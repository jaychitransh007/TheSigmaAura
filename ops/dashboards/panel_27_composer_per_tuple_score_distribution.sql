-- Panel 27 — Composer Per-Tuple Score Distribution
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- composer_tuple_score_histogram_last_7d
WITH scores AS (
    SELECT
        (entry ->> 'base_score')::float AS base_score,
        (entry ->> 'diversity_multiplier')::float AS diversity_multiplier,
        (entry ->> 'picked')::bool      AS picked
    FROM distillation_traces,
         jsonb_array_elements(
             COALESCE(
                 full_output -> 'composer_router_decision' -> 'provenance',
                 '[]'::jsonb
             )
         ) AS entry
    WHERE stage = 'outfit_composer'
      AND created_at >= now() - interval '7 days'
)
SELECT
    width_bucket(base_score, 0.0, 1.0, 10) AS score_bucket,
    COUNT(*)                                AS tuples,
    COUNT(*) FILTER (WHERE picked)          AS picked,
    AVG(diversity_multiplier)               AS avg_diversity_multiplier
FROM scores
GROUP BY score_bucket
ORDER BY score_bucket;
