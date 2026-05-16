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

- [x] **A.3.** Templatized description generator — pure function over enriched attributes (no LLM). [`scripts/seed_thesigmavibe_catalog/`](scripts/seed_thesigmavibe_catalog/)
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
- [ ] **B.8.** Capture Shopify product/variant GIDs back into `catalog_enriched`. **Script ready** at [`scripts/seed_thesigmavibe_catalog/capture_shopify_gids.py`](scripts/seed_thesigmavibe_catalog/capture_shopify_gids.py). User runs once with an Admin API token from the production store (Settings → Apps → Develop apps → custom app, scope `read_products` → install → token). Walks all Shopify products via GraphQL, matches by `vibe.source_product_id` metafield, writes `shopify_product_id` + `shopify_variant_ids` (jsonb keyed by size) back to Supabase. Idempotent — safe to re-run.

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

- [x] **D.1.** Remix + Polaris + App Bridge scaffold — [`vibe-app/`](vibe-app/) at worktree root.
- [x] **D.2.** Merchant-side OAuth install flow — installed on dev store `vibe-test-nmt8wy3q.myshopify.com`.

### D.S — Shared infrastructure (foundation; blocks customer surface)

- [x] **D.S.1.** **App Proxy configuration** wired end-to-end. `thesigmavibe.shop/apps/vibe/*` (and dev store `vibe-test-nmt8wy3q.myshopify.com/apps/vibe/*`) → Vercel-deployed Remix at `vibe-app-five.vercel.app/apps/vibe/*` (server + client URLs aligned to avoid hydration 404s).
- [x] **D.S.2.** HMAC signature validation via `authenticate.public.appProxy(request)` on every customer route. Unsigned requests rejected.
- [x] **D.S.3a.** **Anonymous customer session** (2026-05-16). UUID v4 minted/read from `localStorage["vibe_session_id"]` on the customer's browser via [`vibe-app/app/lib/session.client.ts`](vibe-app/app/lib/session.client.ts) and sent explicitly with every backend request. Cookies don't work through App Proxy — the proxy doesn't reliably round-trip `Set-Cookie` / `Cookie` between the storefront origin and the backend, so every cookie-based identity attempt looked like a fresh customer to the engine. localStorage is the canonical workaround.
- [ ] **D.S.3b.** **Shopify Customer Account** integration when logged in. Merge anonymous-localStorage identity into the authenticated profile via the engine's `merge_external_user_identity` repo method. Unblocks D.C.3 (Wardrobe).
- [ ] **D.S.4.** Remaining GDPR webhooks: `customers/data_request`, `customers/redact`, `shop/redact`. (`app/uninstalled` + `app/scopes_update` already wired by the template.)

### D.C — Customer storefront UI (the actual product)

- [ ] **D.C.1.** Theme App Extension — "Style with Vibe" entry-point widget + storefront nav link. The discoverability layer.
- [x] **D.C.2.** **Conversation page** — live at `/apps/vibe/style`. Chat input, message feed, stage indicator, outfit cards, real engine integration via async poll. End-to-end verified against deployed Fly.io engine 2026-05-16.
- [ ] **D.C.3.** Wardrobe page (CRUD + filters). Requires D.S.3 (customer auth).
- [ ] **D.C.4.** Looks page (saved + past recommendations).
- [ ] **D.C.5.** Outfit Check page (upload outfit → feedback).
- [ ] **D.C.6.** Try-on integration (Gemini) surfaced inside Conversation + Looks.
- [x] **D.C.7.** "Add to Cart" via Shopify Storefront API wired (2026-05-15). Size chips toggle a selected size; Buy Outfit / Buy Now POST to `/cart/add.js` then navigate to `/cart`. [`vibe-app/app/lib/cart.client.ts`](vibe-app/app/lib/cart.client.ts) handles gid→numeric conversion + multi-item add. Mock variant ids detected and surfaced as a friendly inline error instead of hitting `/cart/add.js` with bogus ids. Functional once **B.8** runs and the engine returns real `shopify_variant_ids`.

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
- [x] **D.C.2c.** Engine API client in [`vibe-app/app/lib/engine.server.ts`](vibe-app/app/lib/engine.server.ts). Typed wrappers for `resolve` / `turns/start` / `turns/{id}/status`, mock-mode fallback when `ENGINE_API_URL` is unset, response normalization (engine's `completed`/`assistant_message`/`OutfitCard` → Vibe's `succeeded`/`message`/`Outfit`), `channel: "vibe_storefront"` flag on `startTurn`. `vercel.json` pins functions to `bom1`.
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

**Engine model already supports this** (see [`onboarding_gate.py`](modules/agentic_application/src/agentic_application/onboarding_gate.py) + audit notes): hard-gated fields are now bypassed under `channel="vibe_storefront"`; confidence-improving factors (risk_tolerance, full-body image, headshot image, analysis_completed, seasonal_color_group) only affect [`profile_confidence`](modules/agentic_application/src/agentic_application/profile_confidence.py).

**Sub-tasks**

- [x] **D.O.1.** Engine gate loosened for the `vibe_storefront` channel ([#367](https://github.com/jaychitransh007/TheSigmaAura/pull/367), 2026-05-16). `CreateTurnRequest.channel` pattern widened to `^(web|vibe_storefront)$`; orchestrator bypasses `evaluate_onboarding_gate` + `validate_minimum_profile`; `build_user_context` grows `allow_incomplete_analysis`. Legacy `web` channel keeps the strict gate (regression-tested).
- [ ] **D.O.2.** **Backend proxy routes** for in-chat onboarding. Three new App Proxy endpoints under `apps.vibe.api.onboarding.*.tsx`:
  - **Upload image** — multipart POST → engine `POST /v1/onboarding/images/{full_body|headshot}`. Returns analysis-job status so the UI can show a pill while the snapshot runs.
  - **Save partial profile field** — POST `{field, value}` → engine `PATCH /v1/onboarding/profile/partial`. Single field at a time (name / DOB / gender / height_cm / waist_cm).
  - **Mark profile complete** — POST → engine `POST /v1/onboarding/profile` with whatever's been collected so far; sets `profile_complete=true` even on partial data (Vibe channel tolerates it).
  Auth: HMAC via `authenticate.public.appProxy`. Identity: `sessionId` from the form, same pattern as the chat action.
- [ ] **D.O.3.** **In-chat onboarding UI** in [`vibe-app/app/routes/apps.vibe.style.tsx`](vibe-app/app/routes/apps.vibe.style.tsx) + new components in `app/components/onboarding/`:
  - `WelcomeMessage` — first assistant message on a fresh `vibe_session_id` ("Hey, I'm Vibe — let's find what works on you.").
  - `PhotoCard` — single assistant message with two side-by-side cards (Full Body | Headshot). Each card: drag-and-drop or "Choose file", guidelines copy ("plain background, good lighting, fitted clothing, head-to-toe / face-only, one person"), upload progress, **Skip** button.
  - `MetaLoginCard` — single button + Skip. Deferred to D.O.4; for ship-now, replace with three sequential `FieldCard`s (Name → DOB → Gender).
  - `FieldCard` — text / date / select prompt with Skip. Reusable for the Meta-fallback fields and the height / waist cards.
  - Onboarding state machine — current step persisted in `localStorage["vibe_onboarding_step"]` so a page reload resumes mid-flow. Reveals the regular composer once the customer hits Skip or completes the last step.
- [ ] **D.O.4.** **Meta OAuth integration** (deferred; depends on Meta app review). New routes `auth.meta.start.tsx` + `auth.meta.callback.tsx`. Permissions: `public_profile` (name, default), `user_birthday` + `user_gender` (require Meta app review, ~1–2 weeks). On success: pull name/DOB/gender into the engine profile silently and skip the three manual `FieldCard`s. **Mobile is NOT requested from Meta** — Facebook removed phone access years ago. Replaces the Meta-fallback `FieldCard`s in D.O.3 once approved.

### D.M — Merchant admin UI (trust + control)

Can ship after D.C lands — merchant doesn't need rich admin until Vibe is real.

- [ ] **D.M.1.** Welcome/status screen — replaces today's "Generate a product" template. Shows "Vibe is active", catalog sync status, "Open Vibe on your storefront →" link.
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

- **Wishlist:** skip third-party wishlist apps for now. Vibe's Looks page will be the native equivalent. Re-evaluate after D.6 lands.
- **Auto-collections + nav menu** (Women / Men / Festive / Wedding / Workwear): rules already drafted; user to wire when ready. No code work.

## Next priorities (in execution order)

1. **D.O.2 — Backend proxy routes for in-chat onboarding.** Image upload + partial-profile save + mark-complete endpoints. ~1 day. Unblocks D.O.3.
2. **D.O.3 — In-chat onboarding UI.** Welcome + 2-up PhotoCard + 5 FieldCards (Name, DOB, Gender as Meta fallback, Height, Waist) + Skip on each + state-machine localStorage persistence. ~2–3 days.
3. **B.8 — Capture Shopify GIDs.** Script ready at [`scripts/seed_thesigmavibe_catalog/capture_shopify_gids.py`](scripts/seed_thesigmavibe_catalog/capture_shopify_gids.py); user runs once with an Admin API token. ~3 min. Unblocks real Add-to-Cart against the engine's outfit responses (D.C.7 is wired but waiting on real `shopify_variant_ids`).

After these three:
4. **D.O.4 — Meta OAuth** (gated on Meta app review for `user_birthday` + `user_gender`, ~1–2 weeks). Replaces three of the FieldCards with a single sign-in button.
5. **D.S.3b — Shopify Customer Account integration.** Merge anonymous-localStorage identity into the authenticated customer's profile. Unblocks D.C.3 (Wardrobe).
6. **D.M.1 — Merchant welcome/status screen.** Replace the demo Polaris page with a small "Vibe is active" card. ~1 hr.
7. **D.C.3 / D.C.4 / D.C.5** — Wardrobe, Looks, Outfit Check pages.
8. **B.6 — Real-card test order.** Sanity check before broader access.
9. **B.4 — Mandatory legal pages** (About / Contact / Shipping / Returns / Privacy / Terms). Required before customer-facing launch.
10. **D.P.1 — Install Vibe on the production store** (`thesigmavibe.shop`).
11. **D.S.4 — Remaining GDPR webhooks.** Required for public App Store listing.
12. Eventually: D.M.2–D.M.6 (richer merchant admin), D.P.2–D.P.3 (real-card e2e + listing assets), Phase C (engine multi-tenancy), Phase E (fulfillment SOP).

---

## Trigger-driven (no work needed until trigger fires)

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
