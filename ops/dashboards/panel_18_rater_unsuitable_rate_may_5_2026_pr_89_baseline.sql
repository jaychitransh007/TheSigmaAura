-- Panel 18 — Rater Unsuitable Rate (May 5 2026, PR #89 baseline)
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- rater_unsuitable_rate_last_7d
WITH rater_calls AS (
    SELECT
        date_trunc('day', t.created_at) AS day,
        jsonb_array_elements(t.output_json->'ranked_outfits') AS outfit
    FROM tool_traces t
    WHERE t.tool_name = 'rater_decision'
      AND t.created_at >= now() - interval '7 days'
)
SELECT
    day,
    COUNT(*) AS rated_outfits,
    SUM(CASE WHEN (outfit->>'unsuitable')::boolean THEN 1 ELSE 0 END) AS unsuitable_outfits,
    round(
        100.0 * SUM(CASE WHEN (outfit->>'unsuitable')::boolean THEN 1 ELSE 0 END)::numeric
        / nullif(COUNT(*), 0),
        2
    ) AS unsuitable_pct
FROM rater_calls
GROUP BY 1
ORDER BY 1 DESC;
