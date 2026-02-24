# Test Suite

Last run: February 24, 2026

## Scope
- Config-driven contracts
- Schema integrity
- Batch request builder behavior
- Tier 1 filtering behavior (including relaxations)
- Tier 2 ranking/scoring behavior and explainability contract
- Outfit assembly behavior (mode resolution + combo candidate construction)
- User profile inference schemas and image-input normalization
- Conversation platform schemas, repository behavior, and orchestrator flow

## How To Run
```bash
python3 -m unittest discover -s tests -v
```

## Test Files
- `tests/test_config_and_schema.py`
- `tests/test_batch_builder.py`
- `tests/test_tier1_filters.py`
- `tests/test_tier2_ranker.py`
- `tests/test_outfit_engine.py`
- `tests/test_user_profiler.py`
- `tests/test_conversation_platform.py`
- `tests/test_conversation_orchestrator.py`
- `tests/test_conversation_api_ui.py`

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
- `test_outfit_assembly_config_exists_and_loads`

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

### Outfit Assembly
- `test_outfit_mode_returns_combo_candidates`
- `test_auto_mode_detects_garment_request`
- `test_auto_mode_without_garment_keywords_prefers_outfits`
- `test_combo_candidate_contains_component_metadata`
- `test_invalid_recommendation_mode_raises`
- `test_resolve_mode_detects_hyphenated_keyword`
- `test_garment_mode_falls_back_if_no_targeted_match`

### User Profiler
- `test_visual_schema_has_all_body_fields_plus_gender_age`
- `test_textual_schema_uses_context_enums`
- `test_image_to_input_url_supports_http`
- `test_image_to_input_url_supports_data_url`
- `test_image_to_input_url_supports_local_file`
- `test_visual_model_is_gpt_5_2_and_textual_is_gpt_5_mini`
- `test_store_image_artifact_for_data_url`
- `test_store_image_artifact_for_local_file`

### Conversation Platform
- `test_get_or_create_user_returns_existing`
- `test_get_or_create_user_creates_when_missing`
- `test_get_user_by_id`
- `test_insert_recommendation_items_persists_combo_metadata_payload`
- `test_get_conversation_state_includes_external_user_id`
- `test_process_turn_requests_clarification_without_first_image`
- `test_process_turn_requests_clarification_for_missing_text_context`
- `test_process_turn_happy_path_with_image`
- `test_get_recommendation_run_parses_combo_metadata`
- `test_memory_agent_merges_context`
- `test_stylist_agent_response_with_items`
- `test_stylist_agent_response_without_items`
- `test_stylist_agent_asks_refinement_on_low_confidence`
- `test_stylist_agent_asks_refinement_on_short_ambiguous_prompt`
- `test_telemetry_reward_mapping`
- `test_turn_request_defaults`
- `test_feedback_event_type_validation`
- `test_root_returns_html`
- `test_favicon_route_exists`
- `test_turn_job_start_and_status`
- `test_turn_job_start_and_status_failed`
- `test_feedback_endpoint_success`

## Latest Run Report
- Total tests: `70`
- Passed: `70`
- Failed: `0`
- Result: `OK`

## Notes
- During implementation, one Tier 1 test initially failed due fixture setup; it was corrected so the case isolates `occasion_archetype` relaxation without conflicting archetype-rule failures.
