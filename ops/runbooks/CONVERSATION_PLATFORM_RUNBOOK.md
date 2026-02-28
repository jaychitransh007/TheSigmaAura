# Conversation Platform Runbook

Last updated: February 24, 2026

## Purpose
Run the conversation agentic styling API locally using local Supabase + existing modules.

## Prerequisites
- Local Supabase CLI installed and available as `supabase`.
- Docker daemon running locally (Supabase local stack dependency).
- Local Supabase running (`supabase start`).
- `OPENAI_API_KEY` and `SUPABASE_SERVICE_ROLE_KEY` in `.env`.
- Enriched catalog available at `data/catalog/enriched_catalog.csv`.

## 1) Start local Supabase
```bash
supabase start
```

Get local service-role key and copy into `.env`:
```bash
supabase status
```

Expected local ports for this project:
- API/REST: `55321`
- DB: `55322`
- Studio: `55323`
- Mailpit: `55324`
- Analytics: `55327`

Set `.env` for conversation platform:
```bash
SUPABASE_URL=http://127.0.0.1:55321
SUPABASE_SERVICE_ROLE_KEY=<local-secret-from-supabase-status>
```

Or export both dynamically for current shell:
```bash
eval "$(supabase status --output env | sed -n 's/^API_URL=/export SUPABASE_URL=/p; s/^SERVICE_ROLE_KEY=/export SUPABASE_SERVICE_ROLE_KEY=/p')"
```

## 2) Apply schema migration
```bash
supabase db reset
```

Migration file used:
- `supabase/migrations/20260224160000_conversation_platform.sql`

## 3) Run conversation API server
```bash
python3 run_conversation_platform.py --host 127.0.0.1 --port 8010
```

Open conversational interface in browser:
```bash
open http://127.0.0.1:8010/
```

## 4) Create conversation
```bash
curl -s -X POST http://127.0.0.1:8010/v1/conversations \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"user_123"}'
```

## 5) Create turn (image + text)
```bash
curl -s -X POST http://127.0.0.1:8010/v1/conversations/<conversation_id>/turns \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id":"user_123",
    "message":"I need work looks and one evening option.",
    "image_refs":["/absolute/path/to/user_photo.jpg"],
    "strictness":"balanced",
    "hard_filter_profile":"rl_ready_minimal",
    "max_results":12
  }'
```

## 6) Create iterative turn (text only)
```bash
curl -s -X POST http://127.0.0.1:8010/v1/conversations/<conversation_id>/turns \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id":"user_123",
    "message":"Make it more formal and less embellished.",
    "strictness":"safe",
    "hard_filter_profile":"rl_ready_minimal",
    "max_results":10
  }'
```

Recommendation routing behavior:
- Garment-specific asks (e.g., "show shirts", "need jeans") return garment-mode recommendations.
- Non-specific asks default to outfit-mode where complete garments and combos compete.

## 7) Log feedback
```bash
curl -s -X POST http://127.0.0.1:8010/v1/feedback \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id":"user_123",
    "conversation_id":"<conversation_id>",
    "recommendation_run_id":"<run_id>",
    "garment_id":"<garment_id>",
    "event_type":"buy",
    "notes":"Purchased after comparison"
  }'
```

In web UI (`/`), feedback is also captured directly from recommendation cards:
- `Like`
- `Share`
- `Buy Now`

## API Endpoints
- `GET /healthz`
- `GET /` (web conversational interface)
- `POST /v1/conversations`
- `GET /v1/conversations/{conversation_id}`
- `POST /v1/conversations/{conversation_id}/turns`
- `POST /v1/conversations/{conversation_id}/turns/start` (async turn with stage progress)
- `GET /v1/conversations/{conversation_id}/turns/{job_id}/status` (poll stage progress)
- `GET /v1/recommendations/{run_id}`
- `POST /v1/feedback`

## Eval Workflow
Run prompt-suite quality evaluation (scores + logs + integrity checks):
```bash
python3 ops/scripts/run_conversation_eval.py \
  --base-url http://127.0.0.1:8010 \
  --strictness balanced \
  --hard-filter-profile rl_ready_minimal \
  --max-results 3 \
  --result-filter complete_only \
  --image-ref data/logs/user_profiler/input_09322a34663f.webp \
  --out-dir data/logs/evals \
  --fail-on-integrity
```

See full eval operations guide:
- `ops/runbooks/CONVERSATION_EVAL_RUNBOOK.md`
