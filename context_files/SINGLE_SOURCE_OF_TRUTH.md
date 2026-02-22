# Single Source of Truth (Code-Accurate)

Last reconciled: February 22, 2026

This is the only authoritative context document for this project.

## 1) Project Purpose
- Enrich a catalog CSV with garment attributes and per-attribute confidence using OpenAI Batch API (`/v1/responses`) and `gpt-5-mini`.

## 2) Current Folder Layout
- Context doc: `context_files/SINGLE_SOURCE_OF_TRUTH.md`
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

## 4) Input Contract (Enrichment Pipeline)
- Mandatory columns (validated): `description`, `images__0__src`, `images__1__src`
- Optional but used in prompt context when present: `store`, `url`

Source of truth: `catalog_enrichment/config.py`, `catalog_enrichment/csv_io.py`, `catalog_enrichment/batch_builder.py`

## 5) Attribute Contract
- Total attributes in current code: 46
- Enum attributes: 44
- Text attributes: 2 (`PrimaryColor`, `SecondaryColor`)
- For each attribute `X`, output includes `X` and `X_confidence` with confidence in `[0,1]`.

Source of truth: `catalog_enrichment/attributes.py`, `catalog_enrichment/schema_builder.py`

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
