// Resource route — proxies the engine's local-image serving endpoint.
//
// URL via App Proxy: thesigmavibe.shop/apps/vibe/api/tryon-image?path=...
// Method: GET
//
// The engine returns try-on (and wardrobe) image URLs as relative paths
// like ``/v1/onboarding/images/local?path=data/tryon/images/<hash>.jpg``.
// Those paths only resolve against the engine origin (Fly.io); the
// storefront browser sees them rooted at thesigmavibe.shop and 404s.
//
// engine.server.ts's normalizeOutfit rewrites every such URL to point at
// this route. We re-fetch from the engine server-side and pipe the bytes
// back to the browser. Keeps the engine origin hidden (no need to expose
// ENGINE_API_URL to the client) and avoids any CORS surface.
//
// HMAC signature validated by authenticate.public.appProxy().

import type { LoaderFunctionArgs } from "@remix-run/node";

import { authenticate } from "../shopify.server";

const ENGINE_API_URL = process.env.ENGINE_API_URL?.trim() ?? "";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.public.appProxy(request);

  if (!ENGINE_API_URL) {
    return new Response("Engine not configured", { status: 502 });
  }

  const url = new URL(request.url);
  const path = url.searchParams.get("path") ?? "";
  if (!path) {
    return new Response("Missing path", { status: 400 });
  }

  // The engine's _resolve_local_image_file allowlists data/onboarding/images
  // and data/tryon/images — anything else 404s upstream. We don't need to
  // re-validate here; just forward.
  const upstream = `${ENGINE_API_URL}/v1/onboarding/images/local?path=${encodeURIComponent(path)}`;

  let resp: Response;
  try {
    resp = await fetch(upstream, { signal: AbortSignal.timeout(10_000) });
  } catch (e) {
    const reason = e instanceof Error ? e.message : String(e);
    return new Response(`Engine image fetch failed: ${reason}`, { status: 502 });
  }
  if (!resp.ok || !resp.body) {
    return new Response("Image unavailable", { status: resp.status || 502 });
  }

  // Pass through the body with cache-friendly headers. Try-on images are
  // content-addressed (filename = hash of inputs) so they're effectively
  // immutable; let the browser cache aggressively.
  return new Response(resp.body, {
    status: 200,
    headers: {
      "content-type": resp.headers.get("content-type") ?? "image/jpeg",
      "cache-control": "private, max-age=86400",
    },
  });
};
