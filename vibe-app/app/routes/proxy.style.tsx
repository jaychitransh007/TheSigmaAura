// Conversation page — primary Vibe customer surface.
// URL: thesigmavibe.shop/apps/vibe/style
//
// This file implements D.C.2a (route exists) + D.C.2b (session cookie)
// + D.C.2c (engine API client wired). The full conversation UI shell
// (message list, composer, stage indicator, product cards) lands in
// D.C.2d on top of this foundation.
//
// What runs on this page today:
//   - Validate Shopify App Proxy HMAC signature (rejects unsigned).
//   - Read or mint the customer's anonymous session id (cookie).
//   - Call engine.resolveConversation() — returns the customer's
//     conversation_id (mocked until ENGINE_API_URL is set in Vercel).
//   - Render a foundation card showing the wired state.

import type { LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";

import { VibeShell } from "../components/vibe-shell";
import { ENGINE_MOCK_ACTIVE, resolveConversation } from "../lib/engine.server";
import { getOrCreateSession } from "../lib/session.server";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session: shopSession } = await authenticate.public.appProxy(request);
  const { sessionId, isNew, setCookie } = await getOrCreateSession(request);

  const conversation = await resolveConversation(sessionId);

  const headers: Record<string, string> = {};
  if (isNew && setCookie) {
    headers["Set-Cookie"] = setCookie;
  }

  return json(
    {
      sessionId,
      sessionIsNew: isNew,
      shop: shopSession?.shop ?? null,
      conversationId: conversation.conversation_id,
      mockMode: ENGINE_MOCK_ACTIVE,
    },
    { headers },
  );
};

export default function ConversationPage() {
  const { sessionId, sessionIsNew, shop, conversationId, mockMode } =
    useLoaderData<typeof loader>();

  return (
    <VibeShell
      title={
        <>
          Conversation
          {mockMode && <span className="vibe-mock-badge">Mock</span>}
        </>
      }
      subtitle="The chat UI lands here in D.C.2d. The plumbing below is live."
    >
      <p>App Proxy + session + engine wiring all verified.</p>
      <div className="vibe-meta">
        <p>
          Session: <code>{sessionId.slice(0, 12)}…</code>
          {sessionIsNew && " (new this visit)"}
        </p>
        <p>
          Conversation: <code>{conversationId}</code>
        </p>
        <p>
          Shop: <code>{shop ?? "(unknown)"}</code>
        </p>
        {mockMode && (
          <p>
            Engine is in <strong>mock mode</strong>. Set{" "}
            <code>ENGINE_API_URL</code> on Vercel after Fly.io engine deploy
            to hit the real engine.
          </p>
        )}
      </div>
    </VibeShell>
  );
}
