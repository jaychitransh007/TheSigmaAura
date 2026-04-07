# Operations: Dashboards & Queries (First-50 Rollout)

This document defines the SQL queries and dashboard panels needed to monitor
Aura during the first-50 user validation rollout. Every query targets the
canonical Supabase tables documented in `docs/CURRENT_STATE.md` (§ Database
Table Inventory) and assumes you are connected as a read-only role.

The queries are grouped by panel. Each panel maps to one operational
question. Save them in your Supabase / Metabase / Grafana dashboard and
keep this file as the source of truth.

---

## Panel 1 — Acquisition & Onboarding Funnel

**Question:** how many people start onboarding, finish it, and reach analysis-complete?

```sql
-- onboarding_funnel
SELECT
    COUNT(*)                                                      AS total_starts,
    COUNT(*) FILTER (WHERE profile_complete)                      AS profile_complete,
    COUNT(*) FILTER (WHERE style_preference_complete)             AS style_preference_complete,
    COUNT(*) FILTER (WHERE onboarding_complete)                   AS onboarding_complete
FROM onboarding_profiles
WHERE created_at >= now() - interval '30 days';
```

```sql
-- acquisition_source_breakdown
SELECT
    coalesce(acquisition_source, 'unknown') AS source,
    COUNT(*)                                AS users,
    COUNT(*) FILTER (WHERE onboarding_complete) AS onboarded
FROM onboarding_profiles
WHERE created_at >= now() - interval '30 days'
GROUP BY 1
ORDER BY users DESC;
```

---

## Panel 2 — Daily Active Users / Turn Volume

**Question:** how busy is the recommendation pipeline, and across which channels?

```sql
-- daily_turn_volume_by_channel
SELECT
    date_trunc('day', created_at) AS day,
    coalesce(source_channel, 'web') AS channel,
    COUNT(*)                       AS turns,
    COUNT(DISTINCT user_id)        AS active_users
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND created_at >= now() - interval '30 days'
GROUP BY 1, 2
ORDER BY 1 DESC, 2;
```

---

## Panel 3 — Intent Mix

**Question:** what are users actually asking for?

```sql
-- intent_distribution_last_7d
SELECT
    primary_intent,
    COUNT(*) AS turns
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY turns DESC;
```

```sql
-- answer_source_mix_last_7d
SELECT
    coalesce(metadata_json->>'answer_source', 'unknown') AS answer_source,
    COUNT(*) AS turns
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY turns DESC;
```

---

## Panel 4 — Pipeline Health (Errors & Empty Responses)

**Question:** are users seeing graceful fallbacks or silent failures?

```sql
-- pipeline_error_rate_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) FILTER (WHERE assistant_message IS NULL OR assistant_message = '') AS empty_responses,
    COUNT(*) FILTER (WHERE resolved_context_json ? 'error')                     AS error_responses,
    COUNT(*)                                                                    AS total_turns,
    round(
        100.0 * COUNT(*) FILTER (WHERE resolved_context_json ? 'error')::numeric
        / nullif(COUNT(*), 0),
        2
    ) AS error_rate_pct
FROM conversation_turns
WHERE created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1 DESC;
```

The empty-response count should be **zero** after the silent-empty-response
guard landed (`docs/CURRENT_STATE.md` P0 — Silent empty response, April 2026).
If it goes above zero, the post-pipeline guard regressed.

```sql
-- catalog_unavailable_guardrail_hits
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) AS guardrail_hits
FROM conversation_turns
WHERE created_at >= now() - interval '7 days'
  AND resolved_context_json->>'error' = 'catalog_unavailable'
GROUP BY 1
ORDER BY 1 DESC;
```

A non-zero count here means an environment is missing catalog data /
embeddings — usually a local dev box or a staging instance that never
finished its sync.

---

## Panel 5 — Repeat / Retention

**Question:** are people coming back?

```sql
-- second_session_within_14d
WITH first_seen AS (
    SELECT user_id, MIN(created_at) AS first_at
    FROM dependency_validation_events
    WHERE event_type = 'turn_completed'
    GROUP BY user_id
),
second_session AS (
    SELECT
        e.user_id,
        MIN(e.created_at) AS second_at
    FROM dependency_validation_events e
    JOIN first_seen f USING (user_id)
    WHERE event_type = 'turn_completed'
      AND e.created_at >= f.first_at + interval '12 hours'
      AND e.created_at <= f.first_at + interval '14 days'
    GROUP BY e.user_id
)
SELECT
    COUNT(*)                                  AS users_with_first_session,
    COUNT(s.user_id)                          AS users_with_second_session,
    round(
        100.0 * COUNT(s.user_id) / nullif(COUNT(*), 0),
        2
    ) AS second_session_rate_pct
FROM first_seen f
LEFT JOIN second_session s USING (user_id);
```

The same shape with `interval '30 days'` and a third-session check gives
you the third-session retention number that the dependency report tracks.

---

## Panel 6 — Wardrobe & Catalog Engagement

**Question:** is the wardrobe-first / hybrid path actually used?

```sql
-- wardrobe_first_share_last_7d
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
```

```sql
-- catalog_interaction_volume
SELECT
    date_trunc('day', created_at) AS day,
    interaction_type,
    COUNT(*) AS events
FROM catalog_interaction_history
WHERE created_at >= now() - interval '7 days'
GROUP BY 1, 2
ORDER BY 1 DESC, 2;
```

---

## Panel 7 — Negative Signals

**Question:** what is the user explicitly rejecting?

```sql
-- dislike_volume_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) AS dislikes,
    COUNT(DISTINCT user_id) AS users_disliking,
    COUNT(DISTINCT garment_id) AS unique_disliked_products
FROM feedback_events
WHERE event_type = 'dislike'
  AND created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1 DESC;
```

```sql
-- top_disliked_products
SELECT
    garment_id,
    COUNT(*)              AS dislike_count,
    COUNT(DISTINCT user_id) AS distinct_users
FROM feedback_events
WHERE event_type = 'dislike'
  AND created_at >= now() - interval '14 days'
GROUP BY garment_id
ORDER BY dislike_count DESC
LIMIT 20;
```

If a single product appears at the top of this list across many users, the
catalog enrichment for it is probably wrong — pull the row, audit the
attributes, and consider hiding it.

---

## Panel 8 — Confidence Drift

**Question:** is the system getting more or less confident over time?

```sql
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
```

---

## How to refresh

1. Open Supabase Studio (or your preferred SQL client) connected to staging.
2. Paste each query into a new dashboard panel and label it with the panel
   number above.
3. Set refresh to 5 minutes for panels 4 (pipeline health) and 7 (negative
   signals); the rest can refresh hourly.
4. When a panel definition changes, update **this file first** so the
   dashboard and the source of truth do not drift.

## Related artifacts

- `ops/scripts/smoke_test_full_flow.sh` — end-to-end smoke test against a
  live backend.
- `ops/scripts/validate_dependency_report.py` — seeded validation harness
  for `build_dependency_report`.
- `docs/RELEASE_READINESS.md` — release-readiness criteria built on top of
  these dashboards.
