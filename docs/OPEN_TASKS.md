# Open Tasks

This file lists what's open **now**. Shipped work history lives in `docs/RELEASE_READINESS.md` § "Recently Shipped". Forward-planning content was intentionally removed 2026-05-11 — the user wants this file to reflect only what's worth focusing on today.

---

## Active focus: Shopify split — storefront + Vibe app + multi-tenant engine

The engine, today a single-tenant server-rendered app, is being split into three deployments:

1. **Shopify storefront** — live at `thesigmavibe.shop`. Catalog imported, branded, ready for customers. India / INR only. Manual fulfillment to original retailers.
2. **Vibe (Shopify App)** — scaffolded with Remix + Polaris + App Bridge, OAuth-installed on a dev store. **Vibe-specific UI not yet built** — still showing Shopify's stock template page.
3. **Vibe Engine** — multi-tenant API derived from today's `platform_core`. Refactor deferred until Vibe's UX validates on the single-tenant engine.

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
| Vibe app hosting | **Vercel — live at `https://vibe-app-five.vercel.app`** (deployed 2026-05-15) |
| Vibe app session store | Postgres `vibe` schema on Supabase (isolated from engine's `public` schema) |
| Dev tunnel (legacy) | All free tunnels (Cloudflare quick / ngrok free / localtunnel / Pinggy) failed in BLR/BOM regions due to anti-abuse interstitials breaking server-to-server app proxy requests. **Tunnels eliminated by deploying directly to Vercel.** |
| Engine hosting (planned) | Fly.io Mumbai — not yet deployed |
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
- [ ] **A.1.** Migration: add `tenant_id`, `shopify_product_id`, `shopify_variant_ids` (jsonb keyed by size), `image_hash` columns to `catalog_enriched`. **Blocks B.8.**
- [ ] **A.2.** Backfill `tenant_id = 't_Oq0BSHnewiEAAAAAagWWlmnV-0sJmcGk'` on all 13,177 imported rows. Depends on A.1.

## Phase B — Shopify store setup

- [x] **B.1.** Shopify store created and live at `thesigmavibe.shop`.
- [x] **B.2.** Razorpay + India shipping + GST + theme configured.
- [x] **B.3.** Size-chart section in theme.
- [x] **B.5.** ~~Dry-run 50 products~~ — skipped; went straight to full import.
- [x] **B.7.** Full import of 13,177 products (9 per-vendor CSVs).
- [ ] **B.4.** Mandatory pages: About · Contact · Shipping Policy · Returns/Refund · Privacy · Terms. **Deferred by user** ("we will get back to this later"). Required before customer-facing launch.
- [ ] **B.6.** Real-card test order end-to-end. Should happen before storefront sees real customers.
- [ ] **B.8.** Capture Shopify product/variant GIDs back into `catalog_enriched` (depends on A.1). Reads Shopify Admin API, matches via `vibe.source_product_id` metafield. **Linchpin for "Add to Cart" working from Vibe later.**

## Phase D — Vibe Shopify App

Vibe has **two completely separate surfaces** that get built differently:

| | Merchant Admin UI | Customer Storefront UI |
|---|---|---|
| Who | The merchant (you / future installers) | The shopper |
| URL | `admin.shopify.com/store/.../apps/vibe` | `thesigmavibe.shop/apps/vibe/*` |
| Purpose | Trust, control, attribution, settings | The actual AI experience |
| Mechanism | Embedded admin app (already working) | App Proxy (not yet set up) |
| UI library | Polaris | Custom (storefront brand) |

### Done

- [x] **D.1.** Remix + Polaris + App Bridge scaffold — [`vibe-app/`](vibe-app/) at worktree root.
- [x] **D.2.** Merchant-side OAuth install flow — installed on dev store `vibe-test-nmt8wy3q.myshopify.com`.

### D.S — Shared infrastructure (foundation; blocks customer surface)

- [x] **D.S.1.** **App Proxy configuration** wired end-to-end (verified 2026-05-15). `thesigmavibe.shop/apps/vibe/*` → Vercel-deployed Remix backend at `vibe-app-five.vercel.app/proxy/*`. [`vibe-app/app/routes/proxy.$.tsx`](vibe-app/app/routes/proxy.$.tsx) handles requests; [`vibe-app/shopify.app.vibe.toml`](vibe-app/shopify.app.vibe.toml) declares the route. Validated by rendering the Hello-from-Vibe placeholder at `vibe-test-nmt8wy3q.myshopify.com/apps/vibe/test` via real Shopify→Vercel forwarding.
- [x] **D.S.2.** HMAC signature validation via `authenticate.public.appProxy(request)` in the proxy route. Unsigned requests rejected with 400; signed requests from Shopify pass through.
- [ ] **D.S.3.** Customer auth: Shopify Customer Account integration when logged in, anonymous cookie-based session as fallback. Vibe ties wardrobe / chat history to whichever identity is present.
- [ ] **D.S.4.** Remaining GDPR webhooks: `customers/data_request`, `customers/redact`, `shop/redact`. (`app/uninstalled` + `app/scopes_update` already wired by the template.)

### D.C — Customer storefront UI (the actual product)

- [ ] **D.C.1.** Theme App Extension — "Style with Vibe" entry-point widget + storefront nav link. The discoverability layer.
- [ ] **D.C.2.** **Conversation page** — chat input, scroll-back history, product-card rendering. Calls Engine API.
- [ ] **D.C.3.** Wardrobe page (CRUD + filters). Requires D.S.3 (customer auth).
- [ ] **D.C.4.** Looks page (saved + past recommendations).
- [ ] **D.C.5.** Outfit Check page (upload outfit → feedback).
- [ ] **D.C.6.** Try-on integration (Gemini) surfaced inside Conversation + Looks.
- [ ] **D.C.7.** "Add to Cart" via Shopify Storefront API on every PDP card. **Depends on B.8** (need `shopify_variant_id` per catalog row).

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
- [ ] **C.9.** Deploy engine to Fly.io Mumbai.

## Phase E — Manual fulfillment SOP

- [ ] **E.1.** Document: open Shopify order → read `source_url` metafield → place order at original retailer → mark Shopify order fulfilled with tracking link. Trivial; write when first real order lands.
- [ ] **E.2.** *(Optional, defer until pain felt)* Internal dashboard listing open orders + their source URLs.

## Done outside the original task list

- [x] **Homepage hero** — "Style that gets you." copy locked, hero image generated, 4 value-prop card content drafted.
- [x] **Brand vocabulary map** — 10 retailers → display names hardcoded in `scripts/seed_thesigmavibe_catalog/brands.py`.
- [x] **Catalog price markup** — 20% baked into the CSV build.
- [x] **Vibe dev infrastructure** — Partner org "Vibe" with `mj.nigam28@gmail.com`, dev store `vibe-test-nmt8wy3q.myshopify.com`, ngrok tunnel working (Cloudflare quick-tunnels confirmed broken in user's region).

## Reuse (don't build)

- **Wishlist:** skip third-party wishlist apps for now. Vibe's Looks page will be the native equivalent. Re-evaluate after D.6 lands.
- **Auto-collections + nav menu** (Women / Men / Festive / Wedding / Workwear): rules already drafted; user to wire when ready. No code work.

## Next priorities (in execution order)

1. **D.C.2 — Conversation page (customer).** The first user-visible Vibe feature. Custom UI (not Polaris), calls the existing Engine API, renders product cards. Anonymous-session for now; logged-in customer support comes with D.S.3. **Note:** engine still on `localhost:8010`; we'll either tunnel app→engine via the Aura dev box's IP, or accelerate Phase C engine deployment to Fly.io.
2. **Engine deploy to Fly.io Mumbai.** Container the Python engine, set Supabase + OpenAI + Gemini secrets, deploy. ~1–2 hrs. Lets Vibe app on Vercel call the engine without tunnels.
3. **A.1 + A.2 — Schema migration + tenant_id backfill.** ~30 min total. Pure DB work, no dependencies. Unblocks B.8, which unblocks D.C.7 (Add to Cart).

After these three:
4. **B.8 — Capture Shopify GIDs.** Round-trips Shopify Admin API → writes Shopify product/variant IDs back to `catalog_enriched`.
5. **D.M.1 — Merchant welcome/status screen.** Replace the demo Polaris page with a small "Vibe is active" card. ~1 hr; user-visible polish.
6. **D.S.3 — Customer auth.** Shopify Customer Account integration. Unblocks D.C.3 (Wardrobe).
7. **D.C.3, D.C.4, D.C.5** — Wardrobe, Looks, Outfit Check.
8. **B.6 — Real-card test order.** Sanity check before broader access.
9. **D.S.4 — Remaining GDPR webhooks.** Required for public App Store listing.
10. Eventually: D.M.2–D.M.6 (richer merchant admin), D.P.* (prod rollout + listing), Phase C (engine multi-tenancy), B.4 (legal pages), Phase E.

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
