-- Panel 24 — Composition Engine Runbook (diagnostic queries)
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

-- diagnose_one_turn — replace ::uuid with the actual turn_id
SELECT
    stage,
    model,
    latency_ms,
    full_output -> 'router_decision' AS router_decision
FROM distillation_traces
WHERE turn_id = '00000000-0000-0000-0000-000000000000'::uuid
ORDER BY created_at;
