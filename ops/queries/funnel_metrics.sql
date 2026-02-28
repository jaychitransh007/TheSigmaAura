-- Funnel Metrics and Failure Reason Queries
-- For use in observability dashboards (Phase 5)
-- Last updated: 2026-03-01

-- ============================================================
-- 1. Recommendation Funnel: CTR proxy (feedback events per run)
-- ============================================================
-- Shows recommendation runs with engagement counts.
SELECT
    rr.id AS recommendation_run_id,
    rr.conversation_id,
    rr.strictness,
    rr.resolved_mode,
    rr.candidate_count,
    rr.returned_count,
    rr.created_at,
    COUNT(fe.id) FILTER (WHERE fe.event_type = 'like') AS likes,
    COUNT(fe.id) FILTER (WHERE fe.event_type = 'dislike') AS dislikes,
    COUNT(fe.id) FILTER (WHERE fe.event_type = 'share') AS shares,
    COUNT(fe.id) FILTER (WHERE fe.event_type = 'buy') AS buys,
    COUNT(fe.id) FILTER (WHERE fe.event_type IN ('skip', 'no_action')) AS skips,
    COUNT(fe.id) AS total_events
FROM recommendation_runs rr
LEFT JOIN feedback_events fe ON fe.recommendation_run_id = rr.id
GROUP BY rr.id, rr.conversation_id, rr.strictness, rr.resolved_mode,
         rr.candidate_count, rr.returned_count, rr.created_at
ORDER BY rr.created_at DESC
LIMIT 500;


-- ============================================================
-- 2. Add-to-Cart Rate (checkout preparations per recommendation run)
-- ============================================================
SELECT
    rr.id AS recommendation_run_id,
    rr.resolved_mode,
    rr.returned_count,
    cp.id AS checkout_prep_id,
    cp.status AS checkout_status,
    cp.created_at AS checkout_created_at
FROM recommendation_runs rr
LEFT JOIN checkout_preparations cp ON cp.recommendation_run_id = rr.id
ORDER BY rr.created_at DESC
LIMIT 500;


-- ============================================================
-- 3. Checkout-Prep Completion Rate and Failure Reasons
-- ============================================================
SELECT
    cp.status,
    COUNT(*) AS total,
    ROUND(COUNT(*)::numeric / NULLIF(SUM(COUNT(*)) OVER (), 0) * 100, 1) AS pct
FROM checkout_preparations cp
GROUP BY cp.status
ORDER BY total DESC;


-- ============================================================
-- 4. Checkout Failure Reasons (from validation_json)
-- ============================================================
SELECT
    cp.id AS checkout_prep_id,
    cp.status,
    cp.validation_json->'notes' AS validation_notes,
    cp.validation_json->'substitution_suggestions' AS substitutions,
    cp.created_at
FROM checkout_preparations cp
WHERE cp.status IN ('needs_user_action', 'failed')
ORDER BY cp.created_at DESC
LIMIT 200;


-- ============================================================
-- 5. Mode Resolution Distribution
-- ============================================================
SELECT
    ct.mode_preference,
    ct.resolved_mode,
    COUNT(*) AS turn_count
FROM conversation_turns ct
WHERE ct.resolved_mode IS NOT NULL
GROUP BY ct.mode_preference, ct.resolved_mode
ORDER BY turn_count DESC;


-- ============================================================
-- 6. Mode Routing Accuracy (garment vs outfit resolution)
-- ============================================================
-- Compares mode_preference to resolved_mode. For "auto" mode,
-- shows how often it resolves to garment vs outfit.
SELECT
    ct.mode_preference,
    ct.resolved_mode,
    COUNT(*) AS count,
    ROUND(COUNT(*)::numeric / NULLIF(SUM(COUNT(*)) OVER (PARTITION BY ct.mode_preference), 0) * 100, 1) AS pct_within_preference
FROM conversation_turns ct
WHERE ct.resolved_mode IS NOT NULL
GROUP BY ct.mode_preference, ct.resolved_mode
ORDER BY ct.mode_preference, count DESC;


-- ============================================================
-- 7. Style Constraints Applied Frequency
-- ============================================================
SELECT
    rr.style_constraints_json->'constraints' AS constraints,
    COUNT(*) AS run_count
FROM recommendation_runs rr
WHERE rr.style_constraints_json IS NOT NULL
GROUP BY rr.style_constraints_json->'constraints'
ORDER BY run_count DESC
LIMIT 50;


-- ============================================================
-- 8. Substitution Acceptance Rate
-- ============================================================
-- Shows how many over-budget preparations had substitutions suggested
-- vs those with no substitution available.
SELECT
    CASE
        WHEN cp.validation_json->'notes' ? 'substitution_suggested' THEN 'substitution_suggested'
        WHEN cp.validation_json->'notes' ? 'no_substitution_available' THEN 'no_substitution_available'
        ELSE 'not_over_budget'
    END AS substitution_status,
    COUNT(*) AS total
FROM checkout_preparations cp
GROUP BY substitution_status
ORDER BY total DESC;


-- ============================================================
-- 9. Guardrail Block Events (from tool_traces)
-- ============================================================
SELECT
    tt.tool_name,
    tt.input_json->>'action' AS blocked_action,
    tt.output_json->>'reason' AS reason,
    tt.status,
    tt.created_at
FROM tool_traces tt
WHERE tt.tool_name = 'policy_guardrail.check_action'
  AND tt.status = 'blocked'
ORDER BY tt.created_at DESC
LIMIT 100;


-- ============================================================
-- 10. Daily Funnel Summary
-- ============================================================
SELECT
    DATE(ct.created_at) AS day,
    COUNT(DISTINCT ct.id) AS turns,
    COUNT(DISTINCT rr.id) AS recommendation_runs,
    COUNT(DISTINCT cp.id) AS checkout_preps,
    COUNT(DISTINCT cp.id) FILTER (WHERE cp.status = 'ready') AS checkout_ready,
    COUNT(DISTINCT cp.id) FILTER (WHERE cp.status = 'needs_user_action') AS checkout_needs_action,
    COUNT(DISTINCT fe.id) AS feedback_events,
    COUNT(DISTINCT fe.id) FILTER (WHERE fe.event_type = 'buy') AS buy_events
FROM conversation_turns ct
LEFT JOIN recommendation_runs rr ON rr.turn_id = ct.id
LEFT JOIN checkout_preparations cp ON cp.recommendation_run_id = rr.id
LEFT JOIN feedback_events fe ON fe.recommendation_run_id = rr.id
GROUP BY DATE(ct.created_at)
ORDER BY day DESC
LIMIT 30;
