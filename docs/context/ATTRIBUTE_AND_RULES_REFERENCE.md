# Attribute and Rules Reference

Last updated: February 28, 2026

## Context Sync Note
- Catalog enrichment now supports auto-chunk checkpoint/resume for org-level limits.
- Checkpoint artifacts: `data/logs/auto_chunk_checkpoint.json`, `data/logs/partial_enriched.csv`, `data/logs/pending_chunks/pending_chunk_*.csv`.

## Runtime Attribute Sources
- Garment attributes:
  - `modules/style_engine/configs/config/garment_attributes.json`
  - loaded by `modules/catalog_enrichment/src/catalog_enrichment/attributes.py`
- Body harmony attributes:
  - `modules/style_engine/configs/config/body_harmony_attributes.json`
- User context aliases and filter controls:
  - `modules/style_engine/configs/config/user_context_attributes.json`
- Ranked mappings:
  - `modules/style_engine/configs/config/tier1_ranked_attributes.json`
  - `modules/style_engine/configs/config/tier2_ranked_attributes.json`
- Outfit assembly config:
  - `modules/style_engine/configs/config/outfit_assembly_v1.json`
- RL/reward framework:
  - `modules/style_engine/configs/config/reinforcement_framework_v1.json`
- Structured output schema:
  - `modules/catalog_enrichment/src/catalog_enrichment/schema_builder.py`
- Prompt instructions:
  - `modules/catalog_enrichment/src/catalog_enrichment/prompts/system_prompt.txt`
- User profiler prompts:
  - `modules/user_profiler/src/user_profiler/prompts/visual_prompt.txt`
  - `modules/user_profiler/src/user_profiler/prompts/textual_prompt.txt`
- User profiler response schemas:
  - `modules/user_profiler/src/user_profiler/schemas.py`

## Rules/Policy Sources
- Tier 1 filter rules:
  - `modules/style_engine/src/style_engine/tier_a_filters_v1.json`
- Tier 2 ranking/scoring config:
  - `modules/style_engine/src/style_engine/tier2_rules_v1.json`
- Outfit assembly/routing rules:
  - `modules/style_engine/configs/config/outfit_assembly_v1.json`

## Engines
- Tier 1 hard filter engine:
  - `modules/style_engine/src/style_engine/filters.py`
- Tier 2 ranker:
  - `modules/style_engine/src/style_engine/ranker.py`
- Outfit candidate engine:
  - `modules/style_engine/src/style_engine/outfit_engine.py`
- Schema audit:
  - `modules/catalog_enrichment/src/catalog_enrichment/audit.py`
- User profile inference:
  - `modules/user_profiler/src/user_profiler/service.py`
  - uses standard real-time Responses API (`client.responses.create`)

## CLIs
- Enrichment:
  - `run_catalog_enrichment.py`
- Tier 1 filtering:
  - `ops/scripts/filter_outfits.py`
- Tier 2 ranking:
  - `ops/scripts/rank_outfits.py`
- End-to-end filter+rank:
  - `run_style_pipeline.py`
- Outcome event logger:
  - `ops/scripts/log_styling_outcome.py`
- Schema audit:
  - `ops/scripts/schema_audit.py`
- User profile inference:
  - `run_user_profiler.py`
- Conversation platform API:
  - `run_conversation_platform.py`

## Tier 1 vs Tier 2 Responsibilities
- Tier 1:
  - hard pass/fail filtering
  - occasion/archetype/gender/age/price constraints
  - optional relax controls
- Tier 2:
  - weighted ranking
  - outfit candidate generation (single complete garments + top/bottom combos)
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

## Conversation Platform Contracts
- UI route:
  - `GET /` (browser conversational interface)
- Async turn routes:
  - `POST /v1/conversations/{conversation_id}/turns/start`
  - `GET /v1/conversations/{conversation_id}/turns/{job_id}/status`
- Feedback logging route:
  - `POST /v1/feedback`
- Feedback source in UI:
  - recommendation card actions `Dislike`, `Like`, `Share`, `Buy Now` (two rows: full-width buy, then dislike/like/share)
- Feedback event enum contract:
  - `dislike | like | share | buy | no_action | skip`
- Local Supabase migrations:
  - `supabase/migrations/20260224160000_conversation_platform.sql`
  - `supabase/migrations/20260224170500_feedback_events_event_type_v2.sql`
