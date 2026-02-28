# Tier 2 Ranking (Style + Complete-the-Look)

Last updated: February 28, 2026

## Purpose
Tier 2 performs deterministic compatibility scoring and ranking for:
1. Single-garment recommendations.
2. Complete-look recommendations including combos.

## Core Responsibilities
1. Score rows using body-harmony and garment attributes.
2. Build complete-look candidates.
3. Resolve garment vs outfit behavior.
4. Apply brand-variance and comfort/ease rules in style logic.

## Recommendation Mode Behavior
1. `auto`
- If request explicitly names garment category/subtype, resolve to `garment`.
- Else resolve to `outfit`.

2. `garment`
- Rank best matching requested garments.
- Return complete-the-look offer to extend into outfit assembly.

3. `outfit`
- Complete singles and combo candidates compete in one ranked list.

## Complete-the-Look Composition
Complete look composition uses:
1. single complete item detection.
2. top-bottom combo generation rules.
3. pair bonus signals (occasion coherence, formality distance, color and pattern balance, silhouette clashes).

Configuration source:
1. `modules/style_engine/configs/config/outfit_assembly_v1.json`

## Brand Variance and Comfort/Ease Rules
Brand variance and comfort/ease constraints are applied in Style logic by using:
1. user fit preference.
2. comfort preference tokens.
3. blocked style constraints.
4. per-brand adjustment heuristics where available.

## Scoring Contract
Tier 2 emits explainability fields for each candidate:
1. `tier2_final_score`
2. `tier2_max_score`
3. `tier2_compatibility_confidence`
4. `tier2_reasons`
5. `tier2_penalties`
6. `tier2_flags`

## Intent Policy Overlay
Intent policy priors may adjust ranked output and reasons metadata.
Policy application must be traceable per run.

## Outputs
1. Ranked candidates with mode-resolved metadata.
2. Recommendation kind (`single_garment` or `outfit_combo`).
3. Component metadata for complete looks.
4. Runtime summary counts for singles and combos.
