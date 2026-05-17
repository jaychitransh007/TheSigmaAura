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
  return json({ shop: session.shop });
};

export default function MerchantIndex() {
  const { shop } = useLoaderData<typeof loader>();
  const storefrontUrl = `https://${shop}`;
  const vibeUrl = `https://${shop}/apps/vibe/style`;
  const productsAdminUrl = `shopify:admin/products`;

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
                    Next up
                  </Text>
                  <Text as="p" variant="bodyMd" tone="subdued">
                    Permissions, storefront placement controls, and the
                    analytics dashboard land in the next release.
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
