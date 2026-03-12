# Supabase Sync Runbook

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
APP_ENV=staging python3 run_conversation_platform.py --host 127.0.0.1 --port 8010
```

## Run App Against Local
```bash
APP_ENV=local python3 run_conversation_platform.py --host 127.0.0.1 --port 8010
```

## Run Catalog Embeddings Against Staging
```bash
ENV_FILE=.env.staging \
PYTHONPATH=modules/catalog_retrieval/src:modules/user_profiler/src:modules/conversation_platform/src \
python3 -m catalog_retrieval.main \
  --input data/catalog/enriched_catalog.csv \
  --documents-output data/catalog/embeddings/catalog_documents_sample.jsonl \
  --embeddings-output data/catalog/embeddings/catalog_embeddings_sample.jsonl \
  --max-rows 5 \
  --embed \
  --save-supabase
```
