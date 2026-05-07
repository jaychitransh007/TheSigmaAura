-- Panel 31 — Retrieval-stage hard_attr violation rate by axis (Phase 5x.4 follow-up)
-- Source: distillation_traces.full_output.retrieved_sets[*].attr_violation_summary
--
-- Per-attribute breakdown of how often retrieval demoted items because
-- their enriched_data violated the architect's resolved allowed-value
-- list. Each row is one (turn, query, attribute) cell.
--
-- Columns:
-- - attribute: the catalog_enriched key (PascalCase)
-- - eligible_items: count of items in the rerank pool that CARRIED a
--   non-empty value for this attribute (denominator)
-- - violations: count among those that violated the allowed list
--   (numerator)
-- - violation_rate_pct: violations / eligible_items × 100
--
-- What to look for:
-- - One axis with >70% violation rate AND high eligible_items =
--   architect/planner is asking for something the catalog mostly
--   doesn't carry. Either expand the allowed list or accept the
--   sparse pool.
-- - One axis with near-zero violations AND high eligible_items =
--   axis is dead weight (everyone matches); could be dropped from
--   the rerank without changing behavior.
-- - One axis with low eligible_items = catalog enrichment is sparse
--   on that field; the axis isn't biting at all.

-- retrieval_attr_violation_rate_last_7d
WITH per_set AS (
    SELECT
        attr_name,
        (s.value ->> 'items_with_attr')::int AS eligible,
        (s.value ->> 'violations')::int AS violations
    FROM distillation_traces dt,
         jsonb_array_elements(
             COALESCE(dt.full_output -> 'retrieved_sets', '[]'::jsonb)
         ) AS rs,
         jsonb_each(
             COALESCE(rs -> 'attr_violation_summary', '{}'::jsonb)
         ) AS s(attr_name, value)
    WHERE dt.stage = 'catalog_search'
      AND dt.created_at >= now() - interval '7 days'
)
SELECT
    attr_name AS attribute,
    SUM(eligible) AS eligible_items,
    SUM(violations) AS violations,
    ROUND(
        100.0 * SUM(violations) / NULLIF(SUM(eligible), 0),
        1
    ) AS violation_rate_pct
FROM per_set
GROUP BY attr_name
HAVING SUM(eligible) > 0
ORDER BY violation_rate_pct DESC NULLS LAST, violations DESC;
