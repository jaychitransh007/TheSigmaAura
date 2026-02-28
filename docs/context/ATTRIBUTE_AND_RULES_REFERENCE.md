# Attribute and Rules Reference (Config Contract Only)

Last updated: February 28, 2026

## Purpose
This file is a config contract reference only. It defines where schema and rule configuration lives and how code should consume it.

## Canonical Config Files
1. Garment attribute schema:
- `modules/style_engine/configs/config/garment_attributes.json`

2. Body harmony attribute schema:
- `modules/style_engine/configs/config/body_harmony_attributes.json`

3. User context dimensions and aliases:
- `modules/style_engine/configs/config/user_context_attributes.json`

4. Tier 1 ranked attribute order:
- `modules/style_engine/configs/config/tier1_ranked_attributes.json`

5. Tier 2 ranked attribute order and mappings:
- `modules/style_engine/configs/config/tier2_ranked_attributes.json`

6. Outfit assembly and mode keyword rules:
- `modules/style_engine/configs/config/outfit_assembly_v1.json`

7. Intent policy config:
- `modules/style_engine/configs/config/intent_policy_v1.json`

8. Reinforcement framework and reward contract:
- `modules/style_engine/configs/config/reinforcement_framework_v1.json`

## Loader References
1. `modules/catalog_enrichment/src/catalog_enrichment/config_registry.py`
2. `modules/style_engine/src/style_engine/filters.py`
3. `modules/style_engine/src/style_engine/ranker.py`
4. `modules/style_engine/src/style_engine/outfit_engine.py`
5. `modules/style_engine/src/style_engine/intent_policy.py`
6. `modules/user_profiler/src/user_profiler/schemas.py`

## Contract Rules
1. Runtime behavior must be config-first.
2. Code must not hardcode enum vocabularies that already exist in config.
3. Config edits must include tests for parser/load behavior and downstream usage.
4. Any config version bump must be documented in context and eval artifacts.

## Validation Checklist
1. JSON parses successfully.
2. Enums are internally consistent.
3. Ranked mappings reference valid attributes.
4. Policy and reward keys align with runtime contracts.
