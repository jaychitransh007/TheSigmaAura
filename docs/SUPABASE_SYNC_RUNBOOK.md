# Supabase Sync Runbook

Last updated: March 13, 2026

## Goal
Keep local development and staging on the same migration chain and use explicit env targeting.

## Env Convention
- Local: `.env.local`
- Staging: `.env.staging`

Supported selectors:
- `APP_ENV=local`
- `APP_ENV=staging`
- or explicit `ENV_FILE=/absolute/or/relative/path`

## Env Files
Bootstrap missing env files:
```bash
python3 ops/scripts/bootstrap_env_files.py
```

Create and fill:
- `.env.local` from `.env.example`
- `.env.staging` from `.env.example`

## Staging Env Template
Fill `.env.staging` with:
- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `GEMINI_API_KEY` (from Google AI Studio, required for virtual try-on)

## Before Running Against Staging
```bash
python3 ops/scripts/check_supabase_sync.py --strict
```

## Link Repo To Staging
```bash
supabase link --project-ref zfbqkkegrfhdzqvjoytz --password '<db-password>' --yes
```

## Push Migrations To Staging
```bash
supabase db push --yes
```

## Run App Against Staging
```bash
APP_ENV=staging python3 run_agentic_application.py --host 127.0.0.1 --port 8010
```

## Run App Against Local
```bash
APP_ENV=local python3 run_agentic_application.py --host 127.0.0.1 --port 8010
```

## Run Catalog Embeddings Against Staging
```bash
ENV_FILE=.env.staging \
PYTHONPATH=modules/catalog_retrieval/src:modules/user_profiler/src:modules/platform_core/src \
python3 -m catalog_retrieval.main \
  --input data/catalog/enriched_catalog.csv \
  --documents-output data/catalog/embeddings/catalog_documents_sample.jsonl \
  --embeddings-output data/catalog/embeddings/catalog_embeddings_sample.jsonl \
  --max-rows 5 \
  --embed \
  --save-supabase
```

## Migration Inventory

19 migrations in `supabase/migrations/`:

| Migration | Purpose |
|---|---|
| `20260224160000_conversation_platform.sql` | Core tables: users, conversations, conversation_turns, model_calls, tool_traces, recommendation_events, feedback_events |
| `20260224170500_feedback_events_event_type_v2.sql` | Feedback events schema update |
| `20260228120000_agentic_commerce_phase1.sql` | Agentic commerce scaffolding |
| `20260310120000_onboarding.sql` | onboarding_profiles, onboarding_images tables |
| `20260310133000_user_analysis.sql` | user_analysis_runs table (analysis snapshots with agent outputs) |
| `20260310143000_user_derived_interpretations.sql` | user_derived_interpretations table |
| `20260310153000_onboarding_analysis_history_snapshots.sql` | Analysis history/snapshot support |
| `20260310160000_cleanup_redundant_analysis_tables.sql` | Remove redundant analysis tables |
| `20260311110000_drop_visual_waist_columns.sql` | Drop unused visual waist columns |
| `20260311112000_add_height_category_interpretation.sql` | Add HeightCategory to interpretations |
| `20260312110000_style_archetype_preferences.sql` | user_style_preference table |
| `20260312113000_style_preference_selected_images.sql` | Selected images for style preferences |
| `20260312130000_catalog_item_embeddings.sql` | catalog_item_embeddings table (pgvector 1536) |
| `20260312143000_style_archetype_storage_bucket.sql` | Supabase storage bucket for archetype images |
| `20260312150000_catalog_items_and_embedding_upserts.sql` | Catalog upsert support |
| `20260312153000_catalog_admin_status.sql` | Catalog admin status tracking |
| `20260312160000_catalog_enriched.sql` | catalog_enriched table (50+ attribute columns) |
| `20260312161000_update_catalog_admin_status.sql` | Admin status schema update |
| `20260312162000_catalog_enriched_product_id_unique.sql` | Unique constraint on product_id |

## Key Table Relationships

```text
users
  └── conversations (user_id)
        └── conversation_turns (conversation_id)

onboarding_profiles (user_id → users)
  ├── onboarding_images (user_id, category unique)
  ├── user_analysis_runs (user_id)
  │     └── user_derived_interpretations (analysis_snapshot_id)
  └── user_style_preference (user_id)

catalog_enriched (product_id unique)
  └── catalog_item_embeddings (product_id)
```
