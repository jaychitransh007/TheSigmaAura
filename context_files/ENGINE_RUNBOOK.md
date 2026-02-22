# Engine Runbook

Last updated: February 22, 2026

## End-to-End Flow
1. Enrich catalog with batch model
2. Run Tier 1 hard filtering
3. Run Tier 2 personalized ranking

Single-command orchestration is available via:
- `scripts/run_style_pipeline.py`

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
  --input stores/processed_sample_catalog.csv \
  --output out/enriched.csv \
  --mode all \
  --out-dir out
```

Notes:
- Model: `gpt-5-mini`
- Batch endpoint: `/v1/responses`
- Image normalization: `width=768`
- Automatic schema audit runs before prepare/run_batch/all unless skipped.

## 2) Tier 1 Filter
Strict:
```bash
python3 scripts/filter_outfits.py \
  --occasion "Work Mode" \
  --archetype "Classic" \
  --gender Female \
  --age 25-30 \
  --input out/enriched.csv \
  --output out/filtered_outfits.csv \
  --fail-log out/filtered_outfits_failures.json
```

With relax:
```bash
python3 scripts/filter_outfits.py \
  --occasion "Work Mode" \
  --archetype "Classic" \
  --gender Female \
  --age 25-30 \
  --relax age,archetype \
  --input out/enriched.csv \
  --output out/filtered_outfits_relaxed.csv \
  --fail-log out/filtered_outfits_relaxed_failures.json
```

## 3) Tier 2 Rank
```bash
python3 scripts/rank_outfits.py \
  --input out/filtered_outfits.csv \
  --profile out/sample_user_profile_tier2.json \
  --tier2-strictness balanced \
  --output out/ranked_outfits.csv \
  --explain out/ranked_outfits_explainability.json
```

## 4) Debug Checklist
If Tier 1 returns too few:
1. inspect `out/filtered_outfits_failures.json`
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
1. check `out/batch_errors.jsonl`
2. check model params in request body
3. avoid stale output merges by using new `--out-dir`

## 5) Single Command Runbook
```bash
python3 scripts/run_style_pipeline.py \
  --input out/enriched.csv \
  --profile out/sample_user_profile_tier2.json \
  --occasion "Work Mode" \
  --archetype "Classic" \
  --gender Female \
  --age 25-30 \
  --tier2-strictness balanced \
  --out-dir out \
  --prefix runbook_demo
```

Final ranked output:
- `out/runbook_demo_ranked_summary.csv`
- includes rank, title, image URLs, and scores.
## 6) Core Artifacts
- Enriched CSV: `out/enriched.csv`
- Schema audit: `out/schema_audit.json`
- Tier 1 pass CSV: `out/filtered_outfits.csv`
- Tier 1 fail log: `out/filtered_outfits_failures.json`
- Tier 2 ranked CSV: `out/ranked_outfits.csv`
- Tier 2 explainability JSON: `out/ranked_outfits_explainability.json`
