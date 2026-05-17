// Resource route — current onboarding-analysis status for a customer.
//
// URL via App Proxy: thesigmavibe.shop/apps/vibe/api/onboarding/analysis-status?sessionId=<id>
// Method: GET
//
// Returns: { ok: true, status: "in_progress" | "completed" | "failed" | "not_started", error_message: string }
//
// Polled by the conversation page after the customer completes their
// onboarding photo uploads, so we can flip the "Analyzing your style…"
// stage indicator off and emit the follow-up prompt when the engine
// finishes profiling. Signed via App Proxy + same IDOR guard as the
// wardrobe / wishlist routes.

import type { LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import { EngineError, getAnalysisStatus } from "../lib/engine.server";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.public.appProxy(request);

  const url = new URL(request.url);
  const sessionId = url.searchParams.get("sessionId")?.trim() ?? "";
  if (!sessionId) {
    return json({ ok: false, error: "Missing sessionId" }, { status: 400 });
  }

  // IDOR guard for `shopify:` identities — anonymous UUIDs are
  // unguessable per-browser, but the shopify-prefixed form is
  // enumerable from the storefront. Mirror wardrobe/wishlist routes.
  if (sessionId.startsWith("shopify:")) {
    const expectedId = url.searchParams.get("logged_in_customer_id")?.trim();
    if (!expectedId || sessionId !== `shopify:${expectedId}`) {
      return json({ ok: false, error: "Identity mismatch" }, { status: 403 });
    }
  }

  try {
    const status = await getAnalysisStatus(sessionId);
    if (!status) {
      // Engine unreachable / 4xx — treat as still working so the
      // client keeps polling rather than declaring failure.
      return json({ ok: true, status: "in_progress", error_message: "" });
    }
    return json({
      ok: true,
      status: status.status,
      error_message: status.error_message,
    });
  } catch (err) {
    if (err instanceof EngineError) {
      return json(
        { ok: false, error: err.message },
        { status: err.status || 502 },
      );
    }
    const message = err instanceof Error ? err.message : "Status fetch failed";
    return json({ ok: false, error: message }, { status: 500 });
  }
};
