// Merchant admin landing page — replaces the demo "Generate a product"
// Polaris template (D.M.1). Surfaced inside Shopify admin at
// admin.shopify.com/store/<shop>/apps/vibe.
//
// Three signals the merchant wants the moment they install Vibe:
//   1. Vibe is reachable (status dot).
//   2. The customer-facing surface is somewhere they can click into.
//   3. Their products are wired in (catalog sync state).
//
// Anything richer (D.M.2 permissions, D.M.3 placement, D.M.4 analytics)
// lands in a separate page; this screen stays focused on "you're live".

import { useEffect, useRef, useState } from "react";
import type { LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";
import {
  Badge,
  Banner,
  BlockStack,
  Box,
  Button,
  Card,
  InlineStack,
  Layout,
  Link,
  Page,
  Text,
} from "@shopify/polaris";
import { TitleBar, useAppBridge } from "@shopify/app-bridge-react";

import {
  lookupOrCreateTenant,
  patchTenantThemeOverrides,
  type TenantStatus,
} from "../lib/engine.server";
import { ensureVibeMenuItems } from "../lib/navigation.server";
import {
  readMerchantThemeOverrides,
  type ShopifyThemeOverrides,
} from "../lib/theme-settings.server";
import { authenticate } from "../shopify.server";

// Return true when the probed overrides carry at least one value that
// differs from what the engine has stored. Used to avoid no-op PATCHes
// — the engine bumps updated_at_iso on every write, so an unchanged-
// content refresh would still hit the DB.
function themeOverridesDiffer(
  probed: ShopifyThemeOverrides,
  existing: TenantStatus["theme_overrides"] | undefined | null,
): boolean {
  const existingObj = existing ?? {};
  for (const [key, value] of Object.entries(probed)) {
    const ex = (existingObj as Record<string, unknown>)[key];
    if (Array.isArray(value)) {
      const exArr = Array.isArray(ex) ? ex : [];
      if (exArr.length !== value.length) return true;
      for (let i = 0; i < value.length; i++) {
        if (JSON.stringify(value[i]) !== JSON.stringify(exArr[i])) return true;
      }
      continue;
    }
    if (String(value ?? "") !== String(ex ?? "")) return true;
  }
  return false;
}

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { admin, session } = await authenticate.admin(request);
  // session.shop is the canonical *.myshopify.com domain (e.g.
  // `q8pery-95.myshopify.com`). Use it to build the storefront URL
  // *and* the customer-facing /apps/vibe/style link.
  //
  // session.scope is the space-separated list of scopes the merchant
  // actually granted. Surfacing it on the welcome screen serves as a
  // lightweight permissions transparency layer until D.M.2 lands the
  // dedicated panel.
  const grantedScopes = (session.scope ?? "")
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);

  // F.2.2c: resolve the shop's tenant_id + bootstrap status from the
  // engine. First call after install creates the tenants row with
  // status='pending'; subsequent calls return the existing row. The
  // admin home's SyncProgressCard reads this to decide whether to
  // show the install-progress UI.
  //
  // Engine wobble must not 500 the whole admin page — the merchant
  // can still review the rest of the screen during a transient
  // outage. But we DO need to surface that catalog sync is broken;
  // a silent null-tenant return would let the merchant believe Vibe
  // is fully wired when in fact no tenant row exists and customer
  // queries will fail. Pass `tenantError` to the component so it
  // can render a visible warning when the lookup fails.
  let tenant: TenantStatus | null = null;
  let tenantError: string | null = null;
  try {
    tenant = await lookupOrCreateTenant({ shopDomain: session.shop });
  } catch (err) {
    tenantError = err instanceof Error ? err.message : String(err);
    console.error(
      "[vibe] lookupOrCreateTenant failed for shop=%s:",
      session.shop,
      tenantError,
    );
  }

  // Refresh the merchant's theme settings on every admin home load.
  // Idempotent — engine stores the latest snapshot and Vibe pages
  // consume from `tenant.theme_overrides`. Best-effort — a probe
  // failure can't 500 the admin page. The themes/update webhook
  // handles ongoing updates; this catches first install + any drift
  // if a webhook was missed.
  if (tenant && tenant.tenant_id) {
    try {
      const overrides = await readMerchantThemeOverrides(admin);
      // Only PATCH if (a) at least one field was populated AND
      // (b) the probed values actually differ from what the engine
      // already has. The engine's set_theme_overrides bumps an
      // updated_at_iso on every write, so an unchanged-content PATCH
      // is still a DB write — comparing here keeps the admin home
      // load free of needless engine round-trips.
      const probedAny = Object.values(overrides).some(
        (v) => v && (Array.isArray(v) ? v.length > 0 : String(v).trim()),
      );
      if (probedAny && themeOverridesDiffer(overrides, tenant.theme_overrides)) {
        const updated = await patchTenantThemeOverrides({
          tenantId: tenant.tenant_id,
          overrides,
        });
        // Re-hydrate the tenant so the page renders with the freshly
        // captured overrides without waiting for the next request.
        tenant = updated;
      }
    } catch (err) {
      // Probe / engine PATCH failure — fall back to whatever's already
      // in `tenant.theme_overrides`. Don't surface to the merchant.
      console.warn(
        "[vibe] theme-settings refresh failed for shop=%s:",
        session.shop,
        err instanceof Error ? err.message : err,
      );
    }

    // Ensure "Find your Vibe" + "Your Vibes" are in the merchant's
    // main-menu. Idempotent. Best-effort — silent failure if the
    // write_navigation scope hasn't been granted yet (the
    // permissions banner above already nudges the merchant to
    // re-grant).
    try {
      const result = await ensureVibeMenuItems(admin);
      if (result.skipped) {
        console.info(
          "[vibe] menu-item injection skipped for shop=%s: %s",
          session.shop,
          result.skipped,
        );
      } else if (result.added > 0) {
        console.info(
          "[vibe] menu-item injection: added=%d alreadyPresent=%d for shop=%s",
          result.added,
          result.alreadyPresent,
          session.shop,
        );
      }
    } catch (err) {
      console.warn(
        "[vibe] menu-item injection failed for shop=%s:",
        session.shop,
        err instanceof Error ? err.message : err,
      );
    }
  }

  return json({ shop: session.shop, grantedScopes, tenant, tenantError });
};

// Plain-English description per granted scope so the merchant sees
// *why* each one is requested, not just the raw API string. Kept in
// sync with the toml's [access_scopes].scopes list — adding a new
// scope here without an entry below is a silent regression.
const SCOPE_DESCRIPTIONS: Record<string, { label: string; reason: string }> = {
  read_products: {
    label: "Read your products",
    reason: "So Vibe can recommend outfits from your actual catalog.",
  },
  read_inventory: {
    label: "Read your inventory",
    reason: "So Vibe doesn't recommend pieces that are out of stock.",
  },
  read_orders: {
    label: "Read your orders",
    reason:
      "So we can attribute purchases back to the Vibe sessions that drove them.",
  },
  read_customers: {
    label: "Read your customers",
    reason:
      "So an order's customer can be linked to their chat history with Vibe.",
  },
  read_themes: {
    label: "Read your themes",
    reason:
      "So we can verify the Style-with-Vibe block is live on the active theme.",
  },
  write_navigation: {
    label: "Update your store navigation",
    reason:
      "So we can add 'Find your Vibe' and 'Your Vibes' to your main menu — and remove them when you uninstall.",
  },
};

export default function MerchantIndex() {
  const { shop, grantedScopes, tenant, tenantError } =
    useLoaderData<typeof loader>();
  // App Bridge handle. `shopify.scopes.request([...])` triggers
  // Shopify's native consent dialog for additional scope grants from
  // inside the embedded admin. Required because we use the new
  // embedded-auth strategy (`unstable_newEmbeddedAuthStrategy: true`
  // in shopify.server.ts) which uses token exchange instead of OAuth
  // redirects — scope drift doesn't trigger an automatic re-auth
  // banner, so we trigger it manually.
  const appBridge = useAppBridge();
  const storefrontUrl = `https://${shop}`;
  const vibeUrl = `https://${shop}/apps/vibe/style`;
  const productsAdminUrl = `shopify:admin/products`;
  // Build per-scope rows. If Shopify reports a scope we don't have a
  // description for, still surface the raw scope name — half-known
  // info is more honest than an empty card, and it makes drift
  // visible (e.g. an old `write_products` grant lingering before the
  // merchant re-authorises with the F.1 scope set).
  const scopeRows = grantedScopes.map((scope) => ({
    scope,
    info: SCOPE_DESCRIPTIONS[scope] ?? {
      label: scope,
      reason: "Legacy grant — no longer used; will go away on next re-authorize.",
    },
  }));
  // Detect documented scopes the merchant DOESN'T have. If non-empty,
  // they're running on a stale scope set and need to re-authorize for
  // catalog sync / attribution / placement controls to actually work.
  const grantedSet = new Set(grantedScopes);
  const missingDocumentedScopes = Object.keys(SCOPE_DESCRIPTIONS).filter(
    (scope) => !grantedSet.has(scope),
  );
  const needsScopeUpdate = missingDocumentedScopes.length > 0;

  return (
    <Page>
      <TitleBar title="Vibe" />
      <BlockStack gap="500">
        {tenantError && !tenant ? (
          <Banner
            tone="critical"
            title="Catalog sync unavailable"
            action={{
              content: "Retry",
              onAction: () => window.location.reload(),
            }}
          >
            <BlockStack gap="200">
              <Text as="p" variant="bodyMd">
                Vibe couldn't reach its catalog service to look up your store.
                Customer recommendations may be broken until this is resolved —
                reload to retry.
              </Text>
              <Text as="p" variant="bodySm" tone="subdued">
                {tenantError}
              </Text>
            </BlockStack>
          </Banner>
        ) : null}
        {tenant && tenant.bootstrap_status !== "ready" ? (
          <SyncProgressCard tenant={tenant} />
        ) : null}
        {tenant && tenant.bootstrap_status === "ready" ? (
          <SyncSuccessBanner />
        ) : null}
        <Layout>
          <Layout.Section>
            <Card>
              <BlockStack gap="400">
                <InlineStack align="space-between" blockAlign="center">
                  <Text as="h2" variant="headingLg">
                    Vibe is active
                  </Text>
                  <Badge tone="success">Live</Badge>
                </InlineStack>
                <Text as="p" variant="bodyMd">
                  Your AI stylist is running on{" "}
                  <Link url={storefrontUrl} target="_blank" removeUnderline>
                    {shop}
                  </Link>
                  . Customers can chat with Vibe, build outfits around their
                  own wardrobe, and add full looks to cart from your catalog.
                </Text>
                <InlineStack gap="300">
                  <Button url={vibeUrl} target="_blank" variant="primary">
                    Open Vibe on your storefront
                  </Button>
                  <Button url={productsAdminUrl} target="_blank" variant="plain">
                    Manage products
                  </Button>
                </InlineStack>
              </BlockStack>
            </Card>
          </Layout.Section>

          <Layout.Section variant="oneThird">
            <BlockStack gap="500">
              <Card>
                <BlockStack gap="300">
                  <Text as="h3" variant="headingMd">
                    Catalog sync
                  </Text>
                  <Text as="p" variant="bodyMd" tone="subdued">
                    Vibe styles outfits from the products in your Shopify
                    catalog. When you add or edit products, Vibe picks them up
                    on the next refresh.
                  </Text>
                  <Box>
                    <Link url={productsAdminUrl} target="_blank" removeUnderline>
                      View products in admin →
                    </Link>
                  </Box>
                </BlockStack>
              </Card>

              <Card>
                <BlockStack gap="300">
                  <Text as="h3" variant="headingMd">
                    What customers see
                  </Text>
                  <BlockStack gap="200">
                    <InlineStack align="space-between">
                      <Text as="span" variant="bodyMd">
                        Conversation
                      </Text>
                      <Link url={vibeUrl} target="_blank" removeUnderline>
                        /apps/vibe/style
                      </Link>
                    </InlineStack>
                    <InlineStack align="space-between">
                      <Text as="span" variant="bodyMd">
                        Wardrobe
                      </Text>
                      <Link
                        url={`https://${shop}/apps/vibe/wardrobe`}
                        target="_blank"
                        removeUnderline
                      >
                        /apps/vibe/wardrobe
                      </Link>
                    </InlineStack>
                    <InlineStack align="space-between">
                      <Text as="span" variant="bodyMd">
                        Looks
                      </Text>
                      <Link
                        url={`https://${shop}/apps/vibe/looks`}
                        target="_blank"
                        removeUnderline
                      >
                        /apps/vibe/looks
                      </Link>
                    </InlineStack>
                  </BlockStack>
                </BlockStack>
              </Card>

              <Card>
                <BlockStack gap="300">
                  <Text as="h3" variant="headingMd">
                    Permissions
                  </Text>
                  <Text as="p" variant="bodyMd" tone="subdued">
                    What Vibe accesses on your store. Each permission powers
                    a specific feature — the dedicated controls panel arrives
                    in the next release.
                  </Text>
                  {needsScopeUpdate ? (
                    <Banner
                      tone="warning"
                      title="Permissions update available"
                      action={{
                        content: "Update permissions",
                        onAction: async () => {
                          // The runtime App Bridge object has a `.scopes`
                          // namespace with `request(scopes)` that opens
                          // Shopify's native consent dialog. The React
                          // package's type definitions (4.2.10) don't
                          // expose it yet, so we cast. On approval the
                          // iframe re-fetches and session.scope reflects
                          // the new grant.
                          //
                          // Wrapping in try/catch with toast feedback so
                          // a misconfigured runtime (older App Bridge
                          // script, scopes API missing, request denied)
                          // surfaces visibly instead of silently no-ops.
                          const bridge = appBridge as unknown as {
                            scopes?: {
                              request: (
                                scopes: string[],
                              ) => Promise<{ granted?: string[] } | void>;
                            };
                            toast?: { show: (msg: string, opts?: { isError?: boolean }) => void };
                          };
                          if (!bridge.scopes?.request) {
                            bridge.toast?.show(
                              "Update unavailable — open this app in a recent Shopify Admin.",
                              { isError: true },
                            );
                            console.error(
                              "[vibe] App Bridge scopes.request unavailable; bridge:",
                              bridge,
                            );
                            return;
                          }
                          try {
                            const result = await bridge.scopes.request(
                              missingDocumentedScopes,
                            );
                            console.info("[vibe] scopes.request requested:", missingDocumentedScopes);
                            console.info("[vibe] scopes.request result:", result);
                            const granted =
                              (result as { granted?: string[] } | undefined)
                                ?.granted ?? [];
                            if (granted.length === 0) {
                              // scopes.request resolved but nothing was
                              // actually granted. Most likely cause is
                              // App Bridge thinks the scopes are already
                              // available at the Partner Dashboard level
                              // (vibe-7 lists them) and skipped the
                              // dialog — but our Prisma session row
                              // hasn't picked up the new access token.
                              //
                              // Fall back to the OAuth install URL,
                              // which forces a fresh token exchange and
                              // writes the new scope set into Prisma.
                              bridge.toast?.show(
                                "Reauthorizing via OAuth — popup may open…",
                              );
                              window.open(
                                `/auth/login?shop=${encodeURIComponent(
                                  shop,
                                )}`,
                                "_top",
                              );
                              return;
                            }
                            bridge.toast?.show(
                              `Granted ${granted.length} permission${granted.length === 1 ? "" : "s"} — reloading…`,
                            );
                            window.setTimeout(
                              () => window.location.reload(),
                              500,
                            );
                          } catch (err) {
                            const msg =
                              err instanceof Error ? err.message : String(err);
                            console.error("[vibe] scopes.request failed:", err);
                            bridge.toast?.show(
                              `Couldn't update permissions: ${msg}`,
                              { isError: true },
                            );
                          }
                        },
                      }}
                    >
                      <BlockStack gap="200">
                        <Text as="p" variant="bodyMd">
                          Vibe needs {missingDocumentedScopes.length} additional
                          permission{missingDocumentedScopes.length === 1 ? "" : "s"}{" "}
                          to unlock catalog sync, purchase attribution, and
                          placement controls. Click <strong>Update permissions</strong>{" "}
                          below to grant them — Shopify will show its standard
                          consent dialog.
                        </Text>
                        <Text as="p" variant="bodySm" tone="subdued">
                          Pending: {missingDocumentedScopes.join(", ")}
                        </Text>
                      </BlockStack>
                    </Banner>
                  ) : null}
                  {scopeRows.length === 0 ? (
                    <Text as="p" variant="bodyMd" tone="subdued">
                      No permissions granted yet. Re-install or re-authorize
                      Vibe from the Shopify admin banner above.
                    </Text>
                  ) : (
                    <BlockStack gap="200">
                      {scopeRows.map(({ scope, info }) => (
                        <BlockStack gap="050" key={scope}>
                          <Text as="span" variant="bodyMd" fontWeight="semibold">
                            {info.label}
                          </Text>
                          <Text as="span" variant="bodySm" tone="subdued">
                            {info.reason}
                          </Text>
                        </BlockStack>
                      ))}
                    </BlockStack>
                  )}
                </BlockStack>
              </Card>

              <Card>
                <BlockStack gap="300">
                  <Text as="h3" variant="headingMd">
                    Next up
                  </Text>
                  <Text as="p" variant="bodyMd" tone="subdued">
                    A permissions controls panel, storefront placement
                    settings, and the analytics dashboard land in upcoming
                    releases.
                  </Text>
                </BlockStack>
              </Card>
            </BlockStack>
          </Layout.Section>
        </Layout>
      </BlockStack>
    </Page>
  );
}

// sessionStorage key the SyncProgressCard writes on completion and
// SyncSuccessBanner reads on the post-reload render. sessionStorage
// (not localStorage) so a fresh tab a week later doesn't surface a
// stale "synced" toast — the banner is scoped to "this tab visited
// during this install session".
const SYNC_SUCCESS_STORAGE_KEY = "vibe_sync_just_completed";

// Post-sync success banner. Renders only when the loader sees the
// tenant at status='ready' AND sessionStorage has a recent completion
// record from the SyncProgressCard. The banner is dismissible — once
// the merchant clicks Dismiss the sessionStorage record is cleared
// and the banner doesn't render again in this tab.
function SyncSuccessBanner() {
  // Initialise null so SSR renders nothing and the post-hydration
  // useEffect populates the count without a flash of stale content.
  const [info, setInfo] = useState<{ count: number; at: number } | null>(null);

  useEffect(() => {
    try {
      const raw = window.sessionStorage.getItem(SYNC_SUCCESS_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as { count?: number; at?: number };
      if (typeof parsed.count === "number" && typeof parsed.at === "number") {
        setInfo({ count: parsed.count, at: parsed.at });
      }
    } catch {
      // Ignore — malformed storage just means no banner.
    }
  }, []);

  if (!info) return null;

  return (
    <Banner
      tone="success"
      title={`Catalog synced — ${info.count} product${info.count === 1 ? "" : "s"} ready`}
      onDismiss={() => {
        try {
          window.sessionStorage.removeItem(SYNC_SUCCESS_STORAGE_KEY);
        } catch {
          // ignore
        }
        setInfo(null);
      }}
    >
      <Text as="p" variant="bodyMd">
        Vibe is now styling outfits from your catalog. Vision-attribute
        enrichment (smarter matching) runs in the background and lands within
        the next few hours.
      </Text>
    </Banner>
  );
}

// Response envelope from app.api.bootstrap.tsx. Kept in sync with the
// action's BootstrapTickResponse / BootstrapTickFail union.
type BootstrapTickAck =
  | {
      ok: true;
      processed: number;
      accumulated: number;
      batchResult: { created: number; updated: number; failed: number };
      nextCursor: string | null;
      done: boolean;
    }
  | { ok: false; error: string };

// Install-time catalog sync progress (F.2.2c). Renders only while the
// engine reports a non-ready bootstrap_status; reloads the page on
// completion so the loader picks up `status=ready` and this card goes
// away.
//
// The polling loop runs entirely in the browser — each tick is a
// fresh POST to /app/api/bootstrap which fetches one Shopify Admin
// GraphQL page and forwards it to the engine. Driving from the client
// keeps each function call under Vercel's 60s ceiling even for big
// catalogs (260 ticks × ~3s for a 13K re-install is acceptable; the
// merchant just needs to keep the tab open).
function SyncProgressCard({ tenant }: { tenant: TenantStatus }) {
  const [processed, setProcessed] = useState(tenant.product_count);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Guard against StrictMode double-mount + tab focus changes re-firing
  // the effect. Without this, two tick loops can race on the same
  // cursor space — the engine's idempotency saves correctness but the
  // duplicate GraphQL calls are wasted.
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    if (tenant.bootstrap_status === "ready" || tenant.bootstrap_status === "failed") {
      return;
    }
    startedRef.current = true;
    let cancelled = false;

    async function run() {
      let cursor: string | null = null;
      let total = tenant.product_count;

      while (!cancelled) {
        let resp: Response;
        try {
          resp = await fetch("/app/api/bootstrap", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            // tenant_id is intentionally NOT sent — the action derives
            // it from session.shop server-side. Sending it from the
            // client would just create a confusing surface for someone
            // reading the code; the action ignores any value in the body.
            body: JSON.stringify({
              after: cursor,
              accumulated: total,
            }),
          });
        } catch (e) {
          if (!cancelled) {
            setError(e instanceof Error ? e.message : String(e));
          }
          return;
        }
        if (cancelled) return;

        // Parse JSON first — the action returns structured `{ok:false,
        // error}` envelopes with non-2xx status codes (e.g. 502 on
        // engine failure), so the body has more signal than the status.
        let body: BootstrapTickAck;
        try {
          body = (await resp.json()) as BootstrapTickAck;
        } catch {
          setError(
            resp.ok
              ? "Invalid response from sync endpoint"
              : `Sync failed (HTTP ${resp.status})`,
          );
          return;
        }
        if (cancelled) return;
        if (body.ok !== true) {
          setError(body.error || `Sync failed (HTTP ${resp.status})`);
          return;
        }
        total = body.accumulated;
        cursor = body.nextCursor;
        setProcessed(total);
        if (body.done) {
          setDone(true);
          // Persist the completion to sessionStorage so the post-reload
          // home can render a sticky success banner — without this the
          // SyncProgressCard would just vanish (status='ready' makes it
          // not render) and the merchant gets no confirmation that the
          // work actually happened, especially for small catalogs where
          // the sync runs in seconds.
          try {
            window.sessionStorage.setItem(
              SYNC_SUCCESS_STORAGE_KEY,
              JSON.stringify({ count: total, at: Date.now() }),
            );
          } catch {
            // sessionStorage can throw in private-browsing modes; we
            // can live without the banner.
          }
          // 4s before reload — long enough that a 60-product sync
          // (which can take just a few seconds) is visible in the
          // "complete" state, short enough that the merchant isn't
          // stuck waiting on a stale UI.
          window.setTimeout(() => window.location.reload(), 4_000);
          return;
        }
      }
    }

    void run();
    return () => {
      cancelled = true;
    };
  }, [tenant.tenant_id, tenant.product_count, tenant.bootstrap_status]);

  if (tenant.bootstrap_status === "failed") {
    return (
      <Banner
        tone="critical"
        title="Catalog sync failed"
        action={{
          content: "Retry",
          onAction: () => window.location.reload(),
        }}
      >
        <Text as="p" variant="bodyMd">
          Vibe couldn't finish syncing your catalog. Reload this page to retry —
          previously-synced products are kept, so this picks up where it left
          off.
        </Text>
      </Banner>
    );
  }

  if (error) {
    return (
      <Banner
        tone="warning"
        title="Catalog sync interrupted"
        action={{
          content: "Retry",
          onAction: () => window.location.reload(),
        }}
      >
        <BlockStack gap="200">
          {processed > 0 ? (
            <Text as="p" variant="bodyMd">
              {processed} products synced before the error. Retrying continues
              from there.
            </Text>
          ) : null}
          <Text as="p" variant="bodySm" tone="subdued">
            {error}
          </Text>
        </BlockStack>
      </Banner>
    );
  }

  return (
    <Banner
      tone={done ? "success" : "info"}
      title={done ? "Catalog synced" : "Syncing your catalog"}
    >
      <BlockStack gap="200">
        <Text as="p" variant="bodyMd">
          {done
            ? `${processed} products are styling-ready. Reloading…`
            : `Vibe is reading your products from Shopify. ${processed} processed so far — keep this tab open while we finish.`}
        </Text>
        {!done ? (
          <Text as="p" variant="bodySm" tone="subdued">
            First-time sync runs the vision pipeline once per product. Roughly
            30 seconds per 50 products; subsequent re-installs are near-instant.
          </Text>
        ) : null}
      </BlockStack>
    </Banner>
  );
}
