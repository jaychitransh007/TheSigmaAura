-- Panel 6 — Wardrobe & Catalog Engagement
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- source_preference_share_last_7d (May 5 2026: includes the new
-- auto→catalog default and the wardrobe_unavailable gap fallback)
SELECT
    coalesce(metadata_json->>'answer_source', 'unknown') AS answer_source,
    COUNT(*)                                              AS turns,
    round(100.0 * COUNT(*)::numeric
          / nullif(SUM(COUNT(*)) OVER (), 0), 2)          AS pct_of_total
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND created_at >= now() - interval '7 days'
  AND metadata_json->>'answer_source' IN (
      'catalog_only',
      'catalog_low_confidence',
      'wardrobe_first',
      'wardrobe_first_hybrid',
      'wardrobe_first_pairing',
      'wardrobe_first_pairing_hybrid',
      'wardrobe_unavailable'
  )
GROUP BY 1
ORDER BY turns DESC;

-- wardrobe_first_share_last_7d (now an opt-in slice — expect <30% of
-- turns post-#82; if higher, planner is over-routing to wardrobe)
SELECT
    metadata_json->>'answer_source' AS answer_source,
    COUNT(*)                        AS turns
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND created_at >= now() - interval '7 days'
  AND metadata_json->>'answer_source' IN (
      'wardrobe_first',
      'wardrobe_first_hybrid',
      'wardrobe_first_pairing',
      'wardrobe_first_pairing_hybrid'
  )
GROUP BY 1
ORDER BY turns DESC;

-- catalog_interaction_volume
SELECT
    date_trunc('day', created_at) AS day,
    interaction_type,
    COUNT(*) AS events
FROM catalog_interaction_history
WHERE created_at >= now() - interval '7 days'
GROUP BY 1, 2
ORDER BY 1 DESC, 2;
