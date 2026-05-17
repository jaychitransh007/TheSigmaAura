// F.4 — products/delete webhook handler.
//
// Soft-delete only. Engine marks the row's available_for_sale=false
// + deleted_at=now() but keeps the catalog_enriched / embedding
// rows. Two reasons to keep them:
//
//   1. Vision-enrichment cost we've already paid stays paid. An
//      accidental delete (Shopify lets merchants un-delete within
//      30 days) can be revived via a subsequent products/create
//      with no LLM cost.
//   2. Order/attribution lookups against historical recommendations
//      need to be able to dereference the product_id even after the
//      merchant has removed the product from Shopify.

import type { ActionFunctionArgs } from "@remix-run/node";

import {
  forwardProductDeleteWebhook,
  lookupOrCreateTenant,
} from "../lib/engine.server";
import { logInfo, logError } from "../lib/logger.server";
import { authenticate } from "../shopify.server";

export const action = async ({ request }: ActionFunctionArgs) => {
  const { shop, topic, payload } = await authenticate.webhook(request);

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
    return new Response("tenant lookup failed", { status: 500 });
  }

  try {
    const result = await forwardProductDeleteWebhook({
      tenantId,
      payload,
    });
    logInfo("vibe_product_webhook_delete", {
      topic,
      shop,
      tenant_id: tenantId,
      shopify_product_id: result.shopify_product_id,
      deleted: result.deleted,
      reason: result.reason,
    });
  } catch (err) {
    logError("vibe_product_webhook_delete_failed", {
      topic,
      shop,
      tenant_id: tenantId,
      err: err instanceof Error ? err.message : String(err),
    });
    return new Response("engine forward failed", { status: 500 });
  }

  return new Response();
};
