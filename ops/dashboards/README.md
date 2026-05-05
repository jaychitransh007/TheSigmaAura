# Aura Operations Dashboards — SQL Files

Each `panel_NN_*.sql` file is auto-extracted from `docs/OPERATIONS.md`
by `ops/scripts/extract_dashboard_sql.py`. The doc is the source of truth;
this directory makes the SQL paste-ready for Supabase Studio / Metabase / Grafana.

## Files

- [`panel_01_acquisition_onboarding_funnel.sql`](panel_01_acquisition_onboarding_funnel.sql)
- [`panel_02_daily_active_users_turn_volume.sql`](panel_02_daily_active_users_turn_volume.sql)
- [`panel_03_intent_mix.sql`](panel_03_intent_mix.sql)
- [`panel_04_pipeline_health_errors_empty_responses.sql`](panel_04_pipeline_health_errors_empty_responses.sql)
- [`panel_05_repeat_retention.sql`](panel_05_repeat_retention.sql)
- [`panel_06_wardrobe_catalog_engagement.sql`](panel_06_wardrobe_catalog_engagement.sql)
- [`panel_07_negative_signals.sql`](panel_07_negative_signals.sql)
- [`panel_08_confidence_drift.sql`](panel_08_confidence_drift.sql)
- [`panel_09_visual_evaluator_path_mix_phase_12b.sql`](panel_09_visual_evaluator_path_mix_phase_12b.sql)
- [`panel_10_try_on_quality_gate_health_phase_12e.sql`](panel_10_try_on_quality_gate_health_phase_12e.sql)
- [`panel_11_final_response_count_below_target_phase_12e.sql`](panel_11_final_response_count_below_target_phase_12e.sql)
- [`panel_12_wardrobe_enrichment_failure_rate_phase_12d.sql`](panel_12_wardrobe_enrichment_failure_rate_phase_12d.sql)
- [`panel_13_wardrobe_anchor_try_on_coverage_phase_12d_follow_up.sql`](panel_13_wardrobe_anchor_try_on_coverage_phase_12d_follow_up.sql)
- [`panel_14_non_garment_image_rate_phase_12d_follow_up.sql`](panel_14_non_garment_image_rate_phase_12d_follow_up.sql)
- [`panel_16_low_confidence_catalog_responses.sql`](panel_16_low_confidence_catalog_responses.sql)
- [`panel_17_architect_input_token_growth.sql`](panel_17_architect_input_token_growth.sql)
- [`panel_18_rater_unsuitable_rate.sql`](panel_18_rater_unsuitable_rate.sql)
- [`panel_19_composer_latency.sql`](panel_19_composer_latency.sql)
- [`panel_20_episodic_memory_population.sql`](panel_20_episodic_memory_population.sql)
<!-- preserve-below -->
<!-- Content below this marker is curator-maintained and survives regeneration
     by ops/scripts/extract_dashboard_sql.py. See PR #96 for the marker logic. -->

## Log-based panels (no SQL)

- **Panel 15 — Catalog Search Timeout Rate** — sourced from application logs
  (`catalog_search_agent` `WARNING` lines containing `similarity_search TIMEOUT`).
  Monitor via your log aggregator (Logflare / Datadog / Cloud Logging), not Supabase.
  See `docs/OPERATIONS.md` § Panel 15 for healthy/degraded/unhealthy thresholds.

## Refresh cadence (recommended)

- Panels 4 (Pipeline Health) and 7 (Negative Signals): **5 minutes**
- Panel 10 (Try-on Quality Gate): **15 minutes** during week 1, hourly after
- Panels 17–20 (post-PRs #81–#95): **hourly** for the first week to baseline; once
  curves stabilize fall back to daily for the token/latency panels.
- Everything else: **hourly**
