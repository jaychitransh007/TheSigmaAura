# Single Source of Truth (Index + Governance)

Last updated: February 28, 2026

## Purpose
This file is a strict index and governance contract for `docs/context`. It does not carry deep architecture details. Detailed behavior belongs in module context files listed below.

## Allowed Architecture (Current Baseline)
The approved architecture is Agentic Fashion Commerce for this scope:
1. User intent to recommendations.
2. Single-garment or complete-look generation.
3. Cart build and checkout preparation.

The deterministic ranking foundation remains mandatory and config-driven from `modules/style_engine/configs/config/`.

## Success Criteria
1. User can reach checkout-ready cart in <=3 turns for common intents.
2. Mode routing accuracy (garment vs outfit) >=95% on eval suite.
3. Checkout-prep success rate >=98% when stock/price are valid.
4. No autonomous purchase actions without explicit user approval.

## Out of Scope (Current Baseline)
1. Standalone sizing-risk modeling agent.
2. Order placement and payment capture.
3. Post-order lifecycle workflows.

## Canonical Context Files
1. Overall agent architecture and interactions:
- `docs/context/CONVERSATION_AGENT_PLATFORM.md`
2. API/service contracts and runtime lifecycle:
- `docs/context/CONVERSATION_SERVICE_BLUEPRINT.md`
3. User Profile + Body Harmony module:
- `docs/context/USER_PROFILE_INFERENCE.md`
4. Catalog/policy hard filtering:
- `docs/context/TIER1_FILTERING.md`
5. Style ranking + complete-the-look:
- `docs/context/TIER2_RANKING.md`
6. Config contract reference only:
- `docs/context/ATTRIBUTE_AND_RULES_REFERENCE.md`
7. Eval strategy (per-agent + end-to-end):
- `docs/context/EVAL_IMPLEMENTATION_STRATEGY.md`
8. Implementation status checklist:
- `docs/context/AGENTIC_IMPLEMENTATION_CHECKLIST.md`
9. Test coverage map:
- `docs/context/test_suite.md`

## Drift Rule
Architecture details must appear only in module context files. If any architecture guidance conflicts with module files, module files are authoritative and this index must be updated in the same change.

## Documentation Change Rules
1. Keep this file short and index-only.
2. Do not duplicate API schemas or ranking formulas here.
3. Every architecture change must update:
- relevant module context file(s), and
- `docs/context/AGENTIC_IMPLEMENTATION_CHECKLIST.md`.
