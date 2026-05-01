-- Panel 1 — Acquisition & Onboarding Funnel
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- onboarding_funnel
SELECT
    COUNT(*)                                                      AS total_starts,
    COUNT(*) FILTER (WHERE profile_complete)                      AS profile_complete,
    COUNT(*) FILTER (WHERE style_preference_complete)             AS style_preference_complete,
    COUNT(*) FILTER (WHERE onboarding_complete)                   AS onboarding_complete
FROM onboarding_profiles
WHERE created_at >= now() - interval '30 days';

-- acquisition_source_breakdown
SELECT
    coalesce(acquisition_source, 'unknown') AS source,
    COUNT(*)                                AS users,
    COUNT(*) FILTER (WHERE onboarding_complete) AS onboarded
FROM onboarding_profiles
WHERE created_at >= now() - interval '30 days'
GROUP BY 1
ORDER BY users DESC;
