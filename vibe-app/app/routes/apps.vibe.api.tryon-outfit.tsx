// Resource route — outfit-level virtual try-on (Phase V).
//
// URL via App Proxy: thesigmavibe.shop/apps/vibe/api/tryon-outfit
// Method: POST (application/x-www-form-urlencoded)
//
// Form fields:
//   sessionId  — customer's localStorage session id (= engine user_id)
//   garments   — JSON-encoded array of {role?, image_url} objects
//                (FormData-friendly so the browser can post without
//                pulling in fetch JSON helpers).
//
// Returns:
//   200 { ok: true, dataUrl }            — base64 data URL of the
//                                          rendered outfit try-on
//   400 { ok: false, error, reasonCode } — engine refused
//   502 { ok: false, error }             — engine unreachable
//
// Companion to /apps/vibe/api/tryon. The single-garment route powers
// the storefront PDP modal + the in-chat garment-mode card; this
// route powers the in-chat outfit-mode card so the customer can
// retrigger the multi-garment composite when the engine's auto-
// render didn't fire (or they just want a fresh render).

import type { ActionFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import { identityMismatch } from "../lib/auth.server";
import { outfitTryon, type OutfitTryonGarment } from "../lib/engine.server";
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
  const garmentsRaw = String(form.get("garments") ?? "").trim();

  if (!sessionId) {
    return json({ ok: false, error: "Missing sessionId" }, { status: 400 });
  }
  if (!garmentsRaw) {
    return json({ ok: false, error: "Missing garments" }, { status: 400 });
  }
  if (identityMismatch(new URL(request.url), sessionId)) {
    return json({ ok: false, error: "Identity mismatch" }, { status: 403 });
  }

  // Parse the garments JSON. Bad shape → 400 with a friendly error,
  // not a 500 — the client can correct and retry without us blowing
  // up Vercel's error budget.
  let garments: OutfitTryonGarment[];
  try {
    const parsed = JSON.parse(garmentsRaw) as unknown;
    if (!Array.isArray(parsed)) throw new Error("garments must be a JSON array");
    garments = parsed
      .map((g) => {
        if (typeof g !== "object" || g === null) return null;
        const obj = g as { role?: unknown; image_url?: unknown };
        const image_url = typeof obj.image_url === "string" ? obj.image_url.trim() : "";
        if (!image_url) return null;
        return {
          role: typeof obj.role === "string" ? obj.role : undefined,
          image_url,
        } satisfies OutfitTryonGarment;
      })
      .filter((g): g is OutfitTryonGarment => g !== null);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Invalid garments JSON";
    return json({ ok: false, error: message }, { status: 400 });
  }

  if (garments.length === 0) {
    return json({ ok: false, error: "No garments to render" }, { status: 400 });
  }

  try {
    const result = await outfitTryon({
      userId: sessionId,
      garments,
    });
    if (!result.ok) {
      logWarn("vibe_tryon_outcome", {
        outcome:
          result.reason_code === "missing_person_image"
            ? "missing_person"
            : result.reason_code || "engine_refused",
        surface: "outfit",
        sessionId,
        garmentCount: garments.length,
        garmentUrlHashes: garments.map((g) => hashUrl(g.image_url)),
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
      surface: "outfit",
      sessionId,
      garmentCount: garments.length,
      garmentUrlHashes: garments.map((g) => hashUrl(g.image_url)),
    });
    return json({ ok: true, dataUrl: result.data_url });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Try-on failed";
    logError("vibe_tryon_outcome", {
      outcome: "exception",
      surface: "outfit",
      sessionId,
      garmentCount: garments.length,
      error: message,
      stack: err instanceof Error ? err.stack : undefined,
    });
    return json({ ok: false, error: message }, { status: 500 });
  }
};

// Same djb2-style hash as the single-garment route — stable
// identifier per product image without leaking the full URL.
function hashUrl(url: string): string {
  let hash = 5381;
  for (let i = 0; i < url.length; i += 1) {
    hash = ((hash << 5) + hash + url.charCodeAt(i)) | 0;
  }
  return (hash >>> 0).toString(16);
}
