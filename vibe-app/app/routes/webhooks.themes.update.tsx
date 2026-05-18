// themes/update webhook — fires when the merchant publishes a new
// theme or changes settings on the current theme. Triggers a re-read
// of the theme settings so Vibe pages stay aligned with the merchant's
// host store.
//
// The handler must return 200 within Shopify's 5s budget. The actual
// engine PATCH runs after we resolve the tenant; total network round-
// trip is well under the budget for a normal install. Failure paths
// (Shopify GraphQL transient, engine unreachable) are logged but not
// retried inline — Shopify's webhook delivery retry covers them.

import type { ActionFunctionArgs } from "@remix-run/node";

import {
  EngineError,
  lookupOrCreateTenant,
  patchTenantThemeOverrides,
} from "../lib/engine.server";
import { logInfo, logError } from "../lib/logger.server";
import { authenticate } from "../shopify.server";
import { readMerchantThemeOverrides } from "../lib/theme-settings.server";

export const action = async ({ request }: ActionFunctionArgs) => {
  const { shop, topic, admin } = await authenticate.webhook(request);

  if (!admin) {
    // No admin client = no offline token for this shop. Should not
    // happen for active installs, but defensively log and 200 anyway
    // so Shopify doesn't retry forever.
    logError("vibe_themes_update_no_admin", { shop, topic });
    return new Response();
  }

  let tenantId: string;
  try {
    const tenant = await lookupOrCreateTenant({ shopDomain: shop });
    tenantId = tenant.tenant_id;
  } catch (err) {
    logError("vibe_themes_update_tenant_lookup_failed", {
      shop, topic,
      err: err instanceof Error ? err.message : String(err),
    });
    return new Response("tenant lookup failed", { status: 500 });
  }

  let overrides;
  try {
    overrides = await readMerchantThemeOverrides(admin);
  } catch (err) {
    logError("vibe_themes_update_read_failed", {
      shop, topic, tenant_id: tenantId,
      err: err instanceof Error ? err.message : String(err),
    });
    return new Response();  // 200 — graceful fail; nothing else to retry
  }

  try {
    await patchTenantThemeOverrides({ tenantId, overrides });
    logInfo("vibe_themes_update_applied", {
      shop, topic, tenant_id: tenantId,
      font_body: overrides.font_body || "(empty)",
      color_primary: overrides.color_primary || "(empty)",
    });
  } catch (err) {
    logError("vibe_themes_update_engine_patch_failed", {
      shop, topic, tenant_id: tenantId,
      err: err instanceof EngineError ? err.message : String(err),
    });
    return new Response("engine patch failed", { status: 500 });
  }

  return new Response();
};
