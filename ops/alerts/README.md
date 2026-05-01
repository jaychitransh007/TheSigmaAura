# Aura Alert Rules

Alerts-as-code for Aura. Each YAML file in this directory is one alert
rule — versioned alongside the runtime code that emits the metrics it
references, reviewable in PRs, and impossible to delete by accident
through a dashboard UI.

## File format

Every alert ships these fields:

| Field | Required | Description |
|---|---|---|
| `alert` | yes | Stable rule name in `aura_<...>` form |
| `description` | yes | Human-readable trigger explanation |
| `expr` | yes | PromQL expression that returns >0 when alert is firing |
| `for` | yes | Duration the expression must hold before paging |
| `severity` | yes | `P1` (page on-call) or `P2` (ticket) |
| `runbook` | yes | Path or URL to the response runbook |
| `panel` | no | Reference to the dashboard panel that visualises the same data |
| `labels` | yes | Routing keys (`team`, `service`, etc.) |
| `annotations` | yes | `summary` + `description` shown in alert body |

## Sync

`ops/scripts/sync_alerts.py` validates every YAML and emits the rules in
your alerting system's native format. Initial implementation prints
Prometheus AlertManager rule files to stdout. Extend the script when
you wire it into Datadog Monitors or PagerDuty Event Rules.

## Active alerts

- `pipeline_error_rate.yaml` — turn error rate >5% (Panel 4)
- `catalog_unavailable_guardrail.yaml` — guardrail fires on first hit (Panel 4)
- `architect_latency_p95_high.yaml` — gpt-5.4 architect p95 >10s
- `supabase_latency_p95_high.yaml` — Supabase REST p95 >1s
- `tryon_quality_gate_unhealthy.yaml` — Gemini quality gate failure rate >25% (Panel 10)
- `llm_cost_daily_budget_exceeded.yaml` — daily LLM cost >$50
- `readyz_failing.yaml` — /readyz returning non-200 for 5 min
