# Sigma Aura

> **Personal Fashion Copilot** — Stylist for retention, shopping for revenue.

For people who want to dress better every day, Aura is a personal fashion copilot that knows your body, your style, and your wardrobe — so you always know what to wear and what's worth buying.

## System Architecture

> **[Open Architecture Diagram](docs/fashion-ai-architecture.html)** — download and open in any browser for the full interactive SVG diagram.

The system is organized in six layers:

| Layer | Purpose |
|-------|---------|
| **Entry Surfaces** | Web app (onboarding, chat, wardrobe, profile), chat management, wardrobe studio, catalog admin |
| **User Intelligence** | Onboarding, 3-agent analysis pipeline, interpretations, digital draping, style profile, confidence engines |
| **Intent Runtime** | Intent registry (StrEnum, 12 intents, 9 actions), copilot planner, orchestrator, dedicated handlers, recommendation pipeline (architect → search → assemble → evaluate), wardrobe engine, virtual try-on |
| **Output & Experience** | Response formatter, 3-column PDP cards, chat UI, wardrobe UI, profile UI |
| **Safety & Trust** | Image moderation (dual-layer), policy engine, comfort learning, feedback loop, dependency instrumentation |
| **Data Stores** | User data, conversations, wardrobe, catalog (pgvector), try-on media, telemetry |

## Use Cases

- **Dress Me** — Occasion outfit recommendations (wardrobe-first, catalog, or hybrid)
- **Style This** — Pairing suggestions around an anchor garment
- **Check My Outfit** — Outfit critique with wardrobe swap suggestions
- **Should I Buy?** — Shopping decision with buy/skip verdict
- **What Suits Me?** — Profile-grounded style discovery and advice
- **Plan a Trip** — Duration-aware capsule/trip wardrobe planning
- **Try It On Me** — Virtual try-on via Gemini image generation

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Backend** | Python, FastAPI |
| **Database** | Supabase (PostgreSQL + pgvector) |
| **Frontend** | Server-rendered HTML/CSS/JS (no framework) |
| **LLM** | gpt-5.4 (planner, architect, evaluator, analysis), gpt-5-mini (catalog enrichment) |
| **Embeddings** | text-embedding-3-small (1536 dimensions) |
| **Try-On** | gemini-3.1-flash-image-preview (Google Gemini API) |

## Quick Start

```bash
# Configure environment
cp .env.example .env.local
# Fill in: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, GEMINI_API_KEY

# Start the app
APP_ENV=local python3 run_agentic_application.py --reload --port 8010

# Run tests
python3 -m pytest tests/ -v
```

## Project Stats

- 36 Supabase migrations
- 268 tests (92 agentic + 38 qna + 138 other)
- 12 intent types, 9 action types, 7 follow-up types (StrEnum registry)
- 50+ catalog enrichment attributes
- 46 wardrobe enrichment attributes

## Documentation

**Source of truth:** `docs/CURRENT_STATE.md`. When any doc below disagrees
with it, `CURRENT_STATE.md` wins.

| Document | Purpose |
|----------|---------|
| [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) | **Source of truth.** Project state, gap analysis, execution checklist, parked architectural decisions |
| [`docs/PRODUCT.md`](docs/PRODUCT.md) | Product definition, personas, user journey, stories |
| [`docs/DESIGN.md`](docs/DESIGN.md) | Design system, visual language, UX patterns, component rules |
| [`docs/RELEASE_READINESS.md`](docs/RELEASE_READINESS.md) | 4-gate release checklist (functional / data / observability / product-UX) |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | 8 dashboard panels + SQL queries for the first-50 rollout |
| [`docs/DESIGN_SYSTEM_VALIDATION.md`](docs/DESIGN_SYSTEM_VALIDATION.md) | Manual design QA checklist (9 device journeys + tone audit) |
| [`docs/APPLICATION_SPECS.md`](docs/APPLICATION_SPECS.md) | Implementation spec (⚠️ *partially deprecated* — see banner at top) |
| [`docs/INTENT_COPILOT_ARCHITECTURE.md`](docs/INTENT_COPILOT_ARCHITECTURE.md) | Target system architecture (⚠️ *pre-planner-inlining era* — some sections stale) |
| [`docs/WORKFLOW_REFERENCE.md`](docs/WORKFLOW_REFERENCE.md) | Human-facing reference for per-intent execution flows (not loaded at runtime) |
| [`docs/fashion-ai-architecture.html`](docs/fashion-ai-architecture.html) | Visual architecture diagram (open in browser) |

## Module Structure

```
modules/
├── agentic_application/   # Main runtime: API, orchestrator, agents, services
├── platform_core/         # Config, repositories, REST client, UI, schemas
├── user/                  # Onboarding, analysis, draping, wardrobe, style
├── catalog/               # Admin, enrichment, retrieval, embeddings
└── user_profiler/         # User profiling utilities
```
