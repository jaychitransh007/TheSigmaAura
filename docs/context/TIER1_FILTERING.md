# Tier 1 Filtering Specification

Last updated: February 24, 2026

## Purpose
Tier 1 is the hard-filter stage. It narrows the enriched catalog to items that satisfy user context constraints before personalized ranking.

Inputs:
- Enriched catalog CSV (`data/output/enriched.csv` or equivalent)
- User context:
  - `occasion`
  - `archetype`
  - `gender`
  - `age`
- Tier 1 rule config (`modules/style_engine/src/style_engine/tier_a_filters_v1.json`)
- User context aliases + relaxable filters (`modules/style_engine/configs/config/user_context_attributes.json`)
- Ranked context->garment order (`modules/style_engine/configs/config/tier1_ranked_attributes.json`)

Outputs:
- Filtered CSV of pass candidates
- Failure log JSON with per-item reject reasons
- User-side context can be inferred upstream using `run_user_profiler.py`
  (`data/output/user_style_context.json` provides `occasion`, `archetype`, `gender`, `age`).

Downstream handoff:
- Tier 1 output is consumed by outfit assembly + Tier 2 ranking.
- In outfit mode, complete singles and multi-garment combos are generated only from Tier 1 pass rows.

Engine:
- `modules/style_engine/src/style_engine/filters.py`
- CLI: `ops/scripts/filter_outfits.py`
- End-to-end runner (invokes Tier 1): `run_style_pipeline.py`

Conversation runtime note:
- In the conversation agent, Tier 1 runs only after minimum context is available.
- If context is missing, the system asks clarifying questions first (`needs_clarification=true`) and defers filtering/ranking.

## Hard Filter Order
Applied in this sequence:
1. Price range (`2000–5000`)
2. Occasion constraints
3. Occasion-Archetype compatibility gate
4. Archetype constraints
5. Gender compatibility via `GenderExpression`
6. Age-band constraints

If any hard filter fails, the row is rejected.

## Exact Attribute Coverage (Tier 1)
Tier 1 reads these garment attributes from `data/output/enriched.csv`:

Occasion filter attributes:
- `OccasionFit`
- `OccasionSignal`
- `FormalityLevel`
- `TimeOfDay`

Occasion-Archetype compatibility:
- occasion key vs archetype key using `occasion_archetype_compatibility`

Archetype filter attributes:
- `SilhouetteType`
- `FitType`
- `PatternType`
- `ColorSaturation`
- `ContrastLevel`
- `EmbellishmentLevel`

Gender filter attribute:
- `GenderExpression`

Age-band filter attributes:
- `SkinExposureLevel`
- `NecklineDepth`
- `FormalityLevel`
- `EmbellishmentLevel`
- `PatternScale`

## Rule Sources
All canonical rules are in:
- `modules/style_engine/src/style_engine/tier_a_filters_v1.json`

Sections:
- `price_range_inr`
- `occasions`
- `occasion_archetype_compatibility`
- `archetypes`
- `gender_map`
- `age_bands`

## Context Normalization
The engine normalizes aliases:
- Occasions:
  - `Work Mode` -> `work_mode`
  - `Social Casual` -> `social_casual`
  - `Night Out` -> `night_out`
  - `Formal Events` -> `formal_events`
  - `Beach & Vacation` -> `beach_vacation`
  - `Wedding vibes` -> `wedding_vibes`
- Archetypes:
  - `Modern Professional` -> `modern_professional`
  - `Trend-Forward` -> `trend_forward`
- Age:
  - `18-24` -> `18_24`
  - `25-30` -> `25_30`
  - `30-35` -> `30_35`

## Relaxation Mode
Tier 1 supports optional relaxation with `--relax`.

Allowed relax keys:
- `price`
- `age`
- `archetype`
- `occasion_archetype`

Format:
- repeatable flags:
  - `--relax age --relax price`
- or comma-separated:
  - `--relax age,archetype`

If a filter is relaxed, that filter is skipped for pass/fail evaluation.

## Failure Log Contract
Failure log (`--fail-log`) JSON includes:
- `total_rows`
- `passed_rows`
- `failed_rows`
- `context` (occasion/archetype/gender/age/relaxed_filters)
- `failures[]`
  - `id`
  - `title`
  - `fail_reasons[]`

Example reason tokens:
- `price`
- `occasion:OccasionFit`
- `occasion_archetype`
- `archetype:PatternType`
- `age:PatternScale`
- `gender:GenderExpression`

## CLI Usage
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

Relax age + archetype:
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

Relax compatibility only:
```bash
python3 ops/scripts/filter_outfits.py \
  --occasion "Work Mode" \
  --archetype "Glamorous" \
  --gender Female \
  --age 25-30 \
  --relax occasion_archetype \
  --input data/output/enriched.csv \
  --output data/output/filtered_outfits_compat_relaxed.csv \
  --fail-log data/output/filtered_outfits_compat_relaxed_failures.json
```
