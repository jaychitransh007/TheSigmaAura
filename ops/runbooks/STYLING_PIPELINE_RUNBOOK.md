# Styling Pipeline Runbook

## Purpose
Run the complete styling engine in one command:
1. Tier 1 hard filtering
2. Tier 2 personalized ranking
3. RL-ready telemetry logs for future learning
4. Final ranked summary export (`title`, image URLs, scores)

Optional upstream step:
- Infer profile/context from user image + text via `run_user_profiler.py`.

## Single Command
```bash
python3 run_style_pipeline.py \
  --input data/output/enriched.csv \
  --profile data/output/sample_user_profile_tier2.json \
  --occasion "Night Out" \
  --archetype "Glamorous" \
  --gender Female \
  --age 25-30 \
  --user-id user_123 \
  --session-id session_abc \
  --hard-filter-profile rl_ready_minimal \
  --tier2-strictness balanced \
  --recommendation-mode auto \
  --request-text "I need a complete evening look" \
  --out-dir data/output \
  --prefix nightout_glamorous_female_25_30
```

Mode options:
- `--recommendation-mode auto` (default): garment-specific text triggers garment mode, otherwise outfit mode.
- `--recommendation-mode outfit`: single complete garments + combo outfits compete together.
- `--recommendation-mode garment`: single garments only.

## Optional Upstream Inference
```bash
python3 run_user_profiler.py \
  --image /absolute/path/to/user_photo.jpg \
  --context-text "I need looks for work days and evening outings."
```
This uses real-time Responses API calls:
- visual: `gpt-5.2` with `reasoning.effort=high`
- textual: `gpt-5-mini`

## Full Profile Example (Body Harmony + Preferences)
Use this as `data/output/sample_user_profile_tier2.json`:
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
python3 run_style_pipeline.py \
  --input data/output/enriched.csv \
  --profile data/output/sample_user_profile_tier2.json \
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
With `--out-dir data/output --prefix nightout_glamorous_female_25_30`, this produces:
- `data/output/nightout_glamorous_female_25_30_filtered.csv`
- `data/output/nightout_glamorous_female_25_30_filter_failures.json`
- `data/output/nightout_glamorous_female_25_30_ranked.csv`
- `data/output/nightout_glamorous_female_25_30_ranked_explainability.json`
- `data/output/nightout_glamorous_female_25_30_ranked_summary.csv`
- `data/output/nightout_glamorous_female_25_30_request_log.json`
- `data/output/nightout_glamorous_female_25_30_candidate_set_log.csv`
- `data/output/nightout_glamorous_female_25_30_impression_log.csv`
- `data/output/nightout_glamorous_female_25_30_outcome_event_log_template.csv`

## Final Ranked Output for UI/Review
Use `*_ranked_summary.csv`. It includes:
- `rank`
- `title`
- `recommendation_kind`
- `component_count`
- `images__0__src`
- `images__1__src`
- `tier2_final_score`
- `tier2_max_score`
- `tier2_compatibility_confidence`
- `tier2_flags`

## Logging Outcomes
Append real user feedback events (like/share/buy/skip):
```bash
python3 ops/scripts/log_styling_outcome.py \
  --log-file data/output/nightout_glamorous_female_25_30_outcome_events.csv \
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
