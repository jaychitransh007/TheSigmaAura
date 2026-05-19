// Resource route — single-garment virtual try-on (Phase V).
//
// URL via App Proxy: thesigmavibe.shop/apps/vibe/api/tryon
// Method: POST (application/x-www-form-urlencoded or multipart)
//
// Form fields:
//   sessionId         — customer's localStorage session id (= engine user_id)
//   productImageUrl   — absolute URL of the garment image (Shopify CDN
//                       for storefront PDPs; engine-served URL for the
//                       Vibe Conversation outfit card)
//
// Returns:
//   200 { ok: true, dataUrl }            — base64 data URL of the
//                                          rendered try-on, ready to
//                                          drop into <img src="...">
//   400 { ok: false, error, reasonCode } — engine refused (e.g.
//                                          missing_person_image,
//                                          quality_gate_failed)
//   502 { ok: false, error }             — engine unreachable / bad
//                                          shape
//
// Surfaces calling this:
//   1. Storefront PDP modal (theme app extension block)
//      — opened from the "Virtual Try On" button on the merchant's
//        product page. Customer uploads body photo first (separate
//        request to /apps/vibe/api/onboarding/image), then this
//        endpoint renders the try-on.
//   2. Vibe Conversation outfit card (garment mode)
//      — clicking "Virtual Try On" above the Buy / Add to Cart row
//        fires this directly (customer's body photo is already on
//        file from in-chat onboarding).
//
// HMAC signature validated by authenticate.public.appProxy(). IDOR
// guard on the `shopify:` identity — see apps.vibe.api.wardrobe.tsx
// for the rationale.

import type { ActionFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import { identityMismatch } from "../lib/auth.server";
import { singleGarmentTryon } from "../lib/engine.server";
import { logError, logInfo, logWarn } from "../lib/logger.server";
import { authenticate } from "../shopify.server";

export const action = async ({ request }: ActionFunctionArgs) => {
  await authenticate.public.appProxy(request);

  if (request.method !== "POST") {
    return json(
      { ok: false, error: `Method ${request.method} not supported` },
      { status: 405 },
    );
  }

  const form = await request.formData();
  const sessionId = String(form.get("sessionId") ?? "").trim();
  const productImageUrl = String(form.get("productImageUrl") ?? "").trim();

  if (!sessionId) {
    return json({ ok: false, error: "Missing sessionId" }, { status: 400 });
  }
  if (!productImageUrl) {
    return json(
      { ok: false, error: "Missing productImageUrl" },
      { status: 400 },
    );
  }
  if (identityMismatch(new URL(request.url), sessionId)) {
    return json({ ok: false, error: "Identity mismatch" }, { status: 403 });
  }

  try {
    const result = await singleGarmentTryon({
      userId: sessionId,
      productImageUrl,
    });
    if (!result.ok) {
      // Engine refused — pass through so the client can surface the
      // graceful_policy_message (e.g. "Upload a full-body photo
      // first"). Status maps 1:1 to the engine's HTTP status so the
      // caller can branch on missing-person vs quality-gate failure.
      logWarn("vibe_tryon_outcome", {
        outcome:
          result.reason_code === "missing_person_image"
            ? "missing_person"
            : result.reason_code || "engine_refused",
        sessionId,
        productImageUrlHash: hashUrl(productImageUrl),
        status: result.status,
        error: result.error,
      });
      return json(
        {
          ok: false,
          error: result.error,
          reasonCode: result.reason_code,
        },
        { status: result.status },
      );
    }
    logInfo("vibe_tryon_outcome", {
      outcome: "rendered",
      sessionId,
      productImageUrlHash: hashUrl(productImageUrl),
    });
    return json({ ok: true, dataUrl: result.data_url });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Try-on failed";
    logError("vibe_tryon_outcome", {
      outcome: "exception",
      sessionId,
      productImageUrlHash: hashUrl(productImageUrl),
      error: message,
      stack: err instanceof Error ? err.stack : undefined,
    });
    return json({ ok: false, error: message }, { status: 500 });
  }
};

// Cheap djb2-style hash so logs carry a stable identifier per
// product image without leaking the full URL. The hash isn't
// crypto-grade — it just lets a future panel slice "% of try-ons
// succeed end-to-end" by product without bloating log volume.
function hashUrl(url: string): string {
  let hash = 5381;
  for (let i = 0; i < url.length; i += 1) {
    hash = ((hash << 5) + hash + url.charCodeAt(i)) | 0;
  }
  return (hash >>> 0).toString(16);
}
