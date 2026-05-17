// F.4 — products/{create,update} webhook handler.
//
// Shopify fires this when a merchant creates a new product or
// modifies an existing one (any field — title, description,
// variants, inventory level). Both topics share this route via the
// shopify.app.vibe.toml subscription so we don't have to duplicate
// HMAC validation + tenant-resolution + engine forwarding.
//
// The handler MUST return 200 within Shopify's 5s budget. We resolve
// the tenant from session.shop, forward the raw payload to the
// engine, and return. The engine call is sized to fit (~2s for a
// metadata-only update; ~30s for a cache-miss new product because
// of the embedding call — see below).
//
// Cache-miss bound: a brand-new product NOT in catalog_enriched
// will trigger an OpenAI embedding call inside the engine, which
// adds 1-3s. If the engine is slow, Shopify will retry the webhook
// (up to 48h, exponential backoff). The engine's bootstrap-batch
// path is idempotent so retries are safe.

import type { ActionFunctionArgs } from "@remix-run/node";

import {
  forwardProductUpsertWebhook,
  lookupOrCreateTenant,
} from "../lib/engine.server";
import { logInfo, logError } from "../lib/logger.server";
import { authenticate } from "../shopify.server";

export const action = async ({ request }: ActionFunctionArgs) => {
  const { shop, topic, payload } = await authenticate.webhook(request);

  // Resolve the tenant for this shop. Idempotent — creates the row
  // if this is the very first webhook (shouldn't happen in practice
  // since install runs the bootstrap path first, but be defensive).
  let tenantId: string;
  try {
    const tenant = await lookupOrCreateTenant({ shopDomain: shop });
    tenantId = tenant.tenant_id;
  } catch (err) {
    logError("vibe_product_webhook_tenant_lookup_failed", {
      topic,
      shop,
      err: err instanceof Error ? err.message : String(err),
    });
    // Returning 500 makes Shopify retry the webhook with backoff.
    // Better than swallowing the event silently.
    return new Response("tenant lookup failed", { status: 500 });
  }

  try {
    const result = await forwardProductUpsertWebhook({
      tenantId,
      payload,
    });
    logInfo("vibe_product_webhook_upsert", {
      topic,
      shop,
      tenant_id: tenantId,
      shopify_product_id: result.shopify_product_id,
      created: result.created,
      updated: result.updated,
      failed: result.failed,
      available_for_sale: result.available_for_sale,
    });
  } catch (err) {
    logError("vibe_product_webhook_upsert_failed", {
      topic,
      shop,
      tenant_id: tenantId,
      err: err instanceof Error ? err.message : String(err),
    });
    // 500 → Shopify retries. The engine path is idempotent so the
    // retry will either succeed or land the same way again.
    return new Response("engine forward failed", { status: 500 });
  }

  return new Response();
};
