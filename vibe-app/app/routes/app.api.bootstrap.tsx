// Merchant-admin bootstrap chunk processor (F.2.2c).
//
// Drives the install-time catalog sync one page at a time. Browser
// JS in the admin home polls this in a loop while
// `tenants.bootstrap_status != 'ready'`. Each call:
//
//   1. Fetches one page of products from Shopify Admin GraphQL (50
//      per page; tunable below).
//   2. POSTs them to the engine's /v1/tenants/{tenant_id}/bootstrap-batch
//      which idempotency-checks each product and only embeds the
//      ones it hasn't seen before.
//   3. Returns the next cursor + done flag so the browser knows
//      whether to keep going.
//   4. On done, calls /v1/tenants/{tenant_id}/bootstrap-complete
//      to flip status to 'ready'.
//
// This is the **admin-side** route, NOT a storefront-facing one —
// it uses `authenticate.admin` (Shopify session token from the
// embedded admin app) rather than App Proxy auth.

import type { ActionFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import {
  EngineError,
  lookupOrCreateTenant,
  postBootstrapBatch,
  postBootstrapComplete,
  type BootstrapProductInput,
} from "../lib/engine.server";
import { logInfo, logWarn, logError } from "../lib/logger.server";
import { authenticate } from "../shopify.server";

// Products per Admin GraphQL page. Sized so a fresh-install batch
// stays under Vercel's 60s function ceiling — 50 products × ~600ms
// embedding-generation each (single OpenAI batched call covers
// them all in one shot) = ~30s. For re-installs / cache hits this
// is mostly metadata-update work and finishes in seconds.
const PRODUCTS_PER_PAGE = 50;

// Variants per product. Most apparel SKUs have 5 sizes; cap at 20
// for safety against catalogs with unusual variant fan-out.
const VARIANTS_PER_PRODUCT = 20;

type BootstrapTickRequest = {
  /** GraphQL cursor returned by the previous tick. Omitted on the
   *  first tick — Admin GraphQL returns the first page when `after`
   *  is null. */
  after?: string | null;
  /** Running total carried across ticks for the progress UI. */
  accumulated?: number;
};

type BootstrapTickResponse = {
  ok: true;
  /** Number of products processed in this tick. */
  processed: number;
  /** Sum of products processed across all ticks so far (incl. this). */
  accumulated: number;
  /** Per-tick aggregate from the engine. */
  batchResult: {
    created: number;
    updated: number;
    failed: number;
    errors: Array<{ shopify_product_id: string; error: string }>;
  };
  /** Cursor to pass to the next tick, or null when pagination is done. */
  nextCursor: string | null;
  /** True iff this was the last tick (pagination exhausted + complete
   *  endpoint called). */
  done: boolean;
};

type BootstrapTickFail = { ok: false; error: string };

export const action = async ({ request }: ActionFunctionArgs) => {
  const { admin, session } = await authenticate.admin(request);

  let body: BootstrapTickRequest;
  try {
    body = (await request.json()) as BootstrapTickRequest;
  } catch {
    return json<BootstrapTickFail>(
      { ok: false, error: "Invalid JSON body" },
      { status: 400 },
    );
  }
  const after = body.after?.trim() ? body.after.trim() : null;
  const accumulated = Math.max(0, Number(body.accumulated || 0));

  // Derive the tenant from the authenticated session, NOT from the
  // request body. Trusting body.tenantId would let a malicious shop
  // admin (Shop A) authenticate normally and then POST another
  // tenant's id (Shop B) — the GraphQL call would return Shop A's
  // products (session-bound) but the engine would write them to
  // Shop B's tenant. lookupOrCreateTenant is idempotent so calling
  // it every tick is cheap (one DB lookup); on first tick after
  // install it also handles row creation.
  let tenantId: string;
  try {
    const tenant = await lookupOrCreateTenant({ shopDomain: session.shop });
    tenantId = tenant.tenant_id;
  } catch (err) {
    return json<BootstrapTickFail>(
      {
        ok: false,
        error:
          err instanceof EngineError
            ? `tenant lookup: ${err.message}`
            : String(err),
      },
      { status: 502 },
    );
  }

  // Fetch one page of products from Admin GraphQL. `descriptionHtml`
  // is what the embedding text uses (engine strips HTML internally —
  // see catalog_bootstrap_service._strip_html). `variants.nodes` gets
  // sizes + per-variant gids for the cart-add wiring on the customer
  // storefront.
  const gqlResp = await admin.graphql(
    `#graphql
    query VibeBootstrapProductsPage($first: Int!, $after: String, $variantsFirst: Int!) {
      products(first: $first, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          title
          descriptionHtml
          vendor
          onlineStoreUrl
          featuredImage { url }
          variants(first: $variantsFirst) {
            nodes {
              id
              title
              sku
              price
              availableForSale
            }
          }
        }
      }
    }`,
    {
      variables: {
        first: PRODUCTS_PER_PAGE,
        after,
        variantsFirst: VARIANTS_PER_PRODUCT,
      },
    },
  );
  type GraphQLResponse = {
    data?: {
      products?: {
        pageInfo?: { hasNextPage?: boolean; endCursor?: string | null };
        nodes?: Array<{
          id: string;
          title?: string;
          descriptionHtml?: string;
          vendor?: string;
          onlineStoreUrl?: string;
          featuredImage?: { url?: string };
          variants?: {
            nodes?: Array<{
              id: string;
              title?: string;
              sku?: string;
              price?: string;
              availableForSale?: boolean;
            }>;
          };
        }>;
      };
    };
    errors?: Array<{
      message?: string;
      extensions?: { code?: string };
    }>;
  };

  // Non-2xx response = auth expiry, hard error, or sustained throttle
  // beyond the Shopify client's internal retry. Surface up to the
  // browser so it shows the error banner instead of falling through
  // to the empty-nodes path that would prematurely mark the bootstrap
  // complete.
  if (!gqlResp.ok) {
    return json<BootstrapTickFail>(
      {
        ok: false,
        error: `Shopify Admin GraphQL HTTP ${gqlResp.status}`,
      },
      { status: 502 },
    );
  }
  const gql = (await gqlResp.json()) as GraphQLResponse;
  // Top-level GraphQL errors include THROTTLED, INTERNAL_SERVER_ERROR,
  // ACCESS_DENIED, etc. Shopify returns these with HTTP 200, so they'd
  // slip past the ok check above. Detecting them here protects the
  // "no nodes returned" path from being interpreted as a clean end-of-
  // pagination — which would otherwise flip tenants.bootstrap_status
  // to 'ready' with an incomplete catalog.
  if (Array.isArray(gql.errors) && gql.errors.length > 0) {
    const codes = gql.errors
      .map((e) => e.extensions?.code || e.message || "unknown")
      .join(", ");
    return json<BootstrapTickFail>(
      { ok: false, error: `Shopify Admin GraphQL errors: ${codes}` },
      { status: 502 },
    );
  }
  const page = gql.data?.products;
  const nodes = page?.nodes ?? [];
  const hasNext = !!page?.pageInfo?.hasNextPage;
  const endCursor = page?.pageInfo?.endCursor ?? null;

  // Convert Admin GraphQL shape → engine BootstrapProductInput. Pick
  // the FIRST available variant's price as the headline price; the
  // full per-size variant map goes into shopify_variant_ids so the
  // storefront cart code can map a chosen size to its gid.
  const products: BootstrapProductInput[] = nodes.map((node) => {
    const variantNodes = node.variants?.nodes ?? [];
    const variantMap: Record<string, string> = {};
    let firstPrice: number | undefined;
    let anyAvailable = false;
    for (const v of variantNodes) {
      // `title` from Shopify variants is the size label for apparel
      // (e.g. "S", "M", "L"). For non-apparel it can be "Default
      // Title" — those still get stored but the storefront's size
      // chip UI won't render meaningfully.
      const size = String(v.title ?? "").trim();
      if (size && v.id) variantMap[size] = v.id;
      if (firstPrice === undefined && v.price) {
        const p = parseFloat(v.price);
        if (Number.isFinite(p)) firstPrice = p;
      }
      if (v.availableForSale) anyAvailable = true;
    }
    return {
      shopify_product_id: node.id, // gid://shopify/Product/<n>
      title: node.title ?? "",
      description: node.descriptionHtml ?? "",
      vendor: node.vendor ?? "",
      price: firstPrice,
      image_url: node.featuredImage?.url ?? "",
      product_url: node.onlineStoreUrl ?? "",
      available_for_sale: anyAvailable,
      shopify_variant_ids: variantMap,
    };
  });

  // Empty page = pagination exhausted before we even started. Caller
  // shouldn't normally see this (it means status was already
  // 'syncing' but the cursor walked past the end). Treat as a
  // terminal tick.
  if (products.length === 0) {
    if (!hasNext) {
      try {
        await postBootstrapComplete({ tenantId, productCount: accumulated });
      } catch (err) {
        return json<BootstrapTickFail>(
          {
            ok: false,
            error: err instanceof EngineError ? err.message : String(err),
          },
          { status: 502 },
        );
      }
    }
    return json<BootstrapTickResponse>({
      ok: true,
      processed: 0,
      accumulated,
      batchResult: { created: 0, updated: 0, failed: 0, errors: [] },
      nextCursor: hasNext ? endCursor : null,
      done: !hasNext,
    });
  }

  let batchResult;
  try {
    batchResult = await postBootstrapBatch({ tenantId, products });
  } catch (err) {
    const msg = err instanceof EngineError ? err.message : String(err);
    logError("vibe_bootstrap_tick_failed", {
      shop: session.shop,
      tenant_id: tenantId,
      products_in_page: products.length,
      cursor_in: after,
      err: msg,
    });
    return json<BootstrapTickFail>(
      {
        ok: false,
        error: msg,
      },
      { status: 502 },
    );
  }

  const newAccumulated = accumulated + products.length;

  // Last page — fire the complete endpoint synchronously so the
  // browser sees status='ready' on its next poll.
  if (!hasNext) {
    try {
      await postBootstrapComplete({ tenantId, productCount: newAccumulated });
    } catch (err) {
      // Don't fail the tick — the batch did land. The complete call
      // can be retried by reloading the admin home. Log and continue.
      logWarn("vibe_bootstrap_complete_failed", {
        shop: session.shop,
        tenant_id: tenantId,
        final_count: newAccumulated,
        err: err instanceof Error ? err.message : String(err),
      });
    }
  }

  // Structured tick log — operators can grep `vibe_bootstrap_tick` to
  // walk an install end-to-end and tell "slow but working" from
  // "stuck on tick N". Includes shop AND tenant so single-tenant and
  // multi-tenant dashboards both work.
  logInfo("vibe_bootstrap_tick", {
    shop: session.shop,
    tenant_id: tenantId,
    products_in_page: products.length,
    accumulated: newAccumulated,
    created: batchResult.created,
    updated: batchResult.updated,
    failed: batchResult.failed,
    has_next: hasNext,
    done: !hasNext,
  });

  return json<BootstrapTickResponse>({
    ok: true,
    processed: products.length,
    accumulated: newAccumulated,
    batchResult,
    nextCursor: hasNext ? endCursor : null,
    done: !hasNext,
  });
};
