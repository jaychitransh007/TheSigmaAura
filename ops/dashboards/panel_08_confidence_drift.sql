-- Panel 8 — Confidence Drift
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- recommendation_confidence_distribution_last_7d
SELECT
    width_bucket(score_pct, 0, 100, 10) AS bucket_10pct,
    COUNT(*) AS turns,
    round(avg(score_pct), 1) AS avg_pct
FROM confidence_history
WHERE confidence_type = 'recommendation'
  AND created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1;
