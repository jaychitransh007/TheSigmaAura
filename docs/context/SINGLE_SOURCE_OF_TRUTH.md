# Single Source of Truth (Code-Accurate)

Last reconciled: February 28, 2026

This is the only authoritative context document for this project.

## 1) Project Purpose
- Enrich a catalog CSV with garment attributes and per-attribute confidence using OpenAI Batch API (`/v1/responses`) and `gpt-5-mini`.
- Infer user profile/context from user image + natural-language intent using two standard real-time OpenAI Responses API calls.

## 2) Current Folder Layout
- Context doc: `docs/context/SINGLE_SOURCE_OF_TRUTH.md`
- Central config directory: `modules/style_engine/configs/config/`
  - `modules/style_engine/configs/config/garment_attributes.json` (all garment enum + text attributes)
  - `modules/style_engine/configs/config/body_harmony_attributes.json` (all body-harmony enums)
  - `modules/style_engine/configs/config/user_context_attributes.json` (occasion/archetype/gender/age enums + aliases + Tier 1 filter order)
  - `modules/style_engine/configs/config/tier1_ranked_attributes.json` (Tier 1 context-to-garment ranked filter attributes)
  - `modules/style_engine/configs/config/tier2_ranked_attributes.json` (Tier 2 body-harmony ranking order + body↔garment ranked mapping)
  - `modules/style_engine/configs/config/outfit_assembly_v1.json` (outfit candidate generation + pair-bonus rules + mode detection keywords)
  - `modules/style_engine/configs/config/intent_policy_v1.json` (intent-triggered policy tiers, staged relaxation plan, ranking priors)
  - `modules/style_engine/configs/config/reinforcement_framework_v1.json` (reward policy, RL-ready hard filter profile, telemetry contract)
- Source JSON catalogs: `modules/catalog_enrichment/stores/json_files/`
- Processed per-store CSV outputs: `modules/catalog_enrichment/stores/processed_csv_files/`
- Main sample input CSV: `modules/catalog_enrichment/stores/processed_sample_catalog.csv`
- Batch/runtime artifacts: `data/logs/`

## 3) Runtime Entry Points
- Main launcher: `run_catalog_enrichment.py`
- Pipeline CLI: `modules/catalog_enrichment/src/catalog_enrichment/main.py`
- Store JSON flattener: `modules/catalog_enrichment/stores/json_files/json_to_dataframe.py`
- Per-store processed CSV generator: `save_file.py`
- Schema audit CLI: `ops/scripts/schema_audit.py`
- Tier A outfit filter CLI: `ops/scripts/filter_outfits.py`
- Tier 2 ranking CLI: `ops/scripts/rank_outfits.py`
- Outfit candidate builder: `modules/style_engine/src/style_engine/outfit_engine.py`
- End-to-end styling runbook CLI: `run_style_pipeline.py`
- Outcome event logger CLI: `ops/scripts/log_styling_outcome.py`
- User profile inference CLI: `run_user_profiler.py`
- User profile module: `modules/user_profiler/src/user_profiler/main.py`
- Conversation platform API CLI: `run_conversation_platform.py`
- Conversation platform module: `modules/conversation_platform/src/conversation_platform/`
- Conversation eval runner CLI: `ops/scripts/run_conversation_eval.py`

## 3A) Config-First Runtime Contract
- Runtime behavior must be managed from `modules/style_engine/configs/config/` files first; code should consume config.
- Do not hardcode enums/aliases/ranked mappings in code when config exists.
- Current runtime loaders:
  - `modules/catalog_enrichment/src/catalog_enrichment/config_registry.py`
  - `modules/catalog_enrichment/src/catalog_enrichment/attributes.py` (loads garment schema attrs from config)
  - `modules/style_engine/src/style_engine/filters.py` (loads user context aliases + relaxable filters + Tier 1 ranked mapping from config)
  - `modules/style_engine/src/style_engine/ranker.py` (loads Tier 2 ranking order/mappings from config)
  - `modules/style_engine/src/style_engine/outfit_engine.py` (loads outfit assembly config and resolves auto/outfit/garment recommendation mode)
  - `modules/style_engine/src/style_engine/intent_policy.py` (resolves active intent policy and applies policy filters + ranking priors)

## 4) Input Contract (Enrichment Pipeline)
- Mandatory columns (validated): `description`, `images__0__src`, `images__1__src`
- Optional but used in prompt context when present: `store`, `url`

Source of truth: `modules/catalog_enrichment/src/catalog_enrichment/config.py`, `modules/catalog_enrichment/src/catalog_enrichment/csv_io.py`, `modules/catalog_enrichment/src/catalog_enrichment/batch_builder.py`

## 5) Attribute Contract
- Total attributes in current code: 46
- Enum attributes: 44
- Text attributes: 2 (`PrimaryColor`, `SecondaryColor`)
- For each attribute `X`, output includes `X` and `X_confidence` with confidence in `[0,1]`.

Source of truth: `modules/style_engine/configs/config/garment_attributes.json`, `modules/catalog_enrichment/src/catalog_enrichment/attributes.py`, `modules/catalog_enrichment/src/catalog_enrichment/schema_builder.py`

Body harmony profile attribute enums are centrally defined in:
- `modules/style_engine/configs/config/body_harmony_attributes.json`

## 6) Prompt and Model Parameters
- System prompt is externalized at `modules/catalog_enrichment/src/catalog_enrichment/prompts/system_prompt.txt`.
- Prompt includes drift-priority micro-definitions, tie-break rules, and cross-field consistency rules.
- Model is fixed in config as `gpt-5-mini`.
- Batch requests do not send `temperature` or `top_p`.

Source of truth: `modules/catalog_enrichment/src/catalog_enrichment/prompts/system_prompt.txt`, `modules/catalog_enrichment/src/catalog_enrichment/config.py`, `modules/catalog_enrichment/src/catalog_enrichment/batch_builder.py`

## 7) Schema Audit Behavior
- Audit engine: `modules/catalog_enrichment/src/catalog_enrichment/audit.py`
- Pipeline integration:
  - Automatically runs for `prepare`, `run_batch`, and `all` unless `--skip-audit` is passed.
  - Writes `data/logs/schema_audit.json`.
  - Pipeline fails only when audit `status = fail` (errors present).
- Standalone CLI:
  - `python3 ops/scripts/schema_audit.py --out data/logs/schema_audit.json`
  - `--strict` exits non-zero when warnings exist.
- Audit report includes:
  - enum integrity checks
  - prompt coverage checks
  - overlap diff report for paired families:
    - `SilhouetteContour` vs `SilhouetteType`
    - `FitEase` vs `FitType`
    - `VerticalWeightBias` vs `VisualWeightPlacement`

## 7A) Tier A Styling Filters
- Rules file: `modules/style_engine/src/style_engine/tier_a_filters_v1.json`
- Engine: `modules/style_engine/src/style_engine/filters.py`
- Context enums/aliases and relaxable filters are loaded from `modules/style_engine/configs/config/user_context_attributes.json`.
- Ranked context attribute order is loaded from `modules/style_engine/configs/config/tier1_ranked_attributes.json`.
- Hard filters applied in order:
  1. Price range (`2000-5000`)
  2. Occasion
  3. Archetype
  4. Gender (via `GenderExpression`)
  5. Age band
- Relaxation mode:
  - `--relax` can disable one or more hard filters among `price`, `age`, `archetype`, `occasion_archetype`.
  - Supports repeated or comma-separated values.
  - Examples: `--relax age`, `--relax age,archetype`, `--relax occasion_archetype`, `--relax age --relax price`.
  - Invalid relax names raise an explicit error.
- Occasion-archetype compatibility:
  - Rules are defined in `occasion_archetype_compatibility` inside `modules/style_engine/src/style_engine/tier_a_filters_v1.json`.
  - In strict mode, incompatible occasion/archetype combinations are hard-rejected.
- CLI usage:
  - `python3 ops/scripts/filter_outfits.py --occasion "Work Mode" --archetype "Classic" --gender Female --age 25-30 --input data/catalog/enriched_catalog.csv --output data/logs/filtered_outfits.csv --fail-log data/logs/filtered_outfits_failures.json`
  - `python3 ops/scripts/filter_outfits.py --occasion "Work Mode" --archetype "Classic" --gender Female --age 25-30 --relax age,archetype --input data/catalog/enriched_catalog.csv --output data/logs/filtered_outfits_relaxed.csv --fail-log data/logs/filtered_outfits_relaxed_failures.json`

RL-ready minimal hard filter profile:
- Used in `run_style_pipeline.py --hard-filter-profile rl_ready_minimal`
- Enforced constraints:
  1. inventory (currently placeholder pass-through; `_is_in_stock()` always returns true)
  2. price range (`2000-5000`)
  3. occasion compatibility
  4. gender compatibility
  5. policy/safety exclusions (innerwear/sexywear patterns)
- Source of truth:
  - `modules/style_engine/configs/config/reinforcement_framework_v1.json`

## 7B) Tier 2 Ranking (Body Harmony Scoring)
- Rules file: `modules/style_engine/src/style_engine/tier2_rules_v1.json`
- Engine: `modules/style_engine/src/style_engine/ranker.py`
- Outfit candidate composition engine: `modules/style_engine/src/style_engine/outfit_engine.py`
- Ranked body-harmony order and body→garment priority mapping are loaded from `modules/style_engine/configs/config/tier2_ranked_attributes.json`.
- Formula:
  - `sum(W_bh(a) * sum(W_ga(a,g) * match(a,g) * conf(g))) * confidence_multiplier + color_delta`
- `W_bh` supports scalable ranked-decay weighting via `modules/style_engine/configs/config/tier2_ranked_attributes.json` (`bh_weighting`).
- `W_ga` ordering comes from `body_to_garment_priority_order` in `modules/style_engine/configs/config/tier2_ranked_attributes.json`, with decay formula:
  - `W_ga_i = r^i / Σ(r^k)`
- Match scale:
  - Preferred = `1.0`
  - Acceptable = `0.5`
  - Not Permitted = `-0.25` (penalty, not auto-exclude in Tier 2)
  - Unlisted = `0`
- Conflict engine:
  - preferred intersection
  - acceptable fallback
  - priority override
  - not_permitted union on each garment attribute
- Explainability contract:
  - CSV fields: `tier2_raw_score`, `tier2_confidence_multiplier`, `tier2_color_delta`, `tier2_final_score`, `tier2_max_score`, `tier2_compatibility_confidence`, `tier2_flags`, `tier2_reasons`, `tier2_penalties`
  - JSON sections: `conflict_engine`, `top_positive_contributions`, `top_negative_contributions`, `formula`
- CLI usage:
  - `python3 ops/scripts/rank_outfits.py --input data/logs/filtered_outfits.csv --profile data/logs/user_style_profile.json --recommendation-mode auto --request-text "I need a complete office look" --output data/logs/ranked_outfits.csv --explain data/logs/ranked_outfits_explainability.json`
  - `python3 ops/scripts/rank_outfits.py --input data/logs/filtered_outfits.csv --profile data/logs/user_style_profile.json --tier2-strictness safe --recommendation-mode garment --request-text "show me shirts" --output data/logs/ranked_outfits_safe.csv --explain data/logs/ranked_outfits_safe_explainability.json`
- Strictness switch:
  - `--tier2-strictness balanced` (default): baseline behavior
  - `--tier2-strictness safe`: stronger penalties, more conservative ranking
  - `--tier2-strictness bold`: lighter penalties, stronger standout boosts

Outfit-level behavior:
- `recommendation_mode=auto`: if request text mentions a category/subtype (shirt, dress, jeans, etc.) it resolves to `garment`; otherwise it resolves to `outfit`.
- `recommendation_mode=outfit`: complete-garment singles compete against top+bottom combo candidates.
- Combo scoring: `((top_score + bottom_score) / 2) + pair_bonus`, where `pair_bonus` is config-driven and bounded.
- Pair bonus signals currently include occasion fit coherence, formality distance, color temperature compatibility, pattern balance, embellishment clash, and oversized-silhouette clash.
- `complete_only` runtime behavior:
  - combos are disabled (`include_combos=false`)
  - incomplete rows (`StylingCompleteness=needs_bottomwear|needs_topwear`) are excluded from complete singles
  - standalone outerwear rows are excluded unless explicitly requested in user text (coat/blazer/jacket)

Intent policy overlay (conversation runtime):
- Policy config: `modules/style_engine/configs/config/intent_policy_v1.json`
- Current production policy: `high_stakes_work` for work-mode high-stakes prompts (presentation/interview/client-facing cues).
- Stage-based enforcement:
  1. `strict`
  2. `style_relaxed`
  3. `formality_relaxed`
  4. `smart_casual_limited`
- If no stage satisfies minimum quality thresholds, policy hard filtering is relaxed off.
- Policy priors are appended to explainability reasons as `high_stakes_work:*`.

## 7C) User Profile Inference Module
- Module path: `modules/user_profiler/src/user_profiler/`
- Entry point: `run_user_profiler.py`
- Flow:
  1. Visual reasoning call on uploaded image
  2. Textual reasoning call on natural-language user context
- Models:
  - visual: `gpt-5.2` with `reasoning.effort=high`
  - textual: `gpt-5-mini`
- API mode:
  - standard real-time Responses API (`client.responses.create`)
  - not Batch API
- Visual output attributes:
  - body harmony: `HeightCategory`, `BodyShape`, `VisualWeight`, `VerticalProportion`, `ArmVolume`, `MidsectionState`, `WaistVisibility`, `BustVolume`, `SkinUndertone`, `SkinSurfaceColor`, `SkinContrast`, `FaceShape`, `NeckLength`, `HairLength`, `HairColor`
  - context: `gender`, `age`
- Textual output attributes:
  - `occasion`, `archetype`
- Output files (default):
  - `data/logs/user_profile_inference.json`
  - `data/logs/user_style_profile.json` (ready for `run_style_pipeline.py --profile`)
  - `data/logs/user_style_context.json` (occasion/archetype/gender/age)
  - `data/logs/user_profiler/input_*.{ext}` (stored uploaded image artifact)
  - per-call request/response logs and visual reasoning notes are embedded in `user_profile_inference.json`
- Prompts:
  - `modules/user_profiler/src/user_profiler/prompts/visual_prompt.txt`
  - `modules/user_profiler/src/user_profiler/prompts/textual_prompt.txt`
- Schemas:
  - `modules/user_profiler/src/user_profiler/schemas.py`
- CLI:
  - `python3 run_user_profiler.py --image /absolute/path/to/user.jpg --context-text "I need office and dinner looks"`

## 7D) Conversation Platform Module
- Module path: `modules/conversation_platform/src/conversation_platform/`
- Entry point: `run_conversation_platform.py`
- Local persistence: Supabase PostgREST via `modules/conversation_platform/src/conversation_platform/supabase_rest.py`
- Orchestration:
  - `modules/conversation_platform/src/conversation_platform/orchestrator.py`
  - runs visual/text inference + memory merge + recommendation + telemetry logging
- API endpoints:
  - `GET /healthz`
  - `GET /` (browser conversational interface)
  - `POST /v1/conversations`
  - `GET /v1/conversations/{conversation_id}`
  - `POST /v1/conversations/{conversation_id}/turns`
  - `POST /v1/conversations/{conversation_id}/turns/start`
  - `GET /v1/conversations/{conversation_id}/turns/{job_id}/status`
  - `GET /v1/recommendations/{run_id}`
  - `POST /v1/feedback`
- Browser UX includes:
  - live stage panel using async turn status polling
  - recommendation cards with `Dislike`, `Like`, `Share`, `Buy Now` feedback actions
  - two-row action layout (row 1 full-width buy; row 2 dislike/like/share)
  - result filter toggle: `complete_only` vs `complete_plus_combos`
- Supabase schema migration:
  - `supabase/migrations/20260224160000_conversation_platform.sql`
  - `supabase/migrations/20260224170500_feedback_events_event_type_v2.sql`
- Service-level blueprint:
  - `docs/context/CONVERSATION_SERVICE_BLUEPRINT.md`
- Runbook:
  - `ops/runbooks/CONVERSATION_PLATFORM_RUNBOOK.md`

## 7E) Conversation Evaluation System
- Prompt suite:
  - `ops/evals/conversation_prompt_suite_diverse_v1.json`
- Rubric:
  - `ops/evals/conversation_eval_rubric_v1.json`
- Runner:
  - `ops/scripts/run_conversation_eval.py`
- Runbook:
  - `ops/runbooks/CONVERSATION_EVAL_RUNBOOK.md`

Run output contract:
- `data/logs/evals/<run_id>/run_manifest.json`
- `data/logs/evals/<run_id>/case_inputs.jsonl`
- `data/logs/evals/<run_id>/case_outputs.jsonl`
- `data/logs/evals/<run_id>/case_scores.jsonl`
- `data/logs/evals/<run_id>/case_scores.csv`
- `data/logs/evals/<run_id>/summary.json`
- `data/logs/evals/<run_id>/summary.md`
- `data/logs/evals/<run_id>/artifact_integrity.json`

Per-case integrity checks:
- `turn_id` present
- `recommendation_run_id` present
- recommendation retrievable via `GET /v1/recommendations/{run_id}`
- non-empty recommendation list

## 8) Batch Pipeline Behavior
1. Read CSV and validate headers.
2. Run schema audit (unless skipped).
3. Build `data/logs/batch_input.jsonl` with one request per row (`custom_id=row_{idx}`).
4. Upload JSONL as `purpose=batch`.
5. Create batch job on `/v1/responses`.
6. Poll until terminal status.
7. Download output/error files if present.
8. Parse by `custom_id`.
9. Merge model fields into original rows.
10. Write enriched CSV and `data/logs/run_report.json`.
11. If rows fail, write `data/logs/retry_batch_input.jsonl`.

Result expectation:
- `data/catalog/enriched_catalog.csv` always contains all schema-defined attribute columns and confidence columns.
- Individual attribute values may be null/blank when the model is uncertain.
- Use a fresh `--out-dir` per run (or clear old batch artifacts) to avoid stale-output merges.

Source of truth: `modules/catalog_enrichment/src/catalog_enrichment/main.py`, `modules/catalog_enrichment/src/catalog_enrichment/batch_runner.py`, `modules/catalog_enrichment/src/catalog_enrichment/response_parser.py`, `modules/catalog_enrichment/src/catalog_enrichment/merge_writer.py`, `modules/catalog_enrichment/src/catalog_enrichment/quality.py`

## 9) Image URL Normalization
- Batch builder rewrites image URLs to enforce `width=768`.

Source of truth: `modules/catalog_enrichment/src/catalog_enrichment/batch_builder.py`

## 10) CLI Behavior
- `run_catalog_enrichment.py` is a thin passthrough to `catalog_enrichment.main.run()`.
- Required CLI args are defined in `modules/catalog_enrichment/src/catalog_enrichment/main.py`.
- `modules/catalog_enrichment/src/catalog_enrichment/main.py` defaults:
  - `--mode prepare`
  - `--out-dir out`
  - `--num-products 5` (safety limit), `all` supported
- Large-catalog automation:
  - `--auto-chunk` performs full chunked orchestration for `--mode all`
  - `--max-batch-bytes` controls per-chunk JSONL cap (default `180000000`)
  - chunk outputs/metadata are written under `<out-dir>/chunk_runs/` plus `<out-dir>/chunk_manifest.json`
  - when org limits occur (`enqueued token` or `billing_hard_limit_reached`), pipeline checkpoints progress and can resume from:
    - `<out-dir>/auto_chunk_checkpoint.json`
    - `<out-dir>/partial_enriched.csv`
    - `<out-dir>/pending_chunks/pending_chunk_*.csv`
- No default input catalog is injected by `run_catalog_enrichment.py`; pass `--input` explicitly.

## 11) Example Commands
```bash
python3 ops/scripts/schema_audit.py --out data/logs/schema_audit.json
python3 ops/scripts/schema_audit.py --out data/logs/schema_audit.json --strict
python3 run_catalog_enrichment.py --input modules/catalog_enrichment/stores/processed_sample_catalog.csv --output data/catalog/enriched_catalog.csv --mode all --out-dir data/logs
python3 run_catalog_enrichment.py --input new_catalog.csv --output data/catalog/enriched_catalog.csv --mode all --out-dir data/logs --auto-chunk --max-batch-bytes 180000000 --num-products all
python3 run_catalog_enrichment.py --input modules/catalog_enrichment/stores/processed_sample_catalog.csv --output data/catalog/enriched_catalog.csv --mode run_batch --out-dir data/logs
python3 run_catalog_enrichment.py --input modules/catalog_enrichment/stores/processed_sample_catalog.csv --output data/catalog/enriched_catalog.csv --mode merge --out-dir data/logs --batch-output-jsonl data/logs/batch_output.jsonl
python3 ops/scripts/rank_outfits.py --input data/logs/filtered_outfits.csv --profile data/logs/user_style_profile.json --recommendation-mode auto --request-text "Need complete office looks" --output data/logs/ranked_outfits.csv --explain data/logs/ranked_outfits_explainability.json
python3 run_style_pipeline.py --input data/catalog/enriched_catalog.csv --profile data/logs/user_style_profile.json --occasion "Work Mode" --archetype "Classic" --gender Female --age 25-30 --tier2-strictness balanced --recommendation-mode auto --request-text "Need complete office looks" --out-dir data/logs --prefix demo_outfit
python3 run_user_profiler.py --image /absolute/path/to/user.jpg --context-text "I need office and dinner looks"
python3 run_conversation_platform.py --host 127.0.0.1 --port 8010
python3 ops/scripts/run_conversation_eval.py --base-url http://127.0.0.1:8010 --strictness balanced --hard-filter-profile rl_ready_minimal --max-results 3 --result-filter complete_only --image-ref data/logs/user_profiler/input_09322a34663f.webp --out-dir data/logs/evals --fail-on-integrity
```

## 12) Test Suite
- Master test doc: `docs/context/test_suite.md`
- Test runner: `python3 -m unittest discover -s tests -v`
- Test modules:
  - `tests/test_config_and_schema.py`
  - `tests/test_batch_builder.py`
  - `tests/test_tier1_filters.py`
  - `tests/test_tier2_ranker.py`
  - `tests/test_outfit_engine.py`
  - `tests/test_intent_policy.py`
  - `tests/test_user_profiler.py`
  - `tests/test_conversation_platform.py`
  - `tests/test_conversation_orchestrator.py`
  - `tests/test_conversation_api_ui.py`
  - `tests/test_conversation_eval.py`

## 13) End-to-End Styling Runbook
- Runbook doc: `ops/runbooks/STYLING_PIPELINE_RUNBOOK.md`
- Single-command runner:
  - `python3 run_style_pipeline.py --input data/catalog/enriched_catalog.csv --profile data/logs/user_style_profile.json --occasion "Night Out" --archetype "Glamorous" --gender Female --age 25-30 --tier2-strictness balanced --out-dir data/logs --prefix nightout_glamorous_female_25_30`
- Final ranked list for downstream UI/review:
  - `data/logs/<prefix>_ranked_summary.csv`
  - Includes ranked `title`, both image URLs, and scores.
- RL-ready logs produced per run:
  - `data/logs/<prefix>_request_log.json`
  - `data/logs/<prefix>_candidate_set_log.csv`
  - `data/logs/<prefix>_impression_log.csv`
  - `data/logs/<prefix>_outcome_event_log_template.csv`
- User outcome logging:
  - `python3 ops/scripts/log_styling_outcome.py --log-file <path> --request-id <id> --session-id <id> --user-id <id> --garment-id <id> --event-type like|share|buy|skip`
- Reward policy:
  - `dislike:-5`, `like:+2`, `share:+10`, `buy:+20`, `no_action:-1`, `skip:-1` from `modules/style_engine/configs/config/reinforcement_framework_v1.json`
- Error handling:
  - input/validation issues are shown as one-line `error: ...` messages
  - no traceback for expected user-input mistakes
  - exits with code `2` on handled input/config errors
