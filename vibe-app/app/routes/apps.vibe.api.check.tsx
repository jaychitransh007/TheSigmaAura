// Resource route — Outfit Check turn dispatcher.
//
// URL via App Proxy: thesigmavibe.shop/apps/vibe/api/check
//
// POST  resolve conversation if needed, kick off a turn with the
//       customer's outfit photo, return the job id. The Outfit Check
//       page polls /apps/vibe/api/poll for the result (same poll
//       endpoint the conversation page uses).
//
// Why a separate route from the conversation `op=turn` action:
//   - Pre-canned message ("Honest feedback…") locked server-side so
//     the client can't drift away from the outfit-check phrasing.
//   - No multi-turn message-history state to manage — outfit check is
//     single-shot. The action returns just the job id; rendering the
//     result is the page's job via the existing poll route.
//
// Identity: localStorage session id sent in the body. IDOR-safe for
// shopify:{id} sessions via the same signed-URL check used by the
// wardrobe/looks routes.

import type { ActionFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import {
  EngineError,
  resolveConversation,
  startTurn,
} from "../lib/engine.server";
import { authenticate } from "../shopify.server";

// Same pairing-trigger suffix the conversation page appends whenever
// an attachment is present. The engine's planner uses this to route
// to PAIRING_REQUEST so the architect/composer produce alternative
// outfits alongside the assistant's commentary on the photo.
const PAIRING_TRIGGER = " Build an outfit around this attached piece.";

// Pre-canned outfit-check prompt. Phrased to coax stylist commentary
// in the assistant_message (the headline output) AND alternatives in
// the outfit cards (secondary).
const CHECK_MESSAGE =
  "Give me your honest take on this outfit. What's working, what isn't, " +
  "and what would you change?";

function identityMismatch(url: URL, sessionId: string): boolean {
  if (!sessionId.startsWith("shopify:")) return false;
  // Only trust the signed App Proxy URL parameter; body fields are
  // unsigned (see apps.vibe.api.wardrobe.tsx for the rationale).
  const expected = url.searchParams.get("logged_in_customer_id")?.trim() || "";
  return !expected || sessionId !== `shopify:${expected}`;
}

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
  const rawImage = form.get("imageData");
  const imageData =
    typeof rawImage === "string" && rawImage.startsWith("data:") ? rawImage : "";

  if (!sessionId) {
    return json({ ok: false, error: "Missing sessionId" }, { status: 400 });
  }
  if (!imageData) {
    return json(
      { ok: false, error: "Missing or invalid image" },
      { status: 400 },
    );
  }
  if (identityMismatch(new URL(request.url), sessionId)) {
    return json({ ok: false, error: "Identity mismatch" }, { status: 403 });
  }

  try {
    // resolve→start sequenced (not parallel) — start needs the
    // conversation id. Both are short Mumbai-to-Mumbai round-trips.
    const conv = await resolveConversation(sessionId);
    const turn = await startTurn({
      conversationId: conv.conversation_id,
      userId: sessionId,
      message: CHECK_MESSAGE + PAIRING_TRIGGER,
      imageData,
    });
    return json({
      ok: true,
      conversationId: conv.conversation_id,
      jobId: turn.job_id,
    });
  } catch (err) {
    if (err instanceof EngineError) {
      return json(
        { ok: false, error: err.message },
        { status: err.status || 502 },
      );
    }
    const message = err instanceof Error ? err.message : "Check failed";
    return json({ ok: false, error: message }, { status: 500 });
  }
};
