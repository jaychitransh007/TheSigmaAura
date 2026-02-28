# Test Suite Map (Architecture-Locked)

Last updated: March 1, 2026

## Run Command
```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Coverage by Module Context

### 1) Config Contract and Context Integrity
Primary files:
1. `tests/test_config_and_schema.py`
2. `tests/test_batch_builder.py`

Covers:
1. config-driven schema loading
2. ranked-attribute contract validity
3. context index file existence and baseline content checks

### 2) User Profile + Body Harmony
Primary files:
1. `tests/test_user_profiler.py`
2. `tests/test_conversation_orchestrator.py`

Covers:
1. visual/text schema constraints
2. image input normalization and artifact persistence
3. clarification flow when profile/context is missing

### 3) Tier 1 Catalog and Policy Gating
Primary files:
1. `tests/test_tier1_filters.py`
2. `tests/test_intent_policy.py`

Covers:
1. hard filter behavior and relaxations
2. policy exclusion behavior
3. minimal hard-filter profile safety gates

### 4) Tier 2 Style + Complete-the-Look
Primary files:
1. `tests/test_tier2_ranker.py`
2. `tests/test_outfit_engine.py`

Covers:
1. deterministic scoring behavior
2. recommendation mode resolution
3. combo construction and metadata integrity
4. complete-only behavior constraints

### 5) Conversation API and Orchestration
Primary files:
1. `tests/test_conversation_platform.py`
2. `tests/test_conversation_orchestrator.py`
3. `tests/test_conversation_api_ui.py`

Covers:
1. conversation and turn API contracts
2. orchestration lifecycle and persistence calls
3. async stage polling and UI wiring
4. feedback event handling

### 6) Phase 1 Agentic Commerce (Contracts, Mode Routing, Checkout-Prep)
Primary files:
1. `tests/test_agentic_phase1.py`

Covers:
1. new schema types and enums (ModePreference, ResolvedMode, AutonomyLevel, CheckoutPreparationStatus)
2. SizeOverrides, InitialProfile, CheckoutPrepareRequest/Response models
3. turn request/response new field defaults and validation
4. repository methods for checkout preparation CRUD
5. orchestrator mode routing logic (auto/garment/outfit resolution)
6. complete_the_look_offer behavior
7. style_constraints_applied and profile_fields_used in response
8. initial_profile persistence on conversation create
9. checkout-prep happy path, over-budget, and error cases
10. API endpoint wiring for checkout/prepare and preparations GET
11. DB migration file validation

### 7) Phase 2 Agent Boundary Refactor
Primary files:
1. `tests/test_agentic_phase2.py`

Covers:
1. IntentModeRouterAgent mode resolution (auto/garment/outfit, target_garment_type, complete_the_look_offer)
2. UserProfileAgent merge logic (last-write-wins, size_overrides, initial_profile, field extraction)
3. BodyHarmonyAgent profile extraction and style constraints
4. StyleRequirementInterpreter context parsing
5. CatalogFilterSubAgent and GarmentRankerSubAgent initialization
6. IntentPolicySubAgent resolution
7. BrandVarianceComfortSubAgent passthrough
8. RecommendationAgent sub-agent delegation and legacy ref preservation
9. Orchestrator wiring verification (mode_router, user_profile_agent, body_harmony_agent)

### 8) Phase 3/4 Completion (Mode Switch CTA, Substitution, Tool Traces)
Primary files:
1. `tests/test_agentic_phase3_4.py`

Covers:
1. `mode_switch_cta` schema field defaults and population
2. garment mode CTA present, outfit mode CTA empty
3. `SubstitutionSuggestion` schema model
4. over-budget substitution suggestion from unused recommendation items
5. over-budget with no cheaper alternative
6. within-budget and no-budget-cap paths
7. `log_tool_trace` called in `prepare_checkout`
8. tool trace input/output contract

### 9) Phase 5 Policy/Trust and Observability Hardening
Primary files:
1. `tests/test_agentic_phase5.py`

Covers:
1. `PolicyGuardrailAgent` blocking execute_purchase, place_order, confirm_order, submit_order
2. allowed actions pass through (recommend, prepare_checkout)
3. case-insensitive, hyphen/space normalization for blocked actions
4. `ActionCheckRequest`/`ActionCheckResponse` schema models
5. `/v1/actions/check` API endpoint wiring
6. orchestrator `check_action` delegation and `policy_guardrail` attribute
7. mode resolution trace logging (`mode_router.resolve_mode` tool trace)
8. guardrail trace logging (`policy_guardrail.check_action` tool trace with blocked/ok status)
9. `ops/queries/funnel_metrics.sql` file existence and key query content

### 10) Phase 6 Per-Agent Eval Infrastructure
Primary files:
1. `tests/test_agentic_phase6.py`

Covers:
1. all 9 agent suite files exist and are valid JSON with required fields
2. suite discovery from directory
3. case execution for IntentModeRouterAgent, UserProfileAgent, BodyHarmonyAgent, PolicyGuardrailAgent, TelemetryAgent, StyleRequirementInterpreter
4. metric hints match/mismatch detection
5. gate semantics (worse_gate ordering: pass < warning < fail < fail_integrity)
6. suite scoring with pass/fail/integrity gates
7. aggregation across multiple suites
8. full artifact contract (8 files written to output directory)
9. integration run of single suite, all suites, and max_cases limit

### 11) Phase 7 Rollout and Monitoring
Primary files:
1. `tests/test_agentic_phase7.py`

Covers:
1. CI workflow files exist (pr-eval, nightly-eval, weekly-eval)
2. PR workflow has unit-tests, agent-evals, release-gate jobs with correct flags
3. nightly workflow has E2E eval and schedule
4. weekly workflow has drift report and 180-day artifact retention
5. operational dashboard spec exists with all 8 panels and KPI targets
6. release gate: all-pass, integrity failure, critical agent fail, non-critical fail, warning
7. release gate: missing eval dir, policy guardrail side-effect rate, thresholds match spec
8. integration: agent evals followed by release gate check

### 12) End-to-End Eval Runner Logic
Primary files:
1. `tests/test_conversation_eval.py`

Covers:
1. rubric scoring logic
2. integrity checks and aggregation behavior

## Eval Layers Mapping
1. `L0` static/unit: all existing `tests/test_*.py`
2. `L1` per-agent evals: planned via `ops/scripts/run_agent_evals.py`
3. `L2` integration evals: planned multi-agent fixture runs
4. `L3` end-to-end evals: `ops/scripts/run_conversation_eval.py`
5. `L4` drift monitoring: planned weekly trend checks

## Planned Test Additions

### Unit Tests (Phase 1 — DONE in `test_agentic_phase1.py`)
1. [x] Turn schema tests for `mode_preference`, `target_garment_type`, `autonomy_level`, `size_overrides`.
2. [x] Turn response schema tests for `resolved_mode`, `complete_the_look_offer`, `style_constraints_applied`, `profile_fields_used`.
3. [x] Mode router classification tests (garment-specific vs broad-intent).
4. [x] Checkout-prep status transition tests (`pending -> ready|needs_user_action|failed`).
5. [x] Checkout-prep API endpoint tests.

### Unit Tests (Phase 2+ — pending)
1. [ ] Profile merge precedence and size override tests (last-write-wins).
2. [ ] Style sub-agent contract tests (complete-the-look output shape, combo metadata).
3. [ ] Budget substitution and guardrail tests.

### Integration Tests (pending)
1. [ ] `conversation create -> turn -> recommendation -> checkout/prepare` happy path.
2. [ ] Garment mode with follow-up complete-the-look bundle.
3. [ ] Outfit mode default with combo competition.
4. [ ] Missing size -> clarification branch -> resumed recommendation.
5. [ ] Stock/price drift at checkout prep with fallback substitutions.
6. [ ] Policy block on any purchase-placement attempt.

### Per-Agent Eval Runner Tests
1. Suite load and case dispatch.
2. Threshold gate enforcement.
3. Gate semantics (pass/warning/fail/fail_integrity).
4. Artifact integrity output contract.

### E2E Eval Tests
1. Run existing conversation suite with `complete_only`.
2. Run again with `complete_plus_combos`.
3. Compare score deltas and integrity pass rate.

## Latest Validation Snapshot
1. Full suite command: `python3 -m unittest discover -s tests -p 'test_*.py'`
2. Pre-Phase-1 baseline: `93 passed, 0 failed`.
3. Post-Phase-1 baseline: `137 passed, 0 failed` (44 new tests in `test_agentic_phase1.py`).
4. Post-Phase-2 baseline: `166 passed, 0 failed` (29 new tests in `test_agentic_phase2.py`).
5. Post-Phase-3/4 baseline: `182 passed, 0 failed` (16 new tests in `test_agentic_phase3_4.py`).
6. Post-Phase-5 baseline: `211 passed, 0 failed` (29 new tests in `test_agentic_phase5.py`).
7. Post-Phase-6 baseline: `239 passed, 0 failed` (28 new tests in `test_agentic_phase6.py`).
8. Post-Phase-7 baseline: `266 passed, 0 failed` (27 new tests in `test_agentic_phase7.py`).
