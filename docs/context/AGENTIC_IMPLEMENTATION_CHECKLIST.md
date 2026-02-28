# Agentic Implementation Checklist

Last updated: March 1, 2026

Status legend:
1. `[ ]` pending
2. `[-]` in progress
3. `[x]` complete

## Phase 0: Docs Lock
1. [x] Canonical context split finalized.
- Owner: Platform Architecture
- Artifact: all `docs/context/*.md` module files
- Done definition: docs are architecture-locked and mutually consistent.

2. [x] Contradictory architecture statements removed.
- Owner: Platform Architecture
- Artifact: context diff review
- Done definition: no active architecture references to excluded scope.

3. [x] Index links validated.
- Owner: Platform Architecture
- Artifact: `docs/context/SINGLE_SOURCE_OF_TRUTH.md`
- Done definition: all canonical links resolve.

## Phase 1: Contracts and Schema
1. [x] Add new enums/types (`ModePreference`, `ResolvedMode`, `AutonomyLevel`, `CheckoutPreparationStatus`, `SizeProfile`).
- Owner: Conversation API
- Artifact: `modules/conversation_platform/src/conversation_platform/schemas.py`
- Done definition: types defined and importable.

2. [x] Add turn request fields (`mode_preference`, `target_garment_type`, `autonomy_level`, `size_overrides`).
- Owner: Conversation API
- Artifact: `modules/conversation_platform/src/conversation_platform/schemas.py`
- Done definition: request schema validates new fields with defaults.

3. [x] Add turn response fields (`resolved_mode`, `complete_the_look_offer`, `style_constraints_applied`, `profile_fields_used`, `agent_trace_ids`).
- Owner: Conversation API
- Artifact: response schema and API tests
- Done definition: response contract and tests updated.

4. [x] Add `initial_profile` to conversation create request.
- Owner: Conversation API
- Artifact: conversation create schema and API
- Done definition: optional profile object accepted and persisted.

5. [x] Add checkout-prep endpoints.
- Owner: Conversation API
- Artifact: `api.py` endpoint implementation
- Done definition: both checkout-prep endpoints return validated payloads.

6. [x] Add persistence schema additions (`users.profile_json`, `users.profile_updated_at`, turn mode/autonomy fields, `recommendation_runs` additions, checkout tables).
- Owner: Data Platform
- Artifact: Supabase migration files
- Done definition: migration applies cleanly and tests pass.

7. [x] Keep backward compatibility by defaulting missing new fields.
- Owner: Conversation API
- Artifact: schema defaults and migration
- Done definition: existing API calls work unchanged.

## Phase 2: Agent Refactor in Orchestrator
1. [x] Introduce `IntentModeRouterAgent` before recommendation.
- Owner: Orchestration
- Artifact: orchestrator and trace metadata
- Done definition: resolved mode is explicitly emitted and logged.

2. [x] Split style logic into required sub-agents (Interpreter, Garment Recommender, Complete-the-Look, Combo Composer, Brand Variance & Comfort).
- Owner: Style Engine
- Artifact: style orchestration contract docs and code
- Done definition: interpreter/garment/complete-look/combo/brand-variance responsibilities are traceable.

3. [x] Separate profile ownership vs body-harmony ownership.
- Owner: User Intelligence
- Artifact: profile merge contract and snapshots
- Done definition: explicit input overrides inference where applicable; last-write-wins for explicit fields.

4. [x] Keep deterministic ranker as selection source of truth.
- Owner: Style Engine
- Artifact: ranker integration
- Done definition: all recommendations pass through deterministic scoring.

## Phase 3: Complete-the-Look Behavior
1. [x] Garment mode returns single-item ranking plus `complete_the_look_offer=true`.
- Owner: Style Engine
- Artifact: mode-aware ranking output
- Done definition: garment mode recommendations include follow-up offer.

2. [x] Outfit mode returns complete singles + combos in a unified ranked list.
- Owner: Style Engine
- Artifact: outfit mode ranking output
- Done definition: singles and combos compete in one list.

3. [x] Add explicit mode switch action in response payload.
- Owner: Conversation API
- Artifact: response contract (`mode_switch_cta` field in TurnResponse)
- Done definition: response includes CTA to switch modes.

## Phase 4: Checkout-Prep Integration
1. [x] Implement `checkout/prepare` endpoint with cart adapter.
- Owner: Commerce Integration
- Artifact: checkout-prep service logic
- Done definition: stock and price validations are persisted.

2. [x] Enforce stock/price revalidation and substitution policy.
- Owner: Budget & Cart
- Artifact: substitution policy and tests
- Done definition: returns `needs_user_action` when no valid substitution exists.

3. [x] Persist checkout preparation snapshots and tool traces.
- Owner: Commerce Integration
- Artifact: persistence and trace records
- Done definition: checkout preparation records and items persisted to Supabase.

4. [x] Enforce no-order-placement hard guardrail.
- Owner: Policy & Trust
- Artifact: policy checks and tests
- Done definition: purchase execution attempts always blocked (architectural: no execute endpoint exists).

## Phase 5: Policy/Trust and Observability Hardening
1. [x] Block unsupported actions (`execute_purchase`).
- Owner: Policy & Trust
- Artifact: `PolicyGuardrailAgent` in agents.py, `/v1/actions/check` endpoint, policy enforcement tests
- Done definition: all purchase execution attempts return guardrail explanation.

2. [x] Log mode resolution, constraints, substitutions, and guardrail decisions.
- Owner: Observability
- Artifact: `_log_mode_resolution_trace` and `_log_guardrail_trace` in orchestrator, tool_traces records
- Done definition: all key decisions traceable in tool_traces.

3. [x] Add dashboards/queries for funnel metrics and failure reasons.
- Owner: Observability
- Artifact: `ops/queries/funnel_metrics.sql` (10 queries)
- Done definition: live metrics available.

## Phase 6: Per-Agent Eval Infrastructure
1. [x] Add per-agent eval suites.
- Owner: Quality Engineering
- Artifact: 9 suite files in `ops/evals/agents/` (intent_mode_router, profile_agent, body_harmony, style_agent, catalog_agent, budget_agent, checkout_prep, policy_agent, telemetry_agent)
- Done definition: suite coverage exists for all production agents.

2. [x] Add per-agent runner.
- Owner: Quality Engineering
- Artifact: `ops/scripts/run_agent_evals.py`
- Done definition: runner produces full artifact contract (run_manifest.json, case_inputs.jsonl, case_outputs.jsonl, case_scores.jsonl, case_scores.csv, summary.json, summary.md, artifact_integrity.json).

3. [x] Add per-agent threshold and fail-gate enforcement.
- Owner: Quality Engineering
- Artifact: per-suite thresholds in suite JSON, gate semantics (pass/warning/fail/fail_integrity), `--fail-on-gate` CLI flag
- Done definition: CI fails on defined fail gates.

## Phase 7: Rollout and Monitoring
1. [x] Wire eval cadence into CI (PR/nightly/weekly).
- Owner: DevOps
- Artifact: `.github/workflows/pr-eval.yml`, `nightly-eval.yml`, `weekly-eval.yml`
- Done definition: all scheduled runs execute with artifacts retained (30/90/180 day retention).

2. [x] Publish operational dashboard for key architecture KPIs.
- Owner: Observability
- Artifact: `ops/runbooks/OPERATIONAL_DASHBOARD.md` (8 panels, KPI targets table), `ops/queries/funnel_metrics.sql`
- Done definition: live metrics available for leadership and engineering.

3. [x] Release-gate enforcement policy active.
- Owner: Product + Engineering
- Artifact: `ops/scripts/run_release_gate.py`, `--fail-on-block` CI flag
- Done definition: release blocked automatically on gate failure.

## Anchoring Checklist
### Docs Lock
1. [x] Canonical file split complete.
2. [x] Old contradictory statements removed.
3. [x] Index links valid.

### Contracts
1. [x] API schema updated in docs.
2. [x] DB contract documented.
3. [x] Guardrail behavior documented.
4. [x] Type definitions documented (ModePreference, ResolvedMode, AutonomyLevel, CheckoutPreparationStatus, SizeProfile).

### Agent Boundaries
1. [x] Style sub-agents documented (Interpreter, Garment Recommender, Complete-the-Look, Combo Composer, Brand Variance & Comfort).
2. [x] Profile vs body-harmony responsibilities clear with merge strategy.
3. [x] Mode router contract fixed with complete_the_look_offer behavior.

### Complete-the-Look
1. [x] Garment mode with follow-up offer documented.
2. [x] Outfit mode unified ranking documented.
3. [x] Mode switch CTA documented.

### Checkout-Prep
1. [x] Checkout-prep flow documented.
2. [x] No-order-placement constraint explicit.
3. [x] Failure fallback paths documented.
4. [x] Substitution policy documented.

### Policy/Trust Hardening
1. [x] Purchase execution block documented and tested.
2. [x] Mode resolution logging documented.
3. [x] Funnel dashboards specified.

### Evals
1. [x] Per-agent suites defined.
2. [x] Thresholds and fail gates defined.
3. [x] CI cadence and artifact contract defined.
4. [x] Gate semantics defined (pass/warning/fail/fail_integrity).
5. [x] Evaluator registry pattern defined.

### Acceptance
1. [x] Architecture terminology consistent across all context docs.
2. [x] Standalone sizing agent absent from active architecture.
3. [x] Post-order lifecycle agent absent from active architecture.
4. [x] Test expectations for `SINGLE_SOURCE_OF_TRUTH.md` preserved.
5. [x] Success criteria documented in SINGLE_SOURCE_OF_TRUTH.md.
6. [x] Adaptability design documented.
7. [x] Monitoring and KPI targets documented.
