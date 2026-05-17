# Open Tasks

This file lists what's open **now**. Shipped work history lives in `docs/RELEASE_READINESS.md` § "Recently Shipped". Forward-planning content was intentionally removed 2026-05-11 — the user wants this file to reflect only what's worth focusing on today.

---

## Active focus: Shopify split — storefront + Vibe app + multi-tenant engine

The engine, today a single-tenant server-rendered app, is being split into three deployments:

1. **Shopify storefront** — live at `thesigmavibe.shop`. Catalog imported, branded, ready for customers. India / INR only. Manual fulfillment to original retailers.
2. **Vibe (Shopify App)** — deployed to Vercel at `vibe-app-five.vercel.app`. App Proxy serves the Conversation page at `thesigmavibe.shop/apps/vibe/style` (and on dev store `vibe-test-nmt8wy3q.myshopify.com/apps/vibe/style`). Chat loop end-to-end against the real engine. Merchant admin still on the stock Polaris "Generate a product" template — D.M.1 replaces it.
3. **Vibe Engine** — deployed to Fly.io Mumbai (`vibe-engine.fly.dev`, single 1GB shared-cpu-1x always-on). `vibe_storefront` channel now bypasses the onboarding gate so partial-profile customers can chat. Multi-tenant refactor (Phase C) still deferred until Vibe UX validates.

### Locked infrastructure (2026-05-14/15)

| | Value |
|---|---|
| Storefront brand | TheSigmaVibe |
| Storefront custom domain | `thesigmavibe.shop` |
| Storefront `.myshopify.com` (canonical) | `q8pery-95.myshopify.com` (also reachable: `the-vibe-shop-9376.myshopify.com`) |
| Storefront `tenant_id` | `t_Oq0BSHnewiEAAAAAagWWlmnV-0sJmcGk` |
| Storefront owner email | `hellosigmascience+partner@gmail.com` |
| Partner org | "Vibe" |
| Partner email | `mj.nigam28@gmail.com` |
| Vibe app dev store | `vibe-test-nmt8wy3q.myshopify.com` |
| Vibe app `client_id` | `937540a1df123dfcd486426ede2b3722` |
| Vibe app hosting | **Vercel — live at `https://vibe-app-five.vercel.app`** (deployed 2026-05-15). **Plan: Hobby (free); functions pinned to `bom1` (Mumbai)** via `vercel.json`. Hobby's 60s function-duration cap is fine because we use async poll (each call ≪ 1s). |
| Vibe app session store | Postgres `vibe` schema on Supabase (isolated from engine's `public` schema) |
| Engine ↔ Vibe app co-location | **Both Mumbai** — Vercel `bom1` (Vibe app functions) + Fly.io `bom` (engine, planned). Intra-city RTT ~5–20ms vs cross-region ~200–300ms. Cuts per-turn polling overhead from 3–6s to 75–600ms. |
| Dev tunnel (legacy) | All free tunnels (Cloudflare quick / ngrok free / localtunnel / Pinggy) failed in BLR/BOM regions due to anti-abuse interstitials breaking server-to-server app proxy requests. **Tunnels eliminated by deploying directly to Vercel.** |
| Engine hosting | **Fly.io Mumbai — live at `https://vibe-engine.fly.dev`** (deployed 2026-05-15). App `vibe-engine`, primary_region `bom`, shared-cpu-1x 1GB always-on, `/healthz` checked every 30s. |
| Markup on imported prices | 20% (1.2× source, rounded to whole rupees) |

**Locked decisions:** INR + India only · Razorpay · GST · images served by Shopify CDN (ingested from source URLs on import — no R2 staging needed) · public App Store is the destination, custom app is the starting point · reuse a free Shopify wishlist app, don't build · catalog seeding pipeline is one-shot for TheSigmaVibe (future tenants bring their own Shopify catalog).

### `tenant_id` derivation scheme (for future stores)

```
tenant_id = "t_" + base64url(
    sha256(shop_domain)[:8]      # 8 bytes: shop fingerprint
  + uint64_be(unix_timestamp)     # 8 bytes: creation time
  + random_bytes(8)               # 8 bytes: entropy
)
```

Opaque, stable, collision-free, 34 chars. The mapping `tenant_id → shop_domain` lives in the `tenants` table (to be created in Phase C).

### Scope: one-shot vs multi-tenant

| Task family | Scope |
|---|---|
| **One-shot (MJ only, throwaway):** A.2 backfill, A.3 description generator, A.4 variant scaffolder, A.6 productCreate payload builder, B.5–B.8 import + GID capture | Lives in `scripts/seed_thesigmavibe_catalog/`. Discarded after catalog lands in Shopify. |
| **Multi-tenant (engine + app, permanent):** A.1 column migrations, all of Phase C, all of Phase D | Lives in `platform_core/` and `vibe-app/`. Serves every tenant. |
| **Future tenant onboarding (Phase F, not in current list):** Vibe reads merchant's Shopify catalog via Admin API → enrich → embed | Not blocking MJ's validation. |

---

## Phase A — Catalog readiness

- [x] **A.3.** Templatized description generator — pure function over enriched attributes (no LLM). [`scripts/seed_thesigmavibe_catalog/`](../scripts/seed_thesigmavibe_catalog/)
- [x] **A.4.** Size-variant scaffolding (XS, S, M, L, XL per product) — baked into the CSV builder.
- [x] **A.5.** ~~Image migration to Cloudflare R2~~ — **skipped.** Direct retailer URLs work; Shopify CDN ingests on import.
- [x] **A.6.** Shopify import payload generator — `build_shopify_csv.py` + `split_by_vendor.py`. 9 per-vendor CSVs, 13,177 products, 79,059 rows.
- [x] **A.1.** Migration applied 2026-05-15 via `supabase/migrations/20260515120000_catalog_enriched_shopify_mapping.sql`. `catalog_enriched` now has `tenant_id` (indexed), `shopify_product_id` (indexed where not null), `shopify_variant_ids` (jsonb), `image_hash`.
- [x] **A.2.** Backfilled `tenant_id = 't_Oq0BSHnewiEAAAAAagWWlmnV-0sJmcGk'` on all **13,177 rows** with non-null price (matches the imported count exactly).

## Phase B — Shopify store setup

- [x] **B.1.** Shopify store created and live at `thesigmavibe.shop`.
- [x] **B.2.** Razorpay + India shipping + GST + theme configured.
- [x] **B.3.** Size-chart section in theme.
- [x] **B.5.** ~~Dry-run 50 products~~ — skipped; went straight to full import.
- [x] **B.7.** Full import of 13,177 products (9 per-vendor CSVs).
- [ ] **B.4.** Mandatory pages: About · Contact · Shipping Policy · Returns/Refund · Privacy · Terms. **Drafts ready** at [docs/storefront/legal_pages/](../docs/storefront/legal_pages/) with LEGAL REVIEW REQUIRED banners. Templates use `{{ PLACEHOLDER }}` tokens (entity name, GSTIN, support contacts, DPO, grievance officer, retention windows, arbitration seat) — counsel signs off, find-and-replace tokens, paste into Shopify admin (Online Store → Pages for About + Contact; Settings → Policies for the four policy pages). India-specific drafted against DPDPA 2023, Consumer Protection Act 2019 + E-Commerce Rules 2020, IT Act + IT Rules 2011/2021. Page-by-page caveats called out in [docs/storefront/legal_pages/README.md](../docs/storefront/legal_pages/README.md).
- [ ] **B.6.** Real-card test order end-to-end. Should happen before storefront sees real customers.
- [ ] **B.8.** Capture Shopify product/variant GIDs back into `catalog_enriched`. **Script ready** at [`scripts/seed_thesigmavibe_catalog/capture_shopify_gids.py`](../scripts/seed_thesigmavibe_catalog/capture_shopify_gids.py). User runs once with an Admin API token from the production store (Settings → Apps → Develop apps → custom app, scope `read_products` → install → token). Walks all Shopify products via GraphQL, matches by `vibe.source_product_id` metafield, writes `shopify_product_id` + `shopify_variant_ids` (jsonb keyed by size) back to Supabase. Idempotent — safe to re-run.

## Phase D — Vibe Shopify App

Vibe has **two completely separate surfaces** that get built differently:

| | Merchant Admin UI | Customer Storefront UI |
|---|---|---|
| Who | The merchant (you / future installers) | The shopper |
| URL | `admin.shopify.com/store/.../apps/vibe` | `thesigmavibe.shop/apps/vibe/*` |
| Purpose | Trust, control, attribution, settings | The actual AI experience |
| Mechanism | Embedded admin app (working — stock template) | **App Proxy live** (D.S.1 ✓, placeholder rendering; real pages in D.C.*) |
| UI library | Polaris | Custom (storefront brand) |

### Done

- [x] **D.1.** Remix + Polaris + App Bridge scaffold — [`vibe-app/`](../vibe-app/) at worktree root.
- [x] **D.2.** Merchant-side OAuth install flow — installed on dev store `vibe-test-nmt8wy3q.myshopify.com`.

### D.S — Shared infrastructure (foundation; blocks customer surface)

- [x] **D.S.1.** **App Proxy configuration** wired end-to-end. `thesigmavibe.shop/apps/vibe/*` (and dev store `vibe-test-nmt8wy3q.myshopify.com/apps/vibe/*`) → Vercel-deployed Remix at `vibe-app-five.vercel.app/apps/vibe/*` (server + client URLs aligned to avoid hydration 404s).
- [x] **D.S.2.** HMAC signature validation via `authenticate.public.appProxy(request)` on every customer route. Unsigned requests rejected.
- [x] **D.S.3a.** **Anonymous customer session** (2026-05-16). UUID v4 minted/read from `localStorage["vibe_session_id"]` on the customer's browser via [`vibe-app/app/lib/session.client.ts`](../vibe-app/app/lib/session.client.ts) and sent explicitly with every backend request. Cookies don't work through App Proxy — the proxy doesn't reliably round-trip `Set-Cookie` / `Cookie` between the storefront origin and the backend, so every cookie-based identity attempt looked like a fresh customer to the engine. localStorage is the canonical workaround.
- [x] **D.S.3b.** **Shopify Customer Account merge** (2026-05-16). Loader extracts `logged_in_customer_id` from the signed App Proxy URL; on first detection (vs `vibe_merged_shopify_customer_id` in localStorage), the client dispatches `op=merge` which calls the new engine endpoint `POST /v1/users/merge`. The repo's `merge_external_user_identity` reassigns conversations + history rows from the anonymous UUID to `shopify:{id}`, and `ensureOnboardingProfile` is called for canonical. Subsequent engine calls use the canonical id; sign-in pill in the header flips to "Signed in". Limitation: no logout detection yet (deferred).
- [x] **D.S.4.** Remaining GDPR webhooks wired. Three handlers under [vibe-app/app/routes/](../vibe-app/app/routes/): [webhooks.customers.data_request.tsx](../vibe-app/app/routes/webhooks.customers.data_request.tsx), [webhooks.customers.redact.tsx](../vibe-app/app/routes/webhooks.customers.redact.tsx), [webhooks.shop.redact.tsx](../vibe-app/app/routes/webhooks.shop.redact.tsx). Each validates HMAC via `authenticate.webhook`, emits a structured `vibe_gdpr_*` log event (`external_user_id`, `shop_id`, `shop_domain`, plus per-topic context), and returns 200 within Shopify's 5s budget. `shop/redact` additionally `delete_many`s the Prisma `Session` rows for the shop (idempotent — `app/uninstalled` already wipes them at uninstall time). Registered in [shopify.app.vibe.toml](../vibe-app/shopify.app.vibe.toml) under `[webhooks.privacy_compliance]`. **Engine-side data work intentionally deferred** — see D.S.5 below.
- [x] **D.S.5.** ~~GDPR data pipeline~~ — **dropped** (decision 2026-05-17). India-only operation; customer count is ~0 today; D.S.4 webhook handlers already acknowledge every request within the 5s budget and log structured `vibe_gdpr_*` events to Vercel Log Drain. The 30-day DPDPA/GDPR SLA is processed manually from those log entries until volume justifies the engine pipeline. Revisit if customer count crosses a few hundred or a data-rights request actually fires.

### D.C — Customer storefront UI (the actual product)

- [x] **D.C.1.** Theme App Extension — "Style with Vibe" entry-point widget. Block lives at [extensions/vibe-storefront/blocks/style-with-vibe.liquid](../vibe-app/extensions/vibe-storefront/blocks/style-with-vibe.liquid). Merchant drops the block into any section (header / homepage / PDP / nav); customer clicks it and lands on `/apps/vibe/style` via the App Proxy. Theme editor exposes label, optional subtitle, size, and alignment settings. Shipped as part of the bundled `vibe-storefront` theme app extension (see toml at [shopify.extension.toml](../vibe-app/extensions/vibe-storefront/shopify.extension.toml)).
- [x] **D.C.2.** **Conversation page** — live at `/apps/vibe/style`. Chat input, message feed, stage indicator, outfit cards, real engine integration via async poll. End-to-end verified against deployed Fly.io engine 2026-05-16.
- [x] **D.C.3.** Wardrobe page (CRUD + filters). Lives at [apps.vibe.wardrobe.tsx](../vibe-app/app/routes/apps.vibe.wardrobe.tsx). Tile grid (`vibe-tile-grid`), category filter chips driven by the items themselves, add-piece modal with file picker + live preview, optimistic delete with hover-revealed icon. Reads/writes via the existing [apps.vibe.api.wardrobe.tsx](../vibe-app/app/routes/apps.vibe.api.wardrobe.tsx) (extended with `POST` multipart add + `DELETE` action). Engine helpers `saveWardrobeItem` + `deleteWardrobeItem` added to [engine.server.ts](../vibe-app/app/lib/engine.server.ts). Brand surface comes from a shared [vibe-page-shell.tsx](../vibe-app/app/components/vibe-page-shell.tsx) + [wardrobe/styles.css](../vibe-app/app/components/wardrobe/styles.css).
- [x] **D.C.4.** Looks page (saved + past recommendations). Two tabs — Saved (hearted outfits, deletable) and Recent (last N styled turns, read-only). Both render the same tile grid, tile-click deep-links into `/apps/vibe/style?conversation=<id>&turn=<id>` (scroll restoration TBD). Lives at [apps.vibe.looks.tsx](../vibe-app/app/routes/apps.vibe.looks.tsx), resource route [apps.vibe.api.looks.tsx](../vibe-app/app/routes/apps.vibe.api.looks.tsx) does a parallel `Promise.allSettled` against engine `/saved-looks` + `/results` so a failure in one tab doesn't blank the other.
- [x] **D.C.5.** Outfit Check page. Single-shot upload → engine feedback flow at [apps.vibe.check.tsx](../vibe-app/app/routes/apps.vibe.check.tsx). State machine (idle → selected → running → result), drop-zone + file picker, 4MB pre-flight check, live stage indicator polling [apps.vibe.api.poll.tsx](../vibe-app/app/routes/apps.vibe.api.poll.tsx), verdict panel + alternatives rail using the existing `OutfitCard`. Server-side prompt locked in [apps.vibe.api.check.tsx](../vibe-app/app/routes/apps.vibe.api.check.tsx) so the client can't drift; appends the same pairing trigger the conversation page uses so the engine produces stylist commentary + alternative outfits in one round-trip. Styles in [components/check/styles.css](../vibe-app/app/components/check/styles.css).
- [x] **D.C.6.** Try-on gallery surfaced on the Looks page as a third tab. New [TryonsTab](../vibe-app/app/routes/apps.vibe.looks.tsx) reads from engine `/v1/users/{ext_id}/tryon-gallery` via the existing [apps.vibe.api.looks.tsx](../vibe-app/app/routes/apps.vibe.api.looks.tsx) loader (fan-out extended from 2 → 3 `Promise.allSettled` branches; one branch failing doesn't blank the others). Renders the engine's accumulating try-on renders in the same tile grid as Saved + Recent. Read-only — renders aren't individually deletable today (they expire when the underlying conversation row archives). The other D.C.6 interpretations (on-demand re-render, per-garment try-on, upload-new-body-photo flow) are out of scope here; spin up if/when needed.
- [x] **D.C.7.** "Add to Cart" via Shopify Storefront API wired (2026-05-15). Size chips toggle a selected size; Buy Outfit / Buy Now POST to `/cart/add.js` then navigate to `/cart`. [`vibe-app/app/lib/cart.client.ts`](../vibe-app/app/lib/cart.client.ts) handles gid→numeric conversion + multi-item add. Mock variant ids detected and surfaced as a friendly inline error instead of hitting `/cart/add.js` with bogus ids. **Engine wiring shipped (#374)** — `OutfitItem` now carries `shopify_product_id` + `shopify_variant_ids` end-to-end from `catalog_enriched` → engine response → Vibe `normalizeItem`. Activates the moment **B.8** runs on a store that has the matching catalog imported.
- [x] **D.C.8.** **Wishlist bridge from Vibe → store.** Block at [extensions/vibe-storefront/blocks/saved-with-vibe.liquid](../vibe-app/extensions/vibe-storefront/blocks/saved-with-vibe.liquid) is constrained to `templates/customers/account` + `customers/order` so a merchant can drop it onto the classic customer-account page. Renders a server-side loading card, then [assets/saved-with-vibe.js](../vibe-app/extensions/vibe-storefront/assets/saved-with-vibe.js) fetches `/apps/vibe/api/wishlist?sessionId=shopify:{customer.id}` — Shopify's App Proxy auto-appends `logged_in_customer_id` + HMAC-signs before forwarding, so the existing IDOR guard in [apps.vibe.api.wishlist.tsx:30](../vibe-app/app/routes/apps.vibe.api.wishlist.tsx:30) covers identity. Three render states (loading / empty / error) all use the same calm card so the layout doesn't reflow as data lands.
  - **Source of truth:** engine `wishlist_items` table. No new schema, no Shopify metafield writes — Vibe owns the model end-to-end.
  - **Limitation:** classic accounts only. Stores migrated to Shopify's new Customer Accounts (`shopify.com/<store>/account`, JSX-based UI Extensions) won't see this block — those need a Customer Account UI Extension, a separate package. Revisit if any tenant is fully on new accounts.
  - **Bundled with D.C.1.** Both blocks live in the single `vibe-storefront` theme app extension so one `shopify app deploy` ships them together and Shopify's review process treats them as one change.
- [ ] **D.C.9.** **Add-to-Cart prod verification.** Once **B.8** runs against the production store (gated on **D.P.1**), spot-check that Buy Outfit / Buy Now path: real variant ids on `OutfitItem`, `/cart/add.js` succeeds, customer lands on `/cart` with all garments + correct sizes. Today every add hits the mock-id guard because vibe-test has only ~60 demo products. No code change — just a checklist item so the wiring doesn't sit silently broken after the catalog lands.
- [x] **D.C.10.** Replaced `window.confirm` / `alert` on Wardrobe + Looks with branded reusable components. New [`<ConfirmDialog>`](../vibe-app/app/components/ui/confirm-dialog.tsx) matches the Add-a-piece modal's visual register (warm cream surface, Fraunces title, destructive-red variant for delete confirms). New [`<Toast>` + `ToastsProvider` + `useToasts()`](../vibe-app/app/components/ui/toast.tsx) for non-blocking success / error / info notifications; fixed bottom-right of viewport, auto-dismiss at 4s, dismissable. Wired into [apps.vibe.wardrobe.tsx](../vibe-app/app/routes/apps.vibe.wardrobe.tsx) + [apps.vibe.looks.tsx](../vibe-app/app/routes/apps.vibe.looks.tsx) for delete confirms + outcome toasts.

#### D.C.2 sub-plan — Conversation page

**Goal.** Customer visits `thesigmavibe.shop/apps/vibe/style`, types a styling question ("what should I wear to a wedding?"), and sees outfit recommendations from the engine. Replaces the Hello-from-Vibe placeholder.

**Engine API contract** (confirmed against `modules/agentic_application/src/agentic_application/api.py`):

| Step | Endpoint | Purpose |
|---|---|---|
| 1 | `POST /v1/conversations/resolve` `{user_id}` | Find or create active conversation for this customer |
| 2 | `POST /v1/conversations/{id}/turns/start` `{message, image?}` | Kick off a turn (async; returns `job_id`) |
| 3 | `GET /v1/conversations/{id}/turns/{job_id}/status` | Poll for stage progression + final result |

Engine turn end-to-end takes 30–60s with try-on; up to 90s on cold path. Stage events (`planner_complete`, `architect_complete`, `composer_complete`, `rater_complete`, `tryon_complete`) stream via the poll endpoint.

**Critical dependency.** The Vibe app on Vercel cannot reach the engine on `localhost:8010`. Two paths:
- (a) **Mock-first dev**: build the entire UI against a typed mock engine response. Real engine integration after Fly.io deploy.
- (b) **Block on Fly.io**: deploy engine first, then build UI against the real URL.

**Recommended: path (a)** — start UI immediately, engine deploy proceeds in parallel as priority #2.

**UI reuse strategy (locked).** Reference-based reuse of `platform_core/ui.py`, not literal port. The legacy code is Python f-strings + vanilla JS — fundamentally incompatible with React/Remix runtime. But the *proven UX patterns* (chat layout, outfit card 3-column structure with detail panel, line-clamp + min-height for vertical stability, stylist-voice stage copy, follow-up bucket headers, welcome state with primary CTA + "More ways to style" toggle) carry over. Workflow: open `platform_core/ui.py` as a spec; write fresh React components matching the markup, copy, and behavior. Reuse design tokens 1:1 (Confident Luxe palette + Fraunces/Inter). Drop everything tied to the legacy runtime (view-class CSS switching, localStorage filter persistence, onboarding flow, profile editing — Shopify owns identity now).

##### Sub-tasks

- [x] **D.C.2a.** Routes restructured. `apps.vibe.*.tsx` family matches the customer-facing path (server + client URLs aligned). Stubs for wardrobe / looks / check pages render placeholder cards.
- [x] **D.C.2b.** Session model — moved to D.S.3a (cookies were a non-starter through App Proxy; localStorage on the client is what shipped).
- [x] **D.C.2c.** Engine API client in [`vibe-app/app/lib/engine.server.ts`](../vibe-app/app/lib/engine.server.ts). Typed wrappers for `resolve` / `turns/start` / `turns/{id}/status`, mock-mode fallback when `ENGINE_API_URL` is unset, response normalization (engine's `completed`/`assistant_message`/`OutfitCard` → Vibe's `succeeded`/`message`/`Outfit`), `channel: "vibe_storefront"` flag on `startTurn`. `vercel.json` pins functions to `bom1`.
- [x] **D.C.2d.** Conversation UI shell — components/conversation/ has `welcome-state` / `message` / `composer` / `stage-indicator` / `outfit-card` / `styles.css` (Confident Luxe tokens). Idempotence refs around submit + poll effects so a turn produces exactly one user/assistant pair.
- [x] **D.C.2e.** Outfit card — try-on hero, garment thumbnail rail with detail panel, Like/Hide, Size chips, Buy CTAs. Empty/zero-outfit responses render the engine's message (used by the in-chat onboarding clarification path).
- [x] **D.C.2f.** Confident Luxe brand styling — palette + Fraunces/Inter loaded via Google Fonts, responsive down to 360px.
- [x] **D.C.2g.** Real engine integration — `ENGINE_API_URL=https://vibe-engine.fly.dev` set on Vercel, end-to-end verified on dev store.

**Total estimate.** ~7–10 hours of focused work. Realistically 2-3 days at the pace we've been moving.

**Out of scope for D.C.2** (deferred to later sub-tasks): image upload, true streaming (we poll, not SSE), conversation history sidebar (multi-thread UX), iteration carousels, follow-up suggestion chips, feedback capture beyond Like/Hide.

### D.O — In-chat onboarding (new — replaces the legacy `user/ui.py` web flow for Vibe customers)

**Goal.** A first-time Vibe customer can chat from message one. Every onboarding input is skippable; profile fields only influence recommendation quality, never block. Replaces the engine's hard gate (which previously returned "Complete mandatory onboarding before chat") with a graceful, optional in-conversation flow.

**Decisions locked (2026-05-16):**
- Profession is dropped entirely from onboarding.
- Risk tolerance defaults to `"balanced"` at user-create time; engine learns per user from interactions.
- Mobile is dropped from onboarding (Meta won't supply it; Shopify checkout collects it for order delivery anyway).
- Identity stays on localStorage session id (D.S.3a) until Shopify Customer Account (D.S.3b) lands.

**Engine model already supports this** (see [`onboarding_gate.py`](../modules/agentic_application/src/agentic_application/onboarding_gate.py) + audit notes): hard-gated fields are now bypassed under `channel="vibe_storefront"`; confidence-improving factors (risk_tolerance, full-body image, headshot image, analysis_completed, seasonal_color_group) only affect [`profile_confidence`](../modules/agentic_application/src/agentic_application/profile_confidence.py).

**Sub-tasks**

- [x] **D.O.1.** Engine gate loosened for the `vibe_storefront` channel ([#367](https://github.com/jaychitransh007/TheSigmaAura/pull/367), 2026-05-16). `CreateTurnRequest.channel` pattern widened to `^(web|vibe_storefront)$`; orchestrator bypasses `evaluate_onboarding_gate` + `validate_minimum_profile`; `build_user_context` grows `allow_incomplete_analysis`. Legacy `web` channel keeps the strict gate (regression-tested).
- [x] **D.O.2.** Backend proxy routes shipped (#370). Three App Proxy endpoints under `apps.vibe.api.onboarding.*.tsx`: image upload (multipart → engine `/v1/onboarding/images/{cat}`), single-field profile patch, analysis-phase trigger. Plus `POST /v1/onboarding/profile/ensure` engine endpoint (#372) that creates the row on demand so Vibe customers (OTP-less) don't 404 on the first save. Helper: `parseActionJson` in [`vibe-app/app/lib/fetch.client.ts`](../vibe-app/app/lib/fetch.client.ts) for tolerant body parsing.
- [x] **D.O.3.** In-chat onboarding UI shipped over several iterations (#370 → #436). Final shape:
  - **Branched welcome.** Init action fetches engine onboarding status for the customer's session (`getOnboardingStatus` returns `OnboardingStatus | null | undefined` — 404 means confirmed new customer, errors apply a "assume profile exists" safety net so engine wobble doesn't re-onboard returners). Returning customers see *"welcome back"* + composer; new / anonymous see *"styling co-pilot"* + the initial cards stacked. Anonymous returning customers are no longer re-onboarded on reload (#426).
  - **Parallel initial cards.** Photos (2-up, save + skip) and gender+DOB (chip selector + DD/MM/YYYY segmented input, save only — no skip) emit side-by-side. Customer resolves them in any order. After both resolve, a single combined **height + waist** card emits with ft/in segmented inputs (#425). The `name` step was dropped entirely 2026-05-17 (#424).
  - **HEIC handling.** Client-side `heic-to` transcode to JPEG so iPhone HEIC previews render; falls back to "Saved — preview unavailable" tile if the library can't decode the variant. Engine still receives the file either way.
  - **Photo framing.** Per-tile zoom (1×–3×) + drag-to-pan in the preview frame, with pointer-capture, sub-pixel jitter guard, and ref-based synchronous in-flight gate.
  - **Photos-card re-injection.** If the engine reports no `full_body` photo on session init (volume rebuild / manual delete), the photos card re-emits regardless of the customer's localStorage onboarding step so try-on can recover automatically (#422).
  - **Post-onboarding closure.** Once all onboarding cards resolve AND analysis completes (polled via `/apps/vibe/api/onboarding/analysis-status`), the assistant emits a templated *"what would you like to wear?"* prompt with concrete examples (#425). Idempotency check scans the whole history so a reload doesn't re-emit.
  - **Pairing trigger.** Whenever any attachment is present on a turn (image upload / wardrobe pick / wishlist pick), the Vibe action appends "Build an outfit around this attached piece" to the engine message so the planner routes through `pairing_request` (#403). The user's bubble shows their original prose.
  - **State persistence.** `localStorage` tracks current step (`vibe_onboarding_step`) and resolved kinds (`vibe_onboarding_resolved_kinds`) so a mid-flow reload doesn't re-emit completed cards.
  - **Functional state updates.** `setMessages` uses pure functional updaters; side effects (localStorage writes, ref sync) live in a dedicated useEffect that observes messages. Single reverse pass for step derivation.
- [ ] **D.O.4.** **Meta OAuth integration** — **deferred indefinitely** in favour of Shopify Customer Account (D.S.3b, shipped). Customer Account is the same identity used at checkout / order history, so the merge surface is one round-trip; Meta would give name/DOB/gender prefill at the cost of 1-2 weeks of app review with no checkout-side value. Keep this row for posterity; revisit only if guest-checkout adoption is low and we want a faster sign-in path than Customer Account.

### D.M — Merchant admin UI (trust + control)

**Re-scoped 2026-05-17.** D.M.2–D.M.6 depend on two new platform phases (F + G below). Each admin page is a thin surface on top of catalog sync (Phase F) + revenue attribution (Phase G). See those phases for the plumbing; this section is the UI.

Can ship after D.C lands AND F.2 + G.1/G.2 are live — the admin pages are mostly empty shells without the underlying data.

- [x] **D.M.1.** Welcome/status screen — replaces the demo "Generate a product" template. Lives at [app/routes/app._index.tsx](../vibe-app/app/routes/app._index.tsx). Shows "Vibe is active" status, links to the customer-facing Conversation / Wardrobe / Looks paths on the merchant's storefront, and pulls the shop domain from the authenticated admin session.
- [ ] **D.M.2.** **Permissions panel.** Lists every granted scope in plain English ("Read your products → so Vibe can recommend from your catalog"). Per-scope revoke button → triggers an OAuth dance to a reduced scope set with a warning about which features stop working. Last-active timestamp per scope so unused permissions are visible. Becomes load-bearing the moment the scope set grows under **F.1** (six new scopes). Depends on F.1.
- [ ] **D.M.3.** **Placement + catalog controls.** Two merged surfaces:
  - **Storefront placement** — toggle the `vibe-storefront` theme app extension blocks on PDP / homepage / nav / customer-account page. Show whether each block is currently in the active theme (needs `read_themes` scope from F.1).
  - **Catalog scope** — multi-select against the merchant's Shopify collections: which to include / exclude from Vibe's recommendations. Default include-all. Recommendation guardrails (min / max price, brand exclusions).

  Depends on F.1 (`read_themes`) + F.2 (catalog ingestion so the merchant's collections are queryable).
- [ ] **D.M.4.** **Analytics dashboard.** Four sections:
  - **Engagement** — conversations / day, unique customers, avg messages per conversation, drop-off funnel through onboarding stages
  - **Revenue attribution** — Vibe-attributed orders count + GMV, AOV uplift vs non-Vibe orders, % of total store revenue. Attribution window toggle (24h / 7d / 30d).
  - **Recommendation effectiveness** — which outfits got most Add-to-Carts, which got most Hides, conversion rate per surface (PDP entry vs homepage entry from D.M.3).
  - **Catalog health** — products covered by Vibe (have embeddings), products OOS vs total recommended count.

  Reuse Panel 18 / 25-27 SQL from the engine's existing dashboards where it overlaps. Depends on F.2 + G (all sub-tasks).
- [ ] **D.M.5.** **Settings.**
  - Catalog refresh cadence (webhook-driven default; scheduled bulk for advanced)
  - Attribution window (24h / 7d / 30d, default 24h — matches D.M.4)
  - Brand voice — stylist tone knobs (currently locked to "Confident Luxe")
  - Feature toggles — try-on, outfit-check, in-chat onboarding cards
  - Notification preferences — new order alerts, weekly analytics digest

  Depends on F.2 + G.2 + the brand-voice abstraction (separate small refactor in the stylist prompts).
- [ ] **D.M.6.** **Billing.** Shopify Billing API integration. Plans (working draft, **product decision still open**):
  - Free trial (30 days, all features)
  - Starter — flat fee for stores under N orders/month
  - Growth — flat + usage component
  - Performance — % of Vibe-attributed revenue

  The performance plan only works after G.3 (line-item attribution) is solid — the % is computed over attributed line-item GMV. Depends on G.2 + G.3.

### D.P — Production rollout

- [ ] **D.P.1.** Install Vibe on prod store (`thesigmavibe.shop`) as Custom App.
- [ ] **D.P.2.** End-to-end real-card test: customer arrives → talks to Vibe → adds outfit → checkout → real order → manual fulfillment.
- [ ] **D.P.3.** Public App Store listing assets: privacy policy, support page, screenshots, demo video.

## Phase C — Engine multi-tenancy (deferred until Vibe validates)

Per agreed sequencing — Phase C is a 1–2 week refactor with no user-visible value until tenant #2 onboards. Validating Vibe's UX on `thesigmavibe.shop` matters more right now.

- [ ] **C.1.** Audit every DB query in `platform_core` + `agentic_application` for tenant-scoping requirements.
- [ ] **C.2.** Migration: add `tenant_id` to all tenant-scoped tables (`conversations`, `user_profiles`, `wardrobe_items`, `model_call_logs`, `turn_traces`, etc.) + backfill.
- [ ] **C.3.** Refactor every query to filter by `tenant_id`. Mechanical but high-stakes — every miss is a cross-tenant data leak.
- [ ] **C.4.** Add `tenant_id` to every cache key (planner / retrieval / architect / composer caches).
- [ ] **C.5.** Tenant-resolution middleware: Shopify shop domain → `tenant_id`.
- [ ] **C.6.** `/v1/bootstrap` endpoint: given shop domain, returns `catalog_ready` status.
- [ ] **C.7.** Strip `platform_core/ui.py` — server-rendered HTML migrates into the Vibe Shopify app.
- [ ] **C.8.** Shopify session-token validation on API endpoints.
- [x] **C.9.** Deploy engine to Fly.io Mumbai (2026-05-15). `Dockerfile` + `fly.toml` at repo root; app `vibe-engine` running in `bom`. Secrets injected via `fly secrets set`. Health check at `/healthz`.

## Phase E — Manual fulfillment SOP

- [x] **E.1.** Runbook at [docs/runbooks/E1_manual_fulfillment_sop.md](../docs/runbooks/E1_manual_fulfillment_sop.md). Walks an operator through the eight-step flow: receive Shopify order email → read `vibe.source_product_url` metafield per line item → place order at the source retailer → wait for tracking → fulfill the Shopify order with tracking link → file invoices for GST. Includes customer-comms email templates (out-of-stock, address-check, significant-delay) and explicit "when to graduate this runbook" triggers (>10 orders/day, >2 source retailers per typical order, returns >15%).
- [ ] **E.2.** *(Optional, defer until pain felt)* Internal dashboard listing open orders + their source URLs.

## Phase F — Catalog sync (per-merchant)

**Goal.** Vibe recommends from the *merchant's actual Shopify catalog*, not from a single hard-coded `catalog_enriched` table. Required for any tenant past TheSigmaVibe and for the D.M.* admin pages to surface real data.

**Locked decisions (2026-05-17):**
- **Multi-tenancy posture:** *punt Phase C, build Phase F with `tenant_id` columns ready.* Catalog ingestion writes `tenant_id` from the merchant's `shopify_shop_gid`; engine retrieval / RPCs still treat the catalog as one pool for now. Phase C populates tenant scoping into the read path later. Risk: a second tenant's products would mix with TheSigmaVibe's until Phase C lands — acceptable for one-tenant-only.
- **Scope expansion path:** existing merchants reinstall once. New scopes documented in F.1.

**Sub-tasks**

- [ ] **F.1.** **New scope grant + reinstall flow.** Expand `shopify.app.vibe.toml` scope set:
  - `read_products` — sync the merchant's catalog
  - `read_inventory` — filter recommendations by stock
  - `read_orders` — subscribe to `orders/create` + `orders/paid` for G
  - `read_customers` — link orders to engine `external_user_id`
  - `read_themes` — verify Theme App Extension placement (D.M.3)
  - `write_metafields` — tag Vibe-attributed orders with attribution context

  Drop unused `write_products` to keep the consent screen tight. OAuth re-grant required on existing installs — surface clean copy on the install screen about *what* and *why* for each scope.
- [ ] **F.2.** **Initial sync job.** On install (or scope re-grant), Vibe walks the merchant's catalog via Admin GraphQL (paginated). For each product, writes to `catalog_enriched` with the merchant's `tenant_id`, runs the existing visual enrichment + embedding generation pipeline (~$0.003/row). Status surfaces on the merchant admin home screen ("Catalog syncing: 230 of 1,840 products…"). Idempotent — safe to re-run; skips already-enriched rows by `shopify_product_id` + content hash.
- [ ] **F.3.** **Webhook-driven incremental sync.** Subscribe to `products/create`, `products/update`, `products/delete`, `inventory_levels/update`. Each fires a targeted re-enrichment or delete on the affected product. Avoids the slow path of periodic full re-syncs.
- [ ] **F.4.** **Stock-aware retrieval.** Engine's `match_catalog_item_embeddings` RPC + post-retrieval filter respect `available_for_sale` so the stylist doesn't recommend OOS items. Inventory updates flow in via F.3.

## Phase G — Purchase attribution

**Goal.** Know which orders were driven by a Vibe recommendation and credit revenue accordingly. Powers D.M.4 analytics and D.M.6 performance-billing.

**Locked decisions (2026-05-17):**
- **Attribution model: last-touch v1.** "Customer chatted with Vibe within the last 24h before checkout → order fully attributed." Multi-touch / assist credit deferred until v1 has data to show whether it matters.
- **Attribution window:** default 24h; merchant can override to 7d or 30d in D.M.5 settings.

**Sub-tasks**

- [ ] **G.1.** **Order webhook handlers.** New routes under `vibe-app/app/routes/webhooks.orders.*.tsx` for `orders/create` and `orders/paid`. Each validates HMAC via `authenticate.webhook`, persists the order to a new `vibe_orders` Prisma table with the customer's `shopify:{customer_id}`, shop domain, line items, total, currency, timestamps. Returns 200 within the 5s ack budget.
- [ ] **G.2.** **Attribution engine.** Engine endpoint `POST /v1/users/{ext_id}/attribute-order`. On each order received via G.1, looks up the customer's most recent Vibe session, computes seconds elapsed since session, applies the merchant's attribution window (D.M.5), and writes an `order_attribution` row: `order_id`, `external_user_id`, `tenant_id`, `attributed: bool`, `attribution_session_id`, `attribution_seconds_before`, `outfit_ids_in_session`.
- [ ] **G.3.** **Line-item attribution.** For each line item on a Vibe-attributed order, check whether its `shopify_product_id` appeared in any outfit recommendation in the attribution session. Record per-line-item `vibe_recommended: bool` + `recommended_in_outfit_id`. Lets D.M.4 split "outfit-driven" from "spillover" revenue.
- [ ] **G.4.** **Refund handler.** `orders/refunded` webhook adjusts attributed revenue downward when a Vibe-attributed order gets refunded. Edits the `order_attribution` row's refunded amount rather than deleting it (audit trail).

## Done outside the original task list

- [x] **Homepage hero** — "Style that gets you." copy locked, hero image generated, 4 value-prop card content drafted.
- [x] **Brand vocabulary map** — 10 retailers → display names hardcoded in `scripts/seed_thesigmavibe_catalog/brands.py`.
- [x] **Catalog price markup** — 20% baked into the CSV build.
- [x] **Vibe dev infrastructure** — Partner org "Vibe" with `mj.nigam28@gmail.com`, dev store `vibe-test-nmt8wy3q.myshopify.com`. **Tunnels eliminated entirely** by deploying directly to Vercel (Cloudflare quick / ngrok free / localtunnel / Pinggy free all confirmed broken in BLR/BOM regions due to anti-abuse interstitials breaking server-to-server app proxy requests).

## Reuse (don't build)

- **Wishlist:** skip third-party wishlist apps. Vibe owns the saved-items model end-to-end (engine `wishlist_items` table + Conversation picker), and **D.C.8** bridges it to the storefront customer-account page via a Theme App Extension block. **D.C.4** Looks page remains the richer in-Vibe surface (saved outfits, not just products).
- **Auto-collections + nav menu** (Women / Men / Festive / Wedding / Workwear): rules already drafted; user to wire when ready. No code work.

## Next priorities (in execution order)

**Launch-blocking chain (your action):**

1. **B.4 legal-page review + publish.** Drafts are ready in [docs/storefront/legal_pages/](../docs/storefront/legal_pages/); counsel reviews, you find-and-replace the `{{ PLACEHOLDER }}` tokens, paste into Shopify admin.
2. **B.6 — Real-card test order.** Manual.
3. **D.P.1 — Install Vibe on the production store** (`thesigmavibe.shop`). Unblocks **B.8** + **D.C.9**.
4. **D.C.9 — Add-to-Cart prod verification** after B.8 lands real variant ids.

**Then — Merchant-admin build (F → G → D.M.*), roughly 8-10 weeks:**

5. **F.1 — Scope expansion + reinstall flow** (2-3 days). Foundation for everything below; existing installs reinstall once with the new scope list.
6. **F.2 — Initial catalog sync** (1 week). Per-merchant catalog ingestion + visual enrichment + embeddings; sync status surfaces in D.M.1.
7. **G.1 + G.2 — Order webhooks + attribution engine** (1 week). Unlocks D.M.4 revenue numbers + D.M.6 performance plan billing.
8. **F.3 — Webhook-driven incremental sync** (3 days). Production-readiness for F.2.
9. **F.4 — Stock-aware retrieval** (2-3 days). Quality fix.
10. **G.3 — Line-item attribution** (2-3 days). D.M.4 granularity ("which outfits drove which line items").
11. **D.M.2 — Permissions panel** (3 days).
12. **D.M.3 — Placement + catalog controls** (4 days).
13. **D.M.4 — Analytics dashboard** (2 weeks). The big one.
14. **D.M.5 — Settings** (3-4 days).
15. **D.M.6 — Billing** (1 week). **Pricing plan is a product decision still open** — flat-fee first vs % of attributed revenue.

**Later:** D.P.2 / D.P.3 (real-card e2e + App Store listing), Phase C (engine multi-tenancy — required before tenant #2 onboards), G.4 (refund handler), E.2 (internal fulfillment dashboard, if order volume justifies it), further try-on surfaces (per-garment, on-demand re-render) only if requested.

---

## Trigger-driven (no work needed until trigger fires)

### Observability gaps from the 2026-05-16 audit — "useful" tier

The May-16 audit flagged five observability gaps post in-chat-onboarding + Customer-Account-merge launches. The two blockers (channel-labeled `aura_turn_total` and status-labeled `aura_user_merge_total`) shipped in [#398](https://github.com/jaychitransh007/TheSigmaAura/pull/398). A follow-up audit on 2026-05-17 added a related sweep that shipped in [#436](https://github.com/jaychitransh007/TheSigmaAura/pull/436): `aura_onboarding_endpoint_total{endpoint, status, channel}` + `aura_onboarding_image_bytes{category, channel}` for the seven Vibe onboarding routes, channel-threaded from the Vibe client, plus Vibe-side structured logs (`vibe_init_outcome` / `vibe_merge_outcome` / `vibe_merge_identity_mismatch` / `vibe_turn_pairing_rewrite`).

The three items below remain open — distinct from the per-endpoint outcome counter that #436 shipped (those track request volume and HTTP outcome per route; the items below track funnel stages, payload-level coverage, and merge-time data hygiene).

- **Variant-id coverage histogram.** Tracks what fraction of items in each outfit response carry non-empty `shopify_variant_ids`. **Trigger:** after **D.P.1** + **B.8** run on a real catalog. Until then every response has 0% coverage (vibe-test only has 60 demo products), so the metric would just measure "nothing's wired". **Where:** new `aura_item_variant_id_coverage` histogram (buckets 0/25/50/75/100) in [`modules/platform_core/src/platform_core/metrics.py`](../modules/platform_core/src/platform_core/metrics.py); observe per outfit in the orchestrator response builder.
- **Onboarding-stage reach counter.** `aura_onboarding_stage_reach_total` labeled by `stage` ∈ `{init, photo_uploaded, profile_submitted, complete}`. Lets us spot drop-off through the in-chat flow. **Trigger:** after the first real customer cohort flows through `/apps/vibe/style` on production (D.P.1 + a few live customers). **Where:** new counter in `metrics.py`; increment from the matching App Proxy resource routes (`apps.vibe.api.onboarding.*.tsx`) via a small server-side ping, OR from `process_turn` when the orchestrator first sees a vibe_storefront turn for that user.
- **`acquisition_source` cross-contamination on merge.** When a vibe_storefront customer signs in via Shopify Customer Account, `repo.merge_external_user_identity` doesn't propagate the alias row's `acquisition_source` to the canonical row. Result: a customer who started as `vibe_storefront` and later signs in shows up in [Panel 01](../ops/dashboards/panel_01_acquisition_onboarding_funnel.sql) as `unknown` forever. **Trigger:** when Panel 01 starts seeing unexpectedly high `unknown` after merged customers exist in volume. **Where:** [`modules/platform_core/src/platform_core/repositories.py`](../modules/platform_core/src/platform_core/repositories.py) `merge_external_user_identity` — copy alias `acquisition_source` to canonical when canonical's is `unknown` (don't overwrite a real value).

### Masculine `polo_tshirt` coverage

**Status (verified against staging catalog 2026-05-11 post-re-enrichment):** the gap reported in April 2026 has substantially closed. The catalog now carries:

| Subtype | Masculine | Unisex | Combined |
|---|---:|---:|---:|
| `shirt` | 922 | 9 | 931 |
| `tshirt` | 369 | 17 | 386 |
| `sweatshirt` | 63 | 0 | 63 |
| `hoodie` | 39 | 3 | 42 |
| `polo_tshirt` | **0** | 0 | **0** |

Total masculine inventory: **4,298 items across 21 subtypes** (not the 8 reported pre-re-enrichment). The May re-enrichment fixed subtype recognition; items previously miscategorised as `blazer` / `jacket` got accurate `shirt` / `sweatshirt` tags.

**Remaining gap:** `polo_tshirt` is the only top subtype with literally zero items. Likely a vocabulary signal — polos may be getting tagged as either `tshirt` or `shirt` by the vision pipeline.

**Trigger to act.** Only if `polo_tshirt` becomes a request driver and the existing `tshirt` / `shirt` fallback isn't sufficient.

---

## Frozen-catalog policy (2026-05-11)

The catalog AND its embeddings are **frozen** at the 14,242-row state.

| Operation | Cost | Time | Status |
|---|---|---|---|
| Vision re-enrichment (gpt-5-mini batch on existing rows) | $35-40 | ~30h | ⛔ Forbidden |
| Embedding regeneration (text-embedding-3-small on existing rows) | ~$0.50 | ~35 min | ⛔ Forbidden |

**What's still allowed:**
- Per-product enrichment of NEW catalog items at ingestion time (per-product, not bulk).
- Per-product embedding generation for newly ingested items.
- Schema changes that are pure SQL transforms over existing rows — but note that without embedding regen, such changes only affect SQL-filter behaviour; semantic similarity search keeps encoding the pre-change state, so most aren't worth shipping on SQL-only effect alone.

**Composer engine flag.** `AURA_COMPOSER_ENGINE_ENABLED=true` is a config flip available today — no engineering work needed. Engine acceptance rate is ~4%, so blast radius is small. Recommended posture: flip in staging, watch Panel 18 (rater unsuitable rate) and Panel 25-27 for a week, revert if unsuitable rate climbs >1pp on engine-accepted turns.

---

## Permanently dropped under frozen-catalog policy

Kept here as a guardrail against re-proposing in future sessions.

**Vision-re-enrichment-dependent:**
- ~10 dormant stylist vocab values (`wrap_with_hard_cinching`, `kasavu_border`, `temple_border`, `lightly_padded`, `angled_seam`, `vertical_panel`, `center_gathering`, `textured_yoke`, `epaulettes`, `rigid_tight`, `distributed_heavy`, `hard_cinched` / `soft_defined` / `strategic_defined`, `micro_mini`).
- `FabricTexture` decomposition (split into `FabricTexture` + `SurfaceFinish` + `ConstructionDetail`).
- `SurfaceFinish` axis adoption (`high_shine_metallic` / `antique_metallic` / `brushed_metallic`).
- Wave B ontology surgery (4 deferred ShapeArchitecture axes: `ProjectionType` / `StructuralRhythm` / `EdgeGeometry` / `VolumeIntensity`).
- 4-stage extraction architecture.
- Full Step 4 bodyframe + occasion patches beyond the thin subset already shipped.

**Embedding-regen-dependent (added 2026-05-11 late):**
- Wave A surgical cuts (OccasionSignal / SilhouetteContour / FitEase column drops).
- Color-axes algorithmic switch (Pillow/OpenCV deriving `ContrastLevel` / `ColorTemperature` / `ColorSaturation` / `ColorValue`).
- GarmentSubtype → OutfitStructure carve-out.
- ConstructionDetail cleanup (move `deconstructed` / `utility` / `experimental` to a future `StyleExpression` axis).
- Catalog vocab cleanup Phase 2 (drop `OccasionFit` / `OccasionSignal` / `FormalitySignalStrength` from embedding text).
- Rare-value cleanup (per-row content decisions for ≤5-row subtypes like poncho / leggings / kaftan / tracksuit / dungarees / ethnic_set).

Stylist's prose documentation for the dormant-vocabulary work remains in `knowledge/knowledge_v2/` as a historical reference. If a future policy reversal authorises re-enrichment + embedding regen, those files specify what to add.
