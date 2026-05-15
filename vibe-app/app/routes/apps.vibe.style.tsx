// Conversation page — primary Vibe customer surface.
// URL: thesigmavibe.shop/apps/vibe/style
//
// D.C.2d implementation. Full chat loop with mock engine progression:
//   - Loader: validate App Proxy, resolve customer session + conversation
//   - Action: receive message → engine.startTurn() → return job_id
//   - Client: append user message, kick off polling via useFetcher,
//     update UI with stages, replace stage with final outfit when done
//
// Engine API runs in mock mode (5s simulated turn with stage events)
// until ENGINE_API_URL is set on Vercel post-Fly.io deploy.

import type { ActionFunctionArgs, LoaderFunctionArgs, LinksFunction } from "@remix-run/node";
import { json } from "@remix-run/node";
import { useFetcher, useLoaderData } from "@remix-run/react";
import { useEffect, useRef, useState } from "react";

import { Composer } from "../components/conversation/composer";
import { MessageView, type ChatMessage } from "../components/conversation/message";
import { StageIndicator } from "../components/conversation/stage-indicator";
import { WelcomeState } from "../components/conversation/welcome-state";
import conversationStyles from "../components/conversation/styles.css?url";
import {
  ENGINE_MOCK_ACTIVE,
  resolveConversation,
  startTurn,
  type TurnStatusResponse,
} from "../lib/engine.server";
import { getOrCreateSession } from "../lib/session.server";
import { authenticate } from "../shopify.server";

export const links: LinksFunction = () => [
  { rel: "stylesheet", href: conversationStyles },
  // Fraunces — Confident Luxe display serif (italic 400 + roman 600).
  // Inter already comes from Shopify's CDN in root.tsx.
  { rel: "preconnect", href: "https://fonts.googleapis.com" },
  { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
  {
    rel: "stylesheet",
    href: "https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,600;1,400&display=swap",
  },
];

// ─────────────────────────────────────────────────────────────────────
// Loader — resolves session + conversation on page load
// ─────────────────────────────────────────────────────────────────────

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session: shopSession } = await authenticate.public.appProxy(request);
  const { sessionId, isNew, setCookie } = await getOrCreateSession(request);
  const conversation = await resolveConversation(sessionId);

  const headers: Record<string, string> = {};
  if (isNew && setCookie) headers["Set-Cookie"] = setCookie;

  return json(
    {
      sessionId,
      shop: shopSession?.shop ?? null,
      conversationId: conversation.conversation_id,
      mockMode: ENGINE_MOCK_ACTIVE,
    },
    { headers },
  );
};

// ─────────────────────────────────────────────────────────────────────
// Action — submits a user message, returns the engine job_id
// ─────────────────────────────────────────────────────────────────────

export const action = async ({ request }: ActionFunctionArgs) => {
  await authenticate.public.appProxy(request);

  const form = await request.formData();
  const conversationId = String(form.get("conversationId") ?? "").trim();
  const message = String(form.get("message") ?? "").trim();

  if (!conversationId || !message) {
    return json(
      { ok: false, error: "Missing conversationId or message" },
      { status: 400 },
    );
  }

  const turn = await startTurn({ conversationId, message });
  return json({ ok: true, jobId: turn.job_id, message });
};

// ─────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────

type PendingTurn = {
  jobId: string;
  startedAt: number;
  status: TurnStatusResponse | null;
};

export default function ConversationPage() {
  const { conversationId, mockMode } = useLoaderData<typeof loader>();
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState<PendingTurn | null>(null);

  const submitFetcher = useFetcher<typeof action>();
  const pollFetcher = useFetcher<TurnStatusResponse>();
  const feedRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages or pending state changes.
  useEffect(() => {
    const el = feedRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, pending]);

  // When the submit action returns, append the user message + start polling.
  useEffect(() => {
    if (submitFetcher.state !== "idle") return;
    const data = submitFetcher.data;
    if (!data || !("ok" in data) || !data.ok) return;
    if (pending && pending.jobId === data.jobId) return; // already tracking

    setMessages((prev) => [...prev, { role: "user", text: data.message }]);
    setPending({ jobId: data.jobId, startedAt: Date.now(), status: null });
    setDraft("");
  }, [submitFetcher.state, submitFetcher.data, pending]);

  // Poll loop — fires every second while pending.
  useEffect(() => {
    if (!pending) return;
    if (pollFetcher.state !== "idle") return;

    const status = pollFetcher.data;
    if (status && status.job_id === pending.jobId) {
      // Update with latest status
      setPending((prev) => (prev ? { ...prev, status } : prev));

      if (status.status === "succeeded" && status.result) {
        // Turn complete — append assistant message + outfits, clear pending.
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            text: status.result!.message,
            outfits: status.result!.outfits,
          },
        ]);
        setPending(null);
        return;
      }

      if (status.status === "failed") {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            text:
              status.error ||
              "Something went wrong. Try again in a moment.",
          },
        ]);
        setPending(null);
        return;
      }
    }

    // Schedule next poll
    const timer = setTimeout(() => {
      pollFetcher.load(
        `/apps/vibe/api/poll?conv=${encodeURIComponent(conversationId)}&job=${encodeURIComponent(pending.jobId)}`,
      );
    }, 1000);
    return () => clearTimeout(timer);
  }, [pending, pollFetcher, conversationId]);

  const handleSubmit = () => {
    const text = draft.trim();
    if (!text || pending) return;
    submitFetcher.submit(
      { conversationId, message: text },
      { method: "post" },
    );
  };

  const handlePromptPick = (text: string) => {
    setDraft(text);
  };

  const showWelcome = messages.length === 0 && !pending;
  const composerDisabled = pending !== null || submitFetcher.state !== "idle";

  return (
    <div className="conv-page">
      <header className="conv-header">
        <h1>Vibe{mockMode && <span className="conv-mock-badge"> Mock</span>}</h1>
      </header>

      <div className="conv-feed" ref={feedRef}>
        {showWelcome && <WelcomeState onPick={handlePromptPick} />}

        {messages.map((msg, i) => (
          <MessageView
            key={i}
            message={msg}
            onHideOutfit={(outfitId) =>
              setMessages((prev) =>
                prev.map((m, mi) =>
                  mi === i && m.role === "assistant"
                    ? {
                        ...m,
                        outfits: m.outfits?.filter((o) => o.outfit_id !== outfitId),
                      }
                    : m,
                ),
              )
            }
          />
        ))}

        {pending && <StageIndicator stages={pending.status?.stages ?? []} />}
      </div>

      <Composer
        value={draft}
        onChange={setDraft}
        onSubmit={handleSubmit}
        disabled={composerDisabled}
      />
    </div>
  );
}
