// Resource route — wardrobe list + write operations.
//
// URL via App Proxy: thesigmavibe.shop/apps/vibe/api/wardrobe
//
// GET    list the customer's wardrobe (used by the conversation `+`
//        picker AND the Wardrobe page grid).
// POST   add a wardrobe piece (multipart: file + optional metadata).
// DELETE remove a wardrobe piece (form fields: wardrobeItemId).
//
// HMAC signature validated by authenticate.public.appProxy() on every
// branch. IDOR guard on the `shopify:` identity: anonymous UUIDs are
// unguessable per-browser ids, but the shopify-prefixed shape is
// enumerable from the storefront, so we compare it to the
// `logged_in_customer_id` that Shopify's App Proxy auto-appends and
// HMAC-signs onto the URL. The body is NEVER trusted for identity —
// Shopify only signs the URL params, so a body-supplied id would let a
// hostile client forge any customer id.

import type { ActionFunctionArgs, LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import {
  EngineError,
  deleteWardrobeItem,
  getWardrobeItems,
  saveWardrobeItem,
} from "../lib/engine.server";
import { authenticate } from "../shopify.server";

// Vercel Serverless / Edge Functions enforce a 4.5MB request body cap
// on Hobby (and lower than that on some routes) — bodies above the
// platform limit are rejected with HTTP 413 BEFORE this handler runs.
// We cap a hair under that so the error surfaces as our friendly JSON
// 400 from app code instead of an opaque platform-level 413. Phone
// photos routinely exceed 4MB; clients should compress / transcode
// HEIC → JPEG before posting (the conversation-side onboarding upload
// already does this via the heic-to library).
const MAX_UPLOAD_BYTES = 4 * 1024 * 1024;

function identityMismatch(url: URL, sessionId: string): boolean {
  if (!sessionId.startsWith("shopify:")) return false;
  // Only trust the signed App Proxy URL parameter — Shopify appends
  // `logged_in_customer_id` (and HMAC-signs the full URL) when a
  // Customer Account is signed in. Body fields are unsigned and would
  // be trivially forgeable.
  const expected = url.searchParams.get("logged_in_customer_id")?.trim() || "";
  return !expected || sessionId !== `shopify:${expected}`;
}

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

export const action = async ({ request }: ActionFunctionArgs) => {
  await authenticate.public.appProxy(request);

  if (request.method === "DELETE") {
    const form = await request.formData();
    const sessionId = String(form.get("sessionId") ?? "").trim();
    const wardrobeItemId = String(form.get("wardrobeItemId") ?? "").trim();
    if (!sessionId || !wardrobeItemId) {
      return json(
        { ok: false, error: "Missing sessionId or wardrobeItemId" },
        { status: 400 },
      );
    }
    if (identityMismatch(new URL(request.url), sessionId)) {
      return json({ ok: false, error: "Identity mismatch" }, { status: 403 });
    }
    try {
      await deleteWardrobeItem({ userId: sessionId, wardrobeItemId });
      return json({ ok: true });
    } catch (err) {
      if (err instanceof EngineError) {
        return json(
          { ok: false, error: err.message },
          { status: err.status || 502 },
        );
      }
      const message = err instanceof Error ? err.message : "Delete failed";
      return json({ ok: false, error: message }, { status: 500 });
    }
  }

  if (request.method !== "POST") {
    return json(
      { ok: false, error: `Method ${request.method} not supported` },
      { status: 405 },
    );
  }

  // POST — multipart add.
  const form = await request.formData();
  const sessionId = String(form.get("sessionId") ?? "").trim();
  const title = String(form.get("title") ?? "").trim();
  const garmentCategory = String(form.get("garmentCategory") ?? "").trim();
  const brand = String(form.get("brand") ?? "").trim();
  const file = form.get("file");

  if (!sessionId) {
    return json({ ok: false, error: "Missing sessionId" }, { status: 400 });
  }
  if (identityMismatch(new URL(request.url), sessionId)) {
    return json({ ok: false, error: "Identity mismatch" }, { status: 403 });
  }
  if (!(file instanceof Blob) || file.size === 0) {
    return json({ ok: false, error: "Missing or empty file" }, { status: 400 });
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return json(
      { ok: false, error: "Image must be under 4MB" },
      { status: 400 },
    );
  }
  const filename =
    file instanceof File && file.name ? file.name : "wardrobe.jpg";

  try {
    const item = await saveWardrobeItem({
      userId: sessionId,
      file,
      filename,
      title: title || undefined,
      garmentCategory: garmentCategory || undefined,
      brand: brand || undefined,
    });
    return json({ ok: true, item });
  } catch (err) {
    if (err instanceof EngineError) {
      return json(
        { ok: false, error: err.message },
        { status: err.status || 502 },
      );
    }
    const message = err instanceof Error ? err.message : "Upload failed";
    return json({ ok: false, error: message }, { status: 500 });
  }
};
