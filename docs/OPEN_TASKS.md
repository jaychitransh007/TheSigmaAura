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
- [ ] **B.4.** Mandatory pages: About · Contact · Shipping Policy · Returns/Refund · Privacy · Terms. **Deferred by user** ("we will get back to this later"). Required before customer-facing launch.
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
- [ ] **D.S.4.** Remaining GDPR webhooks: `customers/data_request`, `customers/redact`, `shop/redact`. (`app/uninstalled` + `app/scopes_update` already wired by the template.)

### D.C — Customer storefront UI (the actual product)

- [x] **D.C.1.** Theme App Extension — "Style with Vibe" entry-point widget. Block lives at [extensions/vibe-storefront/blocks/style-with-vibe.liquid](../vibe-app/extensions/vibe-storefront/blocks/style-with-vibe.liquid). Merchant drops the block into any section (header / homepage / PDP / nav); customer clicks it and lands on `/apps/vibe/style` via the App Proxy. Theme editor exposes label, optional subtitle, size, and alignment settings. Shipped as part of the bundled `vibe-storefront` theme app extension (see toml at [shopify.extension.toml](../vibe-app/extensions/vibe-storefront/shopify.extension.toml)).
- [x] **D.C.2.** **Conversation page** — live at `/apps/vibe/style`. Chat input, message feed, stage indicator, outfit cards, real engine integration via async poll. End-to-end verified against deployed Fly.io engine 2026-05-16.
- [x] **D.C.3.** Wardrobe page (CRUD + filters). Lives at [apps.vibe.wardrobe.tsx](../vibe-app/app/routes/apps.vibe.wardrobe.tsx). Tile grid (`vibe-tile-grid`), category filter chips driven by the items themselves, add-piece modal with file picker + live preview, optimistic delete with hover-revealed icon. Reads/writes via the existing [apps.vibe.api.wardrobe.tsx](../vibe-app/app/routes/apps.vibe.api.wardrobe.tsx) (extended with `POST` multipart add + `DELETE` action). Engine helpers `saveWardrobeItem` + `deleteWardrobeItem` added to [engine.server.ts](../vibe-app/app/lib/engine.server.ts). Brand surface comes from a shared [vibe-page-shell.tsx](../vibe-app/app/components/vibe-page-shell.tsx) + [wardrobe/styles.css](../vibe-app/app/components/wardrobe/styles.css).
- [x] **D.C.4.** Looks page (saved + past recommendations). Two tabs — Saved (hearted outfits, deletable) and Recent (last N styled turns, read-only). Both render the same tile grid, tile-click deep-links into `/apps/vibe/style?conversation=<id>&turn=<id>` (scroll restoration TBD). Lives at [apps.vibe.looks.tsx](../vibe-app/app/routes/apps.vibe.looks.tsx), resource route [apps.vibe.api.looks.tsx](../vibe-app/app/routes/apps.vibe.api.looks.tsx) does a parallel `Promise.allSettled` against engine `/saved-looks` + `/results` so a failure in one tab doesn't blank the other.
- [ ] **D.C.5.** Outfit Check page (upload outfit → feedback).
- [ ] **D.C.6.** Try-on integration (Gemini) surfaced inside Conversation + Looks.
- [x] **D.C.7.** "Add to Cart" via Shopify Storefront API wired (2026-05-15). Size chips toggle a selected size; Buy Outfit / Buy Now POST to `/cart/add.js` then navigate to `/cart`. [`vibe-app/app/lib/cart.client.ts`](../vibe-app/app/lib/cart.client.ts) handles gid→numeric conversion + multi-item add. Mock variant ids detected and surfaced as a friendly inline error instead of hitting `/cart/add.js` with bogus ids. **Engine wiring shipped (#374)** — `OutfitItem` now carries `shopify_product_id` + `shopify_variant_ids` end-to-end from `catalog_enriched` → engine response → Vibe `normalizeItem`. Activates the moment **B.8** runs on a store that has the matching catalog imported.
- [x] **D.C.8.** **Wishlist bridge from Vibe → store.** Block at [extensions/vibe-storefront/blocks/saved-with-vibe.liquid](../vibe-app/extensions/vibe-storefront/blocks/saved-with-vibe.liquid) is constrained to `templates/customers/account` + `customers/order` so a merchant can drop it onto the classic customer-account page. Renders a server-side loading card, then [assets/saved-with-vibe.js](../vibe-app/extensions/vibe-storefront/assets/saved-with-vibe.js) fetches `/apps/vibe/api/wishlist?sessionId=shopify:{customer.id}` — Shopify's App Proxy auto-appends `logged_in_customer_id` + HMAC-signs before forwarding, so the existing IDOR guard in [apps.vibe.api.wishlist.tsx:30](../vibe-app/app/routes/apps.vibe.api.wishlist.tsx:30) covers identity. Three render states (loading / empty / error) all use the same calm card so the layout doesn't reflow as data lands.
  - **Source of truth:** engine `wishlist_items` table. No new schema, no Shopify metafield writes — Vibe owns the model end-to-end.
  - **Limitation:** classic accounts only. Stores migrated to Shopify's new Customer Accounts (`shopify.com/<store>/account`, JSX-based UI Extensions) won't see this block — those need a Customer Account UI Extension, a separate package. Revisit if any tenant is fully on new accounts.
  - **Bundled with D.C.1.** Both blocks live in the single `vibe-storefront` theme app extension so one `shopify app deploy` ships them together and Shopify's review process treats them as one change.
- [ ] **D.C.9.** **Add-to-Cart prod verification.** Once **B.8** runs against the production store (gated on **D.P.1**), spot-check that Buy Outfit / Buy Now path: real variant ids on `OutfitItem`, `/cart/add.js` succeeds, customer lands on `/cart` with all garments + correct sizes. Today every add hits the mock-id guard because vibe-test has only ~60 demo products. No code change — just a checklist item so the wiring doesn't sit silently broken after the catalog lands.

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

Can ship after D.C lands — merchant doesn't need rich admin until Vibe is real.

- [x] **D.M.1.** Welcome/status screen — replaces the demo "Generate a product" template. Lives at [app/routes/app._index.tsx](../vibe-app/app/routes/app._index.tsx). Shows "Vibe is active" status, links to the customer-facing Conversation / Wardrobe / Looks paths on the merchant's storefront, and pulls the shop domain from the authenticated admin session.
- [ ] **D.M.2.** Permissions panel — what Vibe accesses (products / orders / customers / themes / customer-account-data) with revoke/re-grant.
- [ ] **D.M.3.** Storefront placement controls — toggle the Vibe widget on PDP / homepage / nav / etc., customize entry-point copy.
- [ ] **D.M.4.** Analytics dashboard — conversations, conversion rate, revenue attribution, share-to-save earnings.
- [ ] **D.M.5.** Settings — feature toggles, brand-voice config.
- [ ] **D.M.6.** Billing — plan / pricing / usage via Shopify Billing API.

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

- [ ] **E.1.** Document: open Shopify order → read `source_url` metafield → place order at original retailer → mark Shopify order fulfilled with tracking link. Trivial; write when first real order lands.
- [ ] **E.2.** *(Optional, defer until pain felt)* Internal dashboard listing open orders + their source URLs.

## Done outside the original task list

- [x] **Homepage hero** — "Style that gets you." copy locked, hero image generated, 4 value-prop card content drafted.
- [x] **Brand vocabulary map** — 10 retailers → display names hardcoded in `scripts/seed_thesigmavibe_catalog/brands.py`.
- [x] **Catalog price markup** — 20% baked into the CSV build.
- [x] **Vibe dev infrastructure** — Partner org "Vibe" with `mj.nigam28@gmail.com`, dev store `vibe-test-nmt8wy3q.myshopify.com`. **Tunnels eliminated entirely** by deploying directly to Vercel (Cloudflare quick / ngrok free / localtunnel / Pinggy free all confirmed broken in BLR/BOM regions due to anti-abuse interstitials breaking server-to-server app proxy requests).

## Reuse (don't build)

- **Wishlist:** skip third-party wishlist apps. Vibe owns the saved-items model end-to-end (engine `wishlist_items` table + Conversation picker), and **D.C.8** bridges it to the storefront customer-account page via a Theme App Extension block. **D.C.4** Looks page remains the richer in-Vibe surface (saved outfits, not just products).
- **Auto-collections + nav menu** (Women / Men / Festive / Wedding / Workwear): rules already drafted; user to wire when ready. No code work.

## Next priorities (in execution order)

1. **D.C.5 — Outfit Check page.** Upload outfit → engine feedback.
2. **B.6 — Real-card test order.** Sanity check before broader access.
3. **B.4 — Mandatory legal pages** (About / Contact / Shipping / Returns / Privacy / Terms). Required before customer-facing launch.
4. **D.P.1 — Install Vibe on the production store** (`thesigmavibe.shop`). Unblocks running **B.8** ([`scripts/seed_thesigmavibe_catalog/capture_shopify_gids.py`](../scripts/seed_thesigmavibe_catalog/capture_shopify_gids.py), ~3 min) against the real 13K-product catalog, which activates Add-to-Cart end-to-end via the wiring shipped in D.C.7 / #374. The `vibe-storefront` theme app extension (D.C.1 + D.C.8) needs `shopify app deploy` against the prod app, and the merchant needs to add the two blocks to the appropriate theme templates. (Running B.8 against vibe-test today matches zero rows since the dev store carries only ~60 demo products — defer until D.P.1.)
5. **D.C.9 — Add-to-Cart prod verification.** Spot-check Buy Outfit / Buy Now end-to-end after B.8 lands real variant ids. No code; just confirm the wiring works on real inventory.
6. **D.S.4 — Remaining GDPR webhooks** (`customers/data_request`, `customers/redact`, `shop/redact`). Required for public App Store listing.
7. Eventually: D.M.2–D.M.6 (richer merchant admin), D.P.2–D.P.3 (real-card e2e + listing assets), Phase C (engine multi-tenancy), Phase E (manual fulfillment SOP).

---

## Trigger-driven (no work needed until trigger fires)

### Observability gaps from the 2026-05-16 audit — "useful" tier

The May-16 audit flagged five observability gaps post in-chat-onboarding + Customer-Account-merge launches. The two blockers (channel-labeled `aura_turn_total`, `aura_user_merge_total`) shipped in [#398](https://github.com/jaychitransh007/TheSigmaAura/pull/398). A follow-up audit on 2026-05-17 added a related sweep that shipped in [#436](https://github.com/jaychitransh007/TheSigmaAura/pull/436): `aura_onboarding_endpoint_total{endpoint, status, channel}` + `aura_onboarding_image_bytes{category, channel}` for the seven Vibe onboarding routes, channel-threaded from the Vibe client, plus Vibe-side structured logs (`vibe_init_outcome` / `vibe_merge_outcome` / `vibe_merge_identity_mismatch` / `vibe_turn_pairing_rewrite`).

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
