-- Panel 32 — Composition Per-Axis Gap Impact
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- Per-axis impact from distillation_traces, last 7 days. Uses the
-- per_axis_gap_impact JSON populated by router.py:RouterDecision.
-- Dollars-and-cents view: how much confidence each axis cost the
-- engine across the cohort.
SELECT
    axis,
    COUNT(*)         AS turns_with_gap,
    AVG(impact)      AS avg_impact_per_turn,
    SUM(impact)      AS total_impact_7d
FROM distillation_traces,
     LATERAL jsonb_each_text(
       full_output -> 'router_decision' -> 'per_axis_gap_impact'
     ) AS gap(axis, impact_str)
CROSS JOIN LATERAL (SELECT impact_str::float AS impact) AS i
WHERE stage = 'outfit_architect'
  AND created_at >= NOW() - INTERVAL '7 days'
  AND full_output -> 'router_decision' -> 'per_axis_gap_impact' IS NOT NULL
GROUP BY axis
ORDER BY total_impact_7d DESC;
