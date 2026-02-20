# Catalog Enrichment Implementation Status

## Objective
Implement a Batch-based garment attribute enrichment pipeline using `gpt-5-nano`, with mandatory CSV input columns:
- `description`
- `store`
- `image`
- `url`

Each derived categorical attribute must include a confidence score.

## Plan Checklist
- [x] Architecture documented (`ARCHITECTURE.md`)
- [x] Create status tracker (`STATUS.md`)
- [x] Scaffold Python package and CLI entrypoint
- [x] Enforce mandatory input-column validation
- [x] Encode attribute enums and strict schema builder
- [x] Implement JSONL batch input generation
- [x] Implement Batch API runner (upload/create/poll/download)
- [x] Implement output parser + merge to enriched CSV
- [x] Add retry path for failed rows
- [x] Add run report (quality metrics)
- [ ] Add unit tests for critical functions
- [ ] Pilot run on sample catalog
- [ ] Add image URL rewrite/normalization for `width=512`

## Current Status
- Phase: Pilot readiness with schema updates
- State: In progress
- Next milestone: run live Batch pilot (`--num-products 5`) and validate quality/cost

## Completed Since Last Update
- Added new attributes end-to-end:
  - `GarmentCategory` (enum)
  - `PrimaryColor` (string, nullable)
  - `SecondaryColor` (string, nullable)
- Updated schema generation to support both enum and free-text attributes with confidence fields.
- Updated prompt guidance for the new attributes.
- Updated architecture and summary documentation for 30-attribute scope.
- Confirmed `prepare` output includes the new fields.

## Action Items
1. Run pilot batch with 5 products and check:
   - `out/batch_metadata.json`
   - `out/batch_output.jsonl`
   - `out/enriched.csv`
   - `out/run_report.json`
2. Validate enum correctness for `GarmentCategory`.
3. Validate `PrimaryColor`/`SecondaryColor` shade quality and confidence behavior.
4. Implement deterministic image URL rewrite to enforce Shopify `width=512` in batch input.
5. Add unit tests for:
   - schema fields and required keys
   - parser handling of output variants
   - merge mapping by `custom_id`
   - mandatory CSV column validation

## Notes
- `ATTRIBUTE_LIST.md` currently lists 30 attributes (including `GarmentCategory`, `PrimaryColor`, `SecondaryColor`); implementation supports all listed attributes.
- If business scope must remain 22 attributes, an `active_attribute_list` filter will be added.
