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

import { Composer, type Attachment } from "../components/conversation/composer";
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
  getOnboardingStatus,
  mergeUserIdentity,
  resolveConversation,
  startTurn,
  type OnboardingImageCategory,
  type TurnStatusResponse,
} from "../lib/engine.server";
import {
  isCardStep,
  markKindResolved,
  nextStep,
  readOnboardingStep,
  readResolvedKinds,
  writeOnboardingStep,
  type OnboardingStep,
} from "../lib/onboarding.client";
import {
  adoptCanonicalSessionId,
  getOrCreateClientSessionId,
  readMergedCustomerId,
  writeMergedCustomerId,
} from "../lib/session.client";
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
// Loader — validates proxy, returns mock-mode flag + the Shopify
// customer id if the storefront forwarded one (D.S.3b).
//
// Shopify's App Proxy automatically appends `logged_in_customer_id` to
// the signed query string when the customer is logged in via the
// storefront's Customer Account flow. We surface it to the client so
// it can decide whether to merge the anonymous localStorage UUID into
// the now-authenticated `shopify:{id}` identity. Absent for guests.
// ─────────────────────────────────────────────────────────────────────

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.public.appProxy(request);
  const url = new URL(request.url);
  const loggedInCustomerId =
    url.searchParams.get("logged_in_customer_id")?.trim() || null;

  // hasProfile drives the welcome-message branch (intro-only vs
  // intro+onboarding-cards). The signal we trust is `gender` on the
  // engine's onboarding_profiles row — cheapest, most-load-bearing
  // attribute and the only one the planner actually requires to make
  // a non-generic recommendation. We can only check for customers
  // signed in via Shopify Customer Account because the loader has no
  // access to the anonymous localStorage session id; anonymous
  // customers fall through to hasProfile=false (the new-customer
  // welcome) every time. Acceptable trade-off for v1.
  let hasProfile = false;
  if (loggedInCustomerId) {
    const status = await getOnboardingStatus(`shopify:${loggedInCustomerId}`);
    hasProfile = Boolean(status?.gender);
  }

  return json({
    mockMode: ENGINE_MOCK_ACTIVE,
    loggedInCustomerId,
    hasProfile,
  });
};

// ─────────────────────────────────────────────────────────────────────
// Action — dispatches on `op`:
//   op=init   → resolveConversation(sessionId) → { conversationId }
//   op=turn   → startTurn(...)                  → { jobId, message }
//   op=merge  → mergeUserIdentity(canonical, alias) → { canonical }
//              (D.S.3b: collapse anonymous UUID into shopify:{id})
// All ops require sessionId from the form body.
// ─────────────────────────────────────────────────────────────────────

type InitOk = { ok: true; op: "init"; conversationId: string };
type TurnOk = { ok: true; op: "turn"; jobId: string; message: string };
type MergeOk = {
  ok: true;
  op: "merge";
  canonicalExternalUserId: string;
  merged: boolean;
};
type ActionFail = { ok: false; error: string };
type ActionResponse = InitOk | TurnOk | MergeOk | ActionFail;

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

  if (op === "merge") {
    // D.S.3b — fold an anonymous-UUID identity into the canonical
    // Shopify-customer one. `sessionId` is the alias (the old
    // localStorage UUID); the form also carries the canonical id
    // (`shopify:{logged_in_customer_id}`).
    const canonical = String(form.get("canonicalExternalUserId") ?? "").trim();
    if (!canonical) {
      return json<ActionResponse>(
        { ok: false, error: "Missing canonicalExternalUserId" },
        { status: 400 },
      );
    }
    // Security: never trust the canonical id from the form. The form
    // is client-controlled — a hostile request could claim to be
    // shopify:<someone else's id> and merge the attacker's anonymous
    // history into the victim's account. The signed App Proxy URL
    // carries logged_in_customer_id (validated by
    // authenticate.public.appProxy above); require canonical to match
    // exactly.
    const expectedId = new URL(request.url)
      .searchParams.get("logged_in_customer_id")
      ?.trim();
    if (!expectedId || canonical !== `shopify:${expectedId}`) {
      return json<ActionResponse>(
        { ok: false, error: "Identity mismatch — refuse to merge" },
        { status: 403 },
      );
    }
    try {
      const result = await mergeUserIdentity({
        canonicalExternalUserId: canonical,
        aliasExternalUserId: sessionId,
      });
      // Make sure the now-canonical user has an onboarding_profiles row
      // — otherwise the customer's first photo upload after login would
      // 404 just as it does on initial sign-up.
      await ensureOnboardingProfile(result.canonical_external_user_id);
      return json<ActionResponse>({
        ok: true,
        op: "merge",
        canonicalExternalUserId: result.canonical_external_user_id,
        merged: result.merged,
      });
    } catch (err) {
      // Either the engine merge or the ensure-profile call failed.
      // Surfacing the engine's message gives the client effect
      // something to render in the init-error slot instead of leaving
      // the page silently stuck with no feed.
      const message =
        err instanceof Error ? err.message : "Failed to merge identity";
      return json<ActionResponse>({ ok: false, error: message }, { status: 502 });
    }
  }

  if (op === "turn") {
    const conversationId = String(form.get("conversationId") ?? "").trim();
    const message = String(form.get("message") ?? "").trim();
    // Image attachments arrive as data URLs. Don't trim — base64 is
    // whitespace-sensitive and a stray newline at the end of a very
    // large payload would break the engine's parser.
    const rawImage = form.get("imageData");
    const imageData =
      typeof rawImage === "string" && rawImage.startsWith("data:")
        ? rawImage
        : "";
    if (!conversationId || !message) {
      return json<ActionResponse>(
        { ok: false, error: "Missing conversationId or message" },
        { status: 400 },
      );
    }
    const turn = await startTurn({
      conversationId,
      userId: sessionId,
      message,
      imageData: imageData || undefined,
    });
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
    case "gender-dob":
      return "Basics saved";
    case "name":
      return "Name saved";
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
    case "gender-dob":
      return "Basics skipped";
    case "name":
      return "Name skipped";
    case "height":
      return "Height skipped";
    case "waist":
      return "Waist skipped";
  }
}

// Welcome-message variants. New customers see B + the initial
// onboarding cards stacked below it. Returning customers (engine
// confirms `gender` is set) see A and a clean composer — no cards
// forced on them.
const WELCOME_RETURNING =
  'Hey, welcome back — I\'m Vibe. Try something like "Dress me for tonight" or "I need an outfit for a wedding".';
const WELCOME_NEW =
  'Hi — I\'m Vibe, your styling co-pilot. Try something like "Dress me for tonight" — and a couple of basics below help me find what works on you.';

export default function ConversationPage() {
  const { mockMode, loggedInCustomerId, hasProfile } =
    useLoaderData<typeof loader>();
  const [sessionId, setSessionId] = useState("");
  const [conversationId, setConversationId] = useState("");
  const [initError, setInitError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  // Short-lived error from the composer's attach button (file too big,
  // wrong type, unreadable). Distinct from initError, which signals a
  // hard session-setup failure the customer can't recover from.
  const [attachError, setAttachError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState<PendingTurn | null>(null);
  // Whether the current identity is bound to a Shopify customer.
  // Drives the header CTA: "Sign in" pill when false, status hint
  // when true. Derived directly from the loader data so it stays in
  // sync with revalidations and renders correctly during SSR — no
  // useState/useEffect dance. logged_in_customer_id is the canonical
  // signal from Shopify's App Proxy on this very request, not stale
  // localStorage.
  const isAuthenticated = !!loggedInCustomerId;

  const initFetcher = useFetcher<typeof action>();
  const submitFetcher = useFetcher<typeof action>();
  const mergeFetcher = useFetcher<typeof action>();
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
  //
  // D.S.3b: if Shopify forwarded a logged_in_customer_id AND we haven't
  // already merged into that customer's identity, dispatch op=merge.
  // The anonymous UUID's conversations/history get folded into
  // `shopify:{customer_id}` and from here on we use that as the
  // canonical sessionId. The init request fires only AFTER the merge
  // settles so the conversation resolves against the canonical id.
  useEffect(() => {
    let sid = getOrCreateClientSessionId();
    // isAuthenticated is derived from loggedInCustomerId at render
    // time (see the const above), so we don't need to sync it here.
    // The merged-customer key is consulted only to decide whether we
    // need a merge round-trip — a returning, already-merged customer
    // skips it entirely.
    const alreadyMergedWith = readMergedCustomerId();
    const needsMerge =
      !!loggedInCustomerId && alreadyMergedWith !== loggedInCustomerId;

    if (needsMerge) {
      const canonical = `shopify:${loggedInCustomerId}`;
      mergeFetcher.submit(
        {
          op: "merge",
          sessionId: sid,
          canonicalExternalUserId: canonical,
        },
        { method: "post" },
      );
      // Init is deferred to the merge-completed effect below so that
      // resolveConversation uses the post-merge canonical id.
      setSessionId(sid); // expose the alias temporarily for the merge call
      return;
    }

    // Returning customer who's already merged, OR an anonymous guest.
    // Just init against whatever's in localStorage.
    setSessionId(sid);
    initFetcher.submit(
      { op: "init", sessionId: sid },
      { method: "post" },
    );
    // run-once; deps are intentionally empty.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // After op=merge settles, adopt the canonical id locally and run
  // op=init against it. If the merge action returned !ok, surface
  // the error instead of leaving the page silently stuck — without
  // this branch the customer would see an empty feed forever after
  // a 5xx from the engine merge endpoint.
  useEffect(() => {
    if (mergeFetcher.state !== "idle") return;
    const data = mergeFetcher.data;
    if (!data || data.op !== "merge") return;
    if (!data.ok) {
      setInitError(data.error || "Couldn't sign in just now.");
      return;
    }

    const canonical = data.canonicalExternalUserId;
    adoptCanonicalSessionId(canonical);
    if (loggedInCustomerId) {
      writeMergedCustomerId(loggedInCustomerId);
    }
    setSessionId(canonical);
    // isAuthenticated stays derived from loggedInCustomerId — no
    // setIsAuthenticated needed; we already render as signed-in
    // because the loader said so.
    initFetcher.submit(
      { op: "init", sessionId: canonical },
      { method: "post" },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mergeFetcher.state, mergeFetcher.data]);

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

  // Seed the feed once per page life. Two shapes:
  //
  //   hasProfile = true  (returning customer w/ gender on engine row)
  //     → just the welcome-back message. No cards forced.
  //     → onboardingStep advances to "done" so no future cards emit.
  //
  //   hasProfile = false (new / anonymous / never-completed)
  //     → welcome message + photos card + gender-DOB card stacked.
  //     → onboardingStep tracks "gender-dob" (the furthest card we've
  //       already emitted). When BOTH initial cards resolve,
  //       handleAdvanceOnboarding promotes to "name" and emits it.
  //
  // seededRef prevents double-seeding when sessionId/conversationId
  // settle on different ticks. Legacy localStorage step values
  // ("dob"/"gender") are migrated by readOnboardingStep already.
  useEffect(() => {
    if (!sessionId || !conversationId) return;
    if (seededRef.current) return;
    seededRef.current = true;

    if (hasProfile) {
      onboardingStepRef.current = "done";
      writeOnboardingStep("done");
      setMessages([{ role: "assistant", text: WELCOME_RETURNING }]);
      return;
    }

    // New-customer path. Two layers of persistence:
    //   - vibe_onboarding_step: the furthest *sequence position* the
    //     customer has reached. Drives where the next card slots in
    //     once the initial parallel pair clears.
    //   - vibe_onboarding_resolved_kinds: explicit list of cards
    //     already saved/skipped. A reload during the parallel
    //     photos+gender-DOB phase consults this so a completed
    //     photos card doesn't re-emit.
    const persisted = readOnboardingStep();
    const resolved = readResolvedKinds();
    const isInitialPhase =
      persisted === "welcome" ||
      persisted === "photos" ||
      persisted === "gender-dob";

    const seeded: ChatMessage[] = [
      { role: "assistant", text: WELCOME_NEW },
    ];

    if (isInitialPhase) {
      if (!resolved.has("photos")) {
        seeded.push({ role: "onboarding", kind: "photos", status: "active" });
      }
      if (!resolved.has("gender-dob")) {
        seeded.push({
          role: "onboarding",
          kind: "gender-dob",
          status: "active",
        });
      }
      onboardingStepRef.current = "gender-dob";
      writeOnboardingStep("gender-dob");
    } else if (isCardStep(persisted) && !resolved.has(persisted)) {
      seeded.push({
        role: "onboarding",
        kind: persisted as OnboardingMessageKind,
        status: "active",
      });
      onboardingStepRef.current = persisted;
    } else {
      onboardingStepRef.current = "done";
    }

    setMessages(seeded);
  }, [sessionId, conversationId, hasProfile]);

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
    if (pending) return;
    if (!sessionId || !conversationId) return;
    const text = draft.trim();
    // The composer enables Send when either text OR an attachment is
    // present. Empty + no attachment shouldn't reach here, but guard
    // anyway so a stray hotkey press doesn't fire a useless turn.
    if (!text && !attachment) return;

    // Pairing-with-image flow: legacy ui.py defaulted the message to
    // "What goes with this? Show me pairing options." when the user
    // attached an image without typing anything. The engine's planner
    // routes this prompt into pairing_request — mirror that here so
    // image-only sends produce a useful turn instead of an empty
    // architect query.
    const message =
      text || "What goes with this? Show me pairing options.";

    // FormData (not the plain-object form) — Remix's submit() encodes
    // plain objects as application/x-www-form-urlencoded, which can
    // mangle very large data URLs in some hosts' URL parsers. FormData
    // is sent as multipart/form-data which carries the base64 payload
    // verbatim. ~13MB max (10MB binary × 1.33 base64 expansion); fits
    // comfortably within Vercel's request-body cap.
    const form = new FormData();
    form.set("op", "turn");
    form.set("sessionId", sessionId);
    form.set("conversationId", conversationId);
    form.set("message", message);
    if (attachment) form.set("imageData", attachment.dataUrl);
    submitFetcher.submit(form, { method: "post", encType: "multipart/form-data" });

    // Clear the attachment optimistically — the next turn shouldn't
    // re-attach the same image, and the user has visual confirmation
    // (the chip disappears the moment they hit send).
    setAttachment(null);
  };

  const handlePromptPick = (text: string) => {
    setDraft(text);
  };

  // Onboarding card → completed / skipped.
  //
  // Two-phase logic:
  //   1. Mark the matching active card resolved (closes its widget,
  //      leaves a "Saved" / "Skipped" summary line).
  //   2. Advance the state machine to the next card ONLY when no
  //      onboarding cards remain active. This is what lets the
  //      initial photos + gender-DOB cards live side-by-side without
  //      racing each other — the customer can resolve them in any
  //      order; we don't emit `name` until both are done. Sequential
  //      cards (name → height → waist) trivially satisfy the
  //      "no other active" check by virtue of being alone.
  //
  // Skipping doesn't save anything — the engine's gate is loosened
  // for vibe_storefront so missing fields only degrade quality.
  // Pure transformation: resolves the most-recent active card of the
  // given kind, and (only when no active onboarding cards remain)
  // appends the next sequential card. Reads only `prev` — never the
  // ref or localStorage — so it's safe to run twice in StrictMode and
  // works correctly across rapid successive calls because React
  // queues functional updaters against the freshest state.
  const transformAdvance = (
    prev: ChatMessage[],
    kind: OnboardingMessageKind,
    mode: "completed" | "skipped",
  ): ChatMessage[] => {
    const next = [...prev];
    // Reverse search: if multiple active cards of the same kind ever
    // existed (shouldn't, but defensive), resolve the most-recent.
    for (let i = next.length - 1; i >= 0; i--) {
      const m = next[i];
      if (
        m.role === "onboarding" &&
        m.status === "active" &&
        m.kind === kind
      ) {
        next[i] = {
          ...m,
          status: mode,
          summary:
            mode === "completed"
              ? completedSummary(kind)
              : skippedSummary(kind),
        };
        break;
      }
    }
    const anyActive = next.some(
      (m) => m.role === "onboarding" && m.status === "active",
    );
    if (!anyActive) {
      // Derive the next step from the last onboarding message
      // (resolved or not). findLast walks end→start internally — no
      // copy + reverse needed. Sidesteps the ref entirely so the
      // updater stays pure even under rapid successive calls.
      const lastOnb = next.findLast((m) => m.role === "onboarding");
      const currentStep: OnboardingStep = lastOnb
        ? (lastOnb.kind as OnboardingStep)
        : "welcome";
      const newStep = nextStep(currentStep);
      if (isCardStep(newStep)) {
        next.push({
          role: "onboarding",
          kind: newStep as OnboardingMessageKind,
          status: "active",
        });
      }
    }
    return next;
  };

  const handleAdvanceOnboarding = (
    kind: OnboardingMessageKind,
    mode: "completed" | "skipped",
  ) => {
    // Functional updater — atomic against the latest queued state,
    // safe under rapid successive calls. The updater stays pure so
    // StrictMode's double invocation can't duplicate writes.
    setMessages((prev) => transformAdvance(prev, kind, mode));
    // Event handlers ARE safe for side effects (StrictMode doesn't
    // double-invoke them). Record the resolved kind here instead of
    // looping through every message in a useEffect — saves an O(N)
    // localStorage scan on every messages change. Idempotent on the
    // storage side (Set semantics) so a duplicate call from any
    // future re-fire is harmless.
    markKindResolved(kind);
  };

  // Side-effects effect: keep the persisted onboarding step in sync
  // with the messages array. Single reverse pass:
  //   - first onboarding card we see is the last-emitted (lastOnb).
  //   - if any onboarding card is active, break early — that's
  //     enough to know step = lastOnb.kind.
  //
  // When there are no onboarding cards in the feed at all (returning
  // customer with the welcome-only seed, or any pre-seed render), we
  // leave the step alone — the seed effect set it correctly already
  // and this effect has nothing to derive from. markKindResolved
  // lives in the event handler now — no scan needed here.
  useEffect(() => {
    // Typing lastOnb as the narrowed onboarding variant lets TS carry
    // .kind through to the step derivation without a second role
    // check after the loop. The `continue` guard inside the loop
    // narrows `m` to the same variant before the assignment.
    let lastOnb: Extract<ChatMessage, { role: "onboarding" }> | undefined;
    let anyActive = false;
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role !== "onboarding") continue;
      if (!lastOnb) lastOnb = m;
      if (m.status === "active") {
        anyActive = true;
        break;
      }
    }
    if (!lastOnb) return;
    const step: OnboardingStep = anyActive
      ? (lastOnb.kind as OnboardingStep)
      : nextStep(lastOnb.kind as OnboardingStep);
    if (onboardingStepRef.current !== step) {
      onboardingStepRef.current = step;
      writeOnboardingStep(step);
    }
  }, [messages]);

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
        {/* D.S.3b — sign-in affordance. Anonymous customers see a pill
            that links to the storefront's Customer Account login; the
            return_url brings them back here, at which point the App
            Proxy starts forwarding logged_in_customer_id and the mount
            effect picks up the merge. Authenticated customers see a
            subtle "Signed in" hint instead (no logout flow yet —
            Shopify handles that on the storefront). */}
        {isAuthenticated ? (
          <span className="conv-auth-pill conv-auth-pill--in" aria-label="Signed in">
            Signed in
          </span>
        ) : (
          <a
            className="conv-auth-pill conv-auth-pill--out"
            href="/account/login?return_url=/apps/vibe/style"
          >
            Sign in
          </a>
        )}
      </header>

      <div className="conv-feed" ref={feedRef}>
        {initError && (
          <div className="conv-init-error">{initError}</div>
        )}
        {attachError && (
          <div className="conv-init-error">{attachError}</div>
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
        attachment={attachment}
        onAttach={(a) => {
          setAttachment(a);
          setAttachError(null);
        }}
        onDetach={() => setAttachment(null)}
        onAttachError={setAttachError}
      />
    </div>
  );
}
