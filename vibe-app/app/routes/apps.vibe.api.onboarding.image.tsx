// Resource route — onboarding photo upload.
//
// URL via App Proxy: thesigmavibe.shop/apps/vibe/api/onboarding/image
// Method: POST (multipart/form-data)
//
// Form fields:
//   sessionId  — customer's localStorage session id (= engine user_id)
//   category   — "full_body" | "headshot"
//   file       — the image blob
//
// Forwards to the engine's POST /v1/onboarding/images/{category}.
// HMAC signature validated by authenticate.public.appProxy().

import type { ActionFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import {
  EngineError,
  uploadOnboardingImage,
  type OnboardingImageCategory,
} from "../lib/engine.server";
import { logError, logInfo, logWarn } from "../lib/logger.server";
import { authenticate } from "../shopify.server";

const ALLOWED_CATEGORIES: ReadonlySet<OnboardingImageCategory> = new Set([
  "full_body",
  "headshot",
]);

export const action = async ({ request }: ActionFunctionArgs) => {
  await authenticate.public.appProxy(request);

  // Multipart parsing happens via the standard FormData API — Remix's
  // request.formData() handles it. We don't write the file to disk;
  // the Blob is forwarded straight to the engine.
  const form = await request.formData();
  const sessionId = String(form.get("sessionId") ?? "").trim();
  const category = String(form.get("category") ?? "").trim() as OnboardingImageCategory;
  const file = form.get("file");

  if (!sessionId) {
    return json({ ok: false, error: "Missing sessionId" }, { status: 400 });
  }
  if (!ALLOWED_CATEGORIES.has(category)) {
    return json(
      { ok: false, error: `Invalid category: ${category}` },
      { status: 400 },
    );
  }
  if (!(file instanceof Blob) || file.size === 0) {
    return json({ ok: false, error: "Missing or empty file" }, { status: 400 });
  }
  // Engine caps at 10MB. Mirror the limit here so we fail fast without
  // round-tripping a useless upload.
  if (file.size > 10 * 1024 * 1024) {
    return json(
      { ok: false, error: "Image must be under 10MB" },
      { status: 400 },
    );
  }

  // Preserve a sensible filename — `File` (which Blob may actually be)
  // carries one; fall back when the client only sent a generic Blob.
  const filename =
    file instanceof File && file.name ? file.name : `${category}.jpg`;

  try {
    const result = await uploadOnboardingImage({
      userId: sessionId,
      category,
      file,
      filename,
    });
    logInfo("vibe_onboarding_stage_reach", {
      stage: "photo_uploaded",
      category,
      sessionId,
    });
    return json({ ok: true, ...result });
  } catch (err) {
    // Always return JSON. Re-throwing here would let Vercel's default
    // error page (HTML) propagate to the client, where the photo-card
    // tries to parse the body as JSON and the customer sees
    // "Unexpected token '<'". Catch-all returns a friendly error
    // string instead so the card's error state can render.
    if (err instanceof EngineError) {
      logWarn("vibe_onboarding_endpoint_failed", {
        endpoint: "image",
        category,
        sessionId,
        status: err.status || 502,
        error: err.message,
      });
      return json(
        { ok: false, error: err.message },
        { status: err.status || 502 },
      );
    }
    const message = err instanceof Error ? err.message : "Upload failed";
    // Unexpected 500 path: route to stderr via logError so error
    // monitoring picks it up. Include the stack trace because the
    // catch-all swallows the exception (we return JSON instead of
    // re-raising to avoid Vercel's HTML error page) — without the
    // trace, ops can't tell what threw.
    logError("vibe_onboarding_endpoint_failed", {
      endpoint: "image",
      category,
      sessionId,
      status: 500,
      error: message,
      stack: err instanceof Error ? err.stack : undefined,
    });
    return json({ ok: false, error: message }, { status: 500 });
  }
};
