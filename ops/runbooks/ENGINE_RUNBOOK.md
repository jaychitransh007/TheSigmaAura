# Engine Runbook

Last updated: February 22, 2026

## End-to-End Flow
1. Enrich catalog with batch model
2. Run Tier 1 hard filtering
3. Run Tier 2 personalized ranking

Single-command orchestration is available via:
- `run_style_pipeline.py`

## 0) Prerequisites
- `OPENAI_API_KEY` available in environment or `.env`
- Input CSV has mandatory columns:
  - `description`
  - `images__0__src`
  - `images__1__src`

## 1) Enrichment (Batch)
Full run:
```bash
python3 run_catalog_enrichment.py \
  --input modules/catalog_enrichment/stores/processed_sample_catalog.csv \
  --output data/output/enriched.csv \
  --mode all \
  --out-dir data/output
```

Notes:
- Model: `gpt-5-mini`
- Batch endpoint: `/v1/responses`
- Image normalization: `width=768`
- Automatic schema audit runs before prepare/run_batch/all unless skipped.

## 2) Tier 1 Filter
Strict:
```bash
python3 ops/scripts/filter_outfits.py \
  --occasion "Work Mode" \
  --archetype "Classic" \
  --gender Female \
  --age 25-30 \
  --input data/output/enriched.csv \
  --output data/output/filtered_outfits.csv \
  --fail-log data/output/filtered_outfits_failures.json
```

With relax:
```bash
python3 ops/scripts/filter_outfits.py \
  --occasion "Work Mode" \
  --archetype "Classic" \
  --gender Female \
  --age 25-30 \
  --relax age,archetype \
  --input data/output/enriched.csv \
  --output data/output/filtered_outfits_relaxed.csv \
  --fail-log data/output/filtered_outfits_relaxed_failures.json
```

## 3) Tier 2 Rank
```bash
python3 ops/scripts/rank_outfits.py \
  --input data/output/filtered_outfits.csv \
  --profile data/output/sample_user_profile_tier2.json \
  --tier2-strictness balanced \
  --output data/output/ranked_outfits.csv \
  --explain data/output/ranked_outfits_explainability.json
```

## 4) Debug Checklist
If Tier 1 returns too few:
1. inspect `data/output/filtered_outfits_failures.json`
2. relax one filter:
   - `--relax age`
   - `--relax archetype`
   - `--relax occasion_archetype`
   - `--relax price`

If Tier 2 scores look flat:
1. confirm enriched confidence fields are populated
2. inspect explainability JSON for contribution traces
3. try `--tier2-strictness bold`

If batch run fails:
1. check `data/output/batch_errors.jsonl`
2. check model params in request body
3. avoid stale output merges by using new `--out-dir`

## 5) Single Command Runbook
```bash
python3 run_style_pipeline.py \
  --input data/output/enriched.csv \
  --profile data/output/sample_user_profile_tier2.json \
  --occasion "Night Out" \
  --archetype "Glamorous" \
  --gender Female \
  --age 25-30 \
  --hard-filter-profile rl_ready_minimal \
  --tier2-strictness balanced \
  --out-dir data/output \
  --prefix nightout_glamorous_female_25_30
```

Final ranked output:
- `data/output/nightout_glamorous_female_25_30_ranked_summary.csv`
- includes rank, title, image URLs, and scores.
- also writes RL-ready logs:
  - `data/output/<prefix>_request_log.json`
  - `data/output/<prefix>_candidate_set_log.csv`
  - `data/output/<prefix>_impression_log.csv`
  - `data/output/<prefix>_outcome_event_log_template.csv`

Error behavior:
- invalid context/inputs are handled gracefully (no traceback)
- runner prints `error: <message>` and exits with code `2`
## 6) Core Artifacts
- Enriched CSV: `data/output/enriched.csv`
- Schema audit: `data/output/schema_audit.json`
- Tier 1 pass CSV: `data/output/filtered_outfits.csv`
- Tier 1 fail log: `data/output/filtered_outfits_failures.json`
- Tier 2 ranked CSV: `data/output/ranked_outfits.csv`
- Tier 2 explainability JSON: `data/output/ranked_outfits_explainability.json`
