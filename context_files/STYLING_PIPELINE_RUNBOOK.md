# Styling Pipeline Runbook

## Purpose
Run the complete styling engine in one command:
1. Tier 1 hard filtering
2. Tier 2 personalized ranking
3. Final ranked summary export (`title`, image URLs, scores)

## Single Command
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
  --prefix work_classic_female_25_30
```

## Optional Relaxation
Relax one or more Tier 1 hard filters:
```bash
python3 scripts/run_style_pipeline.py \
  --input out/enriched.csv \
  --profile out/sample_user_profile_tier2.json \
  --occasion "Work Mode" \
  --archetype "Classic" \
  --gender Female \
  --age 25-30 \
  --relax age,archetype
```

Supported `--relax` values:
- `price`
- `age`
- `archetype`
- `occasion_archetype`

## Output Artifacts
With `--out-dir out --prefix work_classic_female_25_30`, this produces:
- `out/work_classic_female_25_30_filtered.csv`
- `out/work_classic_female_25_30_filter_failures.json`
- `out/work_classic_female_25_30_ranked.csv`
- `out/work_classic_female_25_30_ranked_explainability.json`
- `out/work_classic_female_25_30_ranked_summary.csv`

## Final Ranked Output for UI/Review
Use `*_ranked_summary.csv`. It includes:
- `rank`
- `title`
- `images__0__src`
- `images__1__src`
- `tier2_final_score`
- `tier2_raw_score`
- `tier2_confidence_multiplier`
- `tier2_flags`
