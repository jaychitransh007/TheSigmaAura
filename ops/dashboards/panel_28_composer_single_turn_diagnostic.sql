-- Panel 28 — Composer Single-Turn Diagnostic
-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)
-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py

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
