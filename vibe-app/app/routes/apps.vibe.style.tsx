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
import {
  MessageView,
  type ChatMessage,
  type OnboardingMessageKind,
} from "../components/conversation/message";
import { StageIndicator } from "../components/conversation/stage-indicator";
import { WelcomeState } from "../components/conversation/welcome-state";
import conversationStyles from "../components/conversation/styles.css?url";
import {
  ENGINE_MOCK_ACTIVE,
  ensureOnboardingProfile,
  resolveConversation,
  startTurn,
  type OnboardingImageCategory,
  type TurnStatusResponse,
} from "../lib/engine.server";
import {
  isCardStep,
  nextStep,
  readOnboardingStep,
  writeOnboardingStep,
  type OnboardingStep,
} from "../lib/onboarding.client";
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
    // Resolve (or create) the conversation AND ensure the onboarding-
    // profile row exists. Without ensureOnboardingProfile, the very
    // first photo/profile-field save 404s ("User not found") because
    // the engine's onboarding tables aren't populated by the
    // conversation-resolve path — they were historically populated by
    // OTP verification, which Vibe customers don't go through.
    //
    // The two engine calls touch independent tables and don't depend
    // on each other — run them in parallel to save one Mumbai-to-
    // Mumbai round-trip (~10ms) on every init. Idempotent: a
    // returning customer's ensure call is a no-op.
    const [conversation] = await Promise.all([
      resolveConversation(sessionId),
      ensureOnboardingProfile(sessionId),
    ]);
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

function completedSummary(kind: OnboardingMessageKind): string {
  switch (kind) {
    case "photos":
      return "Photos saved";
    case "name":
      return "Name saved";
    case "dob":
      return "Date of birth saved";
    case "gender":
      return "Style direction saved";
    case "height":
      return "Height saved";
    case "waist":
      return "Waist saved";
  }
}

function skippedSummary(kind: OnboardingMessageKind): string {
  switch (kind) {
    case "photos":
      return "Photos skipped";
    case "name":
      return "Name skipped";
    case "dob":
      return "Date of birth skipped";
    case "gender":
      return "Style direction skipped";
    case "height":
      return "Height skipped";
    case "waist":
      return "Waist skipped";
  }
}

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
  // Onboarding state machine — canonical current step. Mirrored into
  // localStorage by writeOnboardingStep so a reload resumes mid-flow.
  // Lives in a ref (not state) so updating it doesn't trigger an
  // extra re-render — the messages array is what drives the UI.
  const onboardingStepRef = useRef<OnboardingStep>("welcome");
  // Prevents the mount effect from seeding messages twice — useEffect
  // can re-run when sessionId/conversationId arrive at different
  // ticks. We only ever want the welcome + first card emitted once
  // per page life.
  const seededRef = useRef<boolean>(false);

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

  // Seed the feed with the welcome message + current onboarding card
  // once we have both sessionId and conversationId. Runs exactly once
  // per page life (seededRef guards re-entry). A fresh visitor sits at
  // step="welcome" — we promote them to "photos" so the photo card
  // appears below the welcome message. Returning visitors mid-flow
  // resume at whichever step they last reached.
  useEffect(() => {
    if (!sessionId || !conversationId) return;
    if (seededRef.current) return;
    seededRef.current = true;

    let step = readOnboardingStep();
    if (step === "welcome") {
      step = "photos";
      writeOnboardingStep(step);
    }
    onboardingStepRef.current = step;

    const seeded: ChatMessage[] = [
      {
        role: "assistant",
        text:
          "Hey, I'm Vibe — I'll find what works on you. Want to chat, or shall we set the basics first? Skip anything you'd rather not share.",
      },
    ];
    if (isCardStep(step)) {
      seeded.push({
        role: "onboarding",
        kind: step as OnboardingMessageKind,
        status: "active",
      });
    }
    setMessages(seeded);
  }, [sessionId, conversationId]);

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
    // Depend on the identifying fields of `pending`, not the whole
    // object: the effect itself calls `setPending({ ...prev, status })`
    // to attach the latest poll response, which produces a NEW pending
    // object reference. A bare `pending` dep would re-run the effect on
    // that update, call setPending again, and spin forever — never
    // letting the 1s setTimeout fire. conversationId/jobId only change
    // on a brand-new turn, which is exactly when we want to re-arm.
    // pollFetcher.{state,data} drive re-runs as the poll progresses.
    // pollFetcher.load is stable (Remix guarantee), so the lint disable
    // is appropriate.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending?.conversationId, pending?.jobId, pollFetcher.state, pollFetcher.data]);

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

  // Onboarding card → completed / skipped. Closes the active card
  // (replacing its widget with a short summary line) and emits the
  // next card if there is one. Skipping doesn't save anything — the
  // engine's gate is loosened for vibe_storefront so missing fields
  // only degrade quality, never block.
  const handleAdvanceOnboarding = (mode: "completed" | "skipped") => {
    const current = onboardingStepRef.current;
    const newStep = nextStep(current);
    onboardingStepRef.current = newStep;
    writeOnboardingStep(newStep);

    setMessages((prev) => {
      const next = [...prev];
      // Mark the most-recent active onboarding card as resolved.
      for (let i = next.length - 1; i >= 0; i--) {
        const m = next[i];
        if (m.role === "onboarding" && m.status === "active") {
          next[i] = {
            ...m,
            status: mode,
            summary:
              mode === "completed"
                ? completedSummary(m.kind)
                : skippedSummary(m.kind),
          };
          break;
        }
      }
      if (isCardStep(newStep)) {
        next.push({
          role: "onboarding",
          kind: newStep as OnboardingMessageKind,
          status: "active",
        });
      }
      return next;
    });
  };

  // Fire-and-forget analysis trigger after a photo upload. Best-effort:
  // phase1 needs gender + headshot, phase2 needs gender + DOB + both
  // photos. If the prereq isn't met yet the engine 400s and we ignore.
  // Once the missing field is later saved, calling again will succeed.
  // We don't surface failures to the customer — analysis is invisible
  // background work.
  const handleOnboardingPhotoUploaded = (category: OnboardingImageCategory) => {
    if (!sessionId) return;
    const phase = category === "headshot" ? "phase1" : "phase2";
    const form = new FormData();
    form.set("sessionId", sessionId);
    form.set("phase", phase);
    fetch("/apps/vibe/api/onboarding/analysis", {
      method: "POST",
      body: form,
    }).catch(() => {
      // Best-effort.
    });
  };

  const ready = sessionId !== "" && conversationId !== "";
  // WelcomeState's empty-state CTAs aren't rendered now that the
  // onboarding flow seeds the feed with its own welcome message + card.
  // Kept reachable as a fallback for sessions where seeding fails (no
  // sessionId / conversationId).
  const showWelcome = ready && messages.length === 0 && !pending;
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
            sessionId={sessionId}
            onAdvanceOnboarding={handleAdvanceOnboarding}
            onOnboardingPhotoUploaded={handleOnboardingPhotoUploaded}
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
