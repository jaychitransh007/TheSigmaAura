// Resource route — no React component, just a GET loader returning
// JSON. Client-side code on /apps/vibe/style polls this every second
// while a turn is running.
//
// URL after Shopify App Proxy: thesigmavibe.shop/apps/vibe/api/poll
//
// Query params:
//   conv  — conversation id
//   job   — turn job id
//
// Returns the engine's status payload as JSON. HMAC signature on the
// request is validated by authenticate.public.appProxy() — unsigned
// requests get 401.
//
// On terminal status with a result payload, we additionally hydrate
// each item's `catalog_description` with the live Shopify `body_html`
// (single batched Admin REST call per turn). This gives the Vibe
// PDP card the same clean HTML format the storefront product page
// renders — see lib/shopify-body-html.server.ts for the rationale
// (the engine's catalog_enriched.description carries the pre-import
// serialized blob; Shopify's body_html is the cleaned, structured
// version build_shopify_csv.py wrote at store setup).

import type { LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import { pollTurn, type Outfit, type OutfitItem } from "../lib/engine.server";
import {
  fetchShopifyBodyHtmlBatch,
  shopifyNumericIdFromGid,
} from "../lib/shopify-body-html.server";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.public.appProxy(request);

  const url = new URL(request.url);
  const conversationId = url.searchParams.get("conv");
  const jobId = url.searchParams.get("job");

  if (!conversationId || !jobId) {
    return json({ error: "Missing conv or job param" }, { status: 400 });
  }

  const status = await pollTurn({ conversationId, jobId });

  // Hydrate body_html when the turn has terminal outfits in the
  // result. Done in the poll route (not the action) because the
  // turn job may complete on any one of the poll requests — the
  // action only kicks the job off.
  //
  // shopDomain comes off the signed App Proxy params. Without it
  // we can't authenticate against Shopify's Admin API; we
  // gracefully return the engine's response untouched.
  const shopDomain = url.searchParams.get("shop")?.trim() ?? "";
  if (
    shopDomain &&
    status.status === "completed" &&
    status.result &&
    Array.isArray(status.result.outfits) &&
    status.result.outfits.length > 0
  ) {
    await hydrateDescriptions(shopDomain, status.result.outfits);
  }

  return json(status);
};

async function hydrateDescriptions(
  shopDomain: string,
  outfits: Outfit[],
): Promise<void> {
  // Walk every item across every outfit, collect unique Shopify
  // numeric product ids (extracted from the gid stored in
  // shopify_product_id). Items without a Shopify mapping (the
  // ~1,200 unmapped TheSigmaVibe rows) get skipped — their
  // catalog_description stays as the engine emitted it.
  const itemsToHydrate: Array<{ item: OutfitItem; numericId: string }> = [];
  for (const outfit of outfits) {
    for (const item of outfit.items ?? []) {
      const numericId = shopifyNumericIdFromGid(item.shopify_product_id ?? "");
      if (!numericId) continue;
      itemsToHydrate.push({ item, numericId });
    }
  }
  if (itemsToHydrate.length === 0) return;

  const numericIds = itemsToHydrate.map((entry) => entry.numericId);
  const bodyHtmlByNumericId = await fetchShopifyBodyHtmlBatch({
    shopDomain,
    numericProductIds: numericIds,
  });
  if (bodyHtmlByNumericId.size === 0) return;

  // Stamp body_html onto catalog_description in place. GarmentDetail
  // (the per-item PDP rendering on the client) renders this field
  // as trusted HTML now — see outfit-card.tsx for the
  // dangerouslySetInnerHTML branch.
  for (const { item, numericId } of itemsToHydrate) {
    const html = bodyHtmlByNumericId.get(numericId);
    if (html) {
      item.catalog_description = html;
    }
  }
}
