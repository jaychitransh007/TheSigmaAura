// Resource route — Looks page data.
//
// URL via App Proxy: thesigmavibe.shop/apps/vibe/api/looks
//
// GET    list saved looks + recent past results in one round-trip.
//        Querystring: sessionId, optional logged_in_customer_id.
// DELETE remove a saved look. Form fields: sessionId, savedLookId,
//        optional loggedInCustomerId.
//
// HMAC signature validated by authenticate.public.appProxy(). IDOR
// guard on the `shopify:` identity — see apps.vibe.api.wardrobe.tsx
// for the rationale.

import type { ActionFunctionArgs, LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import {
  EngineError,
  deleteSavedLook,
  getPastLooks,
  getSavedLooks,
  type PastLookSummary,
  type SavedLookSummary,
} from "../lib/engine.server";
import { authenticate } from "../shopify.server";

function identityMismatch(url: URL, sessionId: string): boolean {
  if (!sessionId.startsWith("shopify:")) return false;
  // Only trust the signed App Proxy URL parameter — Shopify appends
  // `logged_in_customer_id` (and HMAC-signs the full URL) when a
  // Customer Account is signed in. Body fields are unsigned and would
  // be trivially forgeable, so they can't be a fallback.
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

  // Run both fetches in parallel — saved + past are independent and
  // each takes its own engine round-trip. Promise.allSettled keeps a
  // failure in one from blocking the other.
  const [saved, past] = await Promise.allSettled([
    getSavedLooks(sessionId),
    getPastLooks(sessionId),
  ]);

  const savedLooks: SavedLookSummary[] =
    saved.status === "fulfilled" ? saved.value : [];
  const pastLooks: PastLookSummary[] =
    past.status === "fulfilled" ? past.value : [];

  const errors: string[] = [];
  if (saved.status === "rejected") {
    errors.push(messageOf(saved.reason, "saved looks"));
  }
  if (past.status === "rejected") {
    errors.push(messageOf(past.reason, "past looks"));
  }

  return json({
    ok: true,
    savedLooks,
    pastLooks,
    errors,
  });
};

export const action = async ({ request }: ActionFunctionArgs) => {
  await authenticate.public.appProxy(request);

  if (request.method !== "DELETE") {
    return json(
      { ok: false, error: `Method ${request.method} not supported` },
      { status: 405 },
    );
  }

  const form = await request.formData();
  const sessionId = String(form.get("sessionId") ?? "").trim();
  const savedLookId = String(form.get("savedLookId") ?? "").trim();

  if (!sessionId || !savedLookId) {
    return json(
      { ok: false, error: "Missing sessionId or savedLookId" },
      { status: 400 },
    );
  }
  if (identityMismatch(new URL(request.url), sessionId)) {
    return json({ ok: false, error: "Identity mismatch" }, { status: 403 });
  }

  try {
    await deleteSavedLook({ userId: sessionId, savedLookId });
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
};

function messageOf(reason: unknown, label: string): string {
  if (reason instanceof EngineError) return `${label}: ${reason.message}`;
  if (reason instanceof Error) return `${label}: ${reason.message}`;
  return `${label}: failed`;
}
