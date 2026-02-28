# Tier 2 Ranking Specification

Last updated: February 28, 2026

Context sync note:
- Latest catalog update adds auto-chunk checkpoint/resume in enrichment; Tier 2 scoring/ranking behavior is unchanged.

## Purpose
Tier 2 ranks Tier-1-passed garments using body harmony and style preference signals.
It is a scoring layer (not hard exclusion except explicit color `never` preference).

Engine:
- `modules/style_engine/src/style_engine/ranker.py`
- `modules/style_engine/src/style_engine/outfit_engine.py`
- CLI: `ops/scripts/rank_outfits.py`
- Rules: `modules/style_engine/src/style_engine/tier2_rules_v1.json`
- Ranked mappings config: `modules/style_engine/configs/config/tier2_ranked_attributes.json`
- Outfit assembly config: `modules/style_engine/configs/config/outfit_assembly_v1.json`
- End-to-end runner (invokes Tier 2): `run_style_pipeline.py`

Conversation runtime note:
- Tier 2 outputs are used by the conversational UI card renderer.
- Card actions (`Dislike`, `Like`, `Share`, `Buy Now`) do not change this score immediately; they are logged for future optimization.

## Inputs
- Tier 1 filtered CSV (`data/logs/filtered_outfits.csv` or equivalent)
- User profile JSON (body harmony + color preferences)
- Tier 2 rules JSON
- User profile can be inferred upstream using `run_user_profiler.py`
  (`data/logs/user_style_profile.json` is directly usable as `--profile` input).

## Core Formula
Implemented formula:

`Tier2Raw = Σ_a [ W_bh(a) * Σ_g ( W_ga(a,g) * match(a,g) * conf(g) ) ]`

`FinalScore = Tier2Raw * confidence_multiplier + color_delta`

Outfit combo score (for `recommendation_mode=outfit`):

`OutfitScore = ((TopFinalScore + BottomFinalScore) / 2) + PairBonus`

`PairBonus` is config-bounded and computed from outfit-level coherence signals.

Where:
- `a`: body harmony attribute
- `g`: affected garment attribute
- `W_bh(a)`: body harmony attribute weight
- `W_ga(a,g)`: per-attribute decay-normalized local weight
- `match(a,g)`:
  - preferred = `1.0`
  - acceptable = `0.5`
  - not_permitted = `-0.25`
  - unlisted = `0.0`
- `conf(g)`: garment confidence value from `<g>_confidence`

Confidence handling:
- If `conf(g) >= 0.45`: use as-is
- If `conf(g) < 0.45`: downweight to `conf(g) * 0.5`

## Exact Weights (W_bh)
`W_bh` is now configurable and scalable.

Weight mode is controlled by `bh_weighting.mode`:
- `ranked_decay`: derive from ordered rank using decay formula
- `fixed`: use static `bh_weights` table

Current runtime mode in rules:
- `bh_weighting.mode = ranked_decay`
- `bh_weighting.decay_factor = 0.8`
- ordered attributes:
  - `HeightCategory`
  - `BodyShape`
  - `VisualWeight`
  - `VerticalProportion`
  - `ArmVolume`
  - `MidsectionState`
  - `WaistVisibility`
  - `BustVolume`
  - `SkinUndertone`
  - `SkinSurfaceColor`
  - `SkinContrast`
  - `FaceShape`
  - `NeckLength`
  - `HairLength`
  - `HairColor`

Effective `W_bh` values for current settings:
- `HeightCategory`: `0.207293`
- `BodyShape`: `0.165835`
- `VisualWeight`: `0.132668`
- `VerticalProportion`: `0.106134`
- `ArmVolume`: `0.084907`
- `MidsectionState`: `0.067926`
- `WaistVisibility`: `0.054341`
- `BustVolume`: `0.043473`
- `SkinUndertone`: `0.034778`
- `SkinSurfaceColor`: `0.027822`
- `SkinContrast`: `0.022258`
- `FaceShape`: `0.017806`
- `NeckLength`: `0.014245`
- `HairLength`: `0.011396`
- `HairColor`: `0.009117`

Sum = `1.00`

## Exact Local Weights (W_ga)
`W_ga(a,g)` is computed from ordered affected attributes using decay `r=0.8`.

For `n` affected garment attributes for body attribute `a`:
- raw rank weight at position `i` (0-index): `r^i`
- normalized local weight:
  - `W_ga_i = r^i / Σ_{k=0..n-1}(r^k)`

So earlier garment attributes in each ordered list get higher local impact.

Example (`n=4`, `r=0.8`):
- raw = `[1.0, 0.8, 0.64, 0.512]`
- normalized ≈ `[0.3388, 0.2710, 0.2168, 0.1734]`

## Exact Affected Garment Attributes by Body Attribute
From `affected_garment_attributes` in `tier2_rules_v1.json`:

- `HeightCategory`: `GarmentLength`, `PatternScale`, `PatternOrientation`, `VisualWeightPlacement`, `WaistDefinition`, `FabricWeight`, `ColorCount`, `ContrastLevel`, `SilhouetteType`
- `BodyShape`: `SilhouetteType`, `FitType`, `WaistDefinition`, `VisualWeightPlacement`, `BodyFocusZone`, `NecklineType`, `EmbellishmentLevel`, `FabricDrape`, `FabricWeight`, `FabricTexture`, `SleeveLength`, `ConstructionDetail`
- `VisualWeight`: `SilhouetteType`, `VisualWeightPlacement`, `BodyFocusZone`, `EmbellishmentLevel`, `EmbellishmentZone`, `PatternScale`, `NecklineType`, `FabricDrape`, `FabricTexture`
- `VerticalProportion`: `WaistDefinition`, `GarmentLength`, `VisualWeightPlacement`, `SilhouetteType`
- `ArmVolume`: `SleeveLength`, `SkinExposureLevel`, `FitType`, `BodyFocusZone`, `EmbellishmentLevel`, `EmbellishmentZone`, `NecklineType`, `FabricTexture`
- `MidsectionState`: `SilhouetteType`, `FitType`, `WaistDefinition`, `FabricDrape`, `FabricTexture`, `BodyFocusZone`, `EmbellishmentLevel`, `EmbellishmentZone`, `ConstructionDetail`
- `WaistVisibility`: `WaistDefinition`, `SilhouetteType`, `FitType`, `BodyFocusZone`, `ConstructionDetail`
- `BustVolume`: `NecklineType`, `NecklineDepth`, `SilhouetteType`, `FitType`, `FabricDrape`, `BodyFocusZone`, `SleeveLength`, `EmbellishmentLevel`, `EmbellishmentZone`, `FabricWeight`, `FabricTexture`
- `SkinUndertone`: `ColorTemperature`, `ColorSaturation`
- `SkinSurfaceColor`: `ColorTemperature`, `ColorSaturation`, `ContrastLevel`, `ColorValue`, `FabricTexture`
- `SkinContrast`: `ContrastLevel`, `ColorSaturation`, `PatternType`, `ColorCount`
- `FaceShape`: `NecklineType`, `NecklineDepth`, `EmbellishmentLevel`, `EmbellishmentZone`
- `NeckLength`: `NecklineType`, `NecklineDepth`, `EmbellishmentLevel`, `EmbellishmentZone`
- `HairLength`: `NecklineType`, `NecklineDepth`
- `HairColor`: `ContrastLevel`, `ColorTemperature`, `ColorValue`

## Exact Match Scores
- `preferred`: `1.0`
- `acceptable`: `0.5`
- `not_permitted`: `-0.25`
- `unlisted`: `0.0`

## Rule Resolution
Rule lookup priority:
1. `body_rules` table (if populated in rules JSON)
2. Heuristic fallback rules embedded in ranker (`_heuristic_rule`)

Current implementation includes broad heuristic mappings for:
- `HeightCategory`
- `BodyShape`
- `VisualWeight`
- `VerticalProportion`
- `ArmVolume`
- `MidsectionState`
- `WaistVisibility`
- `BustVolume`
- `SkinUndertone`
- `SkinSurfaceColor`
- `SkinContrast`
- `FaceShape`
- `NeckLength`
- `HairLength`
- `HairColor`

## Conflict Engine (Implemented)
For each garment attribute touched by multiple body attributes:

1. Preferred intersection
- If preferred sets intersect, use intersection signal.

2. Acceptable fallback
- If preferred intersection is empty:
  - intersect highest-priority preferred with lower-priority acceptable.
  - if non-empty, record fallback event.

3. Priority override
- If still empty:
  - highest-priority preferred set wins.
  - record override event.

4. Not-permitted union
- Union all `not_permitted` across active body attributes for each garment attribute.
- If garment value is in union, apply `-0.25` penalty for that contribution.

Conflict counters:
- `acceptable_fallback_count`
- `priority_override_count`

## Confidence Multiplier
From conflict counters:
- full intersection/no conflicts: `1.00`
- 1 fallback: `0.95`
- 2–3 fallbacks: `0.90`
- 1 override: `0.85`
- 2+ overrides: `0.75`

Flags:
- if final score < `nearest_match_threshold` (`0.40`): `nearest_match`
- if confidence multiplier < `limited_match_threshold` (`0.60`): `limited_match`

## Color Preference Layer
User profile can include:
- `loved`
- `liked`
- `disliked`
- `never`

Base deltas:
- loved: `+0.20`
- liked: `+0.10`
- disliked: `-0.15`
- never: hard exclude candidate from Tier 2 output

Applied on `PrimaryColor`.

Additional skin merge guard:
- penalty applied if `SkinSurfaceColor` and `ColorValue` hit merge-protection pairs.

## Strictness Modes
CLI switch: `--tier2-strictness {safe|balanced|bold}`

Behavior (without changing base rules):
- `safe`
  - stronger negative penalties
  - lower confidence multiplier scaling
  - smaller color boosts
- `balanced`
  - baseline
- `bold`
  - lighter negative penalties
  - higher confidence multiplier scaling
  - larger color boosts

Configured in:
- `strictness_profiles` in `modules/style_engine/src/style_engine/tier2_rules_v1.json`

Exact strictness constants:

- `safe`
  - `confidence_multiplier_scale = 0.90`
  - `negative_penalty_scale = 1.20`
  - `color_delta_scale = 0.85`
  - `skin_merge_penalty_scale = 1.20`

- `balanced`
  - `confidence_multiplier_scale = 1.00`
  - `negative_penalty_scale = 1.00`
  - `color_delta_scale = 1.00`
  - `skin_merge_penalty_scale = 1.00`

- `bold`
  - `confidence_multiplier_scale = 1.10`
  - `negative_penalty_scale = 0.85`
  - `color_delta_scale = 1.15`
  - `skin_merge_penalty_scale = 0.85`

## Recommendation Modes
CLI switch:
- `--recommendation-mode auto|outfit|garment`

Behavior:
- `auto`: request text is scanned for category/subtype keywords from `outfit_assembly_v1.json`.
  - explicit garment ask -> `garment`
  - otherwise -> `outfit`
- `outfit`: single complete garments compete with top+bottom combos.
- `garment`: only single-garment candidates are returned (optional category/subtype narrowing when detected).

Pair bonus signals (config-driven):
- occasion-fit coherence
- formality distance
- color-temperature compatibility
- pattern balance (solid-vs-patterned)
- heavy embellishment clash
- dual oversized/boxy silhouette clash

## Output Contracts
CSV adds per-row fields:
- `tier2_raw_score`
- `tier2_confidence_multiplier`
- `tier2_color_delta`
- `tier2_final_score`
- `tier2_flags`
- `tier2_reasons`
- `tier2_penalties`

Explainability JSON includes:
- `profile_used`
- `tier2_strictness`
- top results with:
  - final/raw/multiplier/color delta
  - flags/reasons/penalties
  - `conflict_engine`
  - top positive/negative contribution traces
  - formula string
- `explainability_contract` summary

## CLI Usage
Balanced:
```bash
python3 ops/scripts/rank_outfits.py \
  --input data/logs/filtered_outfits.csv \
  --profile data/logs/sample_user_profile_tier2.json \
  --tier2-strictness balanced \
  --output data/logs/ranked_outfits.csv \
  --explain data/logs/ranked_outfits_explainability.json
```

Safe:
```bash
python3 ops/scripts/rank_outfits.py \
  --input data/logs/filtered_outfits.csv \
  --profile data/logs/sample_user_profile_tier2.json \
  --tier2-strictness safe \
  --output data/logs/ranked_outfits_safe.csv \
  --explain data/logs/ranked_outfits_safe_explainability.json
```

Bold:
```bash
python3 ops/scripts/rank_outfits.py \
  --input data/logs/filtered_outfits.csv \
  --profile data/logs/sample_user_profile_tier2.json \
  --tier2-strictness bold \
  --output data/logs/ranked_outfits_bold.csv \
  --explain data/logs/ranked_outfits_bold_explainability.json
```
