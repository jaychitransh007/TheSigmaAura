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
  --occasion "Night Out" \
  --archetype "Glamorous" \
  --gender Female \
  --age 25-30 \
  --tier2-strictness balanced \
  --out-dir out \
  --prefix nightout_glamorous_female_25_30
```

## Full Profile Example (Body Harmony + Preferences)
Use this as `out/sample_user_profile_tier2.json`:
```json
{
  "HeightCategory": "AVERAGE",
  "BodyShape": "HOURGLASS",
  "VisualWeight": "BALANCED",
  "VerticalProportion": "BALANCED",
  "ArmVolume": "AVERAGE",
  "MidsectionState": "SOFT_AVERAGE",
  "WaistVisibility": "DEFINED",
  "BustVolume": "MEDIUM",
  "SkinUndertone": "WARM",
  "SkinSurfaceColor": "WHEATISH_MEDIUM",
  "SkinContrast": "MEDIUM_CONTRAST",
  "FaceShape": "OVAL",
  "NeckLength": "AVERAGE",
  "HairLength": "SHOULDER_LENGTH",
  "HairColor": "DARK_BROWN",
  "color_preferences": {
    "loved": ["black", "emerald_green"],
    "liked": ["navy_blue", "burgundy"],
    "disliked": ["neon_yellow"],
    "never": ["beige"]
  }
}
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
With `--out-dir out --prefix nightout_glamorous_female_25_30`, this produces:
- `out/nightout_glamorous_female_25_30_filtered.csv`
- `out/nightout_glamorous_female_25_30_filter_failures.json`
- `out/nightout_glamorous_female_25_30_ranked.csv`
- `out/nightout_glamorous_female_25_30_ranked_explainability.json`
- `out/nightout_glamorous_female_25_30_ranked_summary.csv`

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

## Error Handling
- The runner handles common input/config errors gracefully and prints one-line messages without Python tracebacks.
- Typical examples:
  - wrong `--archetype` value (e.g., passing an occasion)
  - wrong `--occasion` value (e.g., passing an archetype)
  - invalid `--relax` token
  - missing input/profile file
  - invalid profile JSON
- Exit code on these validation/input errors: `2`
