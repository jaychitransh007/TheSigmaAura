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

## Panel 9 — Visual Evaluator Path Mix (Phase 12B+)

**Question:** what fraction of recommendation turns took the new visual
evaluator path vs the legacy text-only fallback? The visual path activates
when the user has a full-body profile photo on file. A sustained drop in
the visual share usually means a regression in person-image upload OR a
spike in `tryon_quality_gate_failures`.

```sql
-- evaluator_path_mix_last_7d
SELECT
    coalesce(metadata_json->>'evaluator_path', 'unknown') AS evaluator_path,
    COUNT(*) AS turns,
    round(
        100.0 * COUNT(*) / sum(COUNT(*)) OVER (),
        2
    ) AS share_pct
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND primary_intent IN ('occasion_recommendation', 'pairing_request')
  AND created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY turns DESC;
```

Healthy steady state:
- `visual` ~ 60–80% (most users with full-body photos)
- `legacy_text` ~ 20–40% (users without photos, plus fallback after a
  visual-path exception)

If `visual` drops below 50%, check Panel 10 (quality gate failures) and
Panel 12 (wardrobe enrichment failures) before assuming a code regression.

---

## Panel 10 — Try-on Quality Gate Health (Phase 12E)

**Question:** how often are try-on renders being rejected by the quality
gate, and how often does over-generation save the turn?

```sql
-- tryon_quality_gate_failure_rate_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    sum( (metadata_json->'tryon_stats'->>'tryon_attempted_count')::int )    AS attempts,
    sum( (metadata_json->'tryon_stats'->>'tryon_succeeded_count')::int )    AS successes,
    sum( (metadata_json->'tryon_stats'->>'tryon_quality_gate_failures')::int ) AS quality_gate_failures,
    sum( (metadata_json->'tryon_stats'->>'tryon_overgeneration_used')::int )  AS turns_using_overgeneration,
    round(
        100.0 * sum( (metadata_json->'tryon_stats'->>'tryon_quality_gate_failures')::int )::numeric
        / nullif(sum( (metadata_json->'tryon_stats'->>'tryon_attempted_count')::int ), 0),
        2
    ) AS quality_gate_failure_rate_pct
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND created_at >= now() - interval '7 days'
  AND metadata_json ? 'tryon_stats'
GROUP BY 1
ORDER BY 1 DESC;
```

Healthy steady state:
- `quality_gate_failure_rate_pct` < 15% — anything above 25% means the
  Gemini try-on output is degrading and Phase 12E reranker calibration
  needs to start de-prioritizing low-quality candidates upstream
- `turns_using_overgeneration` should be a small fraction of total turns;
  a sharp increase means the natural top-3 candidates are failing the
  quality gate often enough to force the pool walk into positions 4-5

---

## Panel 11 — Final Response Count Below Target (Phase 12E)

**Question:** how often does over-generation exhaust the pool and ship
fewer than 3 outfits? This is the operational signal that the assembler
needs to produce more candidates OR the quality gate is too strict.

```sql
-- response_count_below_target_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) FILTER (
        WHERE (metadata_json->>'outfit_count')::int < 3
          AND primary_intent IN ('occasion_recommendation', 'pairing_request')
    ) AS sub_target_turns,
    COUNT(*) FILTER (
        WHERE primary_intent IN ('occasion_recommendation', 'pairing_request')
    ) AS recommendation_turns,
    round(
        100.0 * COUNT(*) FILTER (
            WHERE (metadata_json->>'outfit_count')::int < 3
              AND primary_intent IN ('occasion_recommendation', 'pairing_request')
        )::numeric / nullif(COUNT(*) FILTER (
            WHERE primary_intent IN ('occasion_recommendation', 'pairing_request')
        ), 0),
        2
    ) AS sub_target_share_pct
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1 DESC;
```

Healthy: `sub_target_share_pct < 5%`. Page someone if it crosses 15%.

---

## Panel 12 — Wardrobe Enrichment Failure Rate (Phase 12D)

**Question:** how often is the 46-attribute vision enrichment failing on
chat-uploaded garments? Phase 12D added retry logic and graceful
clarification, so users no longer see silent generic responses, but a
sustained spike means the enrichment model itself is degrading.

```sql
-- wardrobe_enrichment_failure_rate_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) FILTER (
        WHERE 'wardrobe_enrichment_failed' = ANY(
            ARRAY(
                SELECT jsonb_array_elements_text(
                    coalesce(resolved_context_json->'response_metadata'->'intent_reason_codes', '[]'::jsonb)
                )
            )
        )
    ) AS enrichment_failed_turns,
    COUNT(*) FILTER (
        WHERE resolved_context_json->'intent_classification'->>'primary_intent' IN (
            'pairing_request', 'occasion_recommendation', 'garment_evaluation'
        )
    ) AS image_capable_turns
FROM conversation_turns
WHERE created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1 DESC;
```

Healthy: `enrichment_failed_turns / image_capable_turns < 5%`.

If this rate spikes:
1. Check the OpenAI status page — the vision model used by
   `wardrobe_enrichment.infer_wardrobe_catalog_attributes` may be
   degraded.
2. Check the `metadata_json.catalog_attribute_error` column on recent
   wardrobe items for the actual error message.
3. The retry-once logic in `service.py:save_wardrobe_item` already
   absorbs transient failures. A persistent spike means the model
   itself is broken or rate-limited.

---

## Panel 13 — Wardrobe-Anchor Try-on Coverage (Phase 12D follow-up)

**Question:** when a user uploads a garment with a pairing question, is
the wardrobe anchor's image actually reaching Gemini? The April 8, 2026
fix made `_product_to_item` resolve `image_url` from the wardrobe
`image_path` and tag `source="wardrobe"`. Before the fix, all
pairing-with-upload turns showed `garment_source="catalog"` and Gemini
hallucinated a stand-in garment instead of using the user's photo.

```sql
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
```

Healthy: for any turn where the user uploaded a garment, the resulting
try-on rows should be `mixed` (anchor + catalog companion) or `wardrobe`
(all-wardrobe outfit). A `catalog`-only label on a turn that started
from an upload is the regression signal — it means `_product_to_item`
or `tryon_service.generate_tryon_outfit` lost the wardrobe path
somewhere and Gemini is hallucinating again.

To narrow to upload turns specifically, join against `conversation_turns`
on `turn_id` and filter for turns where the planner saw an
`anchor_garment` in `live_context_json`.

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
