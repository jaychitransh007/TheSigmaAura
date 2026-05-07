-- Panel 29 — Planner extracted_preferences extraction rate by axis (Phase 5x.4a)
-- Source: turn_traces.query_entities.extracted_preferences
--
-- Measures how often the planner is extracting each open-axis user preference
-- (EmbellishmentLevel, ContrastLevel, NecklineType, FabricDrape, ...). High
-- extraction count for an axis = users mention it often AND planner picks it
-- up. Low / zero count for an axis we expect to be active = either users
-- aren't asking for it OR planner is missing it. Cross-reference with
-- turn_traces.user_message for the latter case to find prompt gaps.

-- planner_extraction_by_axis_last_7d
WITH entries AS (
    SELECT
        attr_name,
        created_at::date AS day,
        turn_id
    FROM turn_traces,
         jsonb_each(
             COALESCE(query_entities -> 'extracted_preferences', '{}'::jsonb)
         ) AS p(attr_name, allowed_values)
    WHERE created_at >= now() - interval '7 days'
      AND query_entities ? 'extracted_preferences'
)
SELECT
    attr_name AS attribute,
    COUNT(DISTINCT turn_id) AS turns_extracted,
    COUNT(DISTINCT day) AS days_seen
FROM entries
GROUP BY attr_name
ORDER BY turns_extracted DESC;
