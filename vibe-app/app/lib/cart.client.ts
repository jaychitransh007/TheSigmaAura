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

/**
 * Where to send the customer after a successful cart add.
 *   - "cart"     — `/cart` review page (default; right for Buy outfit
 *                  where the customer wants to confirm the bundle).
 *   - "checkout" — straight to `/checkout` (right for Buy now — skip
 *                  the review step and start paying).
 *   - "none"     — stay on the current page (right for Add to Cart —
 *                  customer is still browsing).
 */
export type CartNavigation = "cart" | "checkout" | "none";

/** Extract the trailing numeric id from a Shopify gid string. */
export function gidToNumericId(gid: string): string {
  const tail = gid.split("/").pop() ?? "";
  return tail;
}

/** Detect placeholder variant ids from mock engine responses so the
 *  Buy buttons can fail with a clear message before hitting /cart/add.js. */
export function isMockVariantId(gid: string): boolean {
  return gid.includes("mock-");
}

export class CartUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CartUnavailableError";
  }
}

/**
 * Add one or more variants to the customer's Shopify cart. Optional
 * post-add navigation (`/cart`, `/checkout`, or stay-on-page).
 *
 * Uses Shopify's classic ajax cart at /cart/add.js with a JSON body
 * that supports multi-item adds in one call (saves N round-trips for
 * Buy Outfit).
 *
 * Throws `CartUnavailableError` when the inputs aren't backed by real
 * Shopify variant ids — the most common case is the catalog mapping
 * (B.8) hasn't run yet on the merchant's store, so the engine returns
 * items without `shopify_variant_ids`. Callers should surface the
 * message inline rather than retry.
 */
export async function addToCart(
  items: CartItem[],
  opts: { navigate?: CartNavigation } = {},
): Promise<void> {
  if (items.length === 0) {
    throw new CartUnavailableError(
      "Nothing's linked to checkout for this look yet — the storefront " +
        "catalog hasn't finished syncing. Try again in a moment.",
    );
  }

  // Bail out cleanly if anything looks like a mock id — saves a 404 to
  // /cart/add.js that would otherwise confuse the customer.
  for (const item of items) {
    if (isMockVariantId(item.variantId)) {
      throw new CartUnavailableError(
        "This piece isn't connected to the storefront catalog yet — " +
          "Add to Cart will work once the catalog mapping runs.",
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

  const navigation = opts.navigate ?? "cart";
  if (navigation === "cart") {
    window.location.href = "/cart";
  } else if (navigation === "checkout") {
    // Shopify routes /checkout through to the active cart's checkout
    // session — same path the cart-page "Checkout" button hits. Cart
    // state was just mutated; the redirect picks it up.
    window.location.href = "/checkout";
  }
  // navigation === "none" → caller stays on the chat page; success
  // feedback is the caller's responsibility (e.g. flash a label).
}
