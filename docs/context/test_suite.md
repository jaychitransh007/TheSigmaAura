# Test Suite

Last run: February 22, 2026

## Scope
- Config-driven contracts
- Schema integrity
- Batch request builder behavior
- Tier 1 filtering behavior (including relaxations)
- Tier 2 ranking/scoring behavior and explainability contract

## How To Run
```bash
python3 -m unittest discover -s tests -v
```

## Test Files
- `tests/test_config_and_schema.py`
- `tests/test_batch_builder.py`
- `tests/test_tier1_filters.py`
- `tests/test_tier2_ranker.py`

## Case Matrix

### Config + Schema
- `test_garment_config_counts_match_context_contract`
- `test_attributes_module_is_config_backed`
- `test_schema_contains_value_and_confidence_for_all_attributes`
- `test_user_context_config_has_expected_dimensions`
- `test_body_harmony_config_has_all_attributes`
- `test_ranked_configs_reference_valid_garment_attributes`
- `test_context_file_exists`
- `test_garment_config_file_is_valid_json`

### Batch Builder
- `test_normalize_image_url_adds_width`
- `test_normalize_image_url_overrides_existing_width`
- `test_build_request_body_uses_model_and_prompt_and_images`

### Tier 1
- `test_parse_relax_filters_valid`
- `test_parse_relax_filters_invalid_raises`
- `test_parse_relax_filters_trims_and_dedupes`
- `test_invalid_archetype_shows_occasion_hint`
- `test_invalid_occasion_shows_archetype_hint`
- `test_strict_filter_passes_matching_row`
- `test_price_failure_can_be_relaxed`
- `test_occasion_archetype_incompatibility_and_relaxation`
- `test_gender_filter_blocks_mismatch`
- `test_minimal_hard_filters_pass_base_row`
- `test_minimal_hard_filters_exclude_policy_safety`

### Tier 2
- `test_invalid_strictness_raises`
- `test_explainability_contract_fields_exist`
- `test_color_never_excludes_item`
- `test_higher_confidence_improves_score`
- `test_not_permitted_penalty_applies`
- `test_strictness_profiles_affect_ranking_score`
- `test_ranked_bh_weights_from_config_used`
- `test_color_loved_preference_boosts_score`
- `test_compatibility_confidence_is_bounded`

## Latest Run Report
- Total tests: `31`
- Passed: `31`
- Failed: `0`
- Result: `OK`

## Notes
- During implementation, one Tier 1 test initially failed due fixture setup; it was corrected so the case isolates `occasion_archetype` relaxation without conflicting archetype-rule failures.
