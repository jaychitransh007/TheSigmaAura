# Single Source of Truth (Code-Accurate)

Last reconciled: February 24, 2026

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
  - `modules/style_engine/configs/config/reinforcement_framework_v1.json` (reward policy, RL-ready hard filter profile, telemetry contract)
- Source JSON catalogs: `modules/catalog_enrichment/stores/json_files/`
- Processed per-store CSV outputs: `modules/catalog_enrichment/stores/processed_csv_files/`
- Main sample input CSV: `modules/catalog_enrichment/stores/processed_sample_catalog.csv`
- Batch/runtime artifacts: `data/output/`

## 3) Runtime Entry Points
- Main launcher: `run_catalog_enrichment.py`
- Pipeline CLI: `modules/catalog_enrichment/src/catalog_enrichment/main.py`
- Store JSON flattener: `modules/catalog_enrichment/stores/json_files/json_to_dataframe.py`
- Per-store processed CSV generator: `save_file.py`
- Schema audit CLI: `ops/scripts/schema_audit.py`
- Tier A outfit filter CLI: `ops/scripts/filter_outfits.py`
- Tier 2 ranking CLI: `ops/scripts/rank_outfits.py`
- End-to-end styling runbook CLI: `run_style_pipeline.py`
- Outcome event logger CLI: `ops/scripts/log_styling_outcome.py`
- User profile inference CLI: `run_user_profiler.py`
- User profile module: `modules/user_profiler/src/user_profiler/main.py`

## 3A) Config-First Runtime Contract
- Runtime behavior must be managed from `modules/style_engine/configs/config/` files first; code should consume config.
- Do not hardcode enums/aliases/ranked mappings in code when config exists.
- Current runtime loaders:
  - `modules/catalog_enrichment/src/catalog_enrichment/config_registry.py`
  - `modules/catalog_enrichment/src/catalog_enrichment/attributes.py` (loads garment schema attrs from config)
  - `modules/style_engine/src/style_engine/filters.py` (loads user context aliases + relaxable filters + Tier 1 ranked mapping from config)
  - `modules/style_engine/src/style_engine/ranker.py` (loads Tier 2 ranking order/mappings from config)

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
  - Writes `data/output/schema_audit.json`.
  - Pipeline fails only when audit `status = fail` (errors present).
- Standalone CLI:
  - `python3 ops/scripts/schema_audit.py --out data/output/schema_audit.json`
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
  - `python3 ops/scripts/filter_outfits.py --occasion "Work Mode" --archetype "Classic" --gender Female --age 25-30 --input data/output/enriched.csv --output data/output/filtered_outfits.csv --fail-log data/output/filtered_outfits_failures.json`
  - `python3 ops/scripts/filter_outfits.py --occasion "Work Mode" --archetype "Classic" --gender Female --age 25-30 --relax age,archetype --input data/output/enriched.csv --output data/output/filtered_outfits_relaxed.csv --fail-log data/output/filtered_outfits_relaxed_failures.json`

RL-ready minimal hard filter profile:
- Used in `run_style_pipeline.py --hard-filter-profile rl_ready_minimal`
- Enforced constraints:
  1. inventory
  2. price range (`2000-5000`)
  3. occasion compatibility
  4. gender compatibility
  5. policy/safety exclusions (innerwear/sexywear patterns)
- Source of truth:
  - `modules/style_engine/configs/config/reinforcement_framework_v1.json`

## 7B) Tier 2 Ranking (Body Harmony Scoring)
- Rules file: `modules/style_engine/src/style_engine/tier2_rules_v1.json`
- Engine: `modules/style_engine/src/style_engine/ranker.py`
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
  - `python3 ops/scripts/rank_outfits.py --input data/output/filtered_outfits.csv --profile data/output/sample_user_profile_tier2.json --output data/output/ranked_outfits.csv --explain data/output/ranked_outfits_explainability.json`
  - `python3 ops/scripts/rank_outfits.py --input data/output/filtered_outfits.csv --profile data/output/sample_user_profile_tier2.json --tier2-strictness safe --output data/output/ranked_outfits_safe.csv --explain data/output/ranked_outfits_safe_explainability.json`
- Strictness switch:
  - `--tier2-strictness balanced` (default): baseline behavior
  - `--tier2-strictness safe`: stronger penalties, more conservative ranking
  - `--tier2-strictness bold`: lighter penalties, stronger standout boosts

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
  - `data/output/user_profile_inference.json`
  - `data/output/user_style_profile.json` (ready for `run_style_pipeline.py --profile`)
  - `data/output/user_style_context.json` (occasion/archetype/gender/age)
  - `data/output/user_profiler/input_*.{ext}` (stored uploaded image artifact)
  - per-call request/response logs and visual reasoning notes are embedded in `user_profile_inference.json`
- Prompts:
  - `modules/user_profiler/src/user_profiler/prompts/visual_prompt.txt`
  - `modules/user_profiler/src/user_profiler/prompts/textual_prompt.txt`
- Schemas:
  - `modules/user_profiler/src/user_profiler/schemas.py`
- CLI:
  - `python3 run_user_profiler.py --image /absolute/path/to/user.jpg --context-text "I need office and dinner looks"`

## 8) Batch Pipeline Behavior
1. Read CSV and validate headers.
2. Run schema audit (unless skipped).
3. Build `data/output/batch_input.jsonl` with one request per row (`custom_id=row_{idx}`).
4. Upload JSONL as `purpose=batch`.
5. Create batch job on `/v1/responses`.
6. Poll until terminal status.
7. Download output/error files if present.
8. Parse by `custom_id`.
9. Merge model fields into original rows.
10. Write enriched CSV and `data/output/run_report.json`.
11. If rows fail, write `data/output/retry_batch_input.jsonl`.

Result expectation:
- `enriched.csv` always contains all schema-defined attribute columns and confidence columns.
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
  - `--out-dir data/output`
  - `--num-products 5` (safety limit), `all` supported
- No default input catalog is injected by `run_catalog_enrichment.py`; pass `--input` explicitly.

## 11) Example Commands
```bash
python3 ops/scripts/schema_audit.py --out data/output/schema_audit.json
python3 ops/scripts/schema_audit.py --out data/output/schema_audit.json --strict
python3 run_catalog_enrichment.py --input modules/catalog_enrichment/stores/processed_sample_catalog.csv --output data/output/enriched.csv --mode all --out-dir data/output
python3 run_catalog_enrichment.py --input modules/catalog_enrichment/stores/processed_sample_catalog.csv --output data/output/enriched.csv --mode run_batch --out-dir data/output
python3 run_catalog_enrichment.py --input modules/catalog_enrichment/stores/processed_sample_catalog.csv --output data/output/enriched.csv --mode merge --out-dir data/output --batch-output-jsonl data/output/batch_output.jsonl
```

## 12) Test Suite
- Master test doc: `test_suite.md`
- Test runner: `python3 -m unittest discover -s tests -v`
- Test modules:
  - `tests/test_config_and_schema.py`
  - `tests/test_batch_builder.py`
  - `tests/test_tier1_filters.py`
  - `tests/test_tier2_ranker.py`
  - `tests/test_user_profiler.py`

## 13) End-to-End Styling Runbook
- Runbook doc: `ops/runbooks/STYLING_PIPELINE_RUNBOOK.md`
- Single-command runner:
  - `python3 run_style_pipeline.py --input data/output/enriched.csv --profile data/output/sample_user_profile_tier2.json --occasion "Night Out" --archetype "Glamorous" --gender Female --age 25-30 --tier2-strictness balanced --out-dir data/output --prefix nightout_glamorous_female_25_30`
- Final ranked list for downstream UI/review:
  - `data/output/<prefix>_ranked_summary.csv`
  - Includes ranked `title`, both image URLs, and scores.
- RL-ready logs produced per run:
  - `data/output/<prefix>_request_log.json`
  - `data/output/<prefix>_candidate_set_log.csv`
  - `data/output/<prefix>_impression_log.csv`
  - `data/output/<prefix>_outcome_event_log_template.csv`
- User outcome logging:
  - `python3 ops/scripts/log_styling_outcome.py --log-file <path> --request-id <id> --session-id <id> --user-id <id> --garment-id <id> --event-type like|share|buy|skip`
- Reward policy:
  - `like:+5`, `share:+10`, `buy:+50`, `skip:-1` from `modules/style_engine/configs/config/reinforcement_framework_v1.json`
- Error handling:
  - input/validation issues are shown as one-line `error: ...` messages
  - no traceback for expected user-input mistakes
  - exits with code `2` on handled input/config errors
