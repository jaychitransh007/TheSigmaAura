// Mandatory GDPR / Shopify privacy-compliance webhook.
//
// Shopify fires `shop/redact` 48 hours after a merchant uninstalls
// Vibe AND has not reinstalled within that window. We have 48 hours
// from receipt to delete the merchant's shop data.
//
// What "shop data" means for Vibe today:
//   - The Prisma `Session` row(s) keyed on shop (already deleted
//     synchronously by `webhooks.app.uninstalled.tsx` at uninstall
//     time, but we re-run it here defensively in case the uninstall
//     handler missed a row).
//   - Engine-side data: today the engine is single-tenant (Phase C
//     multi-tenancy is deferred), so it doesn't track *which* shop a
//     customer came from. Shop-level erasure of engine data is not
//     possible until tenant_id propagation lands. The webhook still
//     acknowledges (Shopify requires it) and logs the request so the
//     manual operator can decide whether to wipe data anyway.
//
// Returns 200 within Shopify's 5s budget regardless of cleanup
// outcome — partial success here is still a valid response per
// Shopify's compliance docs.

import type { ActionFunctionArgs } from "@remix-run/node";

import db from "../db.server";
import { logError, logInfo } from "../lib/logger.server";
import { authenticate } from "../shopify.server";

type ShopRedactPayload = {
  shop_id?: number;
  shop_domain?: string;
};

export const action = async ({ request }: ActionFunctionArgs) => {
  const { shop, topic, payload } = await authenticate.webhook(request);

  const body = (payload ?? {}) as ShopRedactPayload;

  let sessionsDeleted = 0;
  try {
    // Defensive: app/uninstalled already runs delete_many, but Shopify
    // can fire shop/redact independent of an uninstall webhook arriving
    // (e.g. webhook delivery failure on the earlier event). Re-running
    // is idempotent.
    const result = await db.session.deleteMany({ where: { shop } });
    sessionsDeleted = result.count;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    logError("vibe_gdpr_shop_redact_session_delete_failed", {
      shop,
      error: message,
    });
  }

  logInfo("vibe_gdpr_shop_redact", {
    topic,
    shop,
    shop_id: body.shop_id ?? null,
    shop_domain: body.shop_domain ?? null,
    vibe_sessions_deleted: sessionsDeleted,
    // Engine-side cleanup status flagged for the manual operator —
    // shop-level erasure isn't possible until Phase C ships tenant_id
    // tracking on engine tables. Until then we log + acknowledge.
    engine_data_action: "pending_phase_c_tenant_id",
  });

  return new Response();
};
