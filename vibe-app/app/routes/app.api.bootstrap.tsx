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
  postBootstrapBatch,
  postBootstrapComplete,
  type BootstrapProductInput,
} from "../lib/engine.server";
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
  /** `t_<base64url>` from /v1/tenants/lookup-or-create. */
  tenantId: string;
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
  const tenantId = String(body.tenantId || "").trim();
  if (!tenantId) {
    return json<BootstrapTickFail>(
      { ok: false, error: "Missing tenantId" },
      { status: 400 },
    );
  }
  const after = body.after?.trim() ? body.after.trim() : null;
  const accumulated = Math.max(0, Number(body.accumulated || 0));

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
  };
  const gql = (await gqlResp.json()) as GraphQLResponse;
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
    return json<BootstrapTickFail>(
      {
        ok: false,
        error: err instanceof EngineError ? err.message : String(err),
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
      console.error(
        "[vibe] bootstrap complete failed:",
        err instanceof Error ? err.message : err,
      );
    }
  }

  // Hint for the operator — surface session.shop in the response so
  // debugging logs in Vercel show which store the tick was for.
  console.info(
    "[vibe] bootstrap tick shop=%s tenant=%s processed=%d accumulated=%d created=%d updated=%d failed=%d done=%s",
    session.shop,
    tenantId,
    products.length,
    newAccumulated,
    batchResult.created,
    batchResult.updated,
    batchResult.failed,
    !hasNext,
  );

  return json<BootstrapTickResponse>({
    ok: true,
    processed: products.length,
    accumulated: newAccumulated,
    batchResult,
    nextCursor: hasNext ? endCursor : null,
    done: !hasNext,
  });
};
