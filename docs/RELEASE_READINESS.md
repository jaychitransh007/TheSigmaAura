# Release Readiness Criteria

Last updated: May 18, 2026.

> **RELEASE TARGET (May 18, 2026).** The 4 gates below describe the readiness criteria for the *legacy standalone Aura web app* (port 8010 server-rendered HTML chat). The Shopify-hosted system has shipped on top of that and is now multi-tenant:
>
> - Customer experience ships as a **Shopify storefront** (`thesigmavibe.shop`, live) + a **Vibe Shopify App** (Vercel `bom1`, live at `vibe-app-five.vercel.app`).
> - **Engine deployed to Fly.io Mumbai** (`vibe-engine.fly.dev`, shared-cpu-1x always-on) with persistent `vibe_data` volume mounted at `/app/data` and `strategy = "immediate"` deploys.
> - **Multi-tenant catalog now live** (F.2.x + F.3 + F.4, May 18). `tenants` table, opaque `tenant_id`, per-tenant `catalog_enriched` + `catalog_item_embeddings`, tenant-scoped retrieval RPC `match_catalog_item_embeddings_v2`. Idempotent install-time bootstrap with browser-driven SyncProgressCard. Vision attribute enrichment via OpenAI Batch API + poller. `products/{create,update,delete}` webhooks for real-time catalog updates. Daily Vercel cron for drift safety net + enrichment polling. Two tenants live: TheSigmaVibe production + Vibe Test dev store.
> - **Conversation page live** at `/apps/vibe/style` at full feature parity with the legacy `platform_core/ui.py` reference. In-chat onboarding flow (D.O.1–D.O.3): branched welcome, parallel photos + gender-DOB cards, HEIC handling, photo zoom/pan, combined ft/in height-waist card, post-onboarding analysis indicator + templated "what would you like to wear?" prompt.
> - **Add-to-Cart end-to-end working** (PR #474): response_formatter now passes `shopify_variant_ids` + `shopify_product_id` + `catalog_description` through to the storefront. PR #475 added a regression guard (`aura_outfit_item_variant_ids_missing_total` + WARNING log) so this bug class can't reappear silently.
> - **Shopify Customer Account merge** (D.S.3b) wired via `POST /v1/users/merge`, IDOR-guarded.
> - **Observability** — engine: `aura_turn_total{channel}`, `aura_user_merge_total{status}`, `aura_onboarding_endpoint_total{endpoint, status, channel}`, `aura_onboarding_image_bytes{category, channel}`, plus the F.2.x sweep added in #475/#476 (`aura_outfit_item_variant_ids_missing_total`, `aura_bootstrap_batch_total{status}` + per-outcome histogram, `aura_product_webhook_total{topic, status}`, `aura_enrichment_batch_total{status}` + row-count totals, `aura_catalog_status_change_total{action}`), plus #498 (`aura_theme_overrides_patch_total{outcome}`). Vibe: JSON-to-stdout structured logs (`vibe_init_outcome`, `vibe_merge_outcome`, `vibe_turn_pairing_rewrite`, `vibe_bootstrap_tick`, `vibe_cron_daily_sync_*`, `vibe_product_webhook_*`, `vibe_theme_overrides_refresh`, `vibe_menu_injection_outcome`, `vibe_navigation_menu_{lookup,update}_failed`, `vibe_tenant_lookup_failed`) via [`vibe-app/app/lib/logger.server.ts`](../vibe-app/app/lib/logger.server.ts).
> - The standalone web UI is deprecated. Gates 3 (dependency/retention) and Gate 4 (design polish) targeting `platform_core/ui.py` are no longer the release blocker.
> - **Remaining release blockers** for first-50 rollout, tracked in [`OPEN_TASKS.md`](OPEN_TASKS.md) § Next priorities: **`shopify app deploy`** (registers F.4 webhook subscriptions), **B.6** (real-card test order), **B.4** (mandatory legal pages), **D.P.1** (install on production — unblocks **B.8** GID capture which activates Add-to-Cart end-to-end on prod).
>
> See **Recently Shipped — May 18** below for what's already in place.

This document defines the concrete checklist that must be green before Aura
ships beyond the current dev-complete state. It is the single source of
truth for "are we ready to put a real user in front of this?".

The checklist is split into four gates. Each gate is a hard block — you do
not advance to the next gate until the previous one is fully green.

The companion artifacts are:

- `docs/OPEN_TASKS.md` — **canonical current state, Phase D plan, locked infrastructure**
- `docs/OPERATIONS.md` — dashboards and queries that back the metrics gates
- `ops/scripts/smoke_test_full_flow.sh` — end-to-end smoke test
- `ops/scripts/validate_dependency_report.py` — dependency report validator
- `docs/DESIGN_SYSTEM_VALIDATION.md` — manual UI QA checklist

---

## Recently Shipped — May 18, 2026 (Multi-tenant catalog — F.2.x + F.3 + F.4 + observability sweep)

The largest single-day push of the project. The engine went from single-catalog to fully multi-tenant on the read path; the Vibe app installs and bootstraps a merchant's catalog end-to-end; product webhooks keep the catalog fresh in real time; a daily cron is the safety net + enrichment poller.

### Multi-tenant retrieval foundation (F.2.0/F.2.1)
- **PR #458** ([docs](../docs/OPEN_TASKS.md)) — F.2.1 spike validated HNSW iterative scan with tenant filter at 0.035% selectivity (5 rows out of 14,242) returns all rows in 185ms with `max_scan_tuples=20000`.
- **PR #459** — `tenants` table + `catalog_item_embeddings.tenant_id` + new RPC `match_catalog_item_embeddings_v2(p_tenant_id, ...)` that RAISEs on empty tenant. Backfilled 1,065 orphan rows to TheSigmaVibe.

### Idempotent install-time catalog sync (F.2.2 + F.2.2c)
- **PR #460/#461** — `CatalogBootstrapService.process_products` with per-product existence check (cache-hit refreshes metadata only, no LLM cost; cache-miss embeds + inserts). Tenant-prefixed `product_id` avoids global UNIQUE collision when two tenants import the same Shopify GID. HTML stripping for `descriptionHtml` before embedding.
- **PR #462/#463** — Browser-driven `SyncProgressCard` on the merchant home runs a polling loop against `/app/api/bootstrap` (new route). Each tick fetches one Shopify Admin GraphQL page (50 products), forwards to engine, returns cursor + done. Engine `bootstrap-complete` flips status to `ready` once pagination exhausts. Review fixes: server-side tenant derivation from `session.shop` (no body-trust), GraphQL error detection (don't false-complete on throttle), loader-failure banner.

### Vision attribute enrichment (F.2.2b)
- **PR #464** + **#468** UUID fix + **#472** ingest fix — OpenAI Batch API submit + poll. Migration adds `tenant_enrichment_batches` table + `catalog_enriched.vision_batch_id`. Cost-bearing invariant SQL-enforced: `row_status='pending_enrichment' AND vision_batch_id IS NULL`. Auto-submitted at `bootstrap_complete`. PR #472 fixed the ingest to mirror the 8 retrieval-filter columns to `catalog_item_embeddings` under the canonical lowercase mapping — without this, vision data landed but every retrieval filter excluded every row.

### Real-time product webhooks (F.4)
- **PR #465** + **#467** review fixes + **#470** revival — `products/{create,update,delete}` webhooks via two handlers ([webhooks.products.upsert.tsx](../vibe-app/app/routes/webhooks.products.upsert.tsx), [webhooks.products.delete.tsx](../vibe-app/app/routes/webhooks.products.delete.tsx)) forwarding to engine. Soft-delete only on `products/delete` (preserves vision enrichment cost). Topic-aware revival: only `products/create` clears `deleted_at` (protects against out-of-order `products/update` retries). Migration adds `available_for_sale` + `deleted_at` columns; retrieval RPC filters `IS NOT FALSE`.

### Daily catalog sync cron (F.3)
- **PR #466** + **#467** + **#470** — Vercel cron at 19:30 UTC. Per-tenant incremental Shopify walk (`updated_at:>=30h`), forwards to bootstrap-batch with `revive_soft_deleted=true` so cron-walks revive prior soft-deletes. Then `enrichment/submit-pending-all` + `enrichment/poll-all` to keep vision enrichment caught up. `CRON_SECRET` validated; soft 45s budget; tenants ordered oldest-`last_sync_at`-first.

### Storefront wiring fixes
- **PR #471** — threaded `shop_domain` from the App Proxy URL params into `startTurn` for both `apps.vibe.style` + `apps.vibe.api.check`. Engine's `resolve_tenant_id` refused to default for `vibe_storefront` channel; this had been quietly 500ing every customer turn since F.2.0 landed.
- **PR #473** — `pollTurn` resilience: 8s → 20s abort timeout + soft-fail on transient (return `status="running"` so the storefront keeps polling instead of bubbling abort up as 500).
- **PR #474** — **Cart-wiring fix**. `response_formatter._build_item_card` was silently dropping `shopify_variant_ids` + `shopify_product_id` + `catalog_description` + `is_anchor`. Every catalog item shipped to the storefront had `shopify_variant_ids={}`, which the cart code treats as "catalog hasn't finished syncing". Affected all tenants going through the catalog pipeline since F.2.x — we just hadn't exercised Add-to-Cart on a freshly-bootstrapped tenant before.

### Observability sweep (#475 + #476)
- **PR #475 (critical)**: `aura_outfit_item_variant_ids_missing_total` + WARNING log (would have caught #474 immediately); `aura_bootstrap_batch_total{status}` + per-outcome histogram + `vibe_bootstrap_tick` structured logs; `aura_product_webhook_total{topic, status}` + engine-side tenant context in `CatalogProductSyncService` logs.
- **PR #476 (medium)**: `aura_enrichment_batch_total{status}` + `aura_enrichment_rows_{ingested,failed}_total`; `aura_catalog_status_change_total{action}` ticks separately on webhook revive vs cron revive vs soft-delete.

### End-to-end verified on Vibe Test
- Tenant row `t_IIZj3vNuxRMAAAAAago064SQLXlPuQMq` (`vibe-test-nmt8wy3q.myshopify.com`), 60 products bootstrapped, vision batch ingested (58/60 — 2 image-less products correctly skipped), all 8 retrieval filter columns populated. Customer storefront `/apps/vibe/style` returns real outfit recommendations ("Raven Angle Top + Black Edge Pants" for "sexy date night"), Buy Now / Add to Cart resolve to real variant gids.

### What's next
**Launch-blocking chain (user action):** `shopify app deploy` (registers F.4 webhook subscriptions) · B.4 legal pages · B.6 real-card test · D.P.1 install on production · B.8 GID capture (script in [scripts/seed_thesigmavibe_catalog/](../scripts/seed_thesigmavibe_catalog/)) · D.C.9 cart verify on prod.

**Then:** Phase G (order webhooks + attribution) · D.M.2/.3/.4/.5 (admin pages) · Phase C completion (engine multi-tenancy beyond catalog — required before tenant #3).

---

## Recently Shipped — May 18, 2026 — afternoon push (Theme inheritance + replicated MerchantHeader + 2026-04 API drift)

A separate push, same day. The catalog work shipped in the morning; the afternoon was about making `/apps/vibe/*` pages look + behave like part of the host store rather than an embedded widget.

### Theme inheritance + `theme_overrides` PATCH (#478, #480, #483–#486, #494, #496)
- New engine endpoint `PATCH /v1/tenants/{tenant_id}/theme-overrides` ([api.py](../modules/agentic_application/src/agentic_application/api.py)) writes a per-tenant `theme_overrides` JSONB column: `font_body`, `color_primary`, `color_background`, `color_text`, `logo_url`, `shop_name`, `main_menu`.
- `readMerchantThemeOverrides` ([theme-settings.server.ts](../vibe-app/app/lib/theme-settings.server.ts)) probes the merchant's active theme's `config/settings_data.json` (Dawn / Studio / Refresh fallback chain for the font + colors), `shop.brand.logo.image.url`, `shop.name`, and the `main-menu` top-level items via Admin GraphQL.
- Admin home loader ([app._index.tsx](../vibe-app/app/routes/app._index.tsx)) refreshes on every load with a `themeOverridesDiffer` check so unchanged-content PATCHes are skipped (avoids `updated_at_iso` churn). `themes/update` webhook handles ongoing drift.
- Colors validated by anchored regex (`^rgba?\([^)]+\)$` or `^#[0-9a-f]{3,8}$`) before injection — prevents CSS injection via malformed theme values.

### Replicated MerchantHeader on `/apps/vibe/*` (#479, #491, #492, #495, #496, #497)
- New [merchant-header.tsx](../vibe-app/app/components/merchant-header.tsx) replaces the AURA-branded conv-header on customer-facing Vibe pages. Consumes `theme_overrides` via the loader.
- **Logo**: brand asset image from `shop.brand.logo`; falls back to `shop_name` text; placeholder reads "Vibe".
- **Nav**: merchant's `main-menu` items + the two Vibe-owned destinations get an active underline. Mixed-case / theme-font (no forced UPPERCASE, no forced Fraunces).
- **Utility icons**: search → `/search`, account → `/account` (or `/account/login` if anonymous), cart → `/cart` with live item-count badge from `/cart.js`. `useCartCount` re-fetches on `visibilitychange` so the badge updates after add-to-cart in another tab.
- **Chrome**: white background by default, `color-mix(in srgb, currentColor, transparent N%)` borders that adapt to dark themes. `<style>` injection from [theme-overrides.tsx](../vibe-app/app/components/theme-overrides.tsx) sets `--theme-color-primary` / `--theme-font-body` / `--theme-color-background` / `--theme-color-text` at `:root`.
- **Chat body**: canvas flipped to `#ffffff` (was Confident Luxe cream). User messages render in a soft chip (`--user-message-bg: #f5f0e8`, left-aligned, content-sized).

### Menu navigation injection — "Find your Vibe" + "Your Vibes" (#481, #482 self-review, #487, #488, #489, #490)
- `ensureVibeMenuItems` ([navigation.server.ts](../vibe-app/app/lib/navigation.server.ts)) idempotently writes the two Vibe-owned items into the merchant's `main-menu` linklist via `menuUpdate`. Run on every admin home load.
- `removeVibeMenuItems` runs from the `app/uninstalled` webhook so the merchant's nav stays clean after uninstall.
- Round-trips existing item IDs (in-place update; previously stripped IDs → re-creates with new IDs on every load).
- Fetches three levels of `items` nesting so deeper menus aren't silently truncated by the wholesale-replace semantics of `menuUpdate`.
- **New scope**: `write_online_store_navigation` (replaces an invalid `write_navigation` first try). Existing installs get an inline re-grant nudge via App Bridge `scopes.request(...)`.

### 2026-04 Admin GraphQL drift fixes — three back-to-back live breaks
Surfaced one-by-one only after the previous fix let the next call reach the API:
- **#487** — `menu(handle: "main-menu")` removed in 2026-04. Replaced with `menus(first: 50)` index + handle filter, then `menu(id: $id)` for the chosen menu. Two-step lookup applied to both [navigation.server.ts](../vibe-app/app/lib/navigation.server.ts) and [theme-settings.server.ts](../vibe-app/app/lib/theme-settings.server.ts).
- **#489** — `menuUpdate(items:)` arg type changed from `[MenuItemCreateInput!]!` → `[MenuItemUpdateInput!]!`. Round-trip the `id` field on every item.
- **#490** — `MenuItemType` enum dropped `FRONTEND_LINK`. Vibe items now `HTTP`; explicit rewrite of any legacy `FRONTEND_LINK` so cached items don't reject the whole mutation.
- A parallel codebase sweep (Explore agent) confirmed the remaining GraphQL surfaces (`themes(first: 1)`, products pagination, webhooks) are clean against 2026-04.

### Theme + menu observability (#498)
- Engine: `aura_theme_overrides_patch_total{outcome}` counter (`applied | error`) via `observe_theme_overrides_patch` ([metrics.py](../modules/platform_core/src/platform_core/metrics.py)), wired into the PATCH handler at the happy path + both `HTTPException` paths.
- Vibe-app: structured JSON events via [`logger.server.ts`](../vibe-app/app/lib/logger.server.ts) — `vibe_theme_overrides_refresh{outcome=applied|skipped_unchanged|skipped_empty_probe|failed}` (applied case carries `has_logo`, `has_font`, `has_color_primary`, `menu_items_count` for coverage queries); `vibe_menu_injection_outcome{outcome=added|already_present|skipped|failed}`; `vibe_navigation_menu_lookup_failed` / `vibe_navigation_menu_update_failed` with `stage` labels (replaces 6 `console.warn` sites); `vibe_tenant_lookup_failed` replaces a `console.error`.

### What's next (afternoon push)
Theme/menu infrastructure is fully wired. Optional follow-ups: announcement-bar replication, Shopify Markets currency selector, client-side cart-fetch beacon (needs new endpoint). None are launch-blocking.

---

## Recently Shipped — May 17, 2026 (Vibe parity, hardening, observability)

A focused day on Vibe feature parity + post-launch hardening + observability gaps after the prior May-16 audit.

### Vibe app — feature parity + UX hardening
- **Try-on images, garment descriptions, PDP carousel, attachment composer** restored to parity with legacy Aura (PR #402).
- **Pairing-trigger auto-augmentation** (#403): action appends "Build an outfit around this attached piece" whenever any attachment (image / wardrobe / wishlist) is present, so the engine planner reliably routes attached turns through `pairing_request`. The user's bubble keeps their original prose.
- **UI polish wave** (PRs #404 / #405 / #406 / #407 / #408 / #411 / #412 / #413 / #414 / #415 / #419 / #420 / #421 / #422): chip-in-pill composer with single-line input, baseline-aligned `+` button, IDOR guards on `shopify:`-prefixed sessions + AbortController for fetch cancellation, scrollbar-shift fix on body scroll lock, picker fetch-state reset on URL change, per-item size chips, catalog descriptions for PDP, anchor item first in lists, consistent CTA placement with mobile override.
- **Wardrobe + wishlist pickers in `+` popover** (#410), proxying engine-served images through `apps.vibe.api.tryon-image` so raw `data/...` paths render in the browser.
- **Photos-card re-injection** (#422): when the engine reports no `full_body` row (volume rebuild / manual delete), Vibe re-emits the photos card regardless of the customer's localStorage onboarding step.
- **In-chat onboarding refinements**: `name` step removed entirely (#424); combined height + waist card with ft/in segmented inputs (#425); post-onboarding analysis-running indicator + templated `WHAT_LOOKING_FOR_PROMPT` once analysis completes (#425).
- **Anonymous returning customers no longer re-onboarded on reload** (#426): init action now fetches `getOnboardingStatus` for the localStorage UUID directly (the loader could only do that for Shopify-logged-in customers).
- **Init action resilience** (#432): `Promise.allSettled` fan-out so a transient failure in any single engine call (resolve / ensure-profile / status) degrades gracefully instead of 500ing.
- **`getOnboardingStatus` three-way return** (#434 / #435): `OnboardingStatus | null | undefined` distinguishes confirmed new customer (404) from engine error; init applies the "assume profile exists" safety net only for the error case. Mock-mode returns a populated `OnboardingStatus` so the welcome-back UX is preserved; literal-null JSON bodies are narrowed before field access.

### Engine + infra
- **Persistent storage on Fly** (#416): `vibe_data` volume mounted at `/app/data`. Pre-fix, every `fly deploy` wiped onboarding photos / wardrobe / try-on renders. Migration adds `vibe_storefront` to the `source_channel` CHECK constraint (#417 makes each ALTER guard against missing tables for offline migrations).
- **Deploy strategy** (#418 / #431 / #433): switched to `strategy = "immediate"` — the only Apps v2 strategy compatible with single-machine + single-volume (rolling, canary, bluegreen all deadlock because they need the new machine to claim the volume before the old releases it).
- **Orchestrator carry-forward removed** (#430): the previous turn's `attached_item` no longer auto-anchors the next turn. Reloading a conversation with no attachment now produces an attachment-free turn instead of silently re-anchoring on a stale wardrobe piece.

### Observability — engine
- **`aura_onboarding_endpoint_total{endpoint, status, channel}`** (#436): per-route success/failure counter for all seven Vibe onboarding endpoints (`profile_ensure`, `profile_partial`, `image_upload`, `status_read`, `wardrobe_list`, `analysis_start_phase{1,2}`, `analysis_status_read`). All routes now accept `?channel=` (default `web`); the Vibe client threads `vibe_storefront`.
- **`aura_onboarding_image_bytes{category, channel}`** (#436): upload-size distribution for `full_body` / `headshot` photos. Surfaces regressions in the client-side crop pipeline + creep toward the 10MB cap.
- **Structured logs**: `event=onboarding_endpoint` lines from the `aura.onboarding` logger carry `user_id` + per-route context (`size_bytes`, `has_row`, `fields`, etc.) for grep-by-user debugging.

### Observability — Vibe app
- New helper [`vibe-app/app/lib/logger.server.ts`](../vibe-app/app/lib/logger.server.ts) emits JSON-to-stdout (captured by Vercel Logs + any drain; no Sentry/Datadog dep). Events shipped on Remix action paths:
  - `vibe_init_outcome` — three-way `getOnboardingStatus` result (`ok` / `not_found` / `error`) + ensure-profile outcome + derived `has_profile`. Re-onboarding bugs previously surfaced only via customer reports.
  - `vibe_merge_outcome` — success/failure of `/v1/users/merge` + ensure-profile-on-canonical.
  - `vibe_merge_identity_mismatch` (warn) — the 403 IDOR rejection path; security-relevant.
  - `vibe_turn_pairing_rewrite` — logged on every turn, flags whether the silent message augmentation fired + which attachment kind triggered it.

### What's next
Unchanged from the May 13–16 list — **D.M.1**, **D.C.3** (Wardrobe), **D.C.4** (Looks), **D.C.5** (Outfit Check), **B.4 / B.6**, **D.P.1** (production install + B.8 GID capture), **D.S.4** (remaining GDPR webhooks).

---

## Recently Shipped — Shopify pivot (May 13–16, 2026)

A major architectural pivot from standalone Aura to a Shopify-hosted product. All three deployments are now live.

### Storefront
- **`thesigmavibe.shop` live** on Shopify (custom domain + `q8pery-95.myshopify.com` canonical, `the-vibe-shop-9376.myshopify.com` alias).
- **13,177 products imported** via per-vendor CSVs from `scripts/seed_thesigmavibe_catalog/`: templatized descriptions (Option 3 — aspirational + playful, no cheekiness, no LLM), 5 size variants (XS–XL), 20% markup baked in, `vibe.*` metafields capture `tenant_id`/`source_url`/`source_retailer`/`source_product_id`/`enriched_id`.
- Brand vocabulary: 10 retailers mapped to display names in `brands.py` (Koskii, Showoffff, Taruni, Nicobar, Vastramay, Powerlook, Campus Sutra, Off Duty, Fawn24, Virgio).
- Razorpay + GST + India shipping + size chart configured.
- Hero copy locked ("Style that gets you."), hero image generated via Imagen.
- 1,065 missing-price rows dropped from import.

### Vibe Shopify App
- **Scaffolded with Shopify Remix + Polaris + App Bridge** template (`vibe-app/` at worktree root).
- **Deployed to Vercel** at `https://vibe-app-five.vercel.app` (May 15).
- **OAuth + install flow working** on dev store `vibe-test-nmt8wy3q.myshopify.com`.
- **App Proxy validated end-to-end** (May 15): `thesigmavibe.shop/apps/vibe/*` renders pages from the Vercel-deployed Remix backend via HMAC-signed Shopify forwarding. `proxy.$.tsx` route + `authenticate.public.appProxy()` validate signatures.
- **Prisma session store** migrated from SQLite to Postgres on Supabase, isolated in `vibe` schema (engine's `public` schema untouched).
- Partner org "Vibe" + Partner email `mj.nigam28@gmail.com`. App `client_id = 937540a1df123dfcd486426ede2b3722`.

### Vibe Engine
- **Deployed to Fly.io Mumbai** (May 15) — `vibe-engine.fly.dev`, shared-cpu-1x 1GB always-on, `/healthz` checked every 30s. Co-located with Vercel `bom1` for intra-Mumbai RTT (~5–20ms).
- **`vibe_storefront` channel** (May 16, #367) bypasses the onboarding gate so anonymous / partial-profile customers can chat. `web` channel keeps the legacy strict path.
- **Identity-merge endpoint** `POST /v1/users/merge` (D.S.3b, #375) reassigns conversations + history rows from anonymous UUID to `shopify:{customer_id}` on Shopify Customer Account sign-in.
- **Onboarding ensure-profile endpoint** `POST /v1/onboarding/profile/ensure` (#372) creates an `onboarding_profiles` row on demand for OTP-less Vibe customers.
- **Observability** (#398): `aura_turn_total{channel}` and `aura_user_merge_total{status}` Prometheus counters.

### Vibe Shopify App — customer surface
- **Conversation page** live at `/apps/vibe/style` (D.C.2 a–g, May 15–16) — branched welcome, real engine integration, mock-mode fallback, async-poll turn loop, outfit cards with try-on / Buy CTAs / size chips.
- **In-chat onboarding** (D.O.1–D.O.3, May 16, #370 → #396):
  - Photos card (2-up, save + skip) with HEIC client-side transcode + photo zoom/pan inside the card frame.
  - Gender + DOB card (chip selector + DD/MM/YYYY segmented input, save-only).
  - Name / height / waist FieldCards (sequential after the initial cards resolve).
  - Branched welcome (returning customer w/ engine `gender` set → "welcome back"; new → onboarding cards stacked).
  - localStorage persistence of resolved kinds + current step so reload doesn't lose progress.
- **Identity** (D.S.3a/3b): localStorage UUID for anonymous, Shopify Customer Account merge on sign-in. Sign-in pill in header.
- **Add-to-Cart wired** end-to-end (D.C.7 + #374): engine `OutfitItem` now carries `shopify_product_id` + `shopify_variant_ids`. Activates the moment **B.8** runs on a store that has the catalog imported.

### Infrastructure decisions locked
- **No tunnels.** Cloudflare quick-tunnels, ngrok free, localtunnel, Pinggy free all fail in BLR/BOM regions. Solution: deploy directly to Vercel + Fly.io.
- **Vercel Hobby** for Vibe app, functions pinned to `bom1`. **Fly.io Mumbai** for engine.
- **`tenant_id` scheme locked**: `t_<base64url(sha256(shop_domain)[:8] || timestamp || random_bytes(8))>`. TheSigmaVibe's id: `t_Oq0BSHnewiEAAAAAagWWlmnV-0sJmcGk`.
- **Meta OAuth dropped** in favour of Shopify Customer Account (D.O.4 deferred indefinitely).

### What's next
- **D.M.1** — merchant welcome/status screen (~1 hr).
- **D.C.3** — Wardrobe page (newly unblocked by D.S.3b).
- **D.P.1** — install Vibe on the production store, then run **B.8** to capture Shopify GIDs and activate Add-to-Cart end-to-end against the real 13K catalog.
- **B.4 / B.6 / D.S.4** — legal pages, real-card test, remaining GDPR webhooks.

---

## Gate 1 — Functional Correctness

The pipeline must produce a usable answer for every primary intent without
manual intervention.

- [ ] All tests across `tests/` pass against the current branch
      (verified May 11, 2026: **1,225 L0 tests, 1 skipped, 239 subtests passed,
      0 failures**). Cumulative scope spans the composition + composer
      engines (Phase 4.7–5), per-axis YAML gap weighting + tuning harness
      (PR #200), empty-retrieval auto-relaxation (PR #192), engine-eligibility
      for all 7 follow-up intents (PRs #190/#191/#198/#199), Phase 3 prompt
      compression + audit harness (PR #202), the 4 must-fix observability
      counters (PR #204), cleanup pass (PR #205), the Path A → v3 axis
      additions (PR #237) + Path B rationalization (PR #239), the May-2026
      catalog re-enrichment + embedding resync (Step 2b shipped 2026-05-11),
      Phase 4.3 hard/soft yaml_loader (PR #246), the 4 new pairing matchers
      (PRs #248-#251: distributed_statement_exception,
      guest_vs_bridal_separation, sheen_hierarchy, metallic_neutral_exception),
      bodyframe + occasion existing-vocab edits (PRs #252-#253), the Phase 2
      Wave A audit script + report (PR #254), and the composer-side
      per-rule observability counters + A5.2b runbook (PR #257).
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
      (Verified May 11, 2026: **14,242 items, all enriched on the v3 +
      ShapeArchitecture axis set, all embedded, zero null filter columns.**
      Step 2b re-enrichment shipped 2026-05-11 (PRs #237 + #239 + the
      enrichment run); 54 rows with broken Shopify-CDN image URLs were
      intentionally dropped. **Catalog is frozen — no further bulk
      re-enrichment** per no-re-enrichment policy 2026-05-11.)
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

- [ ] All **32 dashboard panels** in `docs/OPERATIONS.md` exist in the chosen
      dashboard tool (Supabase Studio / Metabase / Grafana) and refresh on
      the cadence specified there. Panels 21-24 cover the composition
      engine flag-on cohort; 25-28 cover the composer engine; 29-32 cover
      the May-8 must-fix gaps (try-on flag state, empty-retrieval
      relaxation outcome, follow-up intent routing, per-axis YAML gap
      impact). Panel 16 — Low-Confidence Catalog Responses tracks the
      rate at which the threshold gate forces a no-confident-match
      response; healthy steady state is < 5%.
- [ ] **Pipeline Health** panel shows zero empty responses and a defined
      error rate over the last 24h.
- [ ] **Catalog-unavailable guardrail** panel shows zero hits in production
      and is documented as a "ring oncall" alert if it goes non-zero.
- [ ] **Negative signals** panel is reviewed daily during the first week of
      rollout. If any single product appears in the top-disliked list for
      more than 3 distinct users, the catalog row is audited and either
      fixed or hidden.
- [ ] An on-call rotation exists with documented escalation steps for:
  - empty responses spike (Runbook A)
  - catalog/embeddings missing (Runbook B)
  - feedback dislikes spike on a single product (Runbook C)
  - dependency report shows acquisition_source = unknown for >50% of
    new users (Runbook D)
  - composition engine flag-on regressions (Runbook A4)
  - composer engine flag-on regressions (Runbook A5)
  - try-on flag accidentally off in production (Runbook A6)
  - empty-retrieval relaxation firing on >2% of turns (Runbook A7)
  - per-axis YAML-gap impact concentration on a single axis (Runbook A8)
- [ ] Logs from `_log.error` / `_log.warning` in `orchestrator.py`,
      `catalog_search_agent.py`, `outfit_composer.py`, and
      `outfit_rater.py` are captured somewhere queryable (cloud
      logging, Logflare, etc.) — not just stdout.

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
- ~~Pairing-pipeline anchor enforcement edge cases~~ — **resolved in Phase 13** (April 10, 2026): anchor rules 4–6 added to the architect prompt covering every anchor category (top/bottom/outerwear/complete) with explicit direction structure constraints and formality conflict resolution. The architect now skips the anchor's role and chooses direction types based on what the anchor fills.

---

# Recently Shipped (May 1, 2026 — migrated May 3, 2026)

_Migrated from `CURRENT_STATE.md`. The May-1 "Open Items Plan" — every item now ✅ shipped — is preserved here as a record of work landed during the platform pass. For ongoing release readiness criteria see the Gates above._

## May 13, 2026 — Pairing pipeline RCA cascade + shoe scope-out + observability (PRs #326–#342)

A 17-PR wave that started from a single user complaint — *"I couldn't find a strong match for shopping just yet"* — and unwound into four nested failure modes plus a scope decision (drop shoes) plus an observability gap-close. The arcs:

1. **Planner normalization** (#326, #327) — the user's "shopping outing" was mapping to `occasion_signal="shopping"`, a value the composition YAML doesn't know, so the architect engine reported a yaml_gap and the composer gave up. Fix: constrain the planner's `occasion_signal` to the 44 canonical keys in `knowledge/style_graph/occasion.yaml` via a strict JSON Schema enum + prompt guidance. The model now picks the closest canonical key for any user phrasing.
2. **Pairing routing fix** (#328) — the staging `AURA_ENGINE_ALLOW_POOL_ANCHOR=true` flag was sending top/bottom anchor pairings to the architect engine, which emitted "paired" directions with **identical top-coded `hard_attrs` on both the top and bottom query**. The bottom query then matched almost nothing. Hardcoded the eligibility gate to always reject pool-injected anchors regardless of the flag; LLM architect handles all pairings now. Also bumped `retrieval_count` for anchor garments from 8 → 20 so the rater sees parity with complete-outfit turns (5×5=25 vs. 1×20=20).
3. **Retrieval RPC overload** (#329) — the May 13 iterative-HNSW rewrite created a NEW 3-arg `match_catalog_item_embeddings` signature alongside the May 7 5-arg version without dropping the old one. PostgREST returned PGRST203 ambiguity errors on every call with empty `hard_attrs`; the search agent silently caught the exception and returned 0 products. New migration drops the 5-arg overload; app-side strips `hard_attrs`/`hard_penalty` from the call chain (Python's `_apply_hard_attr_penalty` already owned that work).
4. **Shoe support scope-out** (#330, #332, #334, #336) — confirmed scope decision: the system doesn't have pairing rules, occasion logic, or catalog coverage for shoes today, so silently producing wrong outfits around them is worse than declining. Strips shoes from `required_roles` / `fill_roles` / complementary-role maps / wardrobe scoring weights / the architect anchor prompt / vision decomposition prompt / planner accessory taxonomy / wardrobe filter UI. Shoe-anchor uploads short-circuit with *"Styling around shoes isn't supported yet — try a top, bottom, dress, or outerwear instead."* Existing wardrobe shoes are filtered globally at `process_turn` entry so they never reach the scoring functions as "other" role items.
5. **Description synthesis for engine-path outfits** (#333) — the composer engine doesn't emit `item_descriptions`; only the LLM composer does. So outfit cards on engine-path turns shipped with empty description panels. New `synthesize_item_description` template builds a 12-25-word stylist-flavored description from catalog attributes (color, fit, pattern, silhouette, formality, occasion) at item-build time. LLM `item_descriptions` still override when present.
6. **Observability close-out** (#339) — audit found four gaps where shipped behavior changes lacked metric / panel coverage. New `observe_wardrobe_shoe_filter` histogram + `observe_item_description_source` counter + new Panel 36 ("Retrieval Empty After Relaxation" — the alert that would have caught #329's silent failure on day 1) + Panel 21 annotation explaining the engine→LLM share shift post-#328 + `shoe_anchor_unsupported` added to the answer_source enum in Panel 6.

### Planner normalization (PRs #326, #327)

| PR | Net change |
|---|---|
| #326 | `_PLAN_JSON_SCHEMA["occasion_signal"]` becomes `["string", "null"]` with `enum=[None, *KNOWN_OCCASIONS]` where `KNOWN_OCCASIONS` is loaded once at import from `knowledge/style_graph/occasion.yaml` (44 keys). Prompt updated with the canonical list grouped by archetype + concrete mapping cues ("shopping" → `everyday_casual`, "drinks tonight" → `rooftop_bar`, "wedding" with no stage → `wedding_ceremony`). Defensive normalizer in `_parse_result` nulls any non-canonical value that slips through. Prompt budget bumped 6000 → 6300. |
| #327 | Review follow-up. `PROMPT_VERSION` (planner cache invalidation key) only hashed the `.md` file; folds `KNOWN_OCCASIONS` into the hash so a `knowledge/style_graph/occasion.yaml` edit busts the cache. |

### Pairing routing + retrieval count (PR #328)

| PR | Net change |
|---|---|
| #328 | `composition/router.is_engine_eligible` always returns `(False, "anchor_pool_injected")` for top/bottom-category anchors, regardless of `allow_pool_anchor`. The T3 experiment shipped without anchor-aware query generation — the engine emitted broken cross-role `hard_attrs` and was inverting our latency win. LLM architect (with its anchor prompt fragment) handles these turns. Architect prompt's anchor-garment row in the retrieval_count table moved from 8 → 20: anchor fixed + 20 complements ≈ 20 outfits to rate, vs. 8 before which gave a much thinner pool. Composer/rater latency re-measurement post-deploy is the metric to watch. |

### Retrieval RPC overload (PR #329)

| PR | Net change |
|---|---|
| #329 | New migration `20260513020000_drop_match_embeddings_5arg_overload.sql` drops the May 7 5-arg `match_catalog_item_embeddings(query_embedding, match_count, filter, hard_attrs, hard_penalty)`. The May 13 iterative-HNSW rewrite created a NEW 3-arg signature alongside it; PostgREST returned PGRST203 on every 3-arg call. Bug ran for ~24h before forensics caught it — the `except` block in `catalog_search_agent` silently returned `matches=[]`. App side strips `hard_attrs`/`hard_penalty` from `vector_store.similarity_search`, the gateway, and the agent's call site. Hard-attr enforcement still lives in Python via `_apply_hard_attr_penalty` against rich `catalog_enriched` data. Test asserts the legacy kwarg now raises `TypeError` — guards against the next overload-style regression. Migration applied to staging by `supabase db push --include-all` against the linked project. |
| #331 | Review follow-up on #329. Added a missing `query_embedding` assertion to `test_catalog_retrieval_gateway` so the test name (`test_forwards_three_args_to_vector_store`) actually checks all three. |

### Shoes are out of scope (PRs #330, #332, #334, #336, #338)

| PR | Net change |
|---|---|
| #330 | Scope decision: the system has no pairing rules / occasion logic / catalog coverage for shoes worth styling around. Strips shoes from the per-turn `_build_wardrobe_gap_analysis` `required_roles` arg (`["top","bottom","shoe"]` → `["top","bottom"]` at 3 call sites in the orchestrator — separate from the `_WARDROBE_REQUIRED_ROLES` eligibility-gate constant for wardrobe-first which stays `("top","bottom","one_piece")`), `fill_roles` logic, complementary-role maps (3 sites), wardrobe scoring weights, the architect anchor prompt (`bottom, shoe, outerwear` → `bottom, outerwear`), `outfit_decomposition.md` vision prompt (no longer identifies shoes), `copilot_planner.md` accessory taxonomy, `user/service.py` wardrobe profile inference (no `_ROLE_SHOE_SUBTYPES`), `fallback_messages.py` ("shoes" dropped from supported-types list). New `_is_shoe_anchor` + `_build_shoe_anchor_unsupported_response` — anchor-intercept fires right after the anchor is set with: *"Styling around shoes isn't supported yet. Try a top, bottom, dress, or outerwear piece instead — I can build a full look around any of those."* The `ui.py` wardrobe view loses the "Shoes" filter chip and gets a new `wardrobeIsShoe` predicate that hides shoe-category items across every filter (data stays in DB, just not visible). Wardrobe scoring weights redistributed 22/22/18/14/12 → 26/26/16/14 — only 12 of the 18 shoe points moved across, so the max-completeness ceiling for "one of each role" dropped from 88 to 82 (caught and fixed in #332's review). |
| #332 | Review follow-up. Globally filter wardrobe shoes at `process_turn` entry — otherwise shoe items fell through to the "other" role in scoring functions and could rank as supplementary picks on dress-anchor pairings. Tokenize `_is_shoe_anchor` input on whitespace / hyphen / underscore so multi-word values (`"running shoes"`, `"chelsea boots"`, `"ankle boot"`) are caught. Trust canonical `garment_category` ({top, bottom, outerwear, one_piece, set}) when present to avoid hiding "boot-cut jeans" — the subtype contains "boot" but the row is a bottom. Mirror the same logic in JS `wardrobeIsShoe`. Restore the original 88-point wardrobe-completeness ceiling with weights 26/26/16/14 → 28/28/18/14 (#330's redistribution had only moved 12 of the 18 shoe points, dropping the ceiling to 82). |
| #334 | Review follow-up. Add `"one piece"` (space-separated) to `_CANONICAL_NON_SHOE_CATEGORIES` (Python) and `CANONICAL_NON_SHOE_CATEGORIES` (JS) — wardrobe enrichment + `user.service.resolve_wardrobe_role` accept either shape. Drop remaining `or []` guards on `user_context.wardrobe_items` (default_factory list, always initialized — dead code). |
| #336 | Review follow-up. Add `"one-piece"` (hyphenated) too for defensive coverage of any future enrichment path. Drop the last two `or []` guards at `wardrobe_count=len(user_context.wardrobe_items or [])` call sites the previous PR missed. |
| #338 | Review follow-up. Docs-only — `_CANONICAL_NON_SHOE_CATEGORIES` comment said `user.service.resolve_wardrobe_role` "emits" the space-separated form, but it actually *returns* `one_piece` (underscore) and *accepts* the space form on input. |

### Item description synthesis + article phonetics (PRs #333, #335, #337, #340, #342)

| PR | Net change |
|---|---|
| #333 | New `synthesize_item_description` builds a 12-25-word stylist-flavored description from catalog attributes (`color`, `fit_type`, `pattern_type`, `silhouette_type`, `garment_subtype`, `formality_level`, `occasion_fit`). Stamped at both item-build sites (`_build_candidate_item` for catalog-pipeline candidates, `_catalog_row_to_outfit_item` for wardrobe-first hybrid fillers). LLM composer's `item_descriptions` still override at the per-item loop in `_handle_planner_pipeline` when present (line refs drift with every commit — search for `composed.item_descriptions.get(iid`). The composer-engine path (which doesn't emit `item_descriptions`) now ships descriptions instead of empty panels. Edge cases handled: `a_line` silhouette pretty-prints to `A-line` ("with an A-line silhouette"); plural subtypes (`jeans`, `trousers`) drop the article and capitalize; `solid` pattern is dropped (no signal vs. omitting); null sentinels excluded. |
| #335 | Review follow-up. Article exceptions: `_indefinite_article("one piece")` returned `"an"` (default vowel rule) — wrong, "one" reads as "wun". Same for `"hourglass"` (silent H, should be "an" not "a"). Added prefix-exception checks. Also: plural-subtype check now looks at the trailing word so multi-word values (`"cargo pants"`, `"chino trousers"`, `"wide-leg trousers"`) are correctly detected. |
| #337 | Review follow-up. Refactored the if-cascade into an `_ARTICLE_PREFIX_EXCEPTIONS` tuple so adding a new exception is a one-line change. Reviewer suggested `inflect` library; we documented why we chose an exception set instead (input domain is bounded fashion vocab, no new dependency). Adds the "yoo" consonant class (`uni*`, `use*`, `europe*`) and silent-H class (`hour*`, `honest`, `honor`/`honour`, `heir`). |
| #340 | Review follow-up. `("unin", "an")` inserted before `("uni", "a")` so `uninsulated` / `uninformed` / `uninhabited` correctly take "an" while `unique` / `unitard` / `unisex` still take "a". `"use"` expanded to `"usa"` / `"use"` / `"usu"` to cover `usable` / `usual`. |
| #342 | Review follow-up. Adds `("unim", "an")` (`unimportant`, `unimpressive`), `("unir", "an")` (`unironed`, `unironic`), and **`("uti", "a")`** — this last one is the biggest catch: *"utility jacket"* / *"utility pants"* are common fashion vocab and were getting *"an utility jacket"* with the default vowel rule. |

### Observability (PRs #339, #341)

| PR | Net change |
|---|---|
| #339 | Audit-driven gap close after the May 13 wave's behavior changes. Adds `observe_wardrobe_shoe_filter(filtered_count=N)` histogram (called once per turn from `process_turn`) — quantifies how often users have shoes saved. Adds `observe_item_description_source(source="llm"\|"synthesized"\|"none")` counter ticked per shipped item — tracks the LLM-vs-synthesized split as a quality signal. New **Panel 36** ("Retrieval Empty After Relaxation") flags turns where `catalog_search` returned 0 products after exhausting the relaxation sequence — exactly the failure mode #329's RPC overload exploited for ~24h. Persists `retrieval_relaxation_outcome` + `retrieval_total_products` in catalog-pipeline metadata so the panel can distinguish "catalog is thin" from "composer rejected a populated pool". `shoe_anchor_unsupported` added to the answer_source enum in Panel 6 (otherwise these turns fell into "unknown" and were invisible). Panel 21 docstring annotation explains the expected engine→LLM share shift on pairing turns post-#328 so the next person reading the dashboard doesn't misread the drop. |
| #341 | Review follow-up on #339. `_catalog_row_to_outfit_item` now records `"none"` when the synthesizer returns empty (catalog row had no descriptor attributes), matching the catalog-pipeline path. Every shipped item ticks the counter once — the source-mix ratio is no longer biased toward `"synthesized"` for attribute-thin rows. |

**State at end of May 13 push:**
- Planner normalization closes the `yaml_gap:occasion_signal:*` class of failures. The cache invalidates correctly when `occasion.yaml` changes.
- Top/bottom anchor pairings always route to the LLM architect with `retrieval_count=20` per role. The `AURA_ENGINE_ALLOW_POOL_ANCHOR` flag is now a no-op for the architect router (still wired for the composer router's separate experimental path).
- Catalog retrieval is unambiguous — only the fast iterative-HNSW 3-arg `match_catalog_item_embeddings` exists in the DB. Migration applied to staging.
- Shoes are explicitly out of scope. Existing wardrobe shoes are filtered from planning + hidden in UI; new shoe-anchor uploads get the "not supported yet" message.
- Outfit cards ship with descriptions in all paths. Engine-path turns get the deterministic synthesizer; LLM-path turns get the stylist-voice copy from the composer.
- Indefinite-article exception table handles `uni`/`use`/`uti` "yoo" sounds, `unin`/`unim`/`unir` negation carve-outs, silent-H words, and "one piece". Documented inline so the next contributor can decide whether to swap in `inflect` if the catalog vocabulary broadens further.
- Observability: Panel 36 alerts on the silent retrieval-failure mode; Panel 6 surfaces shoe-anchor demand; new metrics track wardrobe-shoe filter rate and description-source mix.
- Test suite: 1296 passed, 1 skipped.

---

## May 12, 2026 (late evening) — Card detail panel polish + composer hotfix + docs (PRs #311–#324)

A 14-PR cleanup wave on top of the same-day evening wave. Splits across three substantive arcs (composer hotfix, card UX round 2+3, pairing-anchor behavior) plus review-feedback churn and doc refreshes.

### Composer hotfix — item_descriptions schema reshape (PRs #313–#315)

The day's earlier PR #305 added `item_descriptions` as a dict with dynamic string keys (`additionalProperties: {"type": "string"}`). OpenAI's Structured Outputs rejected this — strict mode forbids `additionalProperties` dicts at every level. **Every composer call had been failing on `main` since #305 merged.**

| PR | Net change |
|---|---|
| #313 | Hotfix. Convert `item_descriptions` to an array of `{item_id, description}` rows. Parser folds it back to `Dict[str, str]` for the rest of the pipeline; downstream (orchestrator, response_formatter, frontend) unchanged. Defensive against the legacy dict shape if a cached payload still has it. Prompt example updated to match. |
| #314 | Budget bump 1600 → 1800 to absorb the schema reshape (CI L0 wasn't a required check, so the hotfix shipped despite a red budget test). |
| #315 | PEP 8 nit on the budget comment per review. |
| #316 | Prompt example `direction_type` fixed: "complete" with 2 items is invalid per the file's own rules; changed to "paired". |

### Outfit card UX — round 2 + round 3 (PRs #317, #318, #319, #321, #323)

Five PRs polishing the detail panel the day's earlier #306 introduced.

| PR | Net change |
|---|---|
| #317 | Round 2. Detail panel gets `min-height: 420px` + line-clamps on title (2) and description (4) — the CTA row stops jumping vertically across cards. Buy Now and Buy Outfit share `min-height: 44px`. Save text → outline-heart icon (filled on wishlist POST). Prices switch from oxblood `--accent` to neutral `var(--ink)`. Card header drops its `border-bottom` divider. |
| #318 | Round 3. Buy Outfit was vertical-stretching because `.btn-buy-primary { flex: 1 }` was intended for the garment-mode `.detail-cta` row; in outfit mode the button was a direct child of the column-flex panel. Wrap Buy Outfit + a new Like heart in a `.detail-cta` so flex:1 stays horizontal. Move Like from card header into the outfit-mode CTA row — both modes now share the "Buy CTA + heart" shape. Composer prompt bumped to 2-3 sentences (30-55 words) per item so descriptions actually fill the 4-line clamp. |
| #319 | Budget bump 1800 → 1900 (CI's char/4 fallback over-counts vs tiktoken). |
| #321 | Reviewer feedback on #319 — bump to 1950 to restore the 5% headroom rule documented in the audit module. |
| #323 | Pairing-card anchor handling. In `pairing_request` cards the wardrobe-source item is the user's anchor ("what goes with this skirt?"). Clicking it now routes to outfit mode (the user already owns it; a product detail panel doesn't carry information). Outfit-mode listing filters wardrobe items out for pairing cards — only recommended pairings appear with price + sizes. |

### Composer schema/prompt consistency (PRs #320, #322, #324)

| PR | Net change |
|---|---|
| #320 | Schema description in `outfit_composer.py` was still saying "single sentence (12-25 words)" while the prompt had moved to 2-3 sentences. Sync. |
| #322 | Tightens the JSON schema description further: now mirrors the prompt's stylist-voice directive and explicit no-pairing-logic rule. Clears stale "one-sentence" comments at `outfit_composer.py:169` and `schemas.py:311`. |
| #324 | The example in `schemas.py`'s doc comment was 27 words, below the 30-55 word range the comment itself documented one line above. Rewrote to 41 words. |

### Docs (PRs #311, #312)

| PR | Net change |
|---|---|
| #311 | Three dense PRODUCT.md / DESIGN.md bullets nested into sub-lists per review feedback. Added a "discrepancy with merchant page" note about the 1.2× FE-only price markup. |
| #312 | PRODUCT.md consistency fixes on the same review pass — `thumbs` → `thumbnails`, `+` → `,` separators, restored `outfit title` / `garment title` fields, "per-garment price" → "per-garment marked-up price" (the markup applies in both modes). |

**State at end of late-evening push:**
- Composer + frontend are back to producing user-facing outfits end-to-end. Production was broken between #305 (10:30 UTC) and #313 (13:06 UTC); hotfix restored it.
- Detail panel has stable layout, identical Buy+heart shape in both modes, pairing-anchor routing, and 2-3 sentence per-item descriptions on new outfits going forward.
- Older cached outfits keep working with empty descriptions (frontend hides the description block when empty).
- Composer prompt budget = 1950. Composer model + retry path unchanged.

---

## May 12, 2026 (evening) — Outfits redesign + outfit card rework + UI polish (PRs #298–#309)

A 12-PR sweep across the Outfits tab grouping, the outfit card right column, and broad UI polish. The user-facing rater radar was retired (the rater still runs server-side for ranking/filtering). The composer gained per-item descriptions to feed the new product detail panel.

### Outfits tab — occasion-driven grouping + flattened carousels (PRs #298–#301)

| PR | Title | Net change |
|---|---|---|
| #298 | Occasion-driven groupings + intent/source filters | Replaces the 8-broad-bucket theme taxonomy with 8 fine-grained occasion buckets (wedding / festive / date / office / beach / travel / party / casual) + 3 formality fallback buckets (smart_looks / easy_everyday / off_duty) for sessions with no occasion signal. New `map_formality_to_bucket()` in `theme_taxonomy.py`; orchestrator overrides `style_sessions` sentinel via avg `formality_pct` across each session's outfits. Intent + source moved from per-session metadata strip into page-level filter chips. Outfits page header dropped. |
| #299 | One carousel per theme + smaller title | Each theme now renders a single carousel of every look across all its sessions (previously one carousel per session). Per-card turn-summary already updates when the user navigates, so the user query naturally shifts as cards from different sessions slide into view. Theme title font 36px → 22px (desktop), 28px → 20px (mobile); subtitle "X looks across Y sessions" dropped; per-session "N looks · Xh ago" strip dropped. |
| #300 | Drop intent filter, widen source filter | Pairings / Occasions / Capsules row removed. Source row (All / From Wardrobe / Hybrid / Shop) stretched to full page width to match Wardrobe page's category-filter rhythm. `.page-outfits` aligned with `.page-wardrobe`: max-width 1440px, 48px padding, 900/600 responsive breakpoints. |
| #301 | Drop tab page headers (Checks / Wardrobe / Saved) | The tab nav is the breadcrumb; on-page titles + subtitles were redundant chrome. Wardrobe keeps the piece-count + Add piece action (functional). |

### UI polish (PRs #302–#304)

| PR | Title | Net change |
|---|---|---|
| #302 | Replace emoji / unicode icons with inline SVGs | 👤 avatar, × image-chip remove, ➤ composer send, 📸 upload placeholder, 🗑 wardrobe trash all become inline SVGs (24px viewBox, 1.8 stroke). Wishlist "Save" → ♥ toggle becomes "Save" → "Saved" text toggle (matches `.btn-wishlist` text-only styling). |
| #303 | `auraPrompt` styled modal replaces native `alert` / `confirm` | New `.modal-prompt` variant of `.modal-overlay`. API: `auraPrompt.confirm(title, message, {okLabel, cancelLabel, danger}) → Promise<bool>`, `auraPrompt.alert(title, message) → Promise<true>`. Replaces 4 call sites (wardrobe delete + 3 upload errors). New `.btn-primary.btn-danger` styling for destructive confirms. |
| #304 | Consolidate 35 inline styles → CSS classes | New classes: `.no-image-placeholder` (3 sites), `.dropzone-label` + `.dropzone-hint`, `.modal-subtitle`, `.saved-card` + `.saved-card-image` / `-body` / `-title` / `-price` / `-meta` / `-buy`. Net: 35 → 23 inline `style=` attrs. |

### Composer per-item description (PR #305)

| PR | Title | Net change |
|---|---|---|
| #305 | Per-item description for the product detail panel | New `item_descriptions: Dict[str, str]` on `ComposedOutfit`; new `description: str` on `OutfitItem`. Composer prompt (`prompt/outfit_composer.md`) now writes one sentence (12-25 words) per chosen item describing the garment itself (not pairing logic). Threaded end-to-end: prompt → JSON schema → parser → orchestrator → `_build_item_card` → frontend. Budget bumped 1600 → 1700. Backward-compat: defaults empty, so cached/older outfits keep working. |

### Outfit card rework (PR #306)

| PR | Title | Net change |
|---|---|---|
| #306 | Context-sync'd detail panel + drop user-facing rater radar | The right column of the outfit card becomes a detail panel whose content tracks the active thumbnail. **Garment mode** (garment thumbnail active): title + ×1.2 marked-up price + composer-authored `description` + XS-XL size chips + Buy Now + Save. **Outfit mode** (try-on thumbnail active — default): outfit title + `reasoning` + per-garment rows with price + size chips + disabled Buy Outfit. New `auraPrice()` JS helper (1.2× markup, en-IN locale, returns "" for non-numeric). New CSS: `.detail-panel`, `.detail-title`, `.detail-price`, `.detail-description`, `.detail-sizes`, `.size-chip`, `.btn-buy-primary`, `.detail-save`, `.detail-items`, `.detail-item-row`, `.detail-item-meta`, `.detail-item-price`, `.detail-item-sizes`. **Rater radar removed from the UI** (`renderCompactProfile()` and ~165 lines of radar SVG deleted) — the rater still runs server-side for ranking/filtering, only the user-facing component is gone. The card header drops its reasoning paragraph (now in the detail panel). |

### Review feedback fixes (PRs #307–#309)

| PR | Title | Net change |
|---|---|---|
| #307 | Review-feedback batch across #300–#305 | `.page-outfits` responsive breakpoints 960/720 → 900/600 to match wardrobe; dead `.results-header` + `.wardrobe-header h2` CSS removed; `aria-hidden="true"` added to 5 decorative SVGs (parent buttons carry the aria-label); `auraPrompt` ESC dismissal + 240ms fade-out reads `--dur-2` from CSS; `.no-image-placeholder` drops `height: 100%` (conflicted with `aspect-ratio: 3/4`); composer `item_descriptions` parser converted to dict comprehension. |
| #308 | Card index mismatch + size-chip toggle + ESC scoping | Detail panel was using thumbnail-array index directly into `items[]`, which mismatched whenever any item had no image. Image entries now carry their source `item` reference; renderDetailPanel reads `images[idx].item` directly. Size chips now toggle off on a second click. ESC handler now checks the top-most open overlay (a literal `stopImmediatePropagation` would have closed the wrong modal when modals stack — capture-phase listeners fire in registration order). |
| #309 | Single-element lookup for size-chip deselect | Tiny perf nit — `querySelectorAll` + `forEach` deselect replaced with `querySelector('.size-chip.selected')`. |

**Card state at end of May-12 evening push:**
- Outfit card: thumbs | hero | context-sync'd detail panel (garment mode or outfit mode); compact header (title + Like/Hide); rater radar retired from UI; ×1.2 price markup applied at render; XS-XL size chips (visual-only); Buy Outfit disabled (multi-item checkout not wired).
- Composer emits `item_descriptions` for every new outfit; older cached outfits show empty description rows (graceful).
- Native browser dialogs replaced with in-app `auraPrompt` modal (ESC-dismissable, scoped to top-most overlay).
- All chrome icons are inline SVGs with `aria-hidden="true"` where the parent button has an aria-label.

**Open follow-ups:** "Buy Outfit" multi-item checkout (the button is rendered disabled; wire when a real cart flow lands).

---

## May 11–12, 2026 — UI multi-turn stacking + wardrobe vision overhaul + catalog title/price recovery + planner anchor + observability waves 1-2

A 27-PR sweep across UI, wardrobe ingestion, catalog data quality, planner architecture, and observability. Grouped by area:

### UI — persistent multi-turn stacking + cleanup (PRs #270-#274, #294)

| PR | Title | Net change |
|---|---|---|
| #270 | Persistent user-query card + `tool_traces` status constraint fix | The user's typed message now persists as a chat card alongside the stylist's response; previously it was replaced when the response rendered. Also fixed the `tool_traces` 400 (`status='fallback'` violated the table's `('ok','error')` CHECK constraint — fallback now goes into `output_json` with `status='ok'`). |
| #271 | Drop context line + follow-up chips from live result | Removed the "CATALOG ONLY · 3 LOOKS" header and the follow-up suggestion chips below outfit cards. |
| #272 | Stack every turn in one session, never wipe prior results | New turns append below previous turns; the entire conversation is scrollable within a session. `setStage()` writes only to the per-turn `pStage` element (not a global one). |
| #273 | Drop dead query-preview-done class (review of #270) | — |
| #274 | Pass preview refs directly, drop global ids (review of #272) | — |
| #294 | Drop duplicate stage indicator from above the composer | The fixed stage bar above the input was redundant with the per-turn stage line. Per-turn is now authoritative. |

### Wardrobe vision enrichment — model + budget + threading + disambiguation (PRs #275-#286)

| PR | Title | Net change |
|---|---|---|
| #275 | Upgrade vision model, stop description leak, fix role exclusion | Initial swap of wardrobe-ingestion vision from `gpt-5-mini` to a larger model. Empty-description response no longer leaks into the wardrobe `notes` field. `resolve_wardrobe_role()` consolidated into a module-scope single source of truth; role-filter exclusion is no longer silent. |
| #276 | Consolidate role mapping to one source of truth (review of #275) | 5 canonical-subtype constants (`_ROLE_ONE_PIECE_SUBTYPES`, `_ROLE_TOP_SUBTYPES`, …); two-tier role resolution — proper enum first, fuzzy subtype fallback second. |
| #277 | Widen latency budget for vision enrichment | Per-request budget raised; the user-facing "Saving…" state was hanging because the SDK was running over the previous budget. |
| #278 | Disable OpenAI SDK retries to honor the timeout (review of #277) | `max_retries=0` on the OpenAI client. Default 2 was silently undoing the timeout (3 × 55s ≈ 165s). |
| #279 | Thread user text to vision, forbid null `GarmentCategory` | Vision call now receives the user's typed message alongside the image so it can disambiguate "what goes with this skirt?" + photo → skirt, not dress. `GarmentCategory` is no longer nullable in the schema. |
| #280 | Reuse module-level OpenAI client (review of #279) | One shared `OpenAI()` instance instead of per-call construction. |
| #281 | Re-validate post-enrichment attrs, cap text_hint length (review of #279) | Post-enrichment validation rejects rows that didn't satisfy the schema; `text_hint` capped to prevent prompt-bomb. |
| #282 | Lazy-init shared OpenAI client (review of #280) | Double-checked locking — the shared client is constructed on first use, not at import. |
| #283 | Text-based garment-type fallback when vision can't anchor | If vision can't anchor the garment, fall back to plural-aware text-hint extraction over the user message before giving up. |
| #284 | Switch vision model to `gpt-5.2/low` | Final model choice. Gpt-5.5/high was 70-110s on a single item; gpt-5.2/low completes in 12-25s with no quality loss on the 57-attribute schema. The locked-in sweet spot for this stage. |
| #285 | Thread-safe lazy init + lazy system prompt (review of #282) | Both `_shared_client()` and `_system_prompt()` use double-checked locking. Mypy-clean (Optional cache + non-Optional return refactored to fast-path early return). |
| #286 | Match plural garment names in text-hint extractor (review of #283) | "skirts" / "blazers" / "sarees" now match the same subtype lookups as their singulars. |

### Planner — structured `anchor_garment` replaces keyword regex (PRs #287, #292)

| PR | Title | Net change |
|---|---|---|
| #287 | Structured `anchor_garment` extraction; drop keyword regex | The planner emits a typed `anchor_garment: {category, subtype, confidence}` block. New `AnchorGarmentHint.is_usable(threshold)` method (explicit threshold, no default). `_PLANNER_ANCHOR_CONFIDENCE_THRESHOLD = 0.5` in the orchestrator. `extract_garment_hint_from_text` deleted. `_PLAN_JSON_SCHEMA` extended (category enum, subtype string, confidence number). |
| #292 | Ship the `anchor_garment` prompt instructions (missed in #287) | The squash for #287 didn't include `prompt/copilot_planner.md` (the file was edited in the main repo's working tree, not the worktree where commits were made). Recovered the 11-line instruction block here, with examples (lehenga, midi, Hindi). `audit_prompt_tokens.py` budget bumped to 6000 to fit the new instructions. |

### Catalog — title/price recovery + `deleted_from_source` filter (PRs #288-#291, #293)

| Item | Detail |
|---|---|
| One-time backfill (May 11) | Recovered ~13,178 real merchant titles + 13,177 real prices on the 14,242-row catalog via Shopify `.json` endpoints (offduty, showoffff, vastramay, powerlook, campussutra, taruni, nicobar, fawn24) and HTML JSON-LD parsing (koskii, virgio). 1,064 rows where the merchant no longer serves the URL were tagged `row_status='deleted_from_source'` rather than dropped. **No new enrichment** — this only touched the `title` and `price` columns. |
| #288 | Exclude `deleted_from_source` from recommendations | Both retrieval paths (`orchestrator._get_catalog_rows()` and the catalog search agent) skip rows tagged `deleted_from_source`. Filter uses Postgrest `or=(row_status.neq.deleted_from_source,row_status.is.null)` because bare `neq` excludes NULL-status rows too. |
| #289 | Review feedback for PRs #284 / #285 / #287 | — |
| #290 | Review feedback for PRs #288 / #289 | — |
| #291 | Extract `deleted_from_source` to shared constant (review of #290) | `ROW_STATUS_DELETED_FROM_SOURCE` constant in `catalog/retrieval/document_builder.py`. |
| #293 | Prefer `enriched.price` over stale `metadata.price="Unknown"` | The orchestrator was reading `metadata.price` first, which carried stale "Unknown" text on some rows. Switched to enriched-price-first with explicit unknown-string canonicalization. |

### Observability — waves 1 + 2 (PRs #295, #296)

| PR | Title | Net change |
|---|---|---|
| #295 | Wave-1 obs review after wardrobe / catalog churn | First-pass audit of the metric surface after the wardrobe / catalog / planner waves; identified gaps for wave 2. |
| #296 | Wave-2 — new metrics + freshness panel | Three new Prometheus instruments: `aura_wardrobe_enrichment_fallback_total{source}` (labels: `vision_ok` / `planner_anchor` / `none`); `aura_catalog_deleted_skipped_total{path}` (labels: `orchestrator_rows` / `catalog_search`); `aura_planner_anchor_confidence` (Histogram, 10 buckets 0.0→1.0). New Panel 35 — Catalog Title/Price Freshness — watches for title/price regressions on the `catalog_enriched` ingestion stream, split by `row_status` so the intentionally-empty `deleted_from_source` rows don't pollute the signal. SQL auto-extracted to `ops/dashboards/panel_35_catalog_title_price_freshness.sql`. |

**Catalog state at end of May-12 push:** still **frozen at 14,242 garment-only rows** under the no-bulk-re-enrichment policy. Title + price columns refreshed (one-time, allowed under policy because this is data recovery, not vision re-enrichment). 1,064 of those rows now visibly tagged `deleted_from_source` and excluded from recommendations.

**Still gated on humans:**
- Phase 4.6 — eval-set curation (100-500 hand-curated queries) remains the blocker for composer engine flag-on validation, threshold calibration, and the borderline Wave A cuts.

## May 9–11, 2026 — Catalog re-enrichment + Phase 4.3 hard/soft + pairing matchers + observability close-out

Catalog re-enrichment (Step 2b) ran on the v3 + Path B axis set, plus the engineering work that depended on it — Phase 4.3 hard/soft yaml_loader, four new composer-side pairing matchers, the bodyframe / occasion existing-vocab edits, the Phase 2 Wave A ontology-surgery audit, and observability follow-ups so the new rules are diagnosable in production. The no-bulk-re-enrichment policy was also codified here.

| PR | Title | Net change |
|---|---|---|
| #237 | Step 2a — v3 axis additions to canonical schema | 12 new axes: ShapeArchitecture quad + v3 axes (FabricTransparency, SurfaceFinish, LayeringVisibility, BlouseLength, ShoulderExposure, SleeveVolume, BorderContrast). Schema migration + canonical garment_attributes.json. |
| #239 | Path B rationalization | Drops 5 weather perf axes (BreathabilityLevel / DryTime / WaterResistance / ThermalInsulation / WrinkleResistance) which couldn't be reliably extracted from vision. Net: 55 enum + 2 text canonical attrs. |
| (May 11) | Step 2b catalog re-enrichment + embedding resync | 14,242 / 14,296 rows enriched ok (99.62%); 54 CDN-broken rows dropped from catalog_enriched + catalog_item_embeddings; embeddings regenerated via text-embedding-3-small. Cost ~$35-40, ~30 hrs wall time with two billing-limit pauses. Ops tooling: `pull_catalog_to_csv.py`, `upsert_enriched_to_db.py`, `resync_catalog_embeddings.py`. |
| #246 | Phase 4.3 hard/soft yaml_loader | yaml_loader recognises `hard_flatters` / `hard_avoid` / `soft_flatters` / `soft_avoid` keys alongside bare `flatters` / `avoid`. Engine `_add_mapping` emits ClassifiedContributions with forced hard/soft tier overriding source-level default. AttributeMapping gains 4 new fields; same-attr-in-both-buckets rejected at load. |
| #248 | distributed_statement_exception matcher | Suspends the `scale_balance.one_statement_per_outfit` cap when items share a single `color_temperature` family AND no item is individually heavy/statement — the coordinated-Indianwear case. |
| #249 | guest_vs_bridal_separation matcher + `bridal_role` on TupleContext | When `ctx.bridal_role ∈ {guest, attendee}` AND occasion is a bridal-role occasion, tuples carrying items at bridal-participant embellishment levels (heavy / statement) drop. Bride / groom bypass. Wires Step 1's `is_bridal_role_occasion` lookup into composer scoring. |
| #250 | sheen_hierarchy matcher | Outside bridal exception, cap items with fabric_texture ∈ {sheen, metallic, embroidered} at 1 per outfit. Soft penalty. Configurable cap via YAML `value` field. |
| #251 | metallic_neutral_exception wiring | `_evaluate_color_story.max_dominant_colors` now excludes items with dominant_color ∈ metallic-neutral set (gold / champagne / antique gold / bronze / etc.) OR fabric_texture=metallic. Fixes false-positive on Indian festive outfits with zari / metallic dupatta accents. |
| #252 | bodyframe existing-vocab edits | 3 surgical hard/soft tier shifts using Phase 4.3 scaffolding: Pear `mermaid avoid → soft_avoid` (bridal exception); JawlineDefinition Soft `sweetheart avoid → flatters`; male Rectangle `sculpted flatters → soft_flatters` (urban-Indian softening). |
| #253 | daily_office_mnc soft_avoid downgrade | `FabricTexture: [metallic, embroidered]` moves from hard avoid → soft_avoid. Subtle Indo-Western fusion (zari kurta + tailored trouser, bandhgala with muted embroidery) stops being retrieval-time vetoed. |
| #254 | Phase 2 Wave A ontology-surgery audit | `ops/scripts/phase2_wave_a_audit.py` + first-run report at `docs/phase2_wave_a_audit.md`. Refuted most of the originally-claimed Wave A removals — 5 of 7 candidates carry independent signal per the entropy + extractability analysis. |
| #255 | OPEN_TASKS Wave A reframe | Updated the Wave A list to reflect the audit findings: 3 borderline candidates remain (OccasionSignal / SilhouetteContour / FitEase), each gated on top-pairs review before any cut. |
| #256 | No-bulk-re-enrichment policy + OPEN_TASKS surgery | -214 / +61 lines on OPEN_TASKS.md. Dropped all dormant-vocab queue items, Wave B (4 deferred ShapeArchitecture axes), FabricTexture decomposition, 4-stage extraction. Added explicit policy section + "Where quality improvements come from on a frozen catalog" forward plan. |
| #257 | Composer-side per-rule observability + A5.2b runbook | New Prometheus counters: `aura_composer_rule_violation_total{rule, is_hard}` ticks per Violation; `aura_composer_rule_exception_applied_total{rule, exception}` ticks when an exception suppresses or modifies a violation. `_summarize_provenance` persists `ctx.bridal_role` for Panel 26 RCA. Panel 26 `LIMIT 30 → 200`. New A5.2b sub-runbook covers the 4 pairing-matcher fire RCA flow. |
| #258 | Sync context files to current system state | After re-enrichment / Phase 4.3 / pairing matchers / observability close-out, six context files had stale claims (catalog count 14,296 → 14,242, test count 1,015 → 1,225, May 9-11 PR table seeded). PRODUCT.md / OPERATIONS.md / RELEASE_READINESS.md / WORKFLOW_REFERENCE.md / composition_semantics.md / composer_semantics.md brought current. |
| #259 | Planner output cache + `recent_user_actions` cap 20 → 10 | `planner_output_cache` table + SHA1 key over (tenant, normalised user_message, cluster, intent, occasion, image flags, wardrobe bucket, prompt version). 14-day TTL with `last_used_at` refresh. Hit path: 7.7s → ~50ms; `model='cache'` stamping for Panel 33. Trim is a -1K-token reduction on architect prompts for active users. |
| #260 | Tighten frozen-catalog policy (also forbid embedding regen) | Policy now forbids BOTH bulk vision re-enrichment AND bulk embedding regeneration on the 14,242-row state. Per-product enrichment + embedding at ingestion-time still allowed. |
| #261 | `elevated_fusion_exception` + `modern_bridal_restraint` matchers | Two new pairing matchers. Elevated-fusion suspends the `indo_western_fusion` penalty when the bridge garment is tailored / solid / minimal. Modern-bridal-restraint caps embellishment for guest / attendee roles at modern bridal occasions. |
| #262 | `anchor_constraints` matchers (Batch B) | `_evaluate_anchor_constraints` reads `ctx.anchor_item_id` (plumbed via `composer_router.extract_tuple_context`) and enforces pairing-anchor soft constraints during composition. Added to SOFT_CATEGORIES. |
| #263 | `indian_weave_compatibility` matcher (Batch C) | Heritage-weave classifier `_is_heavy_heritage_weave` over (subtype, fabric_texture, cultural_register, embellishment) heuristic. Caps heavy heritage weaves in cross-region tuples without re-enriching the catalog for explicit weave families. |
| #264 | Cache-hit-rate dashboards (Batch D — Panel 33 + 34) | Panel 33 — per-stage LLM-cache hit rate from `model_call_logs.model='cache'` (planner / architect / composer). Panel 34 — try-on cache hit rate via `call_type` slicing. Closes observability for all four caches. |
| #265 | Trim OPEN_TASKS.md to focused-today-only | 686 → 67 lines. Removed forward-planning content; kept frozen-catalog policy, the two trigger-driven items, and the permanently-dropped guardrail list. |
| #266 | Correct masculine top coverage claim | Replaced stale April-2026 "0 tshirts / polos / shirts" citation with live state (922 shirts / 369 tshirts / 63 sweatshirts / 39 hoodies). Re-enrichment fixed subtype recognition; only `polo_tshirt` truly empty. |
| #267 | Remove stale `archetypal_preferences` references | Composer phase-out shipped May 8, but OPEN_TASKS still listed it pending and 3 other files referenced the removed `aggregate_archetypal_feedback` as if live. Trimmed to history-only references. |
| #268 | Panel 17 cap update (`recent_user_actions` 30 → 10) | Panel 17 (Architect Input Token Growth) was citing the original 30-event cap. Updated to the current 10-event cap (30 → 20 → 10 history retained in context), token math adjusted (~1K added vs ~3K), and remediation guidance reordered (trim `_CATALOG_ATTR_MAP` before dropping below 10). |

**Test suite at end of May 11 push:** 1,225 passed + 1 skipped + 239 subtests passed (snapshot at #257; later same-day PRs added planner-cache + new-matcher test coverage but no fresh full-suite count was captured before close-out). **Catalog frozen at 14,242 garment-only rows** post-Step-2b; no further bulk re-enrichment per policy. **Embeddings also frozen** post-#260 — neither bulk re-enrichment nor bulk embedding regen is permitted on the existing rows.

**Still gated on humans:**
- Phase 4.2 ✅ done (all 8 stylist files reviewed)
- Phase 4.6 — eval-set curation (100-500 hand-curated queries) — required for Step 5 quality validation, composer engine flag-on rollout, Phase 6 library quality validation, Phase 7 learned-model held-out evaluation, the 3 borderline Wave A cuts, and threshold calibration on both routers

## May 6–7, 2026 — Phase 4.7+ composition engine + canonicalization + observability

A 7-PR push that shipped the deterministic YAML-driven composition engine, the input-canonicalization layer that makes it work on real planner output, and the observability surface around both.

| PR | Title | Net change |
|---|---|---|
| #149 | Phase 4.7 + 4.8 + 4.9 + 4.10 — engine, validator, router, flag | New `composition/` package: `yaml_loader.py` → `reduction.py` → `relaxation.py` → `engine.py` → `render.py` → `quality.py` → `router.py`. `compose_direction()` reduces 8 style-graph YAMLs into a `DirectionSpec` deterministically; router applies spec §9 fall-through criteria; orchestrator wires it behind `AURA_COMPOSITION_ENGINE_ENABLED` (default false). 691 → 599 → 654 tests across the sub-PRs. |
| #150 | Pre-flag observability instrumentation | `aura_composition_router_decision_total` counter, engine latency under `aura_turn_duration_seconds{stage="composition_engine"}`, YAML-gap surfacer in distillation traces, `aura_composition_yaml_load_failure_total` + alert. |
| #151 | Phase 4.11 input canonicalization via embedding nearest-neighbour | The pivotal piece. `composition/canonicalize.py` two-phase (exact-match → batched `text-embedding-3-small`) maps free-text planner output to YAML-canonical keys. 350KB pre-computed embedding bank (`canonical_embeddings.json`). Confidence threshold recalibrated 0.60 → 0.50. Engine bug fix: seasonal_color_group dual-dimension lookup. |
| #152 | `tool_traces` CHECK-constraint fix | Every cache-hit try-on candidate was silently dropping its trace row (`status='cache_hit'` violated the table's `('ok', 'error')` enum). `_coerce_tryon_trace_db_status()` helper coerces the rich path enum to the constrained domain. |
| #153 | `model_call_logs.model` origin stamping | Per-model rollups were attributing every cache + engine row to gpt-5.2 (phantom 0-token rows). New `_resolve_architect_origin_model()` stamps `cache` / `composition_engine` / LLM model id; tokens forced to 0 on non-LLM paths. |
| #154 | Comprehensive observability follow-up | 4 new metrics (canonicalize result counter, embed-duration histogram, tool_traces failure counter, attribute-status counter). 4 new dashboard panels (21 plan-source distribution, 22 yaml-gap distribution, 23 per-attribute status, 24 single-turn diagnostic). `RouterDecision.provenance_summary` plumbed into traces. OPERATIONS.md "A4: Composition engine flag-on regressions" runbook. `ops/scripts/turn_forensics.py`. |
| #155 | OPEN_TASKS.md refresh | Updated the Phase status table + foundation list + per-phase detail to reflect the above shipped state. |

**Verified end-to-end on 2026-05-06:** a real flag-on staging turn (`b356a1bf`, "Find me casual outfits for weekend outing") produced `used_engine=true, engine_confidence=1.0, engine_ms=0`. Total turn 83s → 63s vs the flag-off baseline; per-turn cost ~$0.19 → ~$0.15. Architect stage 19s → ~0ms is the dominant saving.

**Still gated on humans:**
- Phase 4.2 — paid stylist YAML content review (revised YAMLs, edge-case calls, canonical-schema fixes)
- Phase 4.6 — eval-set curation (100-500 hand-curated queries) — required for confidence-threshold calibration, A/B model swap (Phase 1.4), and the bucketed-rollout ramp

## May 5–6, 2026 — episodic memory + R7 rater + composer name + ops recalibration

A 22-PR sweep that overhauled the rater rubric, added episodic memory at the architect, made every outfit a first-class named card, fixed three silent failure modes, and rebuilt the observability surface to match the new system. Grouped by area:

### Composer (PRs #80, #81, #83, #88, #91, #95)

| PR | Title | Net change |
|---|---|---|
| #80 | Harden direction_id contract + per-attempt logging | Dynamic enum on `direction_id` (LLM physically can't write a SKU there); per-attempt callback so `model_call_logs` gets one row per LLM call instead of summing tokens across the retry. T6 turn that "appeared" to have a 24K-token prompt was actually 12K + 12K — the doubling now visible. |
| #81 | Composer → gpt-5.4 + threshold 75 → 60 + weight rebalance | Promoted from gpt-5-mini for the heavier reasoning task. Default weight profile rebalanced (occ 0.35 / body 0.20 / col 0.25 / inter 0.20). Threshold lowered to 60 to compensate for the more honest score distribution under the new model. (Both superseded again by R7 — see below.) |
| #83 | Source composer model from agent instance | Trace + log rows now read `self.outfit_composer._model` rather than a hardcoded literal, mirroring the architect's drift-protection pattern. |
| #88 | Composer emits per-outfit `name` | Cards previously rendered as "Outfit 1", "Outfit 2" — composer now writes a stylist-flavored title (e.g. *"Sharp Navy Boardroom"*, *"Camel Sand Refined"*) per outfit. Surfaces directly as the user-facing card title. |
| #91 | Composer name schema cap + null safety | `maxLength: 100` on `name` in the strict-output schema (review fix); parser uses `or ""` so an explicit JSON null doesn't ship as `"None"`. |
| #95 | Composer `model_call_logs.latency_ms` was always 0 | `_invoke()` never timed `responses.create()`; the per-attempt payload didn't carry latency at all. Fixed: any panel computing composer p50/p95 from `model_call_logs` now reads real values. |

### Rater (PRs #89, #101)

| PR | Title | Net change |
|---|---|---|
| #89 | Drop rater veto on `archetypal_preferences.disliked` | T12 had **8/8 outfits vetoed** because each touched a single disliked attribute (color_temperature: neutral, pattern: solid). Per-dim scores were healthy 70–88; the aggregate-veto rule was punching above its weight. Removed entirely; the rater no longer reads `archetypal_preferences`. |
| #101 | **R7: 6 dims on a 1/2/3 scale** | Most consequential change of the sweep. Rater contract moved from 4 dims on 0–100 → 6 dims on 1/2/3, schema-locked via `enum: [1, 2, 3]` per sub-score. Added Formality (was double-counted across `occasion_fit` + `inter_item_coherence`) and Statement (was a fractional sub-check inside `inter_item_coherence`). Renamed `inter_item_coherence` → `pairing`, scoped to fit + fabric only. Threshold moved 60 → 50 (all-2s outfit lands at exactly 50). Blend math: `((Σ subscore × weight) − 1) / 2 × 100` rescales to 0–100 for the card center. All five weight profiles rebalanced across 6 dims. |

### Architect — episodic memory (PRs #90, #92, #93, #97)

| PR | Title | Net change |
|---|---|---|
| #90 | Surface recent like/dislike timeline to the architect | New repo method `list_recent_user_actions(user_id, lookback_days=30)` returns a chronological 30-day timeline of like/dislike events, each row carrying `user_query`, `created_at`, `event_type`, and the garment's full attribute set. The architect prompt has a new "Recent user actions (episodic memory)" section instructing it to find context-dependent patterns (different occasions can take the same attribute differently) and bias retrieval queries — never as blanket exclusions. Replaces the old aggregate-veto signal with raw evidence the LLM can reason over. |
| #92 | PascalCase fix — episodic memory was empty for every user | PR #90 shipped with snake_case column names (`color_temperature`, `pattern_type`) in the `catalog_enriched` query. The actual schema uses **PascalCase** (`ColorTemperature`, `PatternType`). PostgREST 400-errored on every call; the `except Exception` swallowed it; every user got an empty timeline since #90 merged. Mocks also used snake_case, so tests didn't catch it. |
| #93 | Consolidate catalog attr mappings + log silent excepts | Single `_CATALOG_ATTR_MAP` (snake_case prompt key → PascalCase DB column) replaces the two parallel mappings that drifted in #90. Five `except Exception:` blocks across `aggregate_archetypal_feedback` + `list_recent_user_actions` now log `_log.warning(..., exc_info=True)` instead of swallowing — the next failure surfaces in logs instead of vanishing. |
| #97 | Narrow broad excepts to `(SupabaseError, httpx.RequestError)` | The five `except Exception:` blocks were catching too much — a `KeyError` from `_CATALOG_ATTR_MAP` or a `TypeError` mid-comprehension would silently degrade to an empty timeline (the same shape PR #92 just fixed). Logic errors now propagate fast. |

### Default routing — catalog-first (PR #82)

| PR | Title | Net change |
|---|---|---|
| #82 | Auto → catalog default; ≥2-per-role wardrobe coverage gate | Pre-#82, `source_preference="auto"` (no explicit signal) routed to the **wardrobe-first** path. Now the default routes to the **catalog**; wardrobe-first only fires on explicit "from my wardrobe" / "use my wardrobe". When the user does ask for wardrobe-first, a new minimum-coverage gate requires ≥2 tops AND ≥2 bottoms AND ≥2 one-pieces — falls through to a `wardrobe_unavailable` answer-source with the actual counts surfaced ("you have 2 tops, 2 bottoms, 0 dresses"). New `wardrobe_coverage` metadata block exposes counts + sufficient-flag for observability. |

### Observability + ops (PRs #94, #95, #96, #98, #99, #100)

| PR | Title | Net change |
|---|---|---|
| #94 | Recalibrate alerts + Panel 3 / 6 for the auto→catalog flip | LLM-cost daily-budget alert: $50 → $500 (gpt-5.4 composer was tripping the old threshold on every quiet day). Panel 3 + Panel 6 SQL + narration updated for the new dominant `answer_source` mix. Carve-out paragraph in Panel 16 + the try-on QG alert noting the post-#89 `unsuitable=True` rate baseline shift. |
| #96 | Add Panels 17–20 + script preserve-marker | New panels: **17** Architect Input Token Growth (PR #90/#92), **18** Rater Unsuitable Rate (PR #89 baseline), **19** Composer Latency (PR #95 baseline), **20** Episodic Memory Population (PR #90/#92). Plus `extract_dashboard_sql.py` now preserves curator content past a `<!-- preserve-below -->` marker so README.md no longer gets eaten on every regen. |
| #98 | Drop dates from panel filenames; SUM(CASE) → COUNT FILTER | Renamed `panel_16_*may_3_2026.sql` → `panel_16_low_confidence_catalog_responses.sql` (and 17–20 likewise). Cleaner SQL idiom. |
| #99 | Panel 20 query label was last_7d, CTE was 30d | Single-line comment fix to match the actual query window. |
| #100 | Panel 16 `NULLIF` → `nullif` | Casing alignment with every other panel in OPERATIONS.md. |

### Review-fix follow-ups (PRs #84, #85, #86, #87)

Four small PRs addressing reviewer feedback on PRs #82 + #88: precompute wardrobe coverage once and thread through both the wardrobe-first builder and the fallback (avoid double-walk on the insufficient-coverage path); inline a single-use local; drop a `list(... or [])` defensive wrapper that the schema's `default_factory=list` already covered; switch `getattr(user_context, ...)` to direct attribute access at call sites where `user_context` is statically known to be a `UserContext`.

### Pipeline shape (post-sweep)

```
copilot_planner (gpt-5-mini, 7s)
  → outfit_architect (gpt-5.4, 22-28s, ~15K input tokens with episodic memory)
  → catalog retrieval (text-embedding-3-small + pgvector, 3s)
  → outfit_composer (gpt-5.4, 13s, emits per-outfit name)
  → outfit_rater (gpt-5-mini, 13s, 6 dims on 1/2/3 scale)
  → tryon_render (gemini-3.1-flash-image-preview, 3 parallel, ~25s wallclock)
  → response_formatter
```

Threshold gate moved 60 → 50 (R7). All 6 weight profiles sum to 1.0. Pairing drops for `complete` (single-item) outfits → 5 axes; the orchestrator renormalizes the remaining 5 weights at compute time.

### Live verification (T13, 2026-05-05 17:21)

The first turn after R7 merged shipped 3 outfits with stylist-flavored names ("Camel Sand Refined" / "Chalk Navy Balance" / "Olive Mocha Office"). Rater emitted 1/2/3 across all six dims, no `unsuitable=True`, fashion_scores 87/92/94. Total turn cost 20.81¢, latency 100s — comparable to T10/T11 (3 try-on shipped) within margin; +6K architect tokens vs pre-#90 baseline (episodic memory carries weight).

**L0 tests:** 458 pass post-#101 (up from 434 at start of sweep; net change includes the rater test rewrite for the 6-dim 1/2/3 contract + new tests for composer name, episodic memory hydration, narrow except, threshold gate fixtures).

---

## May 3, 2026 — LLM ranker rollout

| PR | Title | Net change |
|---|---|---|
| #27 | Architect kurta hard rule + retrieval_count 12→5 | Catalog has zero compatible bottoms for a standalone kurta, so paired/three_piece kurta directions are now rejected at the prompt level; retrieval pool drops to 5 per query. |
| #28 | Drop kurta code-side check, rely on prompt | Removed the parser-level kurta validator added in #27; prompt rule alone enforces the contract. |
| #29 | Scaffold OutfitComposer + OutfitRater LLM agents | Two new gpt-5-mini agents + prompts + schemas, behind a flag. No orchestrator wiring yet. |
| #30 | Switch orchestrator to LLM ranker, delete assembler + reranker | Replaces ~600 lines of heuristic pairing code + the deterministic Reranker with the Composer + Rater pipeline. `assembly_score` (0–1) → `fashion_score` (0–100); `ranking_bias` retired. |
| #31 | Address PR #29 review notes | Top-level imports, type hints, tightened exception handling, rater stub schema consistency. |
| #32 | Address PR #30 review notes | Composer prompt mandates item order in `item_ids`; thread-safe `usage` carried on result objects; `_clamp01` → `_clamp_to_100`. |

**Pipeline change:**
- Before: `Architect → Retrieval → Assembler (heuristic) → Reranker (det) → ...`
- After: `Architect → Retrieval → Composer (LLM) → Rater (LLM) → ...`

**Observability:** new `tool_traces.composer_decision` + `rater_decision` rows carry per-outfit rationale + the four-dimension score breakdown. `model_call_logs` gets the full raw LLM JSON.

**L0 tests:** 434 pass (up from 382 pre-rollout; net change includes ~25 deleted assembler/reranker unit tests and ~50 new Composer + Rater tests).

## Open Items Plan (May 1, 2026)

Audit on May 1, 2026 surfaced five categories of open work. The first three are real code-pending tasks; the fourth is ops/deployment work gated on a staging environment; the fifth is a documentation hygiene sweep.

### 1. Wire `ranking_bias` into assembler + reranker — superseded May 3 2026

**Status:** The deterministic OutfitAssembler + Reranker were replaced with the LLM ranker (Composer + Rater) in PRs #29 / #30. `ranking_bias` is gone from the schema; the Rater reads user context directly. This entry is preserved as historical record only.

### 2. Stale onboarding test (P0, trivial)

**Status today:** `tests/test_onboarding.py:272` asserts `"Step 1 of 10"` but the UI now renders `"Step 1 of 9"` since the onboarding flow was streamlined (full-body + headshot merged into one screen, gender moved before images). 1 of 312 tests fails for this reason.

**Plan:**
- [x] Update the assertion to `"Step 1 of 9"`.

### 3. Reranker calibration plumbing — superseded May 3 2026

**Status:** The deterministic Reranker is gone (PR #30). `data/reranker_weights.json`, `ops/scripts/calibrate_reranker.py`, and `tool_traces.reranker_decision` rows are obsolete. The orphan files were removed in the May-3 doc-cleanup PR.

The LLM Rater is now the sole ranker. New observability rows live in `tool_traces` as `composer_decision` and `rater_decision`. Future calibration is informed by joining `rater_decision.fashion_score` to `feedback_events` — see `docs/OPERATIONS.md` Panel 16 for the reference query.

### 4. Release Readiness — gate-by-gate ops checklist (partial staging verification, May 1, 2026)

**Status today (May 1, 2026):** Code-side prep landed AND staging connectivity verified — schema audit, dependency report, catalog health, embedding coverage, and reranker calibration all run cleanly against the live staging Supabase. The remaining items need a deployed app, designer review, and real devices.

**Staging readouts (May 1, 2026):**
| Check | Result |
|---|---|
| `schema_audit.py` against staging | **PASS** — 55 enum + 2 text canonical attrs as of Step 2a + Path B (PRs #237/#239), no migration drift |
| `validate_dependency_report.py` (in-memory harness) | **PASS** — 15/15 assertions |
| Live `dependency_report` against staging telemetry | 11 onboarded users, 9 repeat sessions total, wardrobe memory shows +60pp retention lift, feedback +54pp |
| `catalog_enriched` row count | **14,242** ✅ post-Step-2b re-enrichment (54 CDN-broken rows dropped from original 14,296); all rows enriched on v3 + ShapeArchitecture axis set |
| `catalog_item_embeddings` row count | **14,242** ✅ exact 1:1 with `catalog_enriched`; embeddings regenerated against new axis set (text-embedding-3-small, 1536-dim) |
| Embedding orphan check | 0 orphans after Step-2b cleanup |
| `feedback_events` count | 672 (237 likes / 435 dislikes); all rows have `turn_id`, `outfit_rank`, `event_type` |
| `tool_traces.composer_decision` / `rater_decision` rows | LLM ranker logging shipped May 3 (PR #29 / #30) — needs production traffic to accumulate |

**Live finding — Gate 1 escalation D is firing in staging:** acquisition_source = `unknown` for **100% of 11 onboarded users** (threshold is >50%). The OTP-verify endpoint is no longer writing `acquisition_source` / `acquisition_campaign` / `referral_code` / `icp_tag`. Tracked as a follow-up — see Gate 1 below.

**Plan:** see `docs/RELEASE_READINESS.md` for the existing checklist. The concrete actions per gate:

**Gate 1 — Functional Correctness:**
- ~~run `pytest tests/` (must be 312/312 green)~~ ✅ Updated 2026-05-11: **1,225 passed + 1 skipped + 239 subtests passed** (skip is the "weights file missing" test). Cumulative additions since May 1: composition + composer engines (Phase 4.7-5), Path A→v3 axes (#237), Path B rationalization (#239), Step 2b catalog re-enrichment + embedding resync (May 11), Phase 4.3 hard/soft yaml_loader (#246), 4 new pairing matchers (#248-#251), bodyframe + occasion existing-vocab YAML edits (#252-#253), Phase 2 Wave A audit (#254), composer-side per-rule observability counters (#257).
- ~~run `APP_ENV=staging python3 ops/scripts/validate_dependency_report.py`~~ ✅ May 1, 2026: 15/15 assertions PASS against staging.
- run `ops/scripts/smoke_test_full_flow.sh` end-to-end against staging (deferred — needs deployed app + explicit approval to incur LLM token costs for the architect call. Read-only checks below cover the parts that don't need a live HTTP server.)
- catalog-unavailable test in staging: temporarily empty `catalog_item_embeddings`, POST a turn, assert guardrail copy fires (deferred — destructive against shared staging, needs explicit approval)
- ~~confirm wardrobe-first hybrid pivot user-story test exists~~ ✅ verified May 1, 2026: `test_single_item_wardrobe_first_does_not_short_circuit_catalog_pipeline` (catalog pivot path) at `tests/test_agentic_application.py:1770` and `test_explicit_wardrobe_occasion_request_returns_gap_fallback_when_coverage_is_missing` (gap fallback path) at `tests/test_agentic_application.py:2048`
- ⚠️ **acquisition_source instrumentation — known issue, code path verified intact** (May 1, 2026 → audit May 3, 2026): live staging snapshot showed 11/11 onboarded users with `acquisition_source = 'unknown'`. Code audit on May 3 confirmed the OTP-verify endpoint (`modules/user/src/user/api.py:91`), `verify_otp` service (`modules/user/src/user/service.py:279`), and the `VerifyOtpRequest` schema (`modules/user/src/user/schemas.py:48`) all carry `acquisition_source` end to end. The most likely cause of the staging numbers is the frontend not populating the field on the request — verify by capturing a live OTP-verify request body before the next staging readout. Not blocking; the dependency report can't attribute users to cohorts until this is verified.

**Gate 2 — Data & Environment Readiness:**
- ~~catalog row count ≥ 500 with `row_status in ('ok','complete')`~~ ✅ May 1, 2026: **14,295** in `(ok,complete)` against staging, 14,296 total.
- ~~embedding coverage check returns 0 orphan rows~~ ✅ May 1, 2026: 0 enrichable rows missing an embedding. 1 embedded row whose `catalog_enriched` row was demoted from `(ok,complete)` (cleanup PR-worthy).
- ~~`python3 ops/scripts/schema_audit.py` against staging~~ ✅ May 1, 2026: PASS, 46 attributes, no drift.
- approved enrichment CSV at `data/catalog/uploads/enriched_catalog_upload.csv` (deferred — file management decision)
- seed one fully-onboarded test user (deferred — staging already has 11 onboarded users; pick one via `select * from onboarding_profiles where onboarding_complete=true limit 1` and run the smoke test against them when explicit smoke-test approval lands)
- run smoke test as that user end-to-end (deferred per Gate 1 above)

**Gate 3 — Observability & Operations:**
- ~~build all 8 dashboard panels from `docs/OPERATIONS.md`~~ ✅ May 1, 2026: 14 panel SQL files extracted into `ops/dashboards/panel_NN_*.sql` via `ops/scripts/extract_dashboard_sql.py`; ready to paste into Supabase Studio / Metabase. Panel 15 (catalog search timeout) is log-based, no SQL — see `ops/dashboards/README.md`.
- wire alerts: Panel 4 `error_rate_pct > 5%` → Slack `#aura-oncall`; catalog-unavailable counter > 0 → page; Panel 7 negative signals daily review during week 1 (deferred — needs the dashboard tool to be provisioned first)
- ~~write on-call runbook in `docs/OPERATIONS.md`~~ ✅ May 1, 2026: § On-Call Runbook added with rotation slots, channels, four failure-mode runbooks, escalation timeline, post-incident process. Names + PagerDuty service still need to be filled in by the team.
- ~~pipe `_log.error` / `_log.warning` to a queryable sink~~ ✅ May 1, 2026: structured-logging shim shipped at `platform_core/logging_config.py`. Set `AURA_LOG_FORMAT=json` to emit single-line JSON records every modern aggregator (Logflare / Datadog / Cloud Logging / Loki) can ingest with no parsing. Default text behaviour unchanged. 3 regression tests in `tests/test_platform_core.py::StructuredLoggingConfigTests`.

**Gate 4 — Product & UX:**
- designer (not implementing engineer) walks `docs/DESIGN_SYSTEM_VALIDATION.md` checklist
- real-device QA at 430px (iPhone) + 1280px+ (MacBook) on `/`, `/wardrobe`, `/profile`, chat, outfits, checks tabs
- wardrobe-first pivot copy review with single-item wardrobe scenario
- follow-up `IMPROVE IT / SHOW ALTERNATIVES / SHOP THE GAP` headers visually confirmed
- copy tone review — read 20 staging response transcripts, flag dashboard-speak
- fill in sign-off block at `RELEASE_READINESS.md:122` — engineer + designer + date + commit SHA

### 5. Doc-stale cleanup (this commit)

The audit found 80 unchecked `[ ]` items in CURRENT_STATE.md whose code has actually shipped. They are being marked `[x]` in this same commit. See "Doc-Stale Sweep (May 1, 2026)" section below for the verified list.

### 6. Observability Hardening (May 1, 2026 audit) — **all 12 items SHIPPED**

**Status: complete (May 1, 2026).** All twelve items implemented, tested, and the full suite is **387 passed / 1 skipped**. Per-item summary at the bottom of this section. Original detailed plan kept below for reference.

**Why now:** the May 1 staging audit surfaced two real defects (turn-trace coverage at ~28%, no request-id propagation) and several missing-but-needed surfaces (`/readyz`, Prometheus, OpenTelemetry, PII redaction, alert-as-code). Today's observability tables are good — `turn_traces`, `model_call_logs`, `tool_traces`, `policy_event_log`, `dependency_validation_events`, `feedback_events` are all present and populated in staging — but the layer above them (live RED metrics, distributed tracing, log/trace correlation) is missing. This is the gap before Aura can run at first-50 scale and beyond.

**Verified-against-staging baseline (May 1, 2026):**
| Table | Staging count | Verdict |
|---|---|---|
| `turn_traces` | 120 | **Coverage gap** — 433 conversation_turns exist, only ~28% are traced. Three early-return paths in `process_turn` skip `_persist_trace`. |
| `model_call_logs` | 972 | Solid coverage; missing token usage + cost columns |
| `tool_traces` | 718 | Solid coverage for top-level tools; per-candidate parallel work-items not traced individually |
| `policy_event_log` | 393 | Working |
| `feedback_events` | 672 | All rows have `turn_id`, `outfit_rank`, `event_type` |

#### Plan — 12 items, priority-ordered

##### Item 1: trace coverage on error paths (P0, <1h)

**Problem:** [`orchestrator.py:993, 1067, 4109`](modules/agentic_application/src/agentic_application/orchestrator.py:993) — onboarding-blocked / planner-error / architect-error returns bypass `_persist_trace`. Staging shows 313 of 433 turns have no trace.

**Fix:**
- Wrap the dispatch logic in `process_turn` with a `try/finally` that calls `self._persist_trace(trace)` on every exit. Set `trace._persisted = True` after a successful persist so the finally block doesn't double-write.
- Each early-return path stays as-is; trace builder already accumulates state up to that point.
- Set `trace.set_evaluation({"response_type": "error", "stage_failed": <stage>})` immediately before each error return so the persisted record explains why the turn ended early.

**Tests** in `tests/test_agentic_application.py`:
- `test_onboarding_gate_blocked_turn_persists_trace`
- `test_planner_failure_persists_trace_with_error_stage`
- `test_architect_failure_persists_trace_with_error_stage`

**Files:** `modules/agentic_application/src/agentic_application/orchestrator.py`; new tests.

##### Item 2: request_id middleware + ContextVar log filter (P0, half-day)

**Problem:** zero HTTP middleware in [`api.py`](modules/agentic_application/src/agentic_application/api.py); 118 `_log.info` callsites in `modules/` don't thread `turn_id` / `conversation_id`. Operator can't correlate a user-reported slow turn to log lines or to upstream `OpenAI-Request-Id` / `x-supabase-request-id` headers.

**Fix:**
- New `modules/platform_core/src/platform_core/request_context.py` — `ContextVar` for `request_id`, `turn_id`, `conversation_id`, `external_user_id`. Helpers `set_*`, `get_*`, `clear()`.
- Update `platform_core/logging_config.py` to install `RequestContextFilter` on the root handler. Filter reads ContextVars and injects them into every `LogRecord` so the JSON formatter picks them up automatically.
- Add FastAPI middleware in `api.py` `create_app`:
  ```python
  @app.middleware("http")
  async def request_context(request, call_next):
      request_id = request.headers.get("x-request-id") or str(uuid4())
      token = set_request_id(request_id)
      try:
          response = await call_next(request)
          response.headers["x-request-id"] = request_id
          return response
      finally:
          reset_request_id(token)
  ```
- At top of `process_turn`, set `turn_id` and `conversation_id` ContextVars after `turn_id` is assigned.
- Add `request_id` column to `turn_traces`, `model_call_logs`, `tool_traces` via migration `<date>_observability_request_id.sql`.
- Capture upstream IDs: store `response.headers.get("x-request-id")` from OpenAI / Gemini / Supabase in the corresponding `model_call_logs.response_json.upstream_request_id` field.

**Tests** in `tests/test_platform_core.py`:
- `test_request_context_propagates_to_log_records`
- `test_request_id_middleware_generates_when_header_missing`
- `test_request_id_middleware_echoes_incoming_header`
- `test_orchestrator_sets_turn_id_contextvar`

**Files:**
- New `modules/platform_core/src/platform_core/request_context.py`
- `modules/platform_core/src/platform_core/logging_config.py`
- `modules/agentic_application/src/agentic_application/api.py`
- `modules/agentic_application/src/agentic_application/orchestrator.py`
- `modules/platform_core/src/platform_core/repositories.py` — accept `request_id` kwarg in 3 insert helpers
- New `supabase/migrations/<date>_observability_request_id.sql`
- `tests/test_platform_core.py`

##### Item 3: real `/readyz` + `/version` endpoints (P0, half-day)

**Problem:** [`api.py:450`](modules/agentic_application/src/agentic_application/api.py:450) `/healthz` returns `{"ok": True}` unconditionally — Kubernetes / load balancer thinks the service is healthy when Supabase is unreachable.

**Fix:**
- New `modules/platform_core/src/platform_core/readiness.py`:
  - `check_supabase(client) -> Tuple[bool, str]` — `SELECT 1 FROM users LIMIT 1` with a 2s timeout
  - `check_openai(api_key) -> Tuple[bool, str]` — HEAD on `https://api.openai.com/v1/models` with auth header, 2s timeout
  - `check_gemini(api_key) -> Tuple[bool, str]` — HEAD on `https://generativelanguage.googleapis.com/v1beta/models` with 2s timeout
  - All three run in parallel via `concurrent.futures.ThreadPoolExecutor` so a slow upstream doesn't dominate the check
- Add `/readyz` and `/version` in `api.py`. `/readyz` returns 503 if any check fails; `/version` returns `{commit, deployed_at, env}` from env vars (`AURA_COMMIT_SHA`, `AURA_DEPLOYED_AT`, `APP_ENV`).
- Update Dockerfile / deploy script to set `AURA_COMMIT_SHA=$(git rev-parse HEAD)` and `AURA_DEPLOYED_AT=$(date -u +%FT%TZ)` at build time (deferred to deploy infra).

**Tests** in `tests/test_agentic_application_api_ui.py`:
- `test_readyz_returns_200_when_all_checks_pass`
- `test_readyz_returns_503_when_supabase_check_fails`
- `test_version_returns_commit_and_env`

**Files:**
- New `modules/platform_core/src/platform_core/readiness.py`
- `modules/agentic_application/src/agentic_application/api.py` — 2 new endpoints
- `tests/test_agentic_application_api_ui.py`

##### Item 4: token usage + cost capture on every LLM call (P1, half-day)

**Problem:** [`repositories.py:150`](modules/platform_core/src/platform_core/repositories.py:150) `log_model_call` records request/response JSON but discards the `response.usage` field every OpenAI SDK call returns. No per-user / per-conversation cost attribution.

**Fix:**
- Migration `<date>_model_call_token_usage.sql`: add `prompt_tokens int`, `completion_tokens int`, `total_tokens int`, `estimated_cost_usd numeric(10,6)` columns to `model_call_logs`.
- New `modules/platform_core/src/platform_core/cost_estimator.py` with a static pricing table:
  ```python
  _PRICING = {
      "gpt-5.4":          {"input_per_1m": 2.50, "output_per_1m": 10.00},
      "gpt-5-mini":       {"input_per_1m": 0.15, "output_per_1m": 0.60},
      "text-embedding-3-small": {"input_per_1m": 0.02, "output_per_1m": 0.0},
      "gemini-3.1-flash-image-preview": {"flat_per_image": 0.039},
  }
  ```
  Helper `estimate_cost_usd(model, prompt_tokens, completion_tokens, image_count=0)`.
- Extend `log_model_call` signature with `prompt_tokens`, `completion_tokens`, `total_tokens`, `estimated_cost_usd` kwargs. Persist when present.
- Update each LLM call site to pass them:
  - [`copilot_planner.py:225`](modules/agentic_application/src/agentic_application/agents/copilot_planner.py:225) — read `response.usage.input_tokens` / `output_tokens` (Responses API field names)
  - [`outfit_architect.py:195`](modules/agentic_application/src/agentic_application/agents/outfit_architect.py:195)
  - [`visual_evaluator_agent.py:324`](modules/agentic_application/src/agentic_application/agents/visual_evaluator_agent.py:324)
  - [`style_advisor_agent.py:202`](modules/agentic_application/src/agentic_application/agents/style_advisor_agent.py:202)
  - [`outfit_decomposition.py:127`](modules/agentic_application/src/agentic_application/services/outfit_decomposition.py:127)
  - [`tryon_service.py`](modules/agentic_application/src/agentic_application/services/tryon_service.py) — pass `image_count=N_renders` for Gemini cost
- New `ops/dashboards/panel_16_per_user_llm_cost.sql` and `panel_17_daily_total_cost.sql`. Re-run `ops/scripts/extract_dashboard_sql.py` after adding to OPERATIONS.md.

**Tests** in `tests/test_platform_core.py`:
- `test_cost_estimator_gpt54_input_output_pricing`
- `test_cost_estimator_gemini_per_image`
- `test_cost_estimator_unknown_model_returns_zero`
- `test_log_model_call_persists_token_columns_when_provided`
- `test_log_model_call_back_compat_when_token_kwargs_omitted`

**Files:** new `cost_estimator.py`, modified `repositories.py`, 5 LLM call sites, new migration, OPERATIONS.md panel additions, tests.

##### Item 5: Prometheus `/metrics` endpoint with RED metrics (P1, 1 day)

**Problem:** no live percentile metrics. Latencies live in `turn_traces.steps[].latency_ms` JSON only — operators must run Postgres queries to see p95.

**Fix:**
- Add `prometheus-client>=0.19` to `requirements.txt`.
- New `modules/platform_core/src/platform_core/metrics.py`:
  - `aura_turn_total` — Counter labelled by `intent`, `action`, `status`
  - `aura_turn_duration_seconds` — Histogram labelled by `stage` (architect, search, assembler, reranker, visual_evaluation, response_formatting); buckets `[0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60]`
  - `aura_llm_call_total` — Counter labelled by `service`, `model`, `status`
  - `aura_llm_call_duration_seconds` — Histogram labelled by `service`, `model`
  - `aura_external_call_duration_seconds` — Histogram labelled by `service` (`supabase`, `openai`, `gemini`), `operation`, `status`
  - `aura_tryon_quality_gate_total` — Counter labelled by `passed` (`true`/`false`)
  - `aura_in_flight_turns` — Gauge
- Add `/metrics` endpoint in `api.py`:
  ```python
  from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
  @app.get("/metrics")
  def metrics():
      return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
  ```
- Wire metric `.observe()` calls into existing instrumentation hooks:
  - In `trace_end()` inside `process_turn` → `aura_turn_duration_seconds.labels(stage=step).observe(latency_ms / 1000)`
  - In `log_model_call` → `aura_llm_call_total.labels(...).inc()` + duration histogram
  - In `SupabaseRestClient._request` → `aura_external_call_duration_seconds.labels("supabase", method, status).observe(latency)`
  - In `_render_candidates_for_visual_eval` → `aura_tryon_quality_gate_total.labels(passed=...)`
  - At top of `process_turn` increment `aura_in_flight_turns`, decrement in finally

**Tests** in `tests/test_platform_core.py`:
- `test_metrics_endpoint_returns_prometheus_format`
- `test_turn_counter_increments_on_simulated_turn`
- `test_llm_histogram_records_latency`

**Files:** `requirements.txt`, new `metrics.py`, `api.py`, `orchestrator.py`, `repositories.py`, `supabase_rest.py`, tests.

##### Item 6: OpenTelemetry tracing (P1, 2 days)

**Problem:** spans stop at the FastAPI boundary. No parent/child relationships across the planner→architect→6 parallel searches→assembler→reranker→3 parallel try-ons→3 parallel evaluators graph. No way to share trace context with downstream services or upstream RUM.

**Fix:**
- Add packages: `opentelemetry-api>=1.27`, `opentelemetry-sdk>=1.27`, `opentelemetry-exporter-otlp>=1.27`, `opentelemetry-instrumentation-fastapi>=0.48`, `opentelemetry-instrumentation-urllib>=0.48`.
- New `modules/platform_core/src/platform_core/otel_setup.py`:
  - `configure_otel(service_name="aura")` — sets up `TracerProvider`, `BatchSpanProcessor`, OTLP exporter targeting `OTEL_EXPORTER_OTLP_ENDPOINT` env var.
  - Honours W3C Trace Context (default in SDK).
  - Default sampler: `ParentBased(TraceIdRatioBased(0.1))` so 10% of turns are sampled but children inherit parent decision. Override via `OTEL_TRACES_SAMPLER_ARG`.
  - No-op when `OTEL_EXPORTER_OTLP_ENDPOINT` is unset (local dev).
- Wire into `api.py`:
  ```python
  from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
  configure_otel("aura-agentic-application")
  FastAPIInstrumentor.instrument_app(app)
  ```
- Manual spans in orchestrator (replacing/enhancing the existing `trace_start`/`trace_end` helpers):
  ```python
  tracer = trace.get_tracer("aura.orchestrator")
  with tracer.start_as_current_span("copilot_planner") as span:
      span.set_attribute("aura.model", "gpt-5.4")
      span.set_attribute("aura.user_id_hash", _hash_user_id(external_user_id))
      span.set_attribute("aura.has_image", bool(image_data))
      plan_result = self._copilot_planner.plan(...)
      span.set_attribute("aura.intent", plan_result.intent)
  ```
- Parallel-section span propagation: pass `trace.get_current_span().get_span_context()` into worker callables so each parallel task creates a child span linked to the parent.
- Keep the DB `turn_traces` write — it's the audit log. OTel adds the live waterfall view.

**Tests** in new `tests/test_otel.py`:
- Use OTel test exporter (`opentelemetry.sdk.trace.export.in_memory_span_exporter`) to assert:
  - `test_otel_creates_root_span_per_turn`
  - `test_otel_pipeline_spans_have_correct_parent`
  - `test_otel_parallel_search_spans_share_parent`
  - `test_otel_traceparent_header_propagation`

**Files:** `requirements.txt`, new `otel_setup.py`, `api.py`, `orchestrator.py`, agent files (5 of them), new test file.

##### Item 7: PII redactor before observability inserts (P1, 1 day)

**Problem:** `model_call_logs.request_json` includes raw user message + full profile (gender, height, body shape, color analysis). `turn_traces.user_message` stores raw user input. No redaction. GDPR / least-privilege risk.

**Fix:**
- New `modules/platform_core/src/platform_core/pii_redactor.py`:
  ```python
  EMAIL_RE = re.compile(r'\b[\w.-]+@[\w.-]+\.\w+\b')
  PHONE_RE = re.compile(r'(\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}')
  SSN_RE = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')

  def redact_string(s: str) -> str: ...
  def redact_value(v: Any) -> Any:  # recurse dicts/lists
  def redact_profile(profile: dict) -> dict:
      """Truncate body measurements to bands, drop exact cm/age."""
  ```
  Profile bands: height_cm → `Petite|Average|Tall`; waist_cm → existing `WaistSizeBand`; date_of_birth → 5-year age band.
- Wire into `repositories.py`:
  - `log_model_call(..., redact_pii: bool = True)` — redact `request_json` and `response_json` recursively before insert
  - `insert_turn_trace(..., redact_pii: bool = True)` — redact `user_message` and `profile_snapshot`
- Add data-subject deletion helper:
  ```python
  def delete_user_observability_data(self, external_user_id: str) -> Dict[str, int]:
      """GDPR: delete all observability rows for a user. Returns row counts deleted per table."""
  ```
  Tables: `turn_traces`, `model_call_logs`, `tool_traces`, `policy_event_log`, `feedback_events`, `dependency_validation_events`, `catalog_interaction_history`, `user_comfort_learning`.

**Tests** in new `tests/test_pii_redactor.py`:
- `test_redact_emails`, `test_redact_phones`, `test_redact_ssns`
- `test_redact_profile_buckets_height_cm_into_band`
- `test_redact_value_recurses_nested_dicts_and_lists`
- `test_log_model_call_redacts_pii_in_request_json`
- `test_delete_user_observability_data_returns_row_counts`

**Files:** new `pii_redactor.py`, `repositories.py`, new test file.

##### Item 8: shared logging bootstrap in all entry points (P0, <1h)

**Problem:** `configure_logging()` only wired into `run_agentic_application.py`. `run_catalog_enrichment.py` and `run_user_profiler.py` emit text-formatted logs even when `AURA_LOG_FORMAT=json`.

**Fix:**
- Add `configure_logging()` call to top of `main()` in `run_catalog_enrichment.py` and `run_user_profiler.py`.
- A 2-line change in each.

**Tests:** the existing `tests/test_platform_core.py::StructuredLoggingConfigTests` already covers the configurator. No new tests needed — just visual verification that `AURA_LOG_FORMAT=json python3 run_catalog_enrichment.py …` emits JSON.

**Files:** `run_catalog_enrichment.py`, `run_user_profiler.py`.

##### Item 9: alert rules in code (P1, 1 day)

**Problem:** thresholds described in prose in `OPERATIONS.md`. No `ops/alerts/` directory. Alerts get configured in the dashboard tool's UI by hand → can be deleted accidentally with no audit trail.

**Fix:**
- New `ops/alerts/` directory. One YAML file per alert in Prometheus AlertManager format (most universal target — Datadog, Grafana, AlertManager, even Cloud Monitoring can ingest):
  - `pipeline_error_rate.yaml` — Panel 4 trigger
  - `catalog_unavailable_guardrail.yaml` — Panel 4 trigger; pages on first hit
  - `negative_signals_concentration.yaml` — Panel 7 trigger
  - `tryon_quality_gate_unhealthy.yaml` — Panel 10 trigger
  - `final_response_count_low.yaml` — Panel 11 trigger
  - `wardrobe_enrichment_degraded.yaml` — Panel 12 trigger
  - `catalog_search_timeouts.yaml` — Panel 15 trigger
- Each YAML file contains: `alert`, `expr` (PromQL — uses metrics from item 5), `for` (duration), `severity` (P1/P2), `runbook_url` (link into `docs/OPERATIONS.md` On-Call Runbook section).
- New `ops/scripts/sync_alerts.py` — read the directory, validate YAML structure, emit format-specific output (initial: print to stdout for review; later: HTTP POST to AlertManager / Datadog API).
- Add a section to `docs/OPERATIONS.md` § Alert Rules pointing to `ops/alerts/`.

**Tests** in new `tests/test_alert_rules.py`:
- `test_every_alert_yaml_has_required_fields`
- `test_every_alert_severity_is_valid`
- `test_every_runbook_url_resolves_to_an_existing_section`

**Files:** ~7 new YAML files, new sync script, OPERATIONS.md edit, test file.

##### Item 10: per-stage parallel work-item traces (P2, 1 day)

**Problem:** [`orchestrator.py:4612 _render_candidates_for_visual_eval`](modules/agentic_application/src/agentic_application/orchestrator.py:4612) emits aggregate counters (`tryon_attempted_count`, etc.) but no per-candidate timing. Same for [`_evaluate_candidates_visually:4810`](modules/agentic_application/src/agentic_application/orchestrator.py:4810). A slow turn can't be debugged without rerunning.

**Fix:**
- Wrap each parallel work-item with a `tool_traces` row:
  ```python
  def _render_one(candidate):
      started = time.monotonic()
      try:
          result = self.tryon_service.render(...)
          status, error = "ok", None
      except Exception as e:
          result, status, error = None, "error", str(e)
      latency_ms = int((time.monotonic() - started) * 1000)
      self.repo.log_tool_trace(
          conversation_id=conversation_id, turn_id=turn_id,
          tool_name="tryon_render",
          input_json={"candidate_id": candidate.candidate_id, "garment_ids": [...]},
          output_json={"latency_ms": latency_ms, "status": status, "quality_passed": ..., "parent_step": "visual_evaluation"},
          latency_ms=latency_ms, status=status, error_message=error or "",
      )
      return result
  ```
- Same shape for `_evaluate_one_candidate` inside `_evaluate_candidates_visually`.
- Tools schema gains an implicit `parent_step` field via `output_json` (no migration — `tool_traces` already JSONB-typed).
- These per-candidate rows multiply tool_traces volume by ~3-5×, so the daily retention sweep (item 12) becomes more important.

**Tests** in `tests/test_agentic_application.py`:
- `test_render_candidates_logs_per_candidate_tool_trace`
- `test_evaluate_candidates_logs_per_candidate_tool_trace`
- `test_per_candidate_traces_carry_parent_step_in_output_json`

**Files:** `orchestrator.py`, tests.

##### Item 11: sample `model_call_logs.request_json` (P2, 1h)

**Problem:** every architect call's full request payload (~10 KB) is persisted. Staging is at 972 rows × 10 KB ≈ 10 MB just for that column. At 100× scale this is ~1 GB and growing.

**Fix:**
- Env var `AURA_LOG_REQUEST_BODY_SAMPLE_RATE` (default `1.0`).
- In `log_model_call`, if `random.random() > sample_rate`, replace `request_json` with a summary:
  ```python
  request_json = {
      "sampled_out": True,
      "model": model,
      "input_size_chars": _approx_size(original_request_json),
  }
  ```
- Same option for `response_json` via `AURA_LOG_RESPONSE_BODY_SAMPLE_RATE`.
- Defaults stay at `1.0` so today's behaviour is preserved.

**Tests:** 2 small tests asserting the sampling behavior.

**Files:** `repositories.py`, tests.

##### Item 12: log retention policy (P2, 1h)

**Problem:** observability tables grow unbounded.

**Fix:**
- New `ops/scripts/cleanup_observability_logs.py` — accepts `--days N` (default 30); deletes from `model_call_logs`, `tool_traces`, `turn_traces` where `created_at < now() - N days`.
- Document in `docs/OPERATIONS.md` § Retention: "run `python3 ops/scripts/cleanup_observability_logs.py --days 30` daily via cron / GitHub Action / Supabase scheduled function".
- Aggregates that we want to keep long-term (acquisition, retention, dependency lift) live in `dependency_validation_events` and `feedback_events` — those are NOT swept.

**Tests** in `tests/test_cleanup_observability_logs.py`:
- `test_cleanup_deletes_rows_older_than_threshold`
- `test_cleanup_preserves_recent_rows`
- `test_cleanup_does_not_touch_feedback_events`

**Files:** new script, OPERATIONS.md edit, test file.

#### Effort + priority summary

| # | Item | Priority | Effort |
|---|---|---|---|
| 1 | trace coverage on error paths | P0 | <1h |
| 8 | shared logging bootstrap | P0 | <1h |
| 2 | request_id middleware + ContextVar log filter | P0 | half-day |
| 3 | `/readyz` + `/version` endpoints | P0 | half-day |
| 4 | token usage + cost capture | P1 | half-day |
| 5 | Prometheus `/metrics` + RED histograms | P1 | 1 day |
| 7 | PII redactor + GDPR delete helper | P1 | 1 day |
| 9 | alert rules in code | P1 | 1 day |
| 6 | OpenTelemetry tracing | P1 | 2 days |
| 10 | per-stage parallel work-item traces | P2 | 1 day |
| 11 | request body sampling | P2 | 1h |
| 12 | log retention sweep script | P2 | 1h |

**Total P0 work: 1.5 days** (items 1 + 2 + 3 + 8). Closes the trace-coverage gap, makes logs correlatable, and gives the team a real readiness probe before serving the first 50 users.

**Total P1 work: ~5 days.** Adds production-grade RED metrics, GDPR-clean data flow, alerts-as-code, and full distributed tracing with W3C trace context propagation.

**Total P2 work: 3 days.** Operational polish — deeper trace fidelity, retention, and cost control.

#### Shipped (May 1, 2026) — verification table

| # | Item | Files added/modified | Tests added |
|---|---|---|---|
| 1 | trace coverage on error paths | `orchestrator.py` — `_persist_trace` idempotent + persists on onboarding-blocked / planner-error returns | `test_orchestrator_blocks_turn_when_onboarding_is_incomplete` (extended), `test_orchestrator_planner_failure_persists_trace_with_error_stage` (new) |
| 2 | request_id middleware + ContextVar log filter | new `request_context.py`, `logging_config.py`, `api.py` middleware, `orchestrator.py` ContextVar setters, repo helpers stamp request_id, migration `20260501100000_observability_request_id.sql` | `RequestContextTests`, `RepositoryRequestIdStampingTests`, `test_request_id_middleware_*` (9 tests) |
| 3 | /readyz + /version endpoints | new `readiness.py` with parallel Supabase / OpenAI / Gemini checks; 2 endpoints in `api.py` | `test_healthz_returns_200_*`, `test_readyz_returns_*`, `test_version_returns_*` (4 tests) |
| 4 | token usage + cost capture | new `cost_estimator.py` with pricing + `extract_token_usage`; `repositories.py` extends `log_model_call`; 4 LLM agents expose `last_usage`; orchestrator passes through; migration `20260501110000_model_call_token_usage.sql` | `CostEstimatorTests` (9 tests) |
| 5 | Prometheus /metrics + RED metrics | new `metrics.py` (7 metrics), `requirements.txt` adds `prometheus-client`, `/metrics` endpoint, observe-hooks in `trace_end`, `log_model_call`, `supabase_rest._request`, tryon quality gate | `PrometheusMetricsTests`, `test_metrics_endpoint_returns_prometheus_text` (5 tests) |
| 6 | OpenTelemetry tracing | new `otel_setup.py`, OTLP exporter wiring, FastAPI auto-instrumentation, child-span emission via `trace_end`; `requirements.txt` adds 4 packages | `OtelSetupTests` (4 tests) |
| 7 | PII redactor + GDPR delete | new `pii_redactor.py`, `redact_pii=True` default on `log_model_call` + `insert_turn_trace`, new `repositories.delete_user_observability_data`, `supabase_rest.delete_one` | `test_pii_redactor.py` (19 tests) |
| 8 | shared logging bootstrap | `run_catalog_enrichment.py` + `run_user_profiler.py` call `configure_logging()` | covered by existing `StructuredLoggingConfigTests` |
| 9 | alert rules in code | 7 YAML files in `ops/alerts/`, validation script `ops/scripts/sync_alerts.py`, `ops/alerts/README.md` | `test_alert_rules.py` (4 tests + 7 subtests) |
| 10 | per-candidate parallel work-item traces | `orchestrator.py:_render_one` emits `tool_traces` row per candidate with status (cache_hit / quality_gate_failed / decode_failed / etc.) and parent_step="visual_evaluation" | covered by existing pipeline tests |
| 11 | request body sampling | `repositories.log_model_call` sampling block driven by `AURA_LOG_REQUEST_BODY_SAMPLE_RATE` and `AURA_LOG_RESPONSE_BODY_SAMPLE_RATE` env vars; default 1.0 preserves today's behaviour | inline in repo helper |
| 12 | log retention sweep | new `ops/scripts/cleanup_observability_logs.py` with `--days N` and `--dry-run`, paged delete, only sweeps `model_call_logs` / `tool_traces` / `turn_traces` (aggregate tables preserved) | dry-run verified against staging |

**Test totals after this work:** 387 passed, 1 skipped (was 330 before this section).

**Migrations added (must be applied to staging before deploy):**
- `supabase/migrations/20260501100000_observability_request_id.sql` — adds `request_id` text column + index to `turn_traces`, `model_call_logs`, `tool_traces`
- `supabase/migrations/20260501110000_model_call_token_usage.sql` — adds `prompt_tokens` / `completion_tokens` / `total_tokens` / `estimated_cost_usd` columns to `model_call_logs`

**Operations runbook update:** the `docs/OPERATIONS.md` § On-Call Runbook section now references the metric names that the alerts in `ops/alerts/*.yaml` use; the alert rules sync via `ops/scripts/sync_alerts.py` to Prometheus-format YAML.

**Environment variables added:**
- `AURA_LOG_FORMAT` — `text` (default) or `json`
- `AURA_LOG_LEVEL` — defaults to `INFO`
- `AURA_LOG_INCLUDE_PROC` — `0` / `1`
- `AURA_LOG_REQUEST_BODY_SAMPLE_RATE` / `AURA_LOG_RESPONSE_BODY_SAMPLE_RATE` — sampling rates for `model_call_logs`
- `AURA_COMMIT_SHA` / `AURA_DEPLOYED_AT` — surfaced via `/version`
- `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_TRACES_SAMPLER_ARG` — turn on distributed tracing

#### Open follow-ups

- [x] Apply both May-1 migrations (`request_id` on tracing tables; token-usage columns on `model_call_logs`) to staging — verified May 3, 2026.
- [x] Wire token-cost capture into Gemini try-on calls — `image_count` now flows into `log_model_call` from the `tryon_service` call site so per-Gemini-call cost lands in `model_call_logs.estimated_cost_usd`.

### 7. Outfits Tab Theme Taxonomy (May 1, 2026) — **SHIPPED**

**Status: complete (May 1, 2026).** All planned items shipped, 36 new theme-taxonomy tests + endpoint coverage. Full suite: 423 passed / 1 skipped.

**Why now:** the Outfits tab today groups by raw `occasion_signal` strings the planner extracts from user messages. That string is uncontrolled vocabulary, so semantically-equivalent occasions split into multiple buckets. A real staging user produced this group list:

> *casual outing, general, beach, casual, occasion recommendation, traditional engagement, weekend outing, evening, date night, engagement wedding, wedding engagement, engagement, date night, pairing request*

Two underlying defects:
1. **Vocabulary explosion** — `casual` / `casual outing` / `weekend outing` are one occasion; `engagement` / `traditional engagement` / `engagement wedding` / `wedding engagement` are one wedding-cycle.
2. **Fallback intent labels leak** — when `occasion_signal` is empty, the bucket falls back to `intent.replace("_", " ")` so the user sees `"occasion recommendation"` and `"pairing request"` as if they were occasions. They aren't.

The fix is a deterministic theme taxonomy applied at read-time in the `intent-history` endpoint — no migration, no backfill, no per-turn LLM cost.

#### Plan

- [x] **Theme module** — new `modules/agentic_application/src/agentic_application/services/theme_taxonomy.py` with:
  - `THEMES: dict[str, dict]` — 8 canonical themes (`wedding`, `festive`, `date`, `work`, `casual`, `travel`, `evening`, `style_sessions` fallback) each with `label`, `description`, `order`.
  - `KEYWORDS: list[tuple[str, str]]` — keyword fragments paired with theme keys; precedence is `wedding` > `festive` > `date` > `work` > `travel` > `evening` > `casual` so e.g. "engagement evening" lands in Wedding & Engagement.
  - `map_to_theme(occasion_signal, intent="") -> str` — pure function, returns one of the 8 theme keys. Uses **regex word-boundary matching** so short keywords like `holi` (Holi festival) don't accidentally match `holiday` (which lands in `travel`).
- [x] **Schema additions** — `IntentHistoryThemeBlock` in `platform_core/api_schemas.py` with `theme_key`, `theme_label`, `theme_description`, `group_count`, `total_outfit_count`, `most_recent_at`, `groups: list[IntentHistoryGroup]`. Added `themes: list[IntentHistoryThemeBlock]` to `IntentHistoryResponse` alongside `groups` for back-compat.
- [x] **Endpoint update** — `list_intent_history` in `agentic_application/api.py` folds the flat groups dict into theme blocks via `map_to_theme()`. Sorts themes by most-recently-active turn timestamp (canonical order is the tiebreaker).
- [x] **UI update** — `platform_core/ui.py` Outfits page renders a section per theme: 36px Fraunces italic header (28px on mobile), champagne underline, JetBrains Mono uppercase subtitle ("3 looks across 2 sessions"), then the existing PDP carousel pattern inside each. Empty themes are hidden. Falls back to the flat `groups` list when the server omits the `themes` payload (backwards compat for staged deploys).
- [x] **Telemetry hook** — `is_unmapped()` helper + per-process dedup set in `api.py` (`_THEME_UNMAPPED_LOGGED`). Each unique unmapped signal emits exactly one `tool_traces` row with `tool_name="theme_unmapped"` per process lifetime; a weekly query over the last 7d surfaces the keyword-list growth edge.
- [x] **Tests** — `tests/test_theme_taxonomy.py` (36 tests) covers: every example from the bug report → expected theme; wedding precedence over evening/casual; festive vs date overlaps; word-boundary matching (holi vs holiday); whitespace + casing + underscore normalization; empty signal + intent fallback; helper functions.

**Acceptance test:** the staging user's 14-group list collapses to 5 themes:
- `Wedding & Engagement` — engagement, traditional engagement, engagement wedding, wedding engagement
- `Casual & Everyday` — casual, casual outing, weekend outing
- `Travel & Vacation` — beach
- `Date & Romance` — date night, date night (dedup)
- `Evening & Party` — evening
- `Style Sessions` — general, occasion recommendation, pairing request

**Effort actual:** ~2 hours. No migration, no planner change, contained to the read path.

#### Acceptance verification

The user-reported list of 14 group names collapsed to 5 themes exactly as planned (`tests/test_theme_taxonomy.py::AcceptanceFromBugReport`):

| Original | Theme |
|---|---|
| casual outing, casual, weekend outing | **Casual & Everyday** |
| beach | **Travel & Vacation** |
| traditional engagement, engagement wedding, wedding engagement, engagement | **Wedding & Engagement** |
| evening | **Evening & Party** |
| date night, date night (dup) | **Date & Romance** |
| general, "occasion recommendation" (empty signal), "pairing request" (empty signal) | **Style Sessions** |

#### Files added/modified

| File | Change |
|---|---|
| `modules/agentic_application/src/agentic_application/services/theme_taxonomy.py` | NEW — 220 lines, 8 themes, ~60 keywords, regex word-boundary matcher |
| `modules/platform_core/src/platform_core/api_schemas.py` | `IntentHistoryThemeBlock` class added; `theme_key` on `IntentHistoryGroup`; `themes` list on `IntentHistoryResponse` |
| `modules/agentic_application/src/agentic_application/api.py` | Group construction stamps `theme_key`; new theme-folding pass after group build; per-process dedup'd telemetry on unmapped signals |
| `modules/platform_core/src/platform_core/ui.py` | Outfits tab renders themes-of-groups; new `.theme-block / .theme-header / .theme-title / .theme-subtitle / .theme-groups` CSS |
| `tests/test_theme_taxonomy.py` | NEW — 36 tests |

#### Trade-offs

- Keyword precedence is opinionated. "Wedding cocktail party" lands in Wedding (correct) because wedding outranks evening; "office cocktail" lands in Work then casual. Edge cases get explicit tests in the taxonomy file.
- New themes (Sports & Outdoor, Religious, Cultural performance) require product buy-in to add — keep the list small.
- Long-term move: have the planner emit `occasion_theme` on `resolved_context` once we have a quarter of mapper telemetry showing which signals are hardest. For now, deterministic rules win on inspectability.

### 8. Model Migration (May 1, 2026) — **SHIPPED**

**Why:** gpt-5.4 latency was the long pole on every recommendation turn. The user picked a tiered move: keep the workhorse on a more capable model where reasoning quality drives downstream output (planner, architect, user analysis), and downgrade structured-output paths to gpt-5-mini where schema constraints contain risk (visual evaluator, image moderation, outfit decomposition).

**Changes:**

| Component | Before | After | Rationale |
|---|---|---|---|
| **Copilot Planner** | gpt-5.4 | **gpt-5.5** | Highest leverage call per turn — wrong intent = wrong handler. Pay for the better reasoning. |
| **Outfit Architect** | gpt-5.4 | **gpt-5.5** | Architect output drives retrieval quality across the entire pipeline; better directions / hard filters / query documents lift every downstream stage. |
| **User Analysis (3 agents)** | gpt-5.4 | **gpt-5.5** | One-time onboarding cost but the output drives every recommendation forever after. Better seasonal-color / body-type extraction = better outfits long-term. |
| **Visual Evaluator** | gpt-5.4 | **gpt-5-mini** | Tight JSON schema (9 evaluation pcts + 8 archetype pcts per candidate) constrains output corridor; mini handles structured scoring well. Score noise affects ranking-within-pool only — retrieval is upstream and unaffected. Latency win compounds 3-5x because evaluator runs in parallel post-try-on. |
| **Image Moderation** | gpt-5.4 | **gpt-5-mini** | Binary allow/block decision with one-line rationale; the heuristic layer catches the obvious cases so the model only fires on ambiguous uploads. ~2-3s saved per wardrobe save. |
| **Outfit Decomposition** | gpt-5-mini | gpt-5-mini *(no change)* | Already on mini — flagged for confirmation, no edit needed. |
| **Style Advisor** | gpt-5.4 | **gpt-5.5** | Free-form prose for `style_discovery` and `explanation_request` turns where voice quality is the user-facing value. Upgraded alongside the other reasoning paths to keep stylist tone consistent across the product. |

**Files modified:**
- [`copilot_planner.py:219`](modules/agentic_application/src/agentic_application/agents/copilot_planner.py:219)
- [`outfit_architect.py:188`](modules/agentic_application/src/agentic_application/agents/outfit_architect.py:188)
- [`visual_evaluator_agent.py:266`](modules/agentic_application/src/agentic_application/agents/visual_evaluator_agent.py:266)
- [`image_moderation.py:49`](modules/platform_core/src/platform_core/image_moderation.py:49)
- [`user/analysis.py:111`](modules/user/src/user/analysis.py:111)
- [`user_profiler/config.py:7`](modules/user_profiler/src/user_profiler/config.py:7)
- 10 hardcoded `model="gpt-5.4"` strings in [`orchestrator.py`](modules/agentic_application/src/agentic_application/orchestrator.py) (planner: 3 sites → gpt-5.5; architect: 3 sites → gpt-5.5; visual eval: 4 sites → gpt-5-mini)
- [`cost_estimator.py:25`](modules/platform_core/src/platform_core/cost_estimator.py:25) — added `gpt-5.5` pricing entry at the published OpenAI list price ($5.00/M input, $30.00/M output). Legacy `gpt-5.4` row preserved so historical `model_call_logs` rows still cost-attribute correctly. The 2× input / 1.5× output multiplier OpenAI applies to prompts >272K input tokens is intentionally not modelled — Aura's typical request payloads stay well under 30K, so the simpler formula stays accurate.
- 4 test sites updated to assert the new defaults; the rest of the gpt-5.4 references in tests are incidental (PII redactor, log_model_call shape, OTel attribute) and pass through unchanged because the legacy entry preserves the lookup.

**Verification:** `pytest tests/` 423 passed / 1 skipped, no regressions. Doc table at the top of the **§ Models** section updated to reflect the new state.

**Open follow-ups:** none — gpt-5.5 list price is now in the table; Style Advisor moved to gpt-5.5 alongside the other reasoning paths so the entire user-visible response surface uses the same model.

---

