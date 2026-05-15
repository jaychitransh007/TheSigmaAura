// Shopify storefront Cart API helper. Runs in the customer's browser
// (NOT the Remix server) — uses the customer's session cookie for the
// shop to authenticate the cart write.
//
// We're on thesigmavibe.shop/apps/vibe/* via App Proxy, so fetches to
// "/cart/add.js" are same-origin and Shopify's storefront cookie is
// attached automatically.
//
// Variant id format conversion: catalog_enriched stores Shopify gids
// (gid://shopify/ProductVariant/12345678). The Ajax cart endpoint
// /cart/add.js wants the numeric id. We strip the prefix on the fly.

export type CartItem = {
  /** Shopify variant gid (gid://shopify/ProductVariant/12345). */
  variantId: string;
  /** Default 1. */
  quantity?: number;
};

/** Extract the trailing numeric id from a Shopify gid string. */
export function gidToNumericId(gid: string): string {
  const tail = gid.split("/").pop() ?? "";
  return tail;
}

/** Detect placeholder variant ids from mock engine responses so the
 *  Buy buttons can disable themselves before trying to call /cart/add.js. */
export function isMockVariantId(gid: string): boolean {
  return gid.includes("mock-");
}

/**
 * Add one or more variants to the customer's Shopify cart, then
 * navigate to /cart. Throws on failure so the caller can surface a
 * toast/error inline.
 *
 * Uses Shopify's classic ajax cart at /cart/add.js with a JSON body
 * that supports multi-item adds in one call (saves N round-trips for
 * Buy Outfit).
 */
export async function addToCart(items: CartItem[]): Promise<void> {
  if (items.length === 0) return;

  // Bail out cleanly if anything looks like a mock id — saves a 404 to
  // /cart/add.js that would otherwise confuse the customer.
  for (const item of items) {
    if (isMockVariantId(item.variantId)) {
      throw new Error(
        "Real cart is wired but the engine is still in mock mode. " +
          "Set ENGINE_API_URL on Vercel to point at the deployed engine, " +
          "then redeploy.",
      );
    }
  }

  const body = {
    items: items.map((it) => ({
      id: gidToNumericId(it.variantId),
      quantity: it.quantity ?? 1,
    })),
  };

  const resp = await fetch("/cart/add.js", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(body),
    credentials: "same-origin",
  });

  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`Add to cart failed (${resp.status}): ${text.slice(0, 200)}`);
  }

  // On success, navigate to the cart. Shopify renders the cart in the
  // storefront theme; from there the customer hits checkout.
  window.location.href = "/cart";
}
