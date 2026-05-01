-- Panel 13 — Wardrobe-Anchor Try-on Coverage (Phase 12D follow-up)
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- wardrobe_anchor_tryon_coverage_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) FILTER (WHERE garment_source = 'mixed')   AS mixed_renders,
    COUNT(*) FILTER (WHERE garment_source = 'wardrobe') AS wardrobe_only_renders,
    COUNT(*) FILTER (WHERE garment_source = 'catalog')  AS catalog_only_renders,
    COUNT(*)                                            AS total_renders
FROM virtual_tryon_images
WHERE created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1 DESC;
