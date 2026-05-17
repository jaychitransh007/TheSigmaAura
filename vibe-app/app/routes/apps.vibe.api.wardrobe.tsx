// Resource route — list the customer's wardrobe for the + picker.
//
// URL via App Proxy: thesigmavibe.shop/apps/vibe/api/wardrobe?sessionId=<id>
// Method: GET
//
// Returns: { ok: true, items: WardrobeItem[] } where each item carries
// id + title + image_url + a few enrichment hints the picker grid can
// use to render a label.
//
// HMAC signature validated by authenticate.public.appProxy().

import type { LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import { EngineError, getWardrobeItems } from "../lib/engine.server";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.public.appProxy(request);

  const url = new URL(request.url);
  const sessionId = url.searchParams.get("sessionId")?.trim() ?? "";
  if (!sessionId) {
    return json({ ok: false, error: "Missing sessionId" }, { status: 400 });
  }

  try {
    const items = await getWardrobeItems(sessionId);
    return json({ ok: true, items });
  } catch (err) {
    if (err instanceof EngineError) {
      return json(
        { ok: false, error: err.message },
        { status: err.status || 502 },
      );
    }
    const message = err instanceof Error ? err.message : "Wardrobe fetch failed";
    return json({ ok: false, error: message }, { status: 500 });
  }
};
