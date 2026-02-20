# Project Summary

## Work Completed
- Reviewed requirements in `CATALOG_MODULE.md` and attribute definitions in `ATTRIBUTE_LIST.md`.
- Created architecture blueprint in `ARCHITECTURE.md`.
- Created implementation tracker in `STATUS.md`.
- Implemented modular Python pipeline for catalog enrichment:
  - `catalog_enrichment/config.py`
  - `catalog_enrichment/attributes.py`
  - `catalog_enrichment/schema_builder.py`
  - `catalog_enrichment/csv_io.py`
  - `catalog_enrichment/batch_builder.py`
  - `catalog_enrichment/batch_runner.py`
  - `catalog_enrichment/response_parser.py`
  - `catalog_enrichment/merge_writer.py`
  - `catalog_enrichment/quality.py`
  - `catalog_enrichment/main.py`
  - `run_catalog_enrichment.py`
- Added local secret loading and safety files:
  - `.env` support via config loader
  - `.env.example`
  - `.gitignore` entries for `.env`, `out/`, caches
- Added safety limit for initial runs:
  - `--num-products` accepts `5` or `all`
  - default is `5`
- Implemented per-attribute confidence output for all listed attributes.
- Implemented retry input generation for failed rows: `out/retry_batch_input.jsonl`.

## Current State
- Core implementation is complete and runnable.
- Mandatory input columns are enforced: `description`, `store`, `image`, `url`.
- `prepare` mode verified locally (JSONL generation works).
- `merge` mode verified locally with mock output (enriched CSV + report generated).
- Live batch path is implemented and ready for API execution.
- Attribute scope currently follows `ATTRIBUTE_LIST.md` (27 attributes).

## Testing Plan
1. Pilot run with default 5 products.
2. Validate artifacts:
   - `out/batch_input.jsonl` line count is 5
   - `out/enriched.csv` contains enum + confidence columns
   - `out/run_report.json` generated
3. Manual quality review of pilot rows for enum correctness, null behavior, and confidence sanity.
4. Validate retry behavior (`out/retry_batch_input.jsonl` for non-`ok` rows).
5. Promote to full run using `--num-products all` only after pilot quality passes.
6. Add unit tests for header validation, schema builder, parser, and merge mapping.

## Run Commands
### Pilot (safe default: 5)
```bash
python3 run_catalog_enrichment.py --input sample.csv --output out/enriched.csv --mode all --out-dir out
```

### Full run
```bash
python3 run_catalog_enrichment.py --input sample.csv --output out/enriched.csv --mode all --out-dir out --num-products all
```

### Stage-wise
```bash
python3 run_catalog_enrichment.py --input sample.csv --output out/enriched.csv --mode prepare --out-dir out
python3 run_catalog_enrichment.py --input sample.csv --output out/enriched.csv --mode run_batch --out-dir out
python3 run_catalog_enrichment.py --input sample.csv --output out/enriched.csv --mode merge --out-dir out --batch-output-jsonl out/batch_output.jsonl
```
