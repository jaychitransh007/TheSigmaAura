# Test Suite

Last updated: March 13, 2026

Primary context docs:
- `docs/CURRENT_STATE.md`
- `docs/APPLICATION_SPECS.md`

Canonical test-suite documentation is maintained here:
- `docs/TEST_SUITE.md`

Recommended context-loading order for future work:
1. `docs/CURRENT_STATE.md`
2. `docs/APPLICATION_SPECS.md`
3. `docs/fashion-ai-architecture.jsx`

## Running Tests

Run all tests (266 tests):
```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Run the focused agentic application eval harness:
```bash
python3 ops/scripts/run_agentic_eval.py
```

Include the live HTTP smoke flow:
```bash
USER_ID=your_completed_user_id python3 ops/scripts/run_agentic_eval.py --smoke
```

Run a specific test module:
```bash
python3 -m unittest tests.test_agentic_application -v
```

## Test File Inventory

| File | Coverage Area |
|---|---|
| `tests/test_agentic_application.py` | Core pipeline: orchestrator, planner, evaluator, assembler, formatter, context builders, filters, conversation memory, follow-up intents, filter relaxation, recommendation summaries |
| `tests/test_agentic_application_api_ui.py` | API routes, async turn jobs, UI rendering, conversation lifecycle, error handling |
| `tests/test_onboarding.py` | OTP flow, profile persistence, image upload, analysis pipeline, style preference, rerun support |
| `tests/test_onboarding_interpreter.py` | Deterministic interpretation derivation: seasonal color groups, height categories, waist bands, contrast levels, frame structures |
| `tests/test_catalog_retrieval.py` | Embedding document builder, vector store operations, similarity search, filter application, confidence policy |
| `tests/test_batch_builder.py` | Catalog enrichment batch processing |
| `tests/test_platform_core.py` | SupabaseRestClient, ConversationRepository, config loading |
| `tests/test_user_profiler.py` | User profiler utilities |
| `tests/test_config_and_schema.py` | Configuration validation, schema consistency |
| `tests/test_architecture_boundaries.py` | Module boundary enforcement, import validation |

## Key Test Coverage Areas

### Application pipeline
- Planner deterministic fallback (complete_only, paired_only, mixed)
- Evaluator fallback to assembly_score ranking on LLM failure
- Evaluator hard output cap (max 5 recommendations)
- Follow-up intents: increase_boldness, decrease_formality, increase_formality, change_color, full_alternative, more_options, similar_to_previous
- Filter relaxation: no relaxation → drop occasion_fit → drop occasion_fit + formality_level
- Assembly compatibility: formality, color temperature, occasion, pattern, volume checks
- Response formatter output bounds (max 5 outfits)
- Conversation memory build/apply cycle

### Onboarding
- 4-agent analysis with mock LLM responses
- Interpretation derivation across all 12 seasonal color groups
- Style archetype selection and persistence
- Single-agent rerun with baseline preservation

### Catalog
- Embedding document structure (8 labeled sections)
- Confidence-aware value rendering
- Row status filtering (only ok/complete embeddable)
- Filter column normalization

### Architecture
- No direct cross-boundary imports between application and onboarding/catalog internals
- Gateway pattern enforcement
