# Operations: Dashboards & Queries (First-50 Rollout)

This document defines the SQL queries and dashboard panels needed to monitor
Aura during the first-50 user validation rollout. Every query targets the
canonical Supabase tables documented in `docs/APPLICATION_SPECS.md` (§ Database
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
guard landed (`docs/RELEASE_READINESS.md` § Recently Shipped — Silent empty response, April 2026).
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

**Question:** are recommendation turns consistently reaching the visual
evaluator? Photo upload is mandatory at onboarding, so the `visual` path
should fire for every recommendation turn. The only alternative is a
transient visual-evaluator failure (Gemini/OpenAI outage, timeout) which
now produces a graceful empty response (the legacy text-only
`OutfitEvaluator` fallback was removed April 9, 2026). A sustained
non-visual share means a code regression or an evaluator outage.

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
- `visual` should be ~100% (photo upload is mandatory, legacy fallback removed)
- Any `legacy_text` or `unknown` entries indicate a code regression or
  a turn that bypassed the visual evaluator due to a transient exception

If `visual` drops below 95%, check Panel 10 (quality gate failures) and
Panel 12 (wardrobe enrichment failures) for correlated spikes.

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
  Gemini try-on output is degrading and the LLM ranker
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

## Panel 14 — Non-Garment Image Rate (Phase 12D follow-up)

**Question:** how often are users uploading non-garment images
(charts, screenshots, landscapes, etc.) on chat upload turns? The
April 9, 2026 fix added explicit `is_garment_photo` classification
to the wardrobe enrichment and a `non_garment_image` reason code on
turns where the orchestrator short-circuited the pipeline. This
panel tracks the rate so a sustained spike can flag (a) a UX
problem (users not understanding what to upload), (b) a model
calibration drift (the vision model misclassifying real garments
as non-garments), or (c) intentional adversarial uploads.

```sql
-- non_garment_image_rate_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) FILTER (
        WHERE 'non_garment_image' = ANY(
            ARRAY(
                SELECT jsonb_array_elements_text(
                    coalesce(resolved_context_json->'response_metadata'->'intent_reason_codes', '[]'::jsonb)
                )
            )
        )
    ) AS non_garment_turns,
    COUNT(*) FILTER (
        WHERE resolved_context_json->'intent_classification'->>'primary_intent' IN (
            'pairing_request', 'occasion_recommendation', 'outfit_check'
        )
    ) AS image_capable_turns
FROM conversation_turns
WHERE created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1 DESC;
```

Healthy: `non_garment_turns / image_capable_turns < 5%` for typical
production traffic. A sustained spike means one of:

1. **Vision model drift** — gpt-5-mini is calibrating differently
   than before. Spot-check the rejected images by joining against
   `user_wardrobe_items` (image_path) for the affected turns. If
   they're real garments being misclassified, lower the
   `garment_present_confidence < 0.5` threshold in
   `orchestrator.py` or revisit the user_text instruction in
   `wardrobe_enrichment.py`.
2. **UX issue** — users repeatedly uploading the wrong thing means
   the chat composer needs clearer guidance about what photos are
   accepted. Consider an inline hint or a more prominent example.
3. **Adversarial / spam traffic** — if the rejected images cluster
   to specific users, treat as abuse and rate-limit or suspend.

Cross-reference with Panel 12 (Wardrobe Enrichment Failure Rate) —
the two are related but distinct. Enrichment failure means the
vision API call itself errored or returned empty critical fields;
non-garment is when the call SUCCEEDED but the model classified
the image as not-a-garment.

---

---

## Panel 15 — Catalog Search Timeout Rate (Post-Phase 13B)

**Question:** How often are vector similarity searches timing out?

**Context:** The `catalog_search_agent` runs parallel similarity RPCs against `catalog_item_embeddings`. Under load (7 concurrent queries × cosine scan over 1000+ rows), Supabase statement timeouts (error 57014) cause queries to return 0 products. Post-13B fix: workers reduced from 4→2 and retry-on-timeout added. This panel tracks whether timeouts still occur.

**Signal source:** Application logs from `catalog_search_agent`. The retry logic logs `WARNING` with `similarity_search TIMEOUT` on each timeout. Monitor via log aggregation (grep for `similarity_search TIMEOUT` or `similarity_search FAILED.*timeout`).

**Healthy:** zero timeouts in a 24h window. **Degraded:** occasional timeouts but retry succeeds (retried turns still produce 3 outfits). **Unhealthy:** persistent timeouts even after retry → users see 1-outfit responses. Escalation: check Supabase compute tier, DB connection pool, or add a pgvector HNSW index.

---

## Panel 16 — Low-Confidence Catalog Responses (May 3, 2026)

**Question:** how often does the 0.75 confidence threshold gate force a no-confident-match response instead of shipping outfits?

**Context:** As of May 3, 2026 the orchestrator drops outfits whose `fashion_score < 75` (LLM Rater 0–100 scale) and, when zero candidates clear, returns `answer_source = "catalog_low_confidence"` with `outfits=[]` and a graceful "I couldn't find a strong match" message + refine / show-closest / shop CTAs. This panel tracks that rate so the team can decide when the threshold is too aggressive (catalog needs broadening) vs working as intended (catalog has a real coverage gap).

```sql
-- low_confidence_catalog_response_rate_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    SUM(CASE WHEN metadata_json->>'answer_source' = 'catalog_low_confidence' THEN 1 ELSE 0 END) AS low_conf_turns,
    COUNT(*) AS total_turns,
    round(
        100.0 * SUM(CASE WHEN metadata_json->>'answer_source' = 'catalog_low_confidence' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
        2
    ) AS low_conf_rate_pct,
    round(avg((metadata_json->>'low_confidence_top_match_score')::numeric), 3) AS avg_top_match_score_when_blocked
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND primary_intent IN ('occasion_recommendation', 'pairing_request')
  AND created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1 DESC;
```

**Healthy:** `low_conf_rate_pct` stays <5%. The avg blocked top score should sit close to but below 0.75 (i.e., the gate is catching genuinely borderline turns, not way-off ones).

**Degraded:** `low_conf_rate_pct` 5–20%. Most likely a catalog gap or an architect drift producing weak query documents. Pull a sample of low-confidence turns from `turn_traces` (filter on `evaluation->>'answer_source' = 'catalog_low_confidence'`) and inspect each one's architect query documents + retrieved candidates manually — check whether the architect is targeting `garment_subtype` values the catalog doesn't carry well, or whether the user's seasonal palette / formality target has thin inventory. (A future Panel 17 would join `tool_traces.composer_decision` / `rater_decision` to `catalog_enriched.GarmentSubtype` to surface this automatically.)

**Unhealthy:** `low_conf_rate_pct` > 20% sustained. Either the threshold is too high for current catalog depth, or the architect / assembler is regressing. Pull a sample of low-confidence turns from `turn_traces` and inspect the query documents + retrieved products manually.

---

## How to refresh

1. Open Supabase Studio (or your preferred SQL client) connected to staging.
2. Paste each query into a new dashboard panel and label it with the panel
   number above.
3. Set refresh to 5 minutes for panels 4 (pipeline health) and 7 (negative
   signals); the rest can refresh hourly.
4. When a panel definition changes, update **this file first** so the
   dashboard and the source of truth do not drift.

## On-Call Runbook (First-50 Rollout)

This section satisfies Gate 3 of `docs/RELEASE_READINESS.md`. Every on-call
rotation must have an owner. Fill in the names below before the rollout and
keep them current.

### Rotation

- **Primary:** _______________________  (paged first, P1 ack within 15 min)
- **Secondary:** _____________________  (paged on no-ack escalation)
- **Engineering owner:** ____________   (architectural decisions, post-mortem)
- **Design / product owner:** _______   (UX-impacting incidents, copy review)

### Channels

- **Pages:** PagerDuty service `aura-firstfifty` (or equivalent) → on-call phone.
- **Chat:** Slack `#aura-oncall` for working updates; `#aura-incidents` for active P1.
- **Status:** internal status page `status.internal/aura` (link from this doc once provisioned).

### Failure mode → response

The four failure modes named in `docs/RELEASE_READINESS.md` Gate 3, with the
specific dashboard signal, severity, and the first three actions to take. If
the immediate fix isn't obvious, declare a P1 in `#aura-incidents` first and
work the diagnosis there.

#### A. Empty-response spike

- **Signal:** Panel 4 — `empty_responses` rises above 0 for any single day, or
  `error_rate_pct > 5` for the trailing hour.
- **Severity:** P1 if `error_rate_pct > 10` for 30 minutes; P2 otherwise.
- **First three actions:**
  1. Pull recent `tool_traces` rows where `tool_name='outfit_architect'` and
     status='error' — the error message identifies the upstream stage.
  2. If errors point at the catalog (`catalog_unavailable`), follow B.
  3. If errors point at the LLM provider (rate limit / 5xx), back off the
     architect call rate and post status to `#aura-oncall`. If sustained,
     temporarily route new turns to the assembly-score fallback by setting
     env `AURA_DISABLE_ARCHITECT=1` (planned escape hatch — see Gate 3 follow-ups).

#### B. Catalog / embeddings missing

- **Signal:** Panel 4 — `catalog_unavailable_guardrail_hits` is non-zero. Any
  hit pages on-call.
- **Severity:** P1 — users see a guardrail message instead of recommendations.
- **First three actions:**
  1. Run `select count(*) from catalog_item_embeddings;` — if 0 or far below
     the production target (~14k), restore from the last known-good
     embeddings backup or rerun `POST /v1/admin/catalog/embeddings/resync`.
  2. Verify `catalog_enriched` row count matches expectations (Gate 2
     reference: 14,296 garment-only rows). If `catalog_enriched` shrank,
     investigate the most recent admin job.
  3. If the catalog rows look correct but pgvector queries time out, check
     Panel 15 (Catalog Search Timeout Rate) and the Supabase compute tier;
     consider rebuilding the HNSW index.

#### C. Negative-signal spike on a single product

- **Signal:** Panel 7 — any single `product_id` appears in the top-disliked
  list for **3+ distinct users within 24h**.
- **Severity:** P2 (no user-facing outage; quality issue).
- **First three actions:**
  1. Pull the offending product's `catalog_enriched` row and its image URL —
     decide audit vs. hide.
  2. To hide: set `is_active=false` (or `row_status='hidden'`) on the row;
     re-run the embedding sync's skip-already-embedded path so it drops out
     of retrieval. Confirm by re-running an affected user's last turn.
  3. Open a ticket against the catalog admin team to investigate the
     enrichment that produced the bad recommendation.

#### D. Dependency report drift

- **Signal:** `ops/scripts/validate_dependency_report.py` fails an assertion,
  or Panel 1 shows `acquisition_source = 'unknown'` for **>50% of new users**
  in the trailing 24h.
- **Severity:** P2 — instrumentation regression, not user-facing.
- **First three actions:**
  1. Confirm the OTP-verify endpoint is still writing `acquisition_source`,
     `acquisition_campaign`, `referral_code`, `icp_tag` (see
     `modules/user/src/user/repository.py`).
  2. Cross-check `dependency_validation_events` for the missing event type —
     a recent code change probably removed an emit call.
  3. File a code-fix ticket; the dashboards keep working with the existing
     rows in the meantime.

#### E. Try-on render slowness

- **Signal:** `visual_evaluation` step latency in `turn_traces.steps[]` jumps above ~70 s on a sustained basis. The expected steady state is ~25 s for 3 parallel cold renders, less when the per-user tryon image cache is warm.
- **Severity:** P2 unless it pushes total turn latency above ~120 s, then P1.
- **First three actions:**
  1. Grep the application stdout for the parallel-batch log lines: `tryon parallel batch: N/N succeeded (cold=K, cache_hit=M) in Xms wallclock`. If `cold` count is low and `wallclock` is still high, Gemini is the bottleneck. If `cold` count is high, the cache may be cold (new user / new garments).
  2. If wallclock per cold render >> 30 s, the Gemini API is degraded — check Google's status page and consider a graceful degrade (skip try-on, ship text-only outfits with attribute-fallback evaluator scores).
  3. Cross-check Panel 10 (try-on quality gate) — high QG-failure rates trigger over-generation, which adds a second parallel batch and roughly doubles the rendering wallclock.

### Escalation timeline

| Stage | Trigger | Action |
|---|---|---|
| 0:00 | Page fires | Primary acks within 15 min |
| 0:15 | No primary ack | Secondary paged |
| 0:30 | Active P1 not stabilised | Engineering owner pulled in; post in `#aura-incidents` |
| 0:60 | P1 still active | Design / product owner pulled in if user-visible; user comms drafted |
| 0:90 | P1 still active | Status page update |

### Post-incident

- Within 48h of a P1: written post-mortem in the engineering wiki linking to
  the relevant dashboard panels and the fix PR.
- Update this runbook if the incident exposed a missing alert, panel, or
  escalation step.

## Related artifacts

- `ops/scripts/smoke_test_full_flow.sh` — end-to-end smoke test against a
  live backend.
- `ops/scripts/validate_dependency_report.py` — seeded validation harness
  for `build_dependency_report`.
- `ops/scripts/extract_dashboard_sql.py` — re-extracts every Panel's SQL
  into `ops/dashboards/panel_NN_*.sql` for paste-into-dashboard use.
- `ops/dashboards/` — auto-extracted SQL files, one per panel.
- `docs/RELEASE_READINESS.md` — release-readiness criteria built on top of
  these dashboards.

---

# Operational Reference (migrated May 3, 2026)

_Migrated from `CURRENT_STATE.md`. Operational scripts, run instructions, and Supabase sync notes consolidated here so OPERATIONS.md is the single home for ops concerns._

## Ops Scripts

| Script | Purpose |
|---|---|
| `ops/scripts/run_agentic_eval.py` | Focused eval harness for agentic pipeline |
| `ops/scripts/check_supabase_sync.py` | Verify migration sync between local and staging |
| `ops/scripts/bootstrap_env_files.py` | Create .env.local and .env.staging from .env.example |
| `ops/scripts/backfill_catalog_urls.py` | Backfill missing canonical product URLs |
| `ops/scripts/schema_audit.py` | Audit database schema |


## How To Run

Start the app:

```bash
APP_ENV=local python3 run_agentic_application.py --reload --port 8010
```

Run the smoke flow:

```bash
USER_ID=your_completed_user_id bash ops/scripts/smoke_test_agentic_application.sh
```

Run tests:

```bash
python3 -m pytest tests/ -v
```

268 tests passing across test files (1 pre-existing collection error in `test_catalog_retrieval.py`; 5 pre-existing failures in `test_agentic_application_api_ui.py` and `test_onboarding.py` verified unrelated to recent work).

Focused application suites:

```bash
python3 -m pytest tests/test_agentic_application.py -v
```

### Test File Inventory

| File | Coverage Area |
|---|---|
| `tests/test_agentic_application.py` | Core pipeline: orchestrator, planner, evaluator, assembler, formatter, context builders, filters, conversation memory, follow-up intents, recommendation summaries |
| `tests/test_onboarding.py` | OTP flow, profile persistence, image upload, analysis pipeline, style preference, rerun support |
| `tests/test_onboarding_interpreter.py` | Deterministic interpretation derivation: 4 seasonal color groups, height categories, waist bands, contrast levels, frame structures |
| `tests/test_catalog_retrieval.py` | Embedding document builder, vector store operations, similarity search, filter application, confidence policy |
| `tests/test_batch_builder.py` | Catalog enrichment batch processing |
| `tests/test_platform_core.py` | SupabaseRestClient, ConversationRepository, config loading |
| `tests/test_user_profiler.py` | User profiler utilities |
| `tests/test_config_and_schema.py` | Configuration validation, schema consistency |
| `tests/test_architecture_boundaries.py` | Module boundary enforcement, import validation |
| ~~`tests/test_digital_draping.py`~~ | Deleted — digital draping removed |
| `tests/test_comfort_learning.py` | Comfort learning: 4-season color mapping, high/low-intent signal detection, evaluate-and-update threshold logic, max 2 groups, supersede old rows |
| `tests/test_qna_messages.py` | QnA narration: stage message templates, context-aware narration |

### Key Test Coverage Areas

**Application pipeline:** Copilot planner intent classification and action routing, LLM-only planning (no deterministic fallback), evaluator fallback to fashion_score, evaluator hard output cap (max 5), follow-up intents (7 types), assembly compatibility checks, response formatter bounds (max 3 outfits), concept-first paired planning, model configuration validation, conversation memory build/apply, QnA stage narration, profile-guidance intent routing (color direction, avoidance, suitability), profile-grounded zero-result fallback, style-discovery context continuity across follow-ups.

**Onboarding:** 3-agent analysis with mock LLM responses, interpretation derivation across 4 seasonal color groups (Spring, Summer, Autumn, Winter), style archetype selection, single-agent rerun with baseline preservation.

~~**Digital draping:**~~ Tests deleted — draping removed from codebase.

**Comfort learning:** Season-to-color mapping (4 seasons, warm/cool), high-intent signal detection (outside current groups), low-intent signal detection (color keywords), evaluate-and-update threshold (5 high-intent), max 2 groups, supersede old effective rows, no duplicate direction.

**Catalog:** Embedding document structure (8 sections), confidence-aware rendering, row status filtering, filter column normalization.

**Architecture:** No direct cross-boundary imports, gateway pattern enforcement.


## Supabase Sync

### Env Convention

- Local: `.env.local` / `APP_ENV=local`
- Staging: `.env.staging` / `APP_ENV=staging`
- Or explicit: `ENV_FILE=/path/to/file`

Bootstrap missing env files:
```bash
python3 ops/scripts/bootstrap_env_files.py
```

Required staging keys: `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`

### Link and Push

```bash
supabase link --project-ref zfbqkkegrfhdzqvjoytz --password '<db-password>' --yes
supabase db push --yes
python3 ops/scripts/check_supabase_sync.py --strict
```

### Key Table Relationships

```text
users
  └── conversations (user_id)
        └── conversation_turns (conversation_id)

onboarding_profiles (user_id → users)
  ├── onboarding_images (user_id, category unique)
  ├── user_analysis_runs (user_id)
  │     └── user_derived_interpretations (analysis_snapshot_id)
  ├── user_style_preference (user_id)
  ├── user_effective_seasonal_groups (user_id)
  └── user_comfort_learning (user_id)

catalog_enriched (product_id unique)
  └── catalog_item_embeddings (product_id)
```

