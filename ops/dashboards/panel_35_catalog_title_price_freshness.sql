-- Panel 35 — Catalog Title/Price Freshness
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- Catalog title/price freshness over the last 7 days.
-- Splits by row_status so deleted_from_source rows (which legitimately
-- have empty title/null price) don't pollute the regression signal.
SELECT
    date_trunc('day', created_at)            AS day,
    COUNT(*)                                 AS rows_ingested,
    COUNT(*) FILTER (WHERE coalesce(row_status, '') <> 'deleted_from_source'
                       AND (title IS NULL OR title = ''))
                                             AS empty_title_live_rows,
    COUNT(*) FILTER (WHERE coalesce(row_status, '') <> 'deleted_from_source'
                       AND price IS NULL)    AS null_price_live_rows,
    COUNT(*) FILTER (WHERE row_status = 'deleted_from_source')
                                             AS deleted_from_source_rows
FROM catalog_enriched
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY day
ORDER BY day DESC;
