-- Panel 30 — User-preference override + hard-attr penalty cap-hit trends (Phase 5x.4a)
-- Source: model_call_logs.request_json + turn_traces.query_entities
--
-- Tracks two Phase 5x knobs together:
-- (1) Override rate — how often a user-explicit preference replaces a
--     YAML-derived default. High rate means user prefs are dominating
--     architect output; low rate means they're marginal.
-- (2) Cap hit rate — how often cumulative hard-attr penalty would have
--     exceeded HARD_ATTR_PENALTY_CAP (0.40) and got clipped. Frequent
--     caps suggest the cap is too tight and should be loosened; never
--     hits suggest it's unreachable and can be removed.
--
-- Neither is logged into turn_traces directly today (Prometheus-only),
-- so this panel is the SQL fallback: it counts turns that HAD an
-- extracted_preferences map AND a recommendation pipeline so we have a
-- denominator. Pair with the Prometheus dashboard (aura_user_preference_
-- override_total / aura_hard_attr_penalty_cap_hit_total) for the per-
-- attribute / per-stage slice.

-- daily_5x_signal_volume_last_14d
WITH base AS (
    SELECT
        created_at::date AS day,
        turn_id,
        query_entities ? 'extracted_preferences' AS has_prefs,
        COALESCE(jsonb_typeof(query_entities -> 'extracted_preferences'), 'null') = 'object'
            AND query_entities -> 'extracted_preferences' <> '{}'::jsonb AS prefs_non_empty,
        primary_intent
    FROM turn_traces
    WHERE created_at >= now() - interval '14 days'
      AND primary_intent = 'occasion_recommendation'
)
SELECT
    day,
    COUNT(*) AS recommendation_turns,
    COUNT(*) FILTER (WHERE has_prefs) AS turns_with_prefs_field,
    COUNT(*) FILTER (WHERE prefs_non_empty) AS turns_with_explicit_prefs,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE prefs_non_empty)
        / NULLIF(COUNT(*), 0),
        1
    ) AS pct_turns_with_explicit_prefs
FROM base
GROUP BY day
ORDER BY day DESC;
