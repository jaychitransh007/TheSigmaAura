// Resource route — Looks page data.
//
// URL via App Proxy: thesigmavibe.shop/apps/vibe/api/looks
//
// GET    return the customer's styling history grouped by theme.
//        Querystring: sessionId, optional logged_in_customer_id.
//        Shape: { ok: true, themes: IntentHistoryTheme[] }
//
// Mirrors the legacy `platform_core/ui.py` § Outfits tab. The customer
// sees one PDP carousel per theme (e.g. "Office & Professional",
// "Weekend & Everyday"); per-slide context (the user's original prompt)
// rides on every ThemedOutfit. Saved-looks + try-on gallery are no
// longer surfaced here — the screen is purely the recommendation
// history grouped by occasion, matching the legacy Aura Outfits page.
//
// HMAC signature validated by authenticate.public.appProxy(). IDOR
// guard on the `shopify:` identity — see apps.vibe.api.wardrobe.tsx
// for the rationale.

import type { LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import { identityMismatch } from "../lib/auth.server";
import {
  EngineError,
  getIntentHistory,
  type IntentHistoryTheme,
} from "../lib/engine.server";
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
    const themes: IntentHistoryTheme[] = await getIntentHistory(sessionId);
    return json({ ok: true, themes });
  } catch (err) {
    if (err instanceof EngineError) {
      return json(
        { ok: false, error: err.message },
        { status: err.status || 502 },
      );
    }
    const message = err instanceof Error ? err.message : "Failed to load looks";
    return json({ ok: false, error: message }, { status: 500 });
  }
};
