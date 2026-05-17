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
import { TitleBar } from "@shopify/app-bridge-react";

import { authenticate } from "../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session } = await authenticate.admin(request);
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
  return json({ shop: session.shop, grantedScopes });
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
  write_metafields: {
    label: "Write metafields on orders",
    reason:
      "So Vibe-attributed orders get tagged with the outfit that influenced them — powers your analytics.",
  },
};

export default function MerchantIndex() {
  const { shop, grantedScopes } = useLoaderData<typeof loader>();
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
                    <Banner tone="warning" title="Permissions update available">
                      <BlockStack gap="200">
                        <Text as="p" variant="bodyMd">
                          Vibe needs {missingDocumentedScopes.length} additional
                          permission{missingDocumentedScopes.length === 1 ? "" : "s"}{" "}
                          to unlock catalog sync, purchase attribution, and
                          placement controls. Re-authorize from the Shopify
                          banner at the top of this page; once granted, the new
                          permissions appear below.
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
