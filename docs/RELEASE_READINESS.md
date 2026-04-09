# Release Readiness Criteria

This document defines the concrete checklist that must be green before Aura
ships beyond the current dev-complete state. It is the single source of
truth for "are we ready to put a real user in front of this?".

The checklist is split into four gates. Each gate is a hard block — you do
not advance to the next gate until the previous one is fully green.

The companion artifacts are:

- `docs/OPERATIONS.md` — dashboards and queries that back the metrics gates
- `ops/scripts/smoke_test_full_flow.sh` — end-to-end smoke test
- `ops/scripts/validate_dependency_report.py` — dependency report validator
- `docs/DESIGN_SYSTEM_VALIDATION.md` — manual UI QA checklist

---

## Gate 1 — Functional Correctness

The pipeline must produce a usable answer for every primary intent without
manual intervention.

- [ ] All 318 tests across `tests/` pass against the current branch
      (verified April 10, 2026: three outfit structures + all 46 attributes
      in query docs + parallel retrieval ~4x speedup + occasion-fabric
      coupling + time-of-day inference + role-category validation +
      outerwear recategorization + plan_type removed + catalog 14,296
      garment-only items, zero nulls, 90 accessories purged).
- [ ] `ops/scripts/validate_dependency_report.py` runs to completion with
      zero failed assertions.
- [ ] `ops/scripts/smoke_test_full_flow.sh` runs to completion against a
      staging backend with `pass > 0` and `fail = 0`.
- [ ] The catalog-unavailable guardrail (P0 — local env guard) fires when
      `catalog_item_embeddings` is empty, returning a clear user-facing
      message instead of an empty turn.
- [ ] The silent-empty-response guard (P0) is verified by the
      `test_pipeline_*` tests; the post-pipeline guard rewrites empty
      messages to a graceful fallback.
- [ ] The wardrobe-first hybrid pivot (P0) is exercised by at least one
      user-story test in the suite.
- [ ] Disliked products from `feedback_events` are excluded from
      `catalog_search_agent` retrieval results across turns (verified by
      `test_catalog_search_excludes_disliked_product_ids`).

## Gate 2 — Data & Environment Readiness

The environment we ship to must have the data the pipeline depends on.

- [ ] `catalog_enriched` has at least 500 rows with `row_status in ('ok','complete')`.
      (verified April 10, 2026: 14,296 items, all enriched, all embedded,
      zero null filter columns. Dead/delisted items cleaned up. Vastramay,
      Powerlook, CampusSutra re-embedded from DB via resync endpoint.)
- [ ] `catalog_item_embeddings` has the same row count as the embeddable
      subset of `catalog_enriched` (no orphan rows, no missing embeddings).
- [ ] All Supabase migrations under `supabase/migrations/` have been
      applied to the target environment (`ops/scripts/schema_audit.py`
      reports zero drift).
- [ ] `data/catalog/uploads/` has the most recent enrichment CSV the
      catalog admin team approved.
- [ ] At least one fully-onboarded test user exists with:
  - completed `onboarding_profiles` row (profile_complete + style_preference_complete + onboarding_complete)
  - both `full_body` and `headshot` images uploaded
  - completed `user_analysis_runs` row
  - non-empty `user_derived_interpretations`
  - at least 5 wardrobe items in `user_wardrobe_items`
- [ ] The above test user can complete a full chat → wardrobe-first → catalog
      hybrid → outfit-check journey via `ops/scripts/smoke_test_full_flow.sh`.

## Gate 3 — Observability & Operations

You cannot ship what you cannot watch.

- [ ] All 8 dashboard panels in `docs/OPERATIONS.md` exist in the chosen
      dashboard tool (Supabase Studio / Metabase / Grafana) and refresh on
      the cadence specified there.
- [ ] **Pipeline Health** panel shows zero empty responses and a defined
      error rate over the last 24h.
- [ ] **Catalog-unavailable guardrail** panel shows zero hits in production
      and is documented as a "ring oncall" alert if it goes non-zero.
- [ ] **Negative signals** panel is reviewed daily during the first week of
      rollout. If any single product appears in the top-disliked list for
      more than 3 distinct users, the catalog row is audited and either
      fixed or hidden.
- [ ] An on-call rotation exists with documented escalation steps for:
  - empty responses spike
  - catalog/embeddings missing
  - feedback dislikes spike on a single product
  - dependency report shows acquisition_source = unknown for >50% of
    new users (instrumentation regressed)
- [ ] Logs from `_log.error` / `_log.warning` in `orchestrator.py`,
      `catalog_search_agent.py`, and `outfit_assembler.py` are captured
      somewhere queryable (cloud logging, Logflare, etc.) — not just stdout.

## Gate 4 — Product & UX

The user-facing surface must hold up to a stylist's scrutiny.

- [ ] All items in `docs/DESIGN_SYSTEM_VALIDATION.md` are checked by an
      actual designer (not the implementing engineer).
- [ ] Mobile (430px width) and desktop (≥1280px) variants of every primary
      view (`/`, `/wardrobe`, `/profile`, results page, chat) have been
      walked through end-to-end on real devices, not just devtools.
- [ ] The chat homepage uses one dominant primary CTA + progressive
      disclosure for secondary actions (P0 — Single-Page Shell).
- [ ] Wardrobe-first answers explicitly name the selected pieces and
      explain *why* they fit; single-item wardrobe answers either pivot
      to hybrid or explicitly say what is missing (P1 — Partial Answer UX).
- [ ] Follow-up suggestions render as labelled groups (Improve It /
      Show Alternatives / Shop The Gap), driven by the structured
      `follow_up_groups` field in metadata, not substring matching.
- [ ] All copy has been reviewed for the "stylist, not a dashboard" tone
      (P0 — Design System Realignment).

---

## Sign-off

A release is ready when **every box above is checked** AND the following
two humans have signed:

- [ ] Engineering owner: ____________
- [ ] Design / product owner: ____________

Date: ____________

Branch / commit shipped: ____________

---

## What is *not* in scope for the first-50 release

These are explicit non-goals — do not block the release on them:

- WhatsApp inbound runtime (deliberately removed; rebuilding separately)
- Virtual try-on feedback loop (P2 — try-on quality complaints handler)
- First-50 recurring-intent analysis dashboard (separate workstream)
- Pairing-pipeline anchor enforcement edge cases (architect-side queries
  for the anchor's role still slip through occasionally)
