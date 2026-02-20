# Project Summary

## Scope
- Batch enrichment pipeline using `gpt-5-nano` for catalog rows with mandatory columns: `description`, `store`, `image`, `url`.
- Structured output with strict schema and per-attribute confidence scores.

## Delivered
- Architecture and planning docs:
  - `ARCHITECTURE.md`
  - `STATUS.md`
- End-to-end implementation:
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
- Safety and ops:
  - `.env` support (`OPENAI_API_KEY`)
  - `.env.example`
  - `.gitignore` coverage for `.env`, cache, and run artifacts
  - `--num-products` guardrail (`5` default, `all` optional)
  - Retry input generation for failed rows: `out/retry_batch_input.jsonl`

## Attribute Model
- Current scope follows `ATTRIBUTE_LIST.md` with 30 attributes total:
  - 28 structured categorical/enum attributes
  - 2 free-text color attributes: `PrimaryColor`, `SecondaryColor`
- Added attribute:
  - `GarmentCategory` (enum)
- Every attribute includes `<attribute>_confidence` in `[0,1]`.

## Cost Optimization Decision
- No image re-hosting required currently.
- Use Shopify CDN resize parameter in image URLs (`width=512`) to reduce vision token load and batch cost.
- Keep ability to raise resolution (for example, `width=768`) if quality drops on fine-detail attributes.

## Validation Status
- `prepare` mode validated locally.
- `merge` mode validated with mock output.
- Compile checks pass.
- Live batch execution path is implemented and ready.

## How To Run
### Pilot run (default 5 products)
```bash
python3 run_catalog_enrichment.py --input sample.csv --output out/enriched.csv --mode all --out-dir out
```

### Full run
```bash
python3 run_catalog_enrichment.py --input sample.csv --output out/enriched.csv --mode all --out-dir out --num-products all
```

### Stage-wise run
```bash
python3 run_catalog_enrichment.py --input sample.csv --output out/enriched.csv --mode prepare --out-dir out
python3 run_catalog_enrichment.py --input sample.csv --output out/enriched.csv --mode run_batch --out-dir out
python3 run_catalog_enrichment.py --input sample.csv --output out/enriched.csv --mode merge --out-dir out --batch-output-jsonl out/batch_output.jsonl
```

## Next Actions
1. Run live pilot and review attribute quality/confidence row-by-row.
2. Add unit tests for schema, parser, merge, and header validation.
3. Add URL rewrite utility to force `width=512` systematically before batch generation.
4. Promote to full run once pilot quality and cost are acceptable.
