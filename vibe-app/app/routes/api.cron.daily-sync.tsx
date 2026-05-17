// F.3 — daily catalog sync cron.
//
// Triggered by Vercel cron (see vercel.json). Two jobs:
//
//   1. **Drift catch** — for each `ready` tenant, walk Shopify
//      Admin GraphQL with an `updatedAtMin` filter and forward
//      changed products to engine `bootstrap-batch`. The engine's
//      cache-hit path makes this cheap (metadata refresh only on
//      products without changes; full embed only for genuinely new
//      products that somehow missed the F.4 webhook).
//
//   2. **Enrichment ingest** — call engine `enrichment/poll-all`
//      to pick up any vision-attribute Batch API submissions that
//      completed in the last 24h. This is where freshly enriched
//      attribute columns land (GarmentCategory, FabricDrape, ...).
//
// Why a cron at all if webhooks already handle real-time updates:
//
//   - Webhook delivery is best-effort; Shopify retries for 48h
//     then drops. The cron is the safety net for the drop case.
//   - OpenAI Batch API completion is async (24h SLA) — something
//     has to poll. The cron is the cheapest place for that.
//
// Time budget: Vercel cron functions inherit the platform's 60s
// function ceiling. We process tenants oldest-`last_sync_at`-first
// and exit early if we're approaching the wall to avoid a hard
// truncation. Skipped tenants get picked up the next day.

import type { ActionFunctionArgs, LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import {
  listTenants,
  pollAllEnrichment,
  submitPendingEnrichmentAll,
  type TenantListItem,
} from "../lib/engine.server";
import { logInfo, logError, logWarn } from "../lib/logger.server";
import { unauthenticated } from "../shopify.server";

// Products per Admin GraphQL page — same as the install-time bootstrap.
const PRODUCTS_PER_PAGE = 50;
const VARIANTS_PER_PRODUCT = 20;

// Soft wall-clock budget. Vercel hard-limits the function at 60s; we
// stop entering new tenants past 45s so the enrichment poll has time
// to run at the end. Tenants we don't reach get processed tomorrow.
const SOFT_BUDGET_MS = 45_000;

// How far back to look for updates. A day's worth + a buffer for
// clock skew + missed-webhook tolerance. If the cron is paused for
// a few days, the next run's window still catches everything.
const UPDATED_AT_LOOKBACK_HOURS = 30;

type CronResult = {
  ok: boolean;
  tenants_seen: number;
  tenants_synced: number;
  tenants_skipped_for_budget: number;
  enrichment_submitted: number;
  enrichment_batches_polled: number;
  enrichment_rows_ingested: number;
  errors: Array<{ stage: string; shop: string; error: string }>;
};

export const action = async ({ request }: ActionFunctionArgs) => {
  return runCron(request);
};

// Vercel cron sends a GET, so handle both verbs.
export const loader = async ({ request }: LoaderFunctionArgs) => {
  return runCron(request);
};

async function runCron(request: Request) {
  // Vercel cron auth: the platform sends Authorization: Bearer <CRON_SECRET>
  // on every cron-triggered request. Reject anything without it so
  // randos can't hit the endpoint and trigger the engine load.
  //
  // CRON_SECRET must be set in the Vercel project env. Empty/missing
  // is treated as misconfiguration — fail closed.
  const expected = process.env.CRON_SECRET?.trim();
  if (!expected) {
    logError("vibe_cron_daily_sync_misconfigured", {
      reason: "CRON_SECRET env var is not set",
    });
    return json({ ok: false, error: "CRON_SECRET not configured" }, { status: 503 });
  }
  const provided = request.headers.get("authorization") || "";
  if (provided !== `Bearer ${expected}`) {
    return json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  const startedAt = Date.now();
  const result: CronResult = {
    ok: true,
    tenants_seen: 0,
    tenants_synced: 0,
    tenants_skipped_for_budget: 0,
    enrichment_submitted: 0,
    enrichment_batches_polled: 0,
    enrichment_rows_ingested: 0,
    errors: [],
  };

  // 1. List all ready tenants — the engine returns them oldest
  //    last_sync_at first so a partial cron run still makes forward
  //    progress on the stalest shops.
  let tenants: TenantListItem[];
  try {
    tenants = await listTenants();
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    logError("vibe_cron_daily_sync_list_failed", { err: msg });
    return json({ ...result, ok: false, error: msg }, { status: 502 });
  }
  result.tenants_seen = tenants.length;
  logInfo("vibe_cron_daily_sync_start", { tenants_seen: tenants.length });

  // 2. For each tenant, walk Shopify with an updated_at_min filter
  //    and forward to engine. Idempotent — engine cache-hits the
  //    metadata refresh path for unchanged products.
  const since = new Date(
    Date.now() - UPDATED_AT_LOOKBACK_HOURS * 3600_000,
  ).toISOString();
  for (const tenant of tenants) {
    if (Date.now() - startedAt > SOFT_BUDGET_MS) {
      result.tenants_skipped_for_budget = tenants.length - result.tenants_synced;
      logWarn("vibe_cron_daily_sync_budget_exhausted", {
        elapsed_ms: Date.now() - startedAt,
        tenants_synced: result.tenants_synced,
        tenants_skipped: result.tenants_skipped_for_budget,
      });
      break;
    }
    try {
      const products = await syncOneTenant(tenant, since);
      result.tenants_synced += 1;
      logInfo("vibe_cron_daily_sync_tenant", {
        tenant_id: tenant.tenant_id,
        shop: tenant.shopify_shop_domain,
        products_seen: products,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      result.errors.push({
        stage: "tenant_sync",
        shop: tenant.shopify_shop_domain,
        error: msg,
      });
      logError("vibe_cron_daily_sync_tenant_failed", {
        tenant_id: tenant.tenant_id,
        shop: tenant.shopify_shop_domain,
        err: msg,
      });
    }
  }

  // 3. Kick off enrichment for tenants that have pending-enrichment
  //    rows with no batch in-flight. Closes the gap where F.4 product
  //    webhooks insert new rows but nothing else triggers a submit
  //    (bootstrap_complete only fires at install). Idempotent per
  //    tenant — submit short-circuits if an open batch already exists.
  try {
    const submitted = await submitPendingEnrichmentAll();
    result.enrichment_submitted = submitted.submitted;
    if (submitted.errors.length > 0) {
      for (const e of submitted.errors) {
        result.errors.push({
          stage: "enrichment_submit",
          shop: e.tenant_id,
          error: e.error,
        });
      }
    }
    logInfo("vibe_cron_daily_sync_enrichment_submit", {
      tenants_seen: submitted.tenants_seen,
      submitted: submitted.submitted,
      no_op: submitted.no_op,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    result.errors.push({ stage: "enrichment_submit", shop: "*", error: msg });
    logError("vibe_cron_daily_sync_enrichment_submit_failed", { err: msg });
  }

  // 4. Poll any in-flight enrichment batches across all tenants. This
  //    is what ingests vision-attribute results from the OpenAI Batch
  //    API submissions kicked off above (or by bootstrap_complete).
  //    Safe to call when none are in-flight (no-op).
  try {
    const polled = await pollAllEnrichment();
    result.enrichment_batches_polled = polled.length;
    result.enrichment_rows_ingested = polled.reduce(
      (acc, p) => acc + (p.rows_ingested ?? 0),
      0,
    );
    logInfo("vibe_cron_daily_sync_enrichment", {
      batches_polled: polled.length,
      rows_ingested: result.enrichment_rows_ingested,
      batches: polled.map((p) => ({
        id: p.openai_batch_id,
        status: p.final_status,
        ingested: p.rows_ingested,
        failed: p.rows_failed,
      })),
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    result.errors.push({ stage: "enrichment_poll", shop: "*", error: msg });
    logError("vibe_cron_daily_sync_enrichment_failed", { err: msg });
  }

  result.ok = result.errors.length === 0;
  logInfo("vibe_cron_daily_sync_done", {
    elapsed_ms: Date.now() - startedAt,
    ...result,
  });
  return json(result);
}

// Walk Shopify Admin GraphQL for one tenant with an updated_at_min
// filter, forwarding each page to the engine's bootstrap-batch
// endpoint. Returns the count of products processed across all
// pages so the caller can log it.
async function syncOneTenant(
  tenant: TenantListItem,
  updatedAtMin: string,
): Promise<number> {
  // Offline access token via Prisma session storage. The merchant
  // approved offline scope at install — that token lets us call
  // Admin GraphQL without an active embedded session.
  let admin;
  try {
    ({ admin } = await unauthenticated.admin(tenant.shopify_shop_domain));
  } catch (err) {
    throw new Error(
      `unauthenticated.admin failed for ${tenant.shopify_shop_domain}: ${
        err instanceof Error ? err.message : String(err)
      }`,
    );
  }

  let cursor: string | null = null;
  let totalProcessed = 0;

  // Shopify search syntax: `updated_at:>=<ISO>`. Quote the timestamp
  // so colons don't confuse the parser.
  const query = `updated_at:>='${updatedAtMin}'`;

  while (true) {
    const gqlResp = await admin.graphql(
      `#graphql
      query VibeDailySyncProducts($first: Int!, $after: String, $variantsFirst: Int!, $query: String!) {
        products(first: $first, after: $after, query: $query) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id
            title
            descriptionHtml
            vendor
            onlineStoreUrl
            featuredImage { url }
            variants(first: $variantsFirst) {
              nodes { id title sku price availableForSale }
            }
          }
        }
      }`,
      {
        variables: {
          first: PRODUCTS_PER_PAGE,
          after: cursor,
          variantsFirst: VARIANTS_PER_PRODUCT,
          query,
        },
      },
    );
    if (!gqlResp.ok) {
      throw new Error(`Admin GraphQL HTTP ${gqlResp.status}`);
    }
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
      errors?: Array<{ message?: string; extensions?: { code?: string } }>;
    };
    const gql = (await gqlResp.json()) as GraphQLResponse;
    if (Array.isArray(gql.errors) && gql.errors.length > 0) {
      const codes = gql.errors
        .map((e) => e.extensions?.code || e.message || "unknown")
        .join(", ");
      throw new Error(`Admin GraphQL errors: ${codes}`);
    }
    const page = gql.data?.products;
    const nodes = page?.nodes ?? [];
    const hasNext = !!page?.pageInfo?.hasNextPage;
    cursor = page?.pageInfo?.endCursor ?? null;

    if (nodes.length === 0) {
      // No changed products in the lookback window — done.
      break;
    }

    // Convert GraphQL shape → BootstrapProductInput. Same translation
    // as the install-time chunk processor (vibe-app/routes/app.api.bootstrap.tsx).
    type EngineProduct = {
      shopify_product_id: string;
      title: string;
      description: string;
      vendor: string;
      price?: number;
      image_url: string;
      product_url: string;
      available_for_sale: boolean;
      shopify_variant_ids: Record<string, string>;
    };
    const products: EngineProduct[] = nodes.map((node) => {
      const vNodes = node.variants?.nodes ?? [];
      const variantMap: Record<string, string> = {};
      let firstPrice: number | undefined;
      let anyAvailable = false;
      for (const v of vNodes) {
        const size = String(v.title ?? "").trim();
        if (size && v.id) variantMap[size] = v.id;
        if (firstPrice === undefined && v.price) {
          const p = parseFloat(v.price);
          if (Number.isFinite(p)) firstPrice = p;
        }
        if (v.availableForSale) anyAvailable = true;
      }
      return {
        shopify_product_id: node.id,
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

    // Forward this page to the engine. bootstrap-batch is idempotent
    // and only flips status='syncing' on tenants in pending/failed —
    // a 'ready' tenant stays ready (see PR #466 / api.py change).
    const engineUrl = process.env.ENGINE_API_URL?.trim() ?? "";
    if (!engineUrl) {
      throw new Error("ENGINE_API_URL not set");
    }
    const resp = await fetch(
      `${engineUrl}/v1/tenants/${encodeURIComponent(tenant.tenant_id)}/bootstrap-batch`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ products }),
        signal: AbortSignal.timeout(45_000),
      },
    );
    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new Error(`bootstrap-batch HTTP ${resp.status}: ${text.slice(0, 200)}`);
    }

    totalProcessed += products.length;
    if (!hasNext) break;
  }

  return totalProcessed;
}
