// Conversation page — primary Vibe customer surface.
// URL: thesigmavibe.shop/apps/vibe/style
//
// Identity: the customer's session id lives in localStorage on the
// browser (see app/lib/session.client.ts). Cookies don't work through
// Shopify App Proxy — the proxy doesn't reliably round-trip
// Set-Cookie / Cookie headers between the storefront origin and the
// backend domain, so every cookie-based request looked like a fresh
// customer to the engine. Identity flows explicitly via form fields
// and query params instead.
//
// Lifecycle:
//   - Loader: validates the App Proxy signature, returns the mock-mode
//     flag. No conversation resolution — that's deferred to mount.
//   - Mount: read/mint localStorage session id, POST op=init to the
//     action to resolve a conversation id, store both in state.
//   - User message: POST op=turn with {sessionId, conversationId,
//     message}. Action calls the engine, returns job_id.
//   - Poll loop: GET /apps/vibe/api/poll?conv=…&job=…
//
// Engine API runs in mock mode (5s simulated turn with stage events)
// until ENGINE_API_URL is set on Vercel.

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
import { getOrCreateClientSessionId } from "../lib/session.client";
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
// Loader — validates proxy, returns mock-mode flag. No identity yet.
// ─────────────────────────────────────────────────────────────────────

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.public.appProxy(request);
  return json({ mockMode: ENGINE_MOCK_ACTIVE });
};

// ─────────────────────────────────────────────────────────────────────
// Action — dispatches on `op`:
//   op=init  → resolveConversation(sessionId) → { conversationId }
//   op=turn  → startTurn(...)                  → { jobId, message }
// Both ops require sessionId from the form body.
// ─────────────────────────────────────────────────────────────────────

type InitOk = { ok: true; op: "init"; conversationId: string };
type TurnOk = { ok: true; op: "turn"; jobId: string; message: string };
type ActionFail = { ok: false; error: string };
type ActionResponse = InitOk | TurnOk | ActionFail;

export const action = async ({ request }: ActionFunctionArgs) => {
  await authenticate.public.appProxy(request);

  const form = await request.formData();
  const op = String(form.get("op") ?? "").trim();
  const sessionId = String(form.get("sessionId") ?? "").trim();

  if (!sessionId) {
    return json<ActionResponse>(
      { ok: false, error: "Missing sessionId" },
      { status: 400 },
    );
  }

  if (op === "init") {
    const conversation = await resolveConversation(sessionId);
    return json<ActionResponse>({
      ok: true,
      op: "init",
      conversationId: conversation.conversation_id,
    });
  }

  if (op === "turn") {
    const conversationId = String(form.get("conversationId") ?? "").trim();
    const message = String(form.get("message") ?? "").trim();
    if (!conversationId || !message) {
      return json<ActionResponse>(
        { ok: false, error: "Missing conversationId or message" },
        { status: 400 },
      );
    }
    const turn = await startTurn({ conversationId, userId: sessionId, message });
    return json<ActionResponse>({
      ok: true,
      op: "turn",
      jobId: turn.job_id,
      message,
    });
  }

  return json<ActionResponse>(
    { ok: false, error: `Unknown op: ${op}` },
    { status: 400 },
  );
};

// ─────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────

type PendingTurn = {
  conversationId: string; // frozen at start so polling can't drift
  jobId: string;
  startedAt: number;
  status: TurnStatusResponse | null;
};

export default function ConversationPage() {
  const { mockMode } = useLoaderData<typeof loader>();
  const [sessionId, setSessionId] = useState("");
  const [conversationId, setConversationId] = useState("");
  const [initError, setInitError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState<PendingTurn | null>(null);

  const initFetcher = useFetcher<typeof action>();
  const submitFetcher = useFetcher<typeof action>();
  const pollFetcher = useFetcher<TurnStatusResponse>();
  const feedRef = useRef<HTMLDivElement>(null);
  // submitFetcher.data is sticky — Remix keeps the last response around
  // until the next submit. Without an idempotence guard, the submit
  // effect re-fires every time `pending` clears (because pending is in
  // its deps) and re-appends the user message + restarts a duplicate
  // turn against the same jobId. Track which turn we've already
  // consumed so the effect short-circuits on the re-run.
  const consumedTurnIdRef = useRef<string | null>(null);
  // Same hazard on the poll side: pollFetcher.data keeps the terminal
  // succeeded response and the effect re-runs whenever the fetcher
  // re-renders. Without this guard, every re-render after success
  // re-appends the assistant message.
  const consumedPollIdRef = useRef<string | null>(null);

  // Mount: pull session id from localStorage (or mint one) and resolve
  // the conversation. Anchors identity to this browser for the rest of
  // the page session.
  useEffect(() => {
    const sid = getOrCreateClientSessionId();
    setSessionId(sid);
    initFetcher.submit(
      { op: "init", sessionId: sid },
      { method: "post" },
    );
    // run-once; deps are intentionally empty.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Capture the init response → conversationId.
  useEffect(() => {
    if (initFetcher.state !== "idle") return;
    const data = initFetcher.data;
    if (!data) return;
    if (data.ok && data.op === "init") {
      setConversationId(data.conversationId);
      setInitError(null);
    } else if (!data.ok) {
      setInitError(data.error || "Couldn't start a conversation.");
    }
  }, [initFetcher.state, initFetcher.data]);

  // Auto-scroll to bottom when messages or pending state changes.
  useEffect(() => {
    const el = feedRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, pending]);

  // When the submit action returns, append the user message + start polling.
  useEffect(() => {
    if (submitFetcher.state !== "idle") return;
    const data = submitFetcher.data;
    if (!data || !data.ok || data.op !== "turn") return;
    if (consumedTurnIdRef.current === data.jobId) return;
    consumedTurnIdRef.current = data.jobId;

    setMessages((prev) => [...prev, { role: "user", text: data.message }]);
    setPending({
      conversationId,
      jobId: data.jobId,
      startedAt: Date.now(),
      status: null,
    });
    setDraft("");
  }, [submitFetcher.state, submitFetcher.data, conversationId]);

  // Poll loop — fires every second while pending.
  useEffect(() => {
    if (!pending) return;
    if (pollFetcher.state !== "idle") return;

    const status = pollFetcher.data;
    if (status && status.job_id === pending.jobId) {
      const terminal =
        status.status === "succeeded" || status.status === "failed";
      const alreadyConsumed = consumedPollIdRef.current === pending.jobId;

      if (terminal && alreadyConsumed) {
        // Re-render after we already appended the assistant message
        // and cleared pending — nothing to do, just don't double-write.
        return;
      }

      setPending((prev) => (prev ? { ...prev, status } : prev));

      if (status.status === "succeeded" && status.result) {
        consumedPollIdRef.current = pending.jobId;
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
        consumedPollIdRef.current = pending.jobId;
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

    const timer = setTimeout(() => {
      pollFetcher.load(
        `/apps/vibe/api/poll?conv=${encodeURIComponent(pending.conversationId)}&job=${encodeURIComponent(pending.jobId)}`,
      );
    }, 1000);
    return () => clearTimeout(timer);
    // pollFetcher.load is stable across renders (Remix guarantee) so
    // it's safe to omit from deps. Tracking pollFetcher.{state,data}
    // explicitly drives re-runs when polling progresses — a bare
    // `pollFetcher` dep would re-fire on every parent re-render, while
    // omitting it entirely would stall the loop on the first poll.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, pollFetcher.state, pollFetcher.data]);

  const handleSubmit = () => {
    const text = draft.trim();
    if (!text || pending) return;
    if (!sessionId || !conversationId) return;
    submitFetcher.submit(
      { op: "turn", sessionId, conversationId, message: text },
      { method: "post" },
    );
  };

  const handlePromptPick = (text: string) => {
    setDraft(text);
  };

  const ready = sessionId !== "" && conversationId !== "";
  const showWelcome = messages.length === 0 && !pending;
  const composerDisabled =
    !ready || pending !== null || submitFetcher.state !== "idle";

  return (
    <div className="conv-page">
      <header className="conv-header">
        <h1>Vibe{mockMode && <span className="conv-mock-badge"> Mock</span>}</h1>
      </header>

      <div className="conv-feed" ref={feedRef}>
        {initError && (
          <div className="conv-init-error">{initError}</div>
        )}
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
