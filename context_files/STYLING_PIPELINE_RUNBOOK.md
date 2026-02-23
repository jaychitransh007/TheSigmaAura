# Styling Pipeline Runbook

## Purpose
Run the complete styling engine in one command:
1. Tier 1 hard filtering
2. Tier 2 personalized ranking
3. RL-ready telemetry logs for future learning
4. Final ranked summary export (`title`, image URLs, scores)

## Single Command
```bash
python3 scripts/run_style_pipeline.py \
  --input out/enriched.csv \
  --profile out/sample_user_profile_tier2.json \
  --occasion "Night Out" \
  --archetype "Glamorous" \
  --gender Female \
  --age 25-30 \
  --user-id user_123 \
  --session-id session_abc \
  --hard-filter-profile rl_ready_minimal \
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

## Legacy Hard Filter Mode (Optional)
If you need old hard-filter behavior with archetype/age as hard constraints:
```bash
python3 scripts/run_style_pipeline.py \
  --input out/enriched.csv \
  --profile out/sample_user_profile_tier2.json \
  --occasion "Work Mode" \
  --archetype "Classic" \
  --gender Female \
  --age 25-30 \
  --hard-filter-profile legacy \
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
- `out/nightout_glamorous_female_25_30_request_log.json`
- `out/nightout_glamorous_female_25_30_candidate_set_log.csv`
- `out/nightout_glamorous_female_25_30_impression_log.csv`
- `out/nightout_glamorous_female_25_30_outcome_event_log_template.csv`

## Final Ranked Output for UI/Review
Use `*_ranked_summary.csv`. It includes:
- `rank`
- `title`
- `images__0__src`
- `images__1__src`
- `tier2_final_score`
- `tier2_max_score`
- `tier2_compatibility_confidence`
- `tier2_flags`

## Logging Outcomes
Append real user feedback events (like/share/buy/skip):
```bash
python3 scripts/log_styling_outcome.py \
  --log-file out/nightout_glamorous_female_25_30_outcome_events.csv \
  --request-id <request_id> \
  --session-id <session_id> \
  --user-id user_123 \
  --garment-id <garment_id> \
  --title "<title>" \
  --event-type buy
```

Reward policy (config-driven):
- `like = +5`
- `share = +10`
- `buy = +50`
- `skip = -1`

## Error Handling
- The runner handles common input/config errors gracefully and prints one-line messages without Python tracebacks.
- Typical examples:
  - wrong `--archetype` value (e.g., passing an occasion)
  - wrong `--occasion` value (e.g., passing an archetype)
  - invalid `--relax` token
  - missing input/profile file
  - invalid profile JSON
- Exit code on these validation/input errors: `2`
