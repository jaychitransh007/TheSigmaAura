// Resource route — list the customer's wishlist for the + picker.
//
// URL via App Proxy: thesigmavibe.shop/apps/vibe/api/wishlist?sessionId=<id>
// Method: GET
//
// Returns: { ok: true, items: WishlistItem[] } where each item carries
// product_id + title + image_url + brand + price.
//
// HMAC signature validated by authenticate.public.appProxy().

import type { LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import { identityMismatch } from "../lib/auth.server";
import { EngineError, getWishlistItems } from "../lib/engine.server";
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

  try {
    const items = await getWishlistItems(sessionId);
    return json({ ok: true, items });
  } catch (err) {
    if (err instanceof EngineError) {
      return json(
        { ok: false, error: err.message },
        { status: err.status || 502 },
      );
    }
    const message = err instanceof Error ? err.message : "Wishlist fetch failed";
    return json({ ok: false, error: message }, { status: 500 });
  }
};
