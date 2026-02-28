# Tier 1 Filtering (Catalog + Policy Hard Constraints)

Last updated: February 28, 2026

## Purpose
Tier 1 defines hard-filtering and policy gating before Tier 2 scoring.

## Inputs
1. Resolved context (`occasion`, `archetype`, `gender`, `age`).
2. Profile constraints (sizes, blocked styles, comfort constraints).
3. Runtime filter profile (`rl_ready_minimal` or `legacy`).
4. Mode context (`resolved_mode` garment or outfit).

## Hard Filter Stages
1. Inventory compatibility.
2. Price range constraints.
3. Occasion compatibility.
4. Gender compatibility.
5. Policy safety exclusions.
6. Optional archetype and age constraints depending on filter profile.

## Policy Gating
Policy gating uses intent policy rules configured in:
1. `modules/style_engine/configs/config/intent_policy_v1.json`

Behavior:
1. Resolve active policy from request text and context.
2. Apply hard constraints.
3. Relax by stage only if candidate thresholds are not met.
4. Record active/relaxed stage in telemetry.

## Mode-Sensitive Constraints
1. In `garment` mode:
- prioritize requested category/subtype coverage.
- allow complete-the-look follow-up suggestions.

2. In `outfit` mode:
- allow complete singles and valid combos to compete.

3. In `complete_only` result filter:
- disallow combo rows.
- enforce complete-single integrity.
- block standalone outerwear unless explicitly requested.

## Safety and Guardrail Exclusions
Safety exclusions come from reinforcement framework config:
1. blocked categories (for example innerwear classes).
2. blocked subtypes.
3. blocked keyword patterns.

## Outputs
1. Passed candidate rows.
2. Failed row logs with failure reasons.
3. Policy metadata for downstream scoring and tracing.

## Telemetry Expectations
Tier 1 traces must include:
1. filter profile used.
2. policy id and keyword hits.
3. whether hard filter was relaxed.
4. relaxation stage.
5. counts: total, passed, failed.
