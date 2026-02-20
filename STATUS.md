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

## Current Status
- Phase: Initial end-to-end implementation
- State: In progress
- Next milestone: run live Batch (`run_batch`/`all`) with API key and verify output quality on pilot subset

## Notes
- `ATTRIBUTE_LIST.md` currently lists 27 attributes; implementation will support all listed attributes.
- If business scope must remain 22 attributes, an `active_attribute_list` filter will be added.
