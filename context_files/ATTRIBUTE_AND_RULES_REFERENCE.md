# Attribute and Rules Reference

Last updated: February 22, 2026

## Runtime Attribute Sources
- Garment attributes:
  - `catalog_enrichment/attributes.py`
- Structured output schema:
  - `catalog_enrichment/schema_builder.py`
- Prompt instructions:
  - `catalog_enrichment/prompts/system_prompt.txt`

## Rules/Policy Sources
- Tier 1 filter rules:
  - `catalog_enrichment/tier_a_filters_v1.json`
- Tier 2 ranking/scoring config:
  - `catalog_enrichment/tier2_rules_v1.json`

## Engines
- Tier 1 hard filter engine:
  - `catalog_enrichment/styling_filters.py`
- Tier 2 ranker:
  - `catalog_enrichment/tier2_ranker.py`
- Schema audit:
  - `catalog_enrichment/audit.py`

## CLIs
- Enrichment:
  - `run_catalog_enrichment.py`
- Tier 1 filtering:
  - `scripts/filter_outfits.py`
- Tier 2 ranking:
  - `scripts/rank_outfits.py`
- Schema audit:
  - `scripts/schema_audit.py`

## Tier 1 vs Tier 2 Responsibilities
- Tier 1:
  - hard pass/fail filtering
  - occasion/archetype/gender/age/price constraints
  - optional relax controls
- Tier 2:
  - weighted ranking
  - body-harmony scoring
  - conflict engine
  - confidence-aware weighting
  - explainability generation

## Confidence Usage
- Every garment contribution in Tier 2 is multiplied by garment attribute confidence:
  - `<attribute>_confidence`
- Low confidence values are further downweighted.

## Strictness Modes (Tier 2)
- `safe`
- `balanced` (default)
- `bold`

These adjust:
- confidence multiplier scale
- negative penalty scale
- color delta scale
- skin merge penalty scale

without changing base body-harmony rules.

