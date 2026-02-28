# Operational Dashboard Specification

Last updated: 2026-03-01

## Overview
This document defines the KPI panels, data sources, and alert thresholds for the Aura platform operational dashboard.

## Dashboard Panels

### 1. Recommendation Funnel
- **Data source:** `ops/queries/funnel_metrics.sql` — Query 1 (Recommendation CTR), Query 10 (Daily Funnel)
- **Panels:**
  - Daily recommendation runs (line chart)
  - Daily feedback event distribution (stacked bar: like/dislike/share/buy/skip)
  - Engagement rate = (likes + shares + buys) / total_events (line chart, 7-day rolling avg)
- **Alert:** Engagement rate drops below 15% for 3 consecutive days

### 2. Add-to-Cart and Checkout
- **Data source:** `ops/queries/funnel_metrics.sql` — Query 2 (Add-to-Cart), Query 3 (Completion Rate)
- **Panels:**
  - Checkout-prep creation rate per recommendation run (bar chart)
  - Checkout status distribution (pie: ready / needs_user_action / failed)
  - Checkout completion rate trend (line chart, 7-day rolling avg)
- **Alert:** Completion rate drops below 80% for 2 consecutive days

### 3. Checkout Failure Reasons
- **Data source:** `ops/queries/funnel_metrics.sql` — Query 4 (Failure Reasons)
- **Panels:**
  - Failure reason breakdown (bar: over_budget, no_substitution_available, stock_unavailable)
  - Substitution suggestion acceptance rate (from Query 8)
- **Alert:** `no_substitution_available` exceeds 30% of failures

### 4. Mode Routing
- **Data source:** `ops/queries/funnel_metrics.sql` — Query 5 (Distribution), Query 6 (Accuracy)
- **Panels:**
  - Mode distribution (pie: garment vs outfit)
  - Auto-mode resolution breakdown (stacked bar by resolved_mode)
  - Mode routing accuracy (percentage, with pass/warning/fail thresholds from eval)
- **Alert:** Mode routing accuracy drops below 92%

### 5. Style Constraints
- **Data source:** `ops/queries/funnel_metrics.sql` — Query 7 (Constraints Frequency)
- **Panels:**
  - Constraint application frequency (bar chart)
  - body_harmony usage rate (single stat)
  - size_overrides usage rate (single stat)

### 6. Policy & Trust
- **Data source:** `ops/queries/funnel_metrics.sql` — Query 9 (Guardrail Blocks)
- **Panels:**
  - Guardrail block events over time (line chart)
  - Blocked action distribution (bar)
  - False block rate (single stat)
- **Alert:** Any blocked action that is not in the expected blocked set

### 7. Eval Health
- **Data source:** CI artifacts from `data/logs/agent_evals/*/summary.json`
- **Panels:**
  - Per-agent gate status (traffic light grid: pass=green, warning=amber, fail=red)
  - Overall gate trend (line chart, last 30 runs)
  - E2E integrity pass rate (single stat)
  - E2E average score (line chart)
- **Alert:** Any agent gate status is `fail` or `fail_integrity`

### 8. Daily Funnel Summary
- **Data source:** `ops/queries/funnel_metrics.sql` — Query 10
- **Panels:**
  - Turns → Recommendation Runs → Checkout Preps → Buy Events (funnel visualization)
  - Conversion rates between each stage (single stats)
- **Alert:** Any stage-to-stage conversion drops by >20% relative vs 7-day avg

## KPI Targets (from Architecture Spec)

| KPI | Target | Warning | Critical |
|---|---:|---:|---:|
| Recommendation engagement rate | >=20% | <15% | <10% |
| Checkout-prep completion rate | >=85% | <80% | <70% |
| Mode routing accuracy | >=95% | <92% | <88% |
| Complete-the-look acceptance | >=40% | <30% | <20% |
| Substitution acceptance rate | >=50% | <40% | <25% |
| No-purchase side-effect rate | 100% | <100% | <100% |
| E2E integrity pass rate | >=99% | <97% | <95% |
| Agent eval overall gate | pass | warning | fail |

## Access
- Dashboard tool: Supabase Dashboard / Grafana / Metabase (TBD per deployment)
- Query source: `ops/queries/funnel_metrics.sql`
- Eval artifact source: CI pipeline artifacts
