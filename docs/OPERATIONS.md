# Operations: Dashboards & Queries (First-50 Rollout)

Last updated: May 15, 2026.

> **NEW OPS CONTEXT (May 15, 2026) — Shopify pivot.** The SQL panels below were written for the *legacy standalone Aura web app's* monitoring (onboarding funnel, intent dispatch, dependency/retention, etc.). They still query the engine's `public` schema tables and remain valid for engine-side observability. What's new:
>
> - **Shopify storefront** (`thesigmavibe.shop`) — operational metrics live in Shopify Admin (orders, conversion, sessions). Not queried via the panels below.
> - **Vibe Shopify App** (Vercel-deployed) — runtime logs via `vercel logs --follow https://vibe-app-five.vercel.app`. Errors, function timing, cold-start metrics in the Vercel dashboard.
> - **Session store** — Prisma `Session` table in Supabase `vibe` schema (separate from engine's `public`). Manage via `npx prisma studio` from `vibe-app/` or query: `SELECT * FROM vibe."Session" LIMIT 10;`
> - **Tunnels for local dev** — confirmed broken in BLR/BOM: Cloudflare quick-tunnels, ngrok free (interstitial), localtunnel (502s), Pinggy free (interstitial). Pinggy free works as a 60-min escape hatch; for sustained work, deploy to Vercel and use the production URL.
> - **Engine** — still on `localhost:8010` (single-tenant). Phase C deploys to Fly.io Mumbai with secrets via `fly secrets set`.
>
> See [`OPEN_TASKS.md`](OPEN_TASKS.md) § Locked infrastructure for the canonical infra table.

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

**Reading the answer_source mix (post May 5 2026, PR #82).** The default
routing flipped: `source_preference="auto"` (when the user does not say
"from my wardrobe") now routes to the catalog pipeline. Pre-#82 the
`wardrobe_first*` family was the default and dominated this chart.
Post-#82 the dominant rows should be:

- `catalog_only` — both explicit "from the catalog" and the new auto
  default. Should be the largest bucket by far (>60% of turns) for a
  catalog-led product.
- `catalog_low_confidence` — pipeline ran but the rater's threshold gate
  rejected everything; user got a clarification message. Watch for
  spikes (see Panel 16).
- `wardrobe_first` / `wardrobe_first_hybrid` — users who explicitly
  asked for wardrobe-first AND cleared the ≥2-per-role coverage gate
  (PR #82). Now an opt-in slice, not the default.
- `wardrobe_unavailable` — explicit wardrobe ask + insufficient coverage
  → the gap fallback message. New row introduced by PR #82.
- `shoe_anchor_unsupported` — user uploaded a shoe / heel / sandal as
  the chat anchor. The system doesn't style around shoes yet (PR #330),
  so we short-circuit with an honest "not supported yet" message rather
  than try to build an outfit. **Treat this as customer-demand signal,
  not as an error.** Sustained non-zero counts argue for prioritising
  shoe support.

If `wardrobe_first*` is still >40% post-#82, the planner is mis-extracting
`source_preference` (regression in `prompt/copilot_planner.md`).

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

**Question:** what mix are the two source preferences producing, and is
the catalog (now-default) path landing engagement?

Per PR #82 (May 5 2026) the default `source_preference="auto"` routes to
catalog. Wardrobe-first is an opt-in path users reach by saying "from my
wardrobe", and it has its own minimum-coverage gate (≥2 tops AND ≥2
bottoms AND ≥2 one-pieces). The first query below shows the source-share
across the entire mix; the second shows wardrobe-only paths so you can
size the opt-in slice; the third shows catalog click-through volume so
the dominant path's engagement is visible.

```sql
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
      'wardrobe_unavailable',
      'shoe_anchor_unsupported'
  )
GROUP BY 1
ORDER BY turns DESC;
```

```sql
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

## Panel 16 — Low-Confidence Catalog Responses

**Question:** how often does the 0.75 confidence threshold gate force a no-confident-match response instead of shipping outfits?

**Context:** As of May 3, 2026 the orchestrator drops outfits whose `fashion_score < 75` (LLM Rater 0–100 scale) and, when zero candidates clear, returns `answer_source = "catalog_low_confidence"` with `outfits=[]` and a graceful "I couldn't find a strong match" message + refine / show-closest / shop CTAs. This panel tracks that rate so the team can decide when the threshold is too aggressive (catalog needs broadening) vs working as intended (catalog has a real coverage gap).

```sql
-- low_confidence_catalog_response_rate_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) FILTER (WHERE metadata_json->>'answer_source' = 'catalog_low_confidence') AS low_conf_turns,
    COUNT(*) AS total_turns,
    round(
        100.0 * COUNT(*) FILTER (WHERE metadata_json->>'answer_source' = 'catalog_low_confidence')::numeric
        / nullif(COUNT(*), 0),
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

**Threshold history.** The fashion_score gate started at 75; PR #81
(May 5 2026) lowered it to 60 after the gpt-5.4 composer / rebalanced
weights produced cleaner per-dim scores that were under-clearing 75.
Adjust the docstring if the gate moves again.

**Healthy:** `low_conf_rate_pct` stays <5%. The avg blocked top score
should sit close to but below the active threshold (i.e., the gate is
catching genuinely borderline turns, not way-off ones).

**Degraded:** `low_conf_rate_pct` 5–20%. Most likely a catalog gap or
an architect drift producing weak query documents. Pull a sample of
low-confidence turns from `turn_traces` (filter on
`evaluation->>'answer_source' = 'catalog_low_confidence'`) and inspect
each one's architect query documents + retrieved candidates manually —
check whether the architect is targeting `garment_subtype` values the
catalog doesn't carry well, or whether the user's seasonal palette /
formality target has thin inventory. (A future Panel 17 would join
`tool_traces.composer_decision` / `rater_decision` to
`catalog_enriched.GarmentSubtype` to surface this automatically.)

**Unhealthy:** `low_conf_rate_pct` > 20% sustained. Either the
threshold is too high for current catalog depth, or the architect /
assembler is regressing. Pull a sample of low-confidence turns from
`turn_traces` and inspect the query documents + retrieved products
manually.

**May 5 2026 carve-out (PR #89, rater veto removed).** Before #89, the
rater treated `archetypal_preferences.disliked` as a hard veto: any
single touch of a disliked attribute (color_temperature: neutral,
pattern: solid) drove `fashion_score=0` and pushed the outfit into this
gate. T12 had 8/8 outfits vetoed and the user got the
`catalog_low_confidence` message. PR #89 removed that veto, so this
panel's rate should *drop* meaningfully (the floor moves from "any
disliked attr" → "the rater's per-dim score is genuinely below
threshold"). When establishing a new healthy baseline, pull at least 7
days of post-PR-#89 data — anything compared against pre-#89 numbers
will look artificially good.

---

## Panel 17 — Architect Input Token Growth

**Question:** is the architect's prompt size creeping up because of
the new episodic-memory timeline, and is the event cap (10 events)
still right?

**Context:** PR #90 added `recent_user_actions` (a 30-day timeline of
the user's like/dislike events with full garment attributes) to the
architect's input payload. Each row is ~80–150 tokens; the cap was
30 at introduction, trimmed to 20 in the May 8 latency push, and
trimmed again to 10 in PR #259 (May 9) — at the 10-event cap a power
user now adds ~1K tokens to a prompt that was ~9K before. PR #92 fixed
a silent 400-error that was making the timeline empty for every user.
This panel watches the distribution so we know when the cap or the
per-event field set in `_CATALOG_ATTR_MAP` needs revisiting.

```sql
-- architect_prompt_tokens_p50_p95_last_7d
-- Excludes cache + composition_engine sentinel rows (PR #153) which
-- carry zero tokens and would dilute LLM input-token percentiles.
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) AS calls,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY prompt_tokens) AS p50,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY prompt_tokens) AS p95,
    MAX(prompt_tokens) AS p_max
FROM model_call_logs
WHERE call_type = 'outfit_architect'
  AND model NOT IN ('cache', 'composition_engine')
  AND created_at >= now() - interval '7 days'
  AND prompt_tokens IS NOT NULL
GROUP BY 1
ORDER BY 1 DESC;
```

**Healthy:** p50 sits in the 8K–11K range; p95 ≤14K. Cold-start users
(empty timeline) anchor the p50; active users with feedback history
push the p95.

**Degraded:** p95 climbs above 14K — usually means a power user's
10-event timeline is denser than expected (long item titles, stuffed
`user_query` fields). Trim which fields are surfaced in
`_CATALOG_ATTR_MAP` before tightening the event cap further — at 10
events, further reduction starts cutting into useful signal.

**Unhealthy:** p_max exceeds 18K — that's near the architect prompt
ceiling and approaching gpt-5.4 context-window pressure. First trim
`_CATALOG_ATTR_MAP`; only drop `_RECENT_USER_ACTIONS_MAX` below 10 if
that doesn't help.

---

## Panel 18 — Rater Unsuitable Rate

**Question:** how often is the rater flagging an outfit as `unsuitable`
post-#89, and is the rate stable?

**Context:** PR #89 removed the rater's `archetypal_preferences.disliked`
hard veto. Pre-#89 the unsuitable rate was high — T12 had 8/8 outfits
vetoed because each touched a disliked attribute. Post-#89 the rate
should be low (the rater only flags severe mismatches: wrong-occasion,
strong color clash, severe risk-tolerance violation). This panel
tracks the new baseline so we can spot drift if the prompt regresses.

```sql
-- rater_unsuitable_rate_last_7d
WITH rater_calls AS (
    SELECT
        date_trunc('day', t.created_at) AS day,
        jsonb_array_elements(t.output_json->'ranked_outfits') AS outfit
    FROM tool_traces t
    WHERE t.tool_name = 'rater_decision'
      AND t.created_at >= now() - interval '7 days'
)
SELECT
    day,
    COUNT(*) AS rated_outfits,
    SUM(CASE WHEN (outfit->>'unsuitable')::boolean THEN 1 ELSE 0 END) AS unsuitable_outfits,
    round(
        100.0 * SUM(CASE WHEN (outfit->>'unsuitable')::boolean THEN 1 ELSE 0 END)::numeric
        / nullif(COUNT(*), 0),
        2
    ) AS unsuitable_pct
FROM rater_calls
GROUP BY 1
ORDER BY 1 DESC;
```

**Healthy (post-#89 baseline):** `unsuitable_pct` 0–5%. A small floor
is expected — wrong-occasion outfits and severe risk-tolerance
violations should still veto.

**Degraded:** 5–15%. Either the prompt is drifting back toward the old
veto rule or the architect is seeding genuinely off-occasion outfits
into the composer. Pull a sample of `unsuitable=true` rows and read
the `rationale` field to triage.

**Unhealthy:** >15% sustained. A prompt regression — the rater has
re-acquired an aggregate-veto behavior. Diff `prompt/outfit_rater.md`
against the post-#89 version and revert the offending change.

> Note: the upstream signal here is `tool_traces.rater_decision.output_json`
> (one row per turn that ran the rater). If you see zero rows for a
> day where Panel 4 shows non-zero turn volume, the rater isn't being
> reached — investigate the composer/pool-unsuitable / threshold-gate
> branch upstream.

---

## Panel 19 — Composer Latency

**Question:** what's the per-attempt composer wall-clock latency, and
is the gpt-5.4 promotion (PR #81) still inside the latency budget?

**Context:** PR #81 moved the composer from gpt-5-mini to gpt-5.4 (~25×
cost, also slower). Until PR #95 the composer's `model_call_logs`
rows had `latency_ms = 0` — the column was never populated, so any
prior p50/p95 panel was blind. PR #95 wired the actual wall-clock
through `_record_attempt`. This panel is the first real composer
latency view post-fix.

```sql
-- composer_latency_p50_p95_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    call_type, -- 'outfit_composer' (first attempt) vs 'outfit_composer_retry1'
    COUNT(*) AS calls,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms,
    MAX(latency_ms) AS p_max_ms
FROM model_call_logs
WHERE call_type LIKE 'outfit_composer%'
  AND created_at >= now() - interval '7 days'
  AND latency_ms IS NOT NULL
  AND latency_ms > 0  -- exclude pre-PR-#95 zero-rows when reading historical data
GROUP BY 1, 2
ORDER BY 1 DESC, 2;
```

**Healthy:** First-attempt p50 8–12s, p95 ≤18s on gpt-5.4. Retry rows
should be a small fraction of total calls (PR #80 retry path) and have
similar latency since they're the same model.

**Degraded:** p95 climbs above 20s — the composer is fighting prompt
size (see Panel 17) or gpt-5.4 itself is degrading. Cross-check Panel
17's prompt-token p95 to disambiguate.

**Unhealthy:** p95 >25s sustained, or retry call_type rate climbs
above 5% — the composer is hallucinating product_ids and burning
double tokens to recover. Check `tool_traces.composer_decision`
`drop_reasons` for a recent sample.

---

## Panel 20 — Episodic Memory Population

**Question:** is the architect actually receiving non-empty episodic
memory for our active users, or are timelines silently empty?

**Context:** PR #90 added `list_recent_user_actions(...)`; PR #92
fixed a silent PostgREST 400-error caused by a snake/Pascal column
mismatch that was returning an empty timeline for every user. We want
visibility on the population rate so a future regression of the same
shape can't hide for hours again.

The signal is approximate — we count distinct users with ≥1
`feedback_events` row in the last 30 days, against distinct users
with ≥1 turn in the same window. Users with no feedback history
genuinely have no episodic signal yet (cold start is correct), so the
ratio plateaus below 100% at steady state — what we're guarding
against is a sudden *drop*.

```sql
-- episodic_memory_population_rate_last_30d
WITH recent_users AS (
    SELECT DISTINCT user_id
    FROM dependency_validation_events
    WHERE event_type = 'turn_completed'
      AND created_at >= now() - interval '30 days'
),
users_with_feedback AS (
    SELECT DISTINCT user_id
    FROM feedback_events
    WHERE event_type IN ('like', 'dislike')
      AND created_at >= now() - interval '30 days'
)
SELECT
    (SELECT COUNT(*) FROM recent_users)                                AS recent_active_users,
    (SELECT COUNT(*) FROM users_with_feedback)                         AS users_with_episodic_signal,
    round(
        100.0 * (SELECT COUNT(*) FROM users_with_feedback)::numeric
        / nullif((SELECT COUNT(*) FROM recent_users), 0),
        2
    ) AS population_pct;
```

**Healthy:** `population_pct` is whatever steady-state shakes out to
once a few weeks of post-#92 traffic accumulate (we don't have a hard
target — most products see 30–60% of active users with feedback
history). The point is *no sudden change*.

**Degraded:** `population_pct` drops by ≥20 percentage points
week-over-week without a corresponding feature change. Likely
suspects: (a) the heart/X buttons in `ui.py` regressed and stopped
emitting `feedback_events`, (b) RLS or schema drift on
`feedback_events`, (c) `_persist_chat_feedback` in the orchestrator
errored silently.

**Unhealthy:** drops to ≤5% — same recurrence of the PR #92 failure
mode (silent 400, swallowed exception). With PR #93's `_log.warning`
on the silent `except` blocks, the cause should now appear in logs
— grep `list_recent_user_actions` for warnings.

> Future panel: a per-turn signal (was the architect's
> `recent_user_actions` payload non-empty?). That requires the
> orchestrator to surface the count into `metadata_json.episodic_memory_event_count`,
> a small follow-up. Until then, this user-level rate is the proxy.

---

## Panel 21 — Composition Plan-Source Distribution

**Question:** of the architect-stage rows produced today, what
fraction came from the LLM, the composition engine, and the cache?

**Context:** PR #149 introduced the composition engine; PR #150
added router-decision metadata; PR #151 wired canonicalization;
PR #153 stamped `model_call_logs.model` with three sentinels:
`cache` (architect cache hit), `composition_engine` (engine
accepted), or the LLM model id (e.g., `gpt-5.2`). This panel
tracks the steady-state mix once the engine flag is on.

```sql
-- composition_plan_source_distribution_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    CASE
        WHEN model = 'cache'              THEN 'cache'
        WHEN model = 'composition_engine' THEN 'engine'
        ELSE                                   'llm'
    END                                AS plan_source,
    COUNT(*)                           AS rows,
    AVG(latency_ms)::int               AS avg_latency_ms,
    SUM(prompt_tokens + completion_tokens) AS total_tokens
FROM model_call_logs
WHERE call_type = 'outfit_architect'
  AND status = 'ok'
  AND created_at >= now() - interval '7 days'
GROUP BY 1, 2
ORDER BY 1 DESC, 2;
```

**Healthy:** with engine flag on, expect ~50–70% engine, ~10–20%
cache, ~10–30% LLM (cold-start + fall-through). The exact mix
depends on canonicalize hit rate and the eligibility-skip share.
LLM-row latency p50 ~12s; engine + cache rows ≤ 3s.

**Expected shift — PR #328 (May 13 2026):** top/bottom anchor turns
(pairing requests where the user uploaded a top/bottom) now always
fall through to the LLM architect regardless of
`AURA_ENGINE_ALLOW_POOL_ANCHOR`. The flag's experimental engine path
emitted broken cross-role queries with top-only `hard_attrs` on both
queries; ineligible by construction. If overall engine share dropped
roughly in line with the pairing-anchor traffic share after May 13,
that's the expected behavior, not a regression. Drill into
`aura_composition_router_decision_total{fallback_reason="anchor_pool_injected"}`
to confirm.

**Degraded:** engine share <20% with flag on means canonicalize is
failing too often or fall-through criteria are too tight. Drill
into `panel_22` (yaml_gap distribution) and the
`aura_composition_router_decision_total{fallback_reason}` Prometheus
counter to see which fall-through reason dominates.

**Unhealthy:** zero engine rows despite the flag being on — almost
always means `AURA_COMPOSITION_ENGINE_ENABLED` didn't propagate to
the runtime process. Check the boot log for the resolved flag value.

---

## Panel 22 — Composition YAML-Gap Distribution

**Question:** which planner-emitted values are blocking the
composition engine most often, and where should Phase 4.2 stylist
review focus next?

**Context:** PR #150 captures `yaml_gaps[]` in
`distillation_traces.full_output.router_decision`. Each entry is
`<axis>:<value>` (e.g., `occasion_signal:bachelorette_party`,
`weather_context:gloomy`). The canonicalize layer (PR #151) bridges
common variants, but genuinely novel inputs gap. This panel surfaces
the top-N gaps so the YAML expansion backlog is data-driven.

```sql
-- composition_yaml_gap_top_n_last_30d
WITH gaps AS (
    SELECT
        gap_value AS gap,
        created_at::date AS day
    FROM distillation_traces,
         jsonb_array_elements_text(
             COALESCE(full_output -> 'router_decision' -> 'yaml_gaps', '[]'::jsonb)
         ) AS gap_value
    WHERE stage = 'outfit_architect'
      AND created_at >= now() - interval '30 days'
)
SELECT
    gap,
    COUNT(*) AS occurrences,
    COUNT(DISTINCT day) AS days_seen,
    MIN(day) AS first_seen,
    MAX(day) AS last_seen
FROM gaps
GROUP BY gap
ORDER BY occurrences DESC
LIMIT 30;
```

**How to use:** read top to bottom; the first 5–10 entries are the
candidates for Phase 4.2 stylist YAML review. A gap with high
occurrence + recent `last_seen` is a real, recurring miss; a gap
with low occurrence and old `last_seen` is a one-off.

---

## Panel 23 — Composition Per-Attribute Status

**Question:** of the engine-accepted turns, which garment attributes
get omitted, widened, or relaxed most often — i.e., where is the
algorithm under stress?

**Context:** PR #149's engine emits a per-attribute provenance
trail (`status` ∈ `{clean, soft_relaxed, hard_widened, omitted}`).
This PR (post-#153) surfaces the non-clean entries in
`distillation_traces.full_output.router_decision.provenance_summary`.
Frequent omissions on a specific attribute (e.g., `EmbellishmentLevel`)
are an early signal that the YAML's `flatters` lists are too narrow
for that attribute or that the planner's per-turn signals conflict
on it.

```sql
-- composition_attribute_status_last_30d
WITH entries AS (
    SELECT
        status,
        attribute,
        created_at::date AS day
    FROM distillation_traces,
         jsonb_each(
             COALESCE(full_output -> 'router_decision' -> 'provenance_summary', '{}'::jsonb)
         ) AS s(status, attrs),
         jsonb_array_elements_text(attrs) AS attribute
    WHERE stage = 'outfit_architect'
      AND created_at >= now() - interval '30 days'
)
SELECT
    status,
    attribute,
    COUNT(*) AS occurrences,
    COUNT(DISTINCT day) AS days_seen
FROM entries
GROUP BY status, attribute
ORDER BY status, occurrences DESC;
```

**Healthy:** each `status` has its top-attribute occurrence count
under, say, 20% of engine turns. No single attribute dominates.

**Degraded:** one attribute appears >40% of engine turns under
`omitted` — that attribute's flatters intersection is collapsing
on too many turns; review the YAML rows for it.

**Unhealthy:** an attribute that *never* clears (always omitted)
points to a contradictory YAML setup — usually two sources have
disjoint flatters that no relaxation order can reconcile.

---

## Panel 24 — Composition Engine Runbook (diagnostic queries)

**Question:** for a specific turn that misbehaved (slow, wrong
recommendation, fell through unexpectedly), what did the
composition router decide and why?

```sql
-- diagnose_one_turn — replace ::uuid with the actual turn_id
SELECT
    stage,
    model,
    latency_ms,
    full_output -> 'router_decision' AS router_decision
FROM distillation_traces
WHERE turn_id = '00000000-0000-0000-0000-000000000000'::uuid
ORDER BY created_at;
```

For a richer side-by-side comparison across multiple recent turns,
use `ops/scripts/turn_forensics.py` (see Ops Scripts section).

---

## Panel 25 — Composer Plan-Source Distribution

**Question:** of the composer-stage decisions made today, what
fraction came from the LLM, the composer engine, or the cache?

**Context:** PR 5d (Phase 5d) introduced
`aura_composer_router_decision_total{used_engine, fallback_reason}`
and started tagging distillation traces with the composer router
decision. This panel is the composer-side mirror of Panel 21.
Composer cache hits are a separate code path (orchestrator-level
hash on architect_direction_id × retrieval_fingerprint × cluster ×
composer_prompt_version) and surface as `model_call_logs.model =
'cache'` rows on the `outfit_composer` call_type.

```sql
-- composer_plan_source_distribution_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    CASE
        WHEN model = 'cache'           THEN 'cache'
        WHEN model = 'composer_engine' THEN 'engine'
        ELSE                                'llm'
    END                            AS plan_source,
    COUNT(*)                       AS rows,
    AVG(latency_ms)::int           AS avg_latency_ms,
    SUM(prompt_tokens + completion_tokens) AS total_tokens
FROM model_call_logs
WHERE call_type = 'outfit_composer'
  AND status = 'ok'
  AND created_at >= now() - interval '7 days'
GROUP BY 1, 2
ORDER BY 1 DESC, 2;
```

**Healthy:** with the engine flag on and the architect engine running
upstream, expect ~50–70% engine, ~10–20% cache, ~15–35% LLM
(eligibility-skip + fall-through). LLM-row p50 latency ~12–14s;
engine + cache rows ≤ 1s.

**Degraded:** engine share <20% with `AURA_COMPOSER_ENGINE_ENABLED=1`
means either canonicalize is failing too often upstream OR the
engine's pool eligibility / confidence gates are too tight. Drill
into Panel 26 (rule-violation distribution) and the
`aura_composer_router_decision_total{fallback_reason}` Prometheus
counter.

**Unhealthy:** zero engine rows despite the flag — almost always
means the env var didn't propagate. Check the boot log.

---

## Panel 26 — Composer Rule-Violation Distribution

**Question:** which pairing rules are dropping engine tuples most
often, and which YAML categories need stylist review next?

**Context:** PR 5c (Phase 5c) emits per-tuple provenance with
`drop_reason` is now an open set — the bucket includes category-level
short-circuits (formality_alignment / color_story / pattern_mixing /
scale_balance / bridal_specific), engine fall-through reasons
(low_picks / low_confidence / pool_too_sparse / none), AND specific
per-rule strings emitted by `_evaluate_bridal_specific` and similar
(e.g., `guest_vs_bridal_separation`). The router's `provenance_summary`
keeps counts per drop_reason verbatim. Panel surfaces top reasons over
a 30-day window. **For real-time alerting on specific rule fires use
`aura_composer_rule_violation_total{rule,is_hard}` Prometheus counter
instead — it ticks per Violation rather than per dropped tuple.**

```sql
-- composer_drop_reason_distribution_last_30d
WITH reasons AS (
    SELECT
        kv.key  AS drop_reason,
        kv.value::int AS count,
        created_at::date AS day
    FROM distillation_traces,
         jsonb_each_text(
             COALESCE(
                 full_output -> 'composer_router_decision' -> 'provenance_summary' -> 'dropped_by_reason',
                 '{}'::jsonb
             )
         ) AS kv
    WHERE stage = 'outfit_composer'
      AND created_at >= now() - interval '30 days'
)
SELECT
    drop_reason,
    SUM(count)        AS total_drops,
    COUNT(DISTINCT day) AS days_seen,
    MIN(day)          AS first_seen,
    MAX(day)          AS last_seen
FROM reasons
GROUP BY drop_reason
ORDER BY total_drops DESC
LIMIT 200;
-- LIMIT was 30; raised to 200 (May 11 2026) — drop_reason cardinality is
-- bounded by rule-name count (~15-20 today) but kept loose so the next
-- pairing-rule expansion doesn't silently truncate rare-but-meaningful
-- entries from the panel.
```

**How to use:** the top 5 drop_reasons are the highest-leverage
candidates for stylist YAML review. Phase 4.2 stylist pass should
prioritize these; the same data slices to "where the engine sees
real-world tuples that look problematic to it."

---

## Panel 27 — Composer Per-Tuple Score Distribution

**Question:** how does the engine's tuple scoring distribute on
real traffic — is the diversity penalty + soft-violation accumulation
producing a useful spread, or is everything bunching at 1.0?

**Context:** PR 5c emits `base_score` per tuple (1.0 minus
`SOFT_PENALTY * soft_violations`). Picked tuples additionally get
`diversity_multiplier` ∈ {1.0, 0.6, 0.42, ...}. Healthy spread
suggests the engine has discrimination room; bunching at 1.0
suggests soft rules aren't biting.

```sql
-- composer_tuple_score_histogram_last_7d
WITH scores AS (
    SELECT
        (entry ->> 'base_score')::float AS base_score,
        (entry ->> 'diversity_multiplier')::float AS diversity_multiplier,
        (entry ->> 'picked')::bool      AS picked
    FROM distillation_traces,
         jsonb_array_elements(
             COALESCE(
                 full_output -> 'composer_router_decision' -> 'provenance',
                 '[]'::jsonb
             )
         ) AS entry
    WHERE stage = 'outfit_composer'
      AND created_at >= now() - interval '7 days'
)
SELECT
    width_bucket(base_score, 0.0, 1.0, 10) AS score_bucket,
    COUNT(*)                                AS tuples,
    COUNT(*) FILTER (WHERE picked)          AS picked,
    AVG(diversity_multiplier)               AS avg_diversity_multiplier
FROM scores
GROUP BY score_bucket
ORDER BY score_bucket;
```

**Healthy:** scores spread across at least 3 buckets; picked tuples
concentrate in the upper-2 buckets but aren't always 1.0.

**Degraded:** every tuple at 1.0 means soft rules don't fire on
production data — review pairing.py's per-category evaluators
against actual catalog enrichment shapes.

---

## Panel 28 — Composer Single-Turn Diagnostic

**Question:** for a specific turn, what did the composer router
decide, what tuples were enumerated, what dropped where, and what
got picked?

```sql
-- composer_diagnose_one_turn — replace ::uuid with the actual turn_id
SELECT
    stage,
    model,
    latency_ms,
    full_output -> 'composer_router_decision' AS composer_decision,
    full_output -> 'composer_router_decision' -> 'provenance_summary' AS provenance_summary,
    full_output -> 'composer_router_decision' -> 'shadow_comparison' AS shadow_comparison
FROM distillation_traces
WHERE turn_id = '00000000-0000-0000-0000-000000000000'::uuid
  AND stage = 'outfit_composer'
ORDER BY created_at;
```

`shadow_comparison` is null on every non-shadow turn; populated when
`AURA_COMPOSER_SHADOW=1` is on AND the engine produced output.

For a richer side-by-side comparison across multiple recent turns,
use `ops/scripts/composer_quality_eval.py` (Phase 4.6 eval set
required) or `ops/scripts/turn_forensics.py`.

---

## Panel 29 — Try-on Flag State Distribution

**Question:** is `AURA_TRYON_ENABLED` actually on, and what fraction of
turns hit the rendered path vs the flag-off skip path? Without this
panel, "tryon stage slow" can't be told apart from "tryon stage skipped"
because both produce zero latency observations.

```promql
# Flag-on rate over the last hour (1.0 = flag on every turn that
# reached the gate, 0.0 = always off, in-between = mixed deployment).
sum(rate(aura_tryon_flag_total{enabled="true"}[1h]))
  / sum(rate(aura_tryon_flag_total[1h]))
```

```promql
# Per-turn skip rate. Spikes here = a deploy unintentionally flipped
# the flag off. Compare against the deploy timeline.
sum(rate(aura_tryon_flag_total{enabled="false"}[5m])) by (enabled)
```

Cross-reference: `aura_turn_duration_seconds{stage="tryon_render"}`
should be empty/sparse when `aura_tryon_flag_total{enabled="false"}`
dominates. Mismatch = bug somewhere in the gate.

---

## Panel 30 — Empty-Retrieval Relaxation Outcome

**Question:** how often is auto-relaxation firing, how deep does it
have to go, and how often does it exhaust without finding anything?
Sustained `exhausted` rate is a catalog content gap signal — the
ask hits a hole that no filter relaxation can paper over.

```promql
# Distribution over the last hour.
sum(rate(aura_retrieval_relaxation_total[1h])) by (outcome)
```

```promql
# Exhaustion rate (catalog gap signal). Alert if >2% sustained.
sum(rate(aura_retrieval_relaxation_total{outcome="exhausted"}[1h]))
  / sum(rate(aura_retrieval_relaxation_total[1h]))
```

```promql
# Relaxation-needed rate. High and rising = either the architect is
# over-constraining (re-tune planner) or the catalog is shrinking
# (ingest regression). Cross-reference with Panel 16 (low-confidence
# rate) — the two surface different stages of the same underlying
# coverage problem.
1 - (
  sum(rate(aura_retrieval_relaxation_total{outcome="not_needed"}[1h]))
  / sum(rate(aura_retrieval_relaxation_total[1h]))
)
```

Outcomes: `not_needed` (first pass returned products), `succeeded_level_1`
(only `garment_subtype` dropped), `succeeded_level_2` (`+ formality_level`),
`succeeded_level_3` (`+ occasion_fit` — full sequence), `exhausted`
(all three dropped, still 0 products).

---

## Panel 31 — Follow-up Intent Routing Mix

**Question:** for each follow-up intent, what fraction of turns are
served by the engine vs falling through to the LLM? When PR #186 /
#190 / #191 / #198 / #199 added engine eligibility for the seven
follow-up intents, the existing router-decision counter (Panel 21)
doesn't surface per-intent breakdown — high-volume intents can mask
per-intent regressions.

```promql
# Per-intent engine acceptance rate over the last hour.
sum(rate(aura_followup_intent_routing_total{used_engine="true"}[1h]))
  by (followup_intent)
/ ignoring(used_engine) group_left()
sum(rate(aura_followup_intent_routing_total[1h]))
  by (followup_intent)
```

```promql
# Per-intent volume breakdown — answers "which follow-ups are users
# actually using" so we know which intents to optimize.
sum(rate(aura_followup_intent_routing_total[1h])) by (followup_intent)
```

Expected baseline (May 2026 post-shipping): all 7 engine-friendly
intents land at >80% engine. Drift below 50% on any intent points to
an eligibility gate regression — see Runbook entry A6.

Intents covered: `decrease_formality`, `increase_formality`,
`more_options`, `similar_to_previous`, `change_color`,
`full_alternative`, `increase_boldness`. Anything else (legacy or
unrecognized) shows up under `none` and routes through the LLM.

---

## Panel 32 — Composition Per-Axis Gap Impact

**Question:** for each YAML-gap axis, how much confidence loss did
gaps on that axis actually cost us? Pairs with Panel 22 (gap
*frequency*) — frequency × weight = impact, and impact is what should
drive `_YAML_GAP_AXIS_WEIGHTS` tuning. Without this, the tuning
harness in `ops/scripts/tune_yaml_gap_weights.py` has only frequency
data and can't tell rare-but-catastrophic axes (e.g., `body_shape` at
weight 1.5) apart from common-but-recoverable axes (e.g.,
`formality_hint` at weight 0.5).

```promql
# Total confidence loss attributable to each axis over the last hour
# (weighted by _YAML_GAP_AXIS_WEIGHTS × YAML_GAP_PENALTY).
sum(rate(aura_composition_yaml_gap_impact_total[1h])) by (axis)
```

```sql
-- Per-axis impact from distillation_traces, last 7 days. Uses the
-- per_axis_gap_impact JSON populated by router.py:RouterDecision.
-- Dollars-and-cents view: how much confidence each axis cost the
-- engine across the cohort.
SELECT
    axis,
    COUNT(*)         AS turns_with_gap,
    AVG(impact)      AS avg_impact_per_turn,
    SUM(impact)      AS total_impact_7d
FROM distillation_traces,
     LATERAL jsonb_each_text(
       full_output -> 'router_decision' -> 'per_axis_gap_impact'
     ) AS gap(axis, impact_str)
CROSS JOIN LATERAL (SELECT impact_str::float AS impact) AS i
WHERE stage = 'outfit_architect'
  AND created_at >= NOW() - INTERVAL '7 days'
  AND full_output -> 'router_decision' -> 'per_axis_gap_impact' IS NOT NULL
GROUP BY axis
ORDER BY total_impact_7d DESC;
```

Tuning workflow: when this panel shows `axis X` accounting for >40%
of total impact AND `tune_yaml_gap_weights.py` reports correlation
< 0.30 for that axis, the weight is too aggressive — drop it one
step (0.2). When impact is concentrated on a high-correlation axis,
the weight is doing its job; leave alone.

---

## Panel 33 — Cache Hit-Rate by Stage (LLM caches)

**Question:** how often is each LLM-stage cache serving versus the
LLM running? Three caches contribute: planner (Phase 2 follow-up,
PR #259), architect (Phase 2.2), composer (Phase 2.3). All three
stamp `model='cache'` on the `model_call_logs` row when a hit is
served — Panel 33 reads that stamping directly.

Healthy steady-state hit rate per the design docs:
- Planner: 20-40% (depends on repeat-query rate)
- Architect: 20-40% (same)
- Composer: 25-45% (typically slightly higher because composer
  is downstream of canonicalisation in Phase 4.11)

Below 10% steady-state on any stage = either (a) cache fingerprint
is too discriminating (debug via the cache table's denormalised
key fields) or (b) the user cohort has highly novel queries.

Above 70% steady-state = either healthy (high repeat traffic) or
the key is too COARSE and stale plans are being served. Cross-check
against Panel 18 (rater unsuitable rate) to distinguish.

```promql
# Real-time per-stage hit rate over the last hour.
# aura_planner_cache_decision_total ticks on every planner attempt.
# Architect and composer don't have analogous outcome counters yet —
# the SQL view below covers them.
sum(rate(aura_planner_cache_decision_total{outcome="hit"}[1h]))
  / sum(rate(aura_planner_cache_decision_total[1h]))
```

```sql
-- Per-stage hit rate from model_call_logs over the last 7 days.
-- cache hits stamp model='cache'; LLM runs stamp the model id.
-- Filters by call_type so each row maps to exactly one stage.
WITH stage_decisions AS (
    SELECT
        call_type AS stage,
        CASE WHEN model = 'cache' THEN 'hit' ELSE 'miss' END AS outcome,
        created_at::date AS day
    FROM model_call_logs
    WHERE call_type IN ('copilot_planner', 'outfit_architect', 'outfit_composer')
      AND created_at >= NOW() - INTERVAL '7 days'
      AND status = 'ok'
)
SELECT
    stage,
    COUNT(*)                                         AS total_calls,
    COUNT(*) FILTER (WHERE outcome = 'hit')          AS cache_hits,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE outcome = 'hit')
        / NULLIF(COUNT(*), 0),
        1
    )                                                AS hit_rate_pct
FROM stage_decisions
GROUP BY stage
ORDER BY stage;
```

---

## Panel 34 — Try-on Cache Hit-Rate

**Question:** how often does the try-on render avoid a fresh Gemini
call? This is the single largest cost lever in the pipeline (~$0.04
per render, 84% of cold-turn cost on a typical 3-outfit response).
Try-on cache hits surface in `model_call_logs.call_type='virtual_tryon_cache_hit'`;
misses fire `call_type='virtual_tryon'` (no `_cache_hit` suffix).

```sql
-- Try-on cache hit rate over the last 7 days.
-- Each row in model_call_logs is one render attempt; the call_type
-- distinguishes hit from miss.
WITH tryon_decisions AS (
    SELECT
        CASE
            WHEN call_type = 'virtual_tryon_cache_hit' THEN 'hit'
            WHEN call_type = 'virtual_tryon'           THEN 'miss'
            ELSE 'other'
        END AS outcome,
        created_at::date AS day
    FROM model_call_logs
    WHERE call_type IN ('virtual_tryon', 'virtual_tryon_cache_hit')
      AND created_at >= NOW() - INTERVAL '7 days'
)
SELECT
    day,
    COUNT(*)                                  AS total_renders,
    COUNT(*) FILTER (WHERE outcome = 'hit')   AS cache_hits,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE outcome = 'hit')
        / NULLIF(COUNT(*), 0),
        1
    )                                         AS hit_rate_pct
FROM tryon_decisions
GROUP BY day
ORDER BY day DESC;
```

A turn-level audit (which specific outfit renders are missing) lives
in `ops/scripts/turn_forensics.py` per-turn output — look at the
`virtual_tryon_cache_hit` vs `virtual_tryon` rows under MODEL_CALL_LOGS.

If sustained hit rate is <30%, the next investigation is the
`virtual_tryon_images` fingerprint logic: which inputs determine
cache-key equality? If two turns with the same user + same garment
combo miss, the fingerprint is too discriminating.

---

## Panel 35 — Catalog Title/Price Freshness

**Question:** is the catalog title + price column ever empty on
new rows? PR #292 backfilled all 14k rows from live merchant
endpoints, but new ingestions could re-introduce the gap if the
CSV parser drops the columns again. This panel is the canary —
any non-zero count on a freshly-inserted row is a regression.

```sql
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
```

A non-zero value in `empty_title_live_rows` or `null_price_live_rows`
on a new day means a recent ingestion lost the merchant title/price
during the CSV → catalog_enriched path — most likely the
`enriched_catalog_upload.csv` step has malformed quoting again.
Recovery: re-run `ops/scripts/...` title backfill scripts (or check
the per-merchant source CSV's `title` column header is intact).

`deleted_from_source_rows` is informational — those rows are
correctly tagged and should not appear in recommendations
(verified by Panel 4 / pipeline health).

---

## Panel 36 — Retrieval Empty After Relaxation

**Question:** how often does catalog_search return zero products even
after exhausting the auto-relaxation sequence? A non-zero count on
this panel means the system tried every relaxation level and still
came back empty — either a real catalog gap for the user's request,
or a silent retrieval-layer failure (the failure mode the May 13 RPC
overload bug exploited for ~24h before forensics caught it).

**Context:** PR #329 dropped a duplicate `match_catalog_item_embeddings`
overload that was returning PGRST203 ambiguity errors on every 3-arg
call. The application caught the exception and proceeded with `matches=[]`,
which the orchestrator surfaced as a low-confidence fallback. The bug
was invisible until forensics — every existing panel saw "low-confidence
response shipped" rather than "retrieval failed silently". This panel
is the new SRE-level guard against the next such regression.

PR #339 (this PR) persists `retrieval_relaxation_outcome` and
`retrieval_total_products` in `metadata_json` on every catalog-pipeline
turn, so the panel can distinguish "tried everything, catalog is thin"
from "composer rejected a populated pool".

```sql
-- retrieval_empty_after_relaxation_last_7d
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) AS turns,
    COUNT(*) FILTER (
        WHERE metadata_json->>'retrieval_relaxation_outcome' = 'exhausted'
          AND (metadata_json->>'retrieval_total_products')::int = 0
    ) AS retrieval_empty_after_relaxation,
    COUNT(*) FILTER (
        WHERE metadata_json->>'answer_source' = 'catalog_low_confidence'
    ) AS low_conf_total,
    round(
        100.0 * COUNT(*) FILTER (
            WHERE metadata_json->>'retrieval_relaxation_outcome' = 'exhausted'
              AND (metadata_json->>'retrieval_total_products')::int = 0
        )::numeric
        / nullif(COUNT(*), 0),
        3
    ) AS empty_after_relax_pct
FROM dependency_validation_events
WHERE event_type = 'turn_completed'
  AND primary_intent IN ('occasion_recommendation', 'pairing_request')
  AND created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1 DESC;
```

**Healthy:** `retrieval_empty_after_relaxation` is consistently 0.
Some `catalog_low_confidence` is expected (the rater can refuse
populated pools), but the catalog should always return *something*
when filters are fully dropped.

**Degraded:** sustained `empty_after_relax_pct > 1%` means either
the catalog has a structural gap (no inventory at the user's gender
expression × occasion intersection — investigate via Panel 6 source
mix and the catalog inventory snapshot) or the retrieval RPC is
silently erroring again (check application logs for PGRST200/PGRST202/
PGRST203 patterns).

**Unhealthy:** sudden spike on a single day with no recent catalog
ingestion changes — almost always a database-state regression like
PR #329's overload. Cross-reference with recent Supabase migration
runs and check for ambiguous-function errors in the application log.

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
  2. Verify `catalog_enriched` row count matches expectations
     (reference as of 2026-05-11: **14,242 garment-only rows** post-
     Step-2b re-enrichment; 54 rows with broken Shopify-CDN image URLs
     were intentionally dropped). If `catalog_enriched` shrank below
     14,242, investigate the most recent admin job.
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

### A4: Composition engine flag-on regressions (Phase 4.7+)

The composition engine (PR #149) replaces the LLM architect with deterministic YAML reduction when `AURA_COMPOSITION_ENGINE_ENABLED=true`. Three failure modes are worth a runbook entry:

**A4.1 — Engine flag set but every turn shows `fallback_reason=engine_disabled`.**
- **Signal:** `composition_router_decision used_engine=False fallback_reason=engine_disabled` in the orchestrator log on every turn, even though the env var is set in the shell.
- **Cause (almost always):** the env var was assigned but not exported, so the python subprocess didn't inherit it. Or it was set but the orchestrator process was started before the env update.
- **First three actions:**
  1. Check `.env.staging` (or `.env.local`) contains `AURA_COMPOSITION_ENGINE_ENABLED=true`. The dotenv loader reads at process boot.
  2. Restart the orchestrator process (`AuraRuntimeConfig` reads env at startup, not per-request).
  3. Run `python ops/scripts/turn_forensics.py <turn_id>` — confirm `used_engine: True` after the restart.

**A4.2 — Engine runs but every turn falls through with `yaml_gap`.**
- **Signal:** `fallback_reason=yaml_gap` plus `yaml_gaps=["occasion_signal:...", ...]` in router_decision.
- **Cause:** the planner is emitting values that aren't canonical YAML keys *and* the canonicalize layer (PR #151) couldn't bridge them above the 0.50 cosine threshold.
- **First three actions:**
  1. Run Panel 22 (YAML-Gap Distribution) to see top-N gaps over the last 30 days.
  2. For each frequent gap (≥10 occurrences), decide: add as a YAML alias (cheap), enrich the YAML notes so embedding matches better (best), or accept fall-through and rely on LLM (no-op).
  3. After YAML edits, regenerate the embedding bank: `python ops/scripts/build_canonical_embeddings.py` and commit the new `canonical_embeddings.json`.

**A4.3 — `aura_composition_yaml_load_failure_total` ticks (alert P2).**
- **Signal:** the alert `aura_composition_yaml_load_failure` fires.
- **Cause:** a YAML in `knowledge/style_graph/*.yaml` failed to parse or validate at process boot. The orchestrator caught it and disabled the engine for the rest of the process — turns silently fall through to LLM.
- **First three actions:**
  1. Grep the application stdout for `Composition engine YAML load failed:` — the exception message names the offending file + reason.
  2. Run the YAML validator locally: `python ops/scripts/validate_style_graph_yaml.py` and `validate_style_graph_conflicts.py`.
  3. Once fixed on main, restart the affected pods (the in-process disable persists until restart).

### A5: Composer engine flag-on regressions (Phase 5d+)

The composer engine (PR 5c, wired in PR 5d) replaces the LLM `OutfitComposer` with deterministic tuple scoring + greedy top-K when `AURA_COMPOSER_ENGINE_ENABLED=true`. Same shape of failure modes as A4 — three runbook entries:

**A5.1 — Engine flag set but every turn shows `fallback_reason=engine_disabled` on the composer router.**
- **Signal:** `composer_router_decision used_engine=False fallback_reason=engine_disabled` in the orchestrator log on every turn.
- **Cause (almost always):** env var was assigned but not exported, OR the orchestrator process started before the env update.
- **First three actions:**
  1. Confirm `.env.staging` (or `.env.local`) contains `AURA_COMPOSER_ENGINE_ENABLED=true`.
  2. Restart the orchestrator process (config is read at startup).
  3. Run `python ops/scripts/turn_forensics.py <turn_id>` — confirm composer-side `used_engine: True` after the restart.

**A5.2 — Engine runs but every turn falls through with `pool_too_sparse`.**
- **Signal:** `fallback_reason=pool_too_sparse` (composer-side) on most turns; Panel 25 shows engine share <10%.
- **Cause:** the architect is emitting directions whose retrieval pools have <2 items per role. Most often this means upstream retrieval is returning fewer items than expected (catalog SKU coverage gap, over-aggressive hard filters), or the architect is emitting directions that don't match the catalog inventory shape.
- **First three actions:**
  1. Cross-check Panel 16 (low_confidence_catalog_responses) — if architect+composer pool sizes look low, retrieval is the upstream cause.
  2. Inspect `model_call_logs.request_json` on a sparse turn for the architect's emitted directions; verify they map to actual catalog inventory via `ops/scripts/turn_forensics.py`.
  3. If retrieval is underperforming generally, that's a catalog data problem, not a composer problem — engine will start succeeding once retrieval recovers.

**A5.2b — Engine runs but specific pairing rules are over-dropping (post-PR #248-#251).**
- **Signal:** Panel 26 shows high counts of `guest_vs_bridal_separation`, `sheen_hierarchy`, `max_dominant_colors`, or `one_statement_per_outfit`; the four pairing matchers shipped May 2026 changed the composer's drop landscape and can over-fire if the YAML thresholds drift from the catalog's actual value distribution.
- **Cause hierarchy (check in order):**
  1. `guest_vs_bridal_separation` fires — `provenance_summary.bridal_role == "guest"` or `"attendee"` correctly identifies the upstream role context. If `bridal_role == "unset"` AND the rule still fired, that's a matcher bug (the rule's gate should require a non-empty role). RCA via `aura_composer_rule_violation_total{rule="guest_vs_bridal_separation"}` rate vs `bridal_role="guest"` rate.
  2. `sheen_hierarchy` fires outside the bridal exception — likely the YAML's `value: 1` cap is too strict for the catalog's actual fabric_texture distribution. Check `aura_composer_rule_exception_applied_total{exception="distributed_statement_exception"}` to see if related exceptions are saving similar cases; if not, the cap needs review.
  3. `max_dominant_colors` fires with `(excluded N metallic-neutral)` in detail — the metallic-neutral exception is firing but not enough; expand `_METALLIC_NEUTRAL_COLORS` set in `pairing.py` after auditing actual catalog `dominant_color` values via Panel 22.
- **First three actions:**
  1. Open Panel 26; sort by `total_drops`. Compare to baseline (typical: formality/color/pattern rules dominate).
  2. Cross-reference with `aura_composer_rule_exception_applied_total` — high violations + low exception fires = matcher is correctly identifying violations and exceptions aren't masking them; high violations + high exception fires = exception is partially working but threshold needs tuning.
  3. Per-rule YAML lives at `knowledge/style_graph/pairing_rules.yaml`. Stylist context (when and why each rule was added) lives in `knowledge/knowledge_v2/updated_review_style_notes_pairing.md`.

**A5.3 — Engine accepts but Panel 18 (rater unsuitable rate) ticks above 5%.**
- **Signal:** rater-side `unsuitable=True` rate climbs after the composer flag flips.
- **Cause:** the engine is producing tuples that pass its hard rules but the rater (which has aesthetic judgment the engine doesn't) flags as unsuitable. Likely candidates: diversity penalty too lax (similar outfits dominating picks), OR `MIN_OUTFIT_SCORE` floor too low (weak tuples surviving).
- **First three actions:**
  1. Run Panel 26 (rule-violation distribution) — heavy soft-violation accumulation correlates with rater rejection.
  2. Run Panel 27 (per-tuple score histogram) — if picks are bunching at base_score < 0.7, the engine isn't filtering hard enough; calibrate `MIN_OUTFIT_SCORE`.
  3. Capture 50 unsuitable-rated engine outfits via Panel 28 + `ops/scripts/turn_forensics.py`; spot-check what the engine missed that the rater caught — this is the YAML-tuning backlog.

### A6: Try-on flag accidentally off in production

**Signal:** Panel 29 shows `aura_tryon_flag_total{enabled="false"}` rate climbing or sustained at >50% during business hours, OR users report "no images on cards."
**Cause:** `AURA_TRYON_ENABLED` env var unset / set to a falsy value on the production orchestrator. The flag was added in PR #185 with `default=False` so an unset var silently disables try-on rendering.
**First three actions:**
1. Confirm production env: `kubectl exec <pod> -- env | grep AURA_TRYON_ENABLED` (or equivalent for your deploy). Empty / falsy → flag is off.
2. If unintentional: set `AURA_TRYON_ENABLED=true` in the deploy manifest and restart pods.
3. If intentional (cost-saving during a degraded mode): check that user-facing copy reflects "previews unavailable" rather than rendering empty cards. Update `qna_messages.py` if the message is missing.

### A7: Empty-retrieval relaxation firing on >2% of turns

**Signal:** Panel 30 shows `outcome="exhausted"` rate >2% sustained, OR `not_needed` share dropping below 90%.
**Cause:** the catalog has shrunk OR the architect is over-constraining. PR #192 added the relaxation as a safety net for legitimate catalog gaps (e.g., turn `9abaf4d4` — masculine catalog had no tshirts/hoodies for "loungewear"). High exhaustion rate means the safety net is bottoming out, which is a content gap signal rather than a software bug.
**First three actions:**
1. Run the SQL drilldown on `distillation_traces.full_output.relaxation_applied` for the last 24h, grouped by `(planner.target_product_type, gender_expression)` — surface which (subtype, gender) cells dominate the exhausted bucket.
2. If a specific cell dominates: it's a catalog content gap. File against the catalog ingestion backlog with the exact subtype × gender × occasion that exhausted.
3. If exhaustion is spread across many cells: the architect is likely emitting over-constrained `hard_filters`. Cross-check Panel 16 (low_confidence_catalog_responses) — both panels move together when the architect is the cause. Recalibrate the planner's hard-filter binding (`_apply_target_product_type_to_plan` in orchestrator.py).

### A8: Per-axis YAML-gap impact concentrated on one axis

**Signal:** Panel 32 shows one axis accounting for >40% of total impact across the cohort, AND `ops/scripts/tune_yaml_gap_weights.py` reports correlation < 0.30 for that axis.
**Cause:** `_YAML_GAP_AXIS_WEIGHTS[axis]` is too aggressive — gaps on this axis are dragging confidence below the 0.50 threshold even when the gap turns out to be benign (engine-served turns rate fine). High impact + low fallback correlation = wasted fall-throughs.
**First three actions:**
1. Run `python ops/scripts/tune_yaml_gap_weights.py --limit 1000` on the staging trace pool. If the axis is in the "weight down" suggestion list, the analysis confirms the panel's read.
2. Drop the axis weight one step (0.2) in `composition/engine.py:_YAML_GAP_AXIS_WEIGHTS`. Open a config-only PR — same flow as PR #197.
3. After merge: re-baseline against Panel 32 in 7 days to confirm impact dropped without a regression in Panel 21 (engine acceptance rate).

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
| `ops/scripts/turn_forensics.py` | Per-turn forensics: latency / cost / router decision side-by-side |
| `ops/scripts/build_canonical_embeddings.py` | Regenerate `composition/canonical_embeddings.json` after a YAML change |
| `ops/scripts/composition_quality_eval.py` | Architect engine-vs-LLM divergence eval (consumes Phase 4.6 eval set) |
| `ops/scripts/composer_quality_eval.py` | Composer engine-vs-LLM divergence eval (consumes Phase 4.6 eval set + retrieval pools per cell) |


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

