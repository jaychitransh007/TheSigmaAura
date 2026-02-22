# Tier 1 Filtering Specification

Last updated: February 22, 2026

## Purpose
Tier 1 is the hard-filter stage. It narrows the enriched catalog to items that satisfy user context constraints before personalized ranking.

Inputs:
- Enriched catalog CSV (`out/enriched.csv` or equivalent)
- User context:
  - `occasion`
  - `archetype`
  - `gender`
  - `age`
- Tier 1 rule config (`catalog_enrichment/tier_a_filters_v1.json`)
- User context aliases + relaxable filters (`config/user_context_attributes.json`)
- Ranked context->garment order (`config/tier1_ranked_attributes.json`)

Outputs:
- Filtered CSV of pass candidates
- Failure log JSON with per-item reject reasons

Engine:
- `catalog_enrichment/styling_filters.py`
- CLI: `scripts/filter_outfits.py`
- End-to-end runner (invokes Tier 1): `scripts/run_style_pipeline.py`

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
Tier 1 reads these garment attributes from `out/enriched.csv`:

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
- `catalog_enrichment/tier_a_filters_v1.json`

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
python3 scripts/filter_outfits.py \
  --occasion "Work Mode" \
  --archetype "Classic" \
  --gender Female \
  --age 25-30 \
  --input out/enriched.csv \
  --output out/filtered_outfits.csv \
  --fail-log out/filtered_outfits_failures.json
```

Relax age + archetype:
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

Relax compatibility only:
```bash
python3 scripts/filter_outfits.py \
  --occasion "Work Mode" \
  --archetype "Glamorous" \
  --gender Female \
  --age 25-30 \
  --relax occasion_archetype \
  --input out/enriched.csv \
  --output out/filtered_outfits_compat_relaxed.csv \
  --fail-log out/filtered_outfits_compat_relaxed_failures.json
```
