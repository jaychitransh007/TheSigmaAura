// Resource route — Looks page data.
//
// URL via App Proxy: thesigmavibe.shop/apps/vibe/api/looks
//
// GET    return the customer's styling history grouped by theme.
//        Querystring: sessionId, optional logged_in_customer_id.
//        Shape: { ok: true, themes: IntentHistoryTheme[] }
//
// Mirrors the legacy `platform_core/ui.py` § Outfits tab. The customer
// sees one PDP carousel per theme (e.g. "Office & Professional",
// "Weekend & Everyday"); per-slide context (the user's original prompt)
// rides on every ThemedOutfit. Saved-looks + try-on gallery are no
// longer surfaced here — the screen is purely the recommendation
// history grouped by occasion, matching the legacy Aura Outfits page.
//
// HMAC signature validated by authenticate.public.appProxy(). IDOR
// guard on the `shopify:` identity — see apps.vibe.api.wardrobe.tsx
// for the rationale.

import type { LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import { identityMismatch } from "../lib/auth.server";
import {
  EngineError,
  getIntentHistory,
  getOnboardingStatus,
  type IntentHistoryTheme,
} from "../lib/engine.server";
import {
  fetchShopifyBodyHtmlBatch,
  shopifyNumericIdFromGid,
} from "../lib/shopify-body-html.server";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.public.appProxy(request);

  const url = new URL(request.url);
  const sessionId = url.searchParams.get("sessionId")?.trim() ?? "";
  if (!sessionId) {
    return json({ ok: false, error: "Missing sessionId" }, { status: 400 });
  }
  if (identityMismatch(url, sessionId)) {
    return json({ ok: false, error: "Identity mismatch" }, { status: 403 });
  }
  const shopDomain = url.searchParams.get("shop")?.trim() ?? "";

  try {
    const [themes, onboardingStatus]: [
      IntentHistoryTheme[],
      Awaited<ReturnType<typeof getOnboardingStatus>>,
    ] = await Promise.all([
      getIntentHistory(sessionId),
      getOnboardingStatus(sessionId).catch(() => null),
    ]);
    // Hydrate every item's catalog_description with the live
    // Shopify body_html. Same wipe-then-set as the poll route +
    // seed-product loader, so Looks cards render the same store
    // HTML the Vibe Conversation cards do.
    if (shopDomain && themes.length > 0) {
      await hydrateLooksDescriptions(shopDomain, themes);
    }
    // Tell the client whether this customer has a full_body photo
    // on file with the engine. Powers the OutfitCard auto-fire
    // safety net for any historical outfit whose tryon_image_url
    // wasn't persisted at original turn time (rare but possible —
    // flag off at the time, quality gate blocked, etc.).
    const hasBodyPhoto = Boolean(
      onboardingStatus && onboardingStatus !== null && onboardingStatus !== undefined &&
        onboardingStatus.images_uploaded?.includes("full_body"),
    );
    return json({ ok: true, themes, hasBodyPhoto });
  } catch (err) {
    if (err instanceof EngineError) {
      return json(
        { ok: false, error: err.message },
        { status: err.status || 502 },
      );
    }
    const message = err instanceof Error ? err.message : "Failed to load looks";
    return json({ ok: false, error: message }, { status: 500 });
  }
};

async function hydrateLooksDescriptions(
  shopDomain: string,
  themes: IntentHistoryTheme[],
): Promise<void> {
  const itemsToHydrate: Array<{
    item: { catalog_description?: string; shopify_product_id?: string };
    numericId: string;
  }> = [];
  for (const theme of themes) {
    for (const outfit of theme.outfits) {
      for (const item of outfit.items) {
        // Wipe whatever the engine wrote — Shopify body_html is
        // the single source of truth for the displayed description.
        item.catalog_description = "";
        const numericId = shopifyNumericIdFromGid(item.shopify_product_id ?? "");
        if (!numericId) continue;
        itemsToHydrate.push({ item, numericId });
      }
    }
  }
  if (itemsToHydrate.length === 0) return;
  const bodyHtmlByNumericId = await fetchShopifyBodyHtmlBatch({
    shopDomain,
    numericProductIds: itemsToHydrate.map((entry) => entry.numericId),
  });
  if (bodyHtmlByNumericId.size === 0) return;
  for (const { item, numericId } of itemsToHydrate) {
    const html = bodyHtmlByNumericId.get(numericId);
    if (html) item.catalog_description = html;
  }
}
