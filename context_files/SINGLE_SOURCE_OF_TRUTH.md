# Single Source of Truth (Code-Accurate)

Last reconciled: February 22, 2026

This is the only authoritative context document for this project.

## 1) Project Purpose
- Enrich a catalog CSV with garment attributes and per-attribute confidence using OpenAI Batch API (`/v1/responses`) and `gpt-5-mini`.

## 2) Current Folder Layout
- Context doc: `context_files/SINGLE_SOURCE_OF_TRUTH.md`
- Central config directory: `config/`
  - `config/garment_attributes.json` (all garment enum + text attributes)
  - `config/body_harmony_attributes.json` (all body-harmony enums)
  - `config/user_context_attributes.json` (occasion/archetype/gender/age enums + aliases + Tier 1 filter order)
  - `config/tier1_ranked_attributes.json` (Tier 1 context-to-garment ranked filter attributes)
  - `config/tier2_ranked_attributes.json` (Tier 2 body-harmony ranking order + body↔garment ranked mapping)
- Source JSON catalogs: `stores/json_files/`
- Processed per-store CSV outputs: `stores/processed_csv_files/`
- Main sample input CSV: `stores/processed_sample_catalog.csv`
- Batch/runtime artifacts: `out/`

## 3) Runtime Entry Points
- Main launcher: `run_catalog_enrichment.py`
- Pipeline CLI: `catalog_enrichment/main.py`
- Store JSON flattener: `stores/json_files/json_to_dataframe.py`
- Per-store processed CSV generator: `save_file.py`
- Schema audit CLI: `scripts/schema_audit.py`
- Tier A outfit filter CLI: `scripts/filter_outfits.py`
- Tier 2 ranking CLI: `scripts/rank_outfits.py`
- End-to-end styling runbook CLI: `scripts/run_style_pipeline.py`

## 3A) Config-First Runtime Contract
- Runtime behavior must be managed from `config/` files first; code should consume config.
- Do not hardcode enums/aliases/ranked mappings in code when config exists.
- Current runtime loaders:
  - `catalog_enrichment/config_registry.py`
  - `catalog_enrichment/attributes.py` (loads garment schema attrs from config)
  - `catalog_enrichment/styling_filters.py` (loads user context aliases + relaxable filters + Tier 1 ranked mapping from config)
  - `catalog_enrichment/tier2_ranker.py` (loads Tier 2 ranking order/mappings from config)

## 4) Input Contract (Enrichment Pipeline)
- Mandatory columns (validated): `description`, `images__0__src`, `images__1__src`
- Optional but used in prompt context when present: `store`, `url`

Source of truth: `catalog_enrichment/config.py`, `catalog_enrichment/csv_io.py`, `catalog_enrichment/batch_builder.py`

## 5) Attribute Contract
- Total attributes in current code: 46
- Enum attributes: 44
- Text attributes: 2 (`PrimaryColor`, `SecondaryColor`)
- For each attribute `X`, output includes `X` and `X_confidence` with confidence in `[0,1]`.

Source of truth: `config/garment_attributes.json`, `catalog_enrichment/attributes.py`, `catalog_enrichment/schema_builder.py`

Body harmony profile attribute enums are centrally defined in:
- `config/body_harmony_attributes.json`

## 6) Prompt and Model Parameters
- System prompt is externalized at `catalog_enrichment/prompts/system_prompt.txt`.
- Prompt includes drift-priority micro-definitions, tie-break rules, and cross-field consistency rules.
- Model is fixed in config as `gpt-5-mini`.
- Batch requests do not send `temperature` or `top_p`.

Source of truth: `catalog_enrichment/prompts/system_prompt.txt`, `catalog_enrichment/config.py`, `catalog_enrichment/batch_builder.py`

## 7) Schema Audit Behavior
- Audit engine: `catalog_enrichment/audit.py`
- Pipeline integration:
  - Automatically runs for `prepare`, `run_batch`, and `all` unless `--skip-audit` is passed.
  - Writes `out/schema_audit.json`.
  - Pipeline fails only when audit `status = fail` (errors present).
- Standalone CLI:
  - `python3 scripts/schema_audit.py --out out/schema_audit.json`
  - `--strict` exits non-zero when warnings exist.
- Audit report includes:
  - enum integrity checks
  - prompt coverage checks
  - overlap diff report for paired families:
    - `SilhouetteContour` vs `SilhouetteType`
    - `FitEase` vs `FitType`
    - `VerticalWeightBias` vs `VisualWeightPlacement`

## 7A) Tier A Styling Filters
- Rules file: `catalog_enrichment/tier_a_filters_v1.json`
- Engine: `catalog_enrichment/styling_filters.py`
- Context enums/aliases and relaxable filters are loaded from `config/user_context_attributes.json`.
- Ranked context attribute order is loaded from `config/tier1_ranked_attributes.json`.
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
  - Rules are defined in `occasion_archetype_compatibility` inside `catalog_enrichment/tier_a_filters_v1.json`.
  - In strict mode, incompatible occasion/archetype combinations are hard-rejected.
- CLI usage:
  - `python3 scripts/filter_outfits.py --occasion "Work Mode" --archetype "Classic" --gender Female --age 25-30 --input out/enriched.csv --output out/filtered_outfits.csv --fail-log out/filtered_outfits_failures.json`
  - `python3 scripts/filter_outfits.py --occasion "Work Mode" --archetype "Classic" --gender Female --age 25-30 --relax age,archetype --input out/enriched.csv --output out/filtered_outfits_relaxed.csv --fail-log out/filtered_outfits_relaxed_failures.json`

## 7B) Tier 2 Ranking (Body Harmony Scoring)
- Rules file: `catalog_enrichment/tier2_rules_v1.json`
- Engine: `catalog_enrichment/tier2_ranker.py`
- Ranked body-harmony order and body→garment priority mapping are loaded from `config/tier2_ranked_attributes.json`.
- Formula:
  - `sum(W_bh(a) * sum(W_ga(a,g) * match(a,g) * conf(g))) * confidence_multiplier + color_delta`
- `W_bh` supports scalable ranked-decay weighting via `config/tier2_ranked_attributes.json` (`bh_weighting`).
- `W_ga` ordering comes from `body_to_garment_priority_order` in `config/tier2_ranked_attributes.json`, with decay formula:
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
  - CSV fields: `tier2_raw_score`, `tier2_confidence_multiplier`, `tier2_color_delta`, `tier2_final_score`, `tier2_flags`, `tier2_reasons`, `tier2_penalties`
  - JSON sections: `conflict_engine`, `top_positive_contributions`, `top_negative_contributions`, `formula`
- CLI usage:
  - `python3 scripts/rank_outfits.py --input out/filtered_outfits.csv --profile out/sample_user_profile_tier2.json --output out/ranked_outfits.csv --explain out/ranked_outfits_explainability.json`
  - `python3 scripts/rank_outfits.py --input out/filtered_outfits.csv --profile out/sample_user_profile_tier2.json --tier2-strictness safe --output out/ranked_outfits_safe.csv --explain out/ranked_outfits_safe_explainability.json`
- Strictness switch:
  - `--tier2-strictness balanced` (default): baseline behavior
  - `--tier2-strictness safe`: stronger penalties, more conservative ranking
  - `--tier2-strictness bold`: lighter penalties, stronger standout boosts

## 8) Batch Pipeline Behavior
1. Read CSV and validate headers.
2. Run schema audit (unless skipped).
3. Build `out/batch_input.jsonl` with one request per row (`custom_id=row_{idx}`).
4. Upload JSONL as `purpose=batch`.
5. Create batch job on `/v1/responses`.
6. Poll until terminal status.
7. Download output/error files if present.
8. Parse by `custom_id`.
9. Merge model fields into original rows.
10. Write enriched CSV and `out/run_report.json`.
11. If rows fail, write `out/retry_batch_input.jsonl`.

Result expectation:
- `enriched.csv` always contains all schema-defined attribute columns and confidence columns.
- Individual attribute values may be null/blank when the model is uncertain.
- Use a fresh `--out-dir` per run (or clear old batch artifacts) to avoid stale-output merges.

Source of truth: `catalog_enrichment/main.py`, `catalog_enrichment/batch_runner.py`, `catalog_enrichment/response_parser.py`, `catalog_enrichment/merge_writer.py`, `catalog_enrichment/quality.py`

## 9) Image URL Normalization
- Batch builder rewrites image URLs to enforce `width=768`.

Source of truth: `catalog_enrichment/batch_builder.py`

## 10) CLI Behavior
- `run_catalog_enrichment.py` is a thin passthrough to `catalog_enrichment.main.run()`.
- Required CLI args are defined in `catalog_enrichment/main.py`.
- `catalog_enrichment/main.py` defaults:
  - `--mode prepare`
  - `--out-dir out`
  - `--num-products 5` (safety limit), `all` supported
- No default input catalog is injected by `run_catalog_enrichment.py`; pass `--input` explicitly.

## 11) Example Commands
```bash
python3 scripts/schema_audit.py --out out/schema_audit.json
python3 scripts/schema_audit.py --out out/schema_audit.json --strict
python3 run_catalog_enrichment.py --input stores/processed_sample_catalog.csv --output out/enriched.csv --mode all --out-dir out
python3 run_catalog_enrichment.py --input stores/processed_sample_catalog.csv --output out/enriched.csv --mode run_batch --out-dir out
python3 run_catalog_enrichment.py --input stores/processed_sample_catalog.csv --output out/enriched.csv --mode merge --out-dir out --batch-output-jsonl out/batch_output.jsonl
```

## 12) Test Suite
- Master test doc: `test_suite.md`
- Test runner: `python3 -m unittest discover -s tests -v`
- Test modules:
  - `tests/test_config_and_schema.py`
  - `tests/test_batch_builder.py`
  - `tests/test_tier1_filters.py`
  - `tests/test_tier2_ranker.py`

## 13) End-to-End Styling Runbook
- Runbook doc: `context_files/STYLING_PIPELINE_RUNBOOK.md`
- Single-command runner:
  - `python3 scripts/run_style_pipeline.py --input out/enriched.csv --profile out/sample_user_profile_tier2.json --occasion "Work Mode" --archetype "Classic" --gender Female --age 25-30 --tier2-strictness balanced --out-dir out --prefix work_classic_female_25_30`
- Final ranked list for downstream UI/review:
  - `out/<prefix>_ranked_summary.csv`
  - Includes ranked `title`, both image URLs, and scores.
