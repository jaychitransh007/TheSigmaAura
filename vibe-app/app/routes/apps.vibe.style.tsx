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
  ENGINE_HTTP_TIMEOUT_MS,
  ENGINE_MOCK_ACTIVE,
  ensureOnboardingProfile,
  getOnboardingStatus,
  lookupOrCreateTenant,
  mergeUserIdentity,
  resolveConversation,
  startTurn,
  type OnboardingImageCategory,
  type OnboardingStatus,
  type TenantThemeOverrides,
  type TurnStatusResponse,
} from "../lib/engine.server";
import { logInfo, logWarn, logError } from "../lib/logger.server";
import { MerchantHeader } from "../components/merchant-header";
import "../components/merchant-header.css";
import { ThemeOverridesStyle } from "../components/theme-overrides";
import {
  isCardStep,
  markKindResolved,
  nextStep,
  readOnboardingStep,
  readResolvedKinds,
  unmarkKindResolved,
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
  //
  // getOnboardingStatus now distinguishes 404 (null, confirmed new
  // user) from engine error (undefined). For the loader's SSR hint we
  // mirror the init action's safety net: assume hasProfile=true on
  // engine error so a returning customer hitting transient trouble
  // doesn't flash the new-customer welcome before init lands and
  // overrides this value.
  let hasProfile = false;
  if (loggedInCustomerId) {
    const status = await getOnboardingStatus(`shopify:${loggedInCustomerId}`);
    if (status === undefined) {
      hasProfile = true;
    } else if (status === null) {
      hasProfile = false;
    } else {
      hasProfile = Boolean(status.gender);
    }
  }

  // PR #478: theme inheritance — look up the tenant's captured
  // theme overrides (font + accent color from the merchant's active
  // Shopify theme) so vibe-page styles can use them as CSS vars.
  // Best-effort: engine failure → no overrides → Confident Luxe
  // defaults. Don't 500 the storefront chat on a tenant-lookup hiccup.
  const shopDomain = url.searchParams.get("shop")?.trim() ?? "";
  let themeOverrides: TenantThemeOverrides | null = null;
  if (shopDomain) {
    try {
      const tenant = await lookupOrCreateTenant({ shopDomain });
      themeOverrides = tenant.theme_overrides ?? null;
    } catch {
      // Silent — fall back to Confident Luxe defaults.
    }
  }

  return json({
    mockMode: ENGINE_MOCK_ACTIVE,
    loggedInCustomerId,
    hasProfile,
    themeOverrides,
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

type InitOk = {
  ok: true;
  op: "init";
  conversationId: string;
  /** Categories the engine has on file for this user
   *  ("full_body" / "headshot"). The seed effect re-injects the
   *  PhotosCard when the customer's localStorage step is past
   *  "photos" but the engine reports no full_body photo — covers
   *  cases where photos were lost (volume rebuild, manual delete,
   *  etc.) so try-on can recover automatically. */
  imagesUploaded: string[];
  /** Authoritative "has the customer completed enough onboarding"
   *  signal for THIS sessionId. The loader's hasProfile only fires
   *  for Shopify-logged-in customers (it has access to that user
   *  id), so anonymous returning customers always saw hasProfile=
   *  false and got re-onboarded every reload. The init action has
   *  the sessionId, so it queries the engine directly and surfaces
   *  the answer here. The seed effect prefers this over the
   *  loader's value when present. */
  hasProfile: boolean;
};
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

  // Shop domain is in the signed App Proxy URL params (HMAC-validated
  // by authenticate.public.appProxy above). Pull it once here and
  // thread it into engine calls that need a tenant — the storefront
  // chat path is where F.2.0 enforces tenant-scoped retrieval, so
  // missing this silently used to surface as a 500 from the engine.
  const shopDomain =
    new URL(request.url).searchParams.get("shop")?.trim() ?? "";

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
    // Resolve (or create) the conversation, ensure the onboarding-
    // profile row exists, AND read the engine's profile snapshot.
    // The three engine calls touch independent tables — run them in
    // parallel to save the Mumbai-to-Mumbai round-trips on every init.
    //
    // Promise.allSettled (not Promise.all) so a transient failure
    // on any single call doesn't 500 the whole action. The init
    // response is degraded but usable in every partial-failure mode:
    //   - resolveConversation fails → no conversationId → client
    //     surfaces an init error and retries on next page load
    //   - ensureOnboardingProfile fails → no immediate impact; the
    //     ensure call is idempotent and will retry on the next photo
    //     upload / profile patch
    //   - getOnboardingStatus → three-way outcome (see helper docs):
    //       * OnboardingStatus → trust it
    //       * null  (404)     → confirmed new customer; hasProfile=false
    //       * undefined (err) → state unknown; safe-default to
    //                           hasProfile=true + imagesUploaded
    //                           non-empty so we don't push a returning
    //                           customer back through onboarding on
    //                           engine wobble
    //
    // Status call gets ENGINE_HTTP_TIMEOUT_MS (8s) explicitly — the
    // helper's default of 1500ms protects the SSR loader at the cost
    // of false negatives under engine contention; the init action has
    // a more relaxed budget and benefits from the longer ceiling.
    const [conversationRes, ensureRes, statusRes] = await Promise.allSettled([
      resolveConversation(sessionId),
      ensureOnboardingProfile(sessionId),
      getOnboardingStatus(sessionId, ENGINE_HTTP_TIMEOUT_MS),
    ]);

    if (conversationRes.status === "rejected") {
      const reason =
        conversationRes.reason instanceof Error
          ? conversationRes.reason.message
          : String(conversationRes.reason);
      logError("vibe_init_outcome", {
        session_id: sessionId,
        outcome: "conversation_failed",
        error: reason,
      });
      return json<ActionResponse>(
        { ok: false, error: `Couldn't start a conversation: ${reason}` },
        { status: 502 },
      );
    }

    // statusRes.value is OnboardingStatus | null | undefined; a rejected
    // settle treats as the same "unknown" case as undefined since
    // getOnboardingStatus shouldn't throw, but be defensive.
    const status: OnboardingStatus | null | undefined =
      statusRes.status === "fulfilled" ? statusRes.value : undefined;
    // Branch on the three-way outcome. Apply the safety-net fallback
    // ONLY when status is undefined (engine error), so a confirmed
    // new customer (null/404) still gets the new-customer flow.
    const imagesUploaded =
      status === undefined
        ? ["full_body"]
        : status === null
          ? []
          : status.images_uploaded;
    const hasProfile =
      status === undefined
        ? true
        : status === null
          ? false
          : Boolean(status.gender);
    // Log the three-way status outcome and the ensure-profile outcome
    // so dashboards can tell "new customer detected (not_found)" from
    // "engine wobble + safety net engaged (error)" and from "everything
    // worked (ok)". Pre-instrumentation, a returning customer hitting a
    // 5xx timeout silently flowed through as hasProfile=true with no
    // ops signal — re-onboarding bugs only surfaced via customer
    // reports. ensure-profile failure is non-fatal (idempotent retry on
    // next photo upload / profile patch) but worth flagging because
    // subsequent /onboarding/* calls 404 until it succeeds.
    const statusOutcome: "ok" | "not_found" | "error" =
      status === undefined ? "error" : status === null ? "not_found" : "ok";
    const ensureOutcome = ensureRes.status === "fulfilled" ? "ok" : "error";
    logInfo("vibe_init_outcome", {
      session_id: sessionId,
      conversation_id: conversationRes.value.conversation_id,
      status_outcome: statusOutcome,
      ensure_outcome: ensureOutcome,
      has_profile: hasProfile,
      images_uploaded_count: imagesUploaded.length,
      ensure_error:
        ensureRes.status === "rejected"
          ? (ensureRes.reason instanceof Error
              ? ensureRes.reason.message
              : String(ensureRes.reason))
          : undefined,
    });
    return json<ActionResponse>({
      ok: true,
      op: "init",
      conversationId: conversationRes.value.conversation_id,
      imagesUploaded,
      hasProfile,
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
      // Security-relevant: form-supplied canonical id didn't match the
      // App-Proxy-signed logged_in_customer_id. Could be benign (stale
      // tab after the customer logged out and back in as someone else)
      // or hostile (attacker trying to graft their anonymous history
      // onto someone else's Shopify account). Warn-level so it surfaces
      // on log drains' default filters without paging.
      logWarn("vibe_merge_identity_mismatch", {
        alias_session_id: sessionId,
        claimed_canonical: canonical,
        expected_logged_in_customer_id: expectedId ?? "",
      });
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
      logInfo("vibe_merge_outcome", {
        alias_session_id: sessionId,
        canonical_external_user_id: result.canonical_external_user_id,
        merged: result.merged,
      });
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
      logError("vibe_merge_outcome", {
        alias_session_id: sessionId,
        canonical_external_user_id: canonical,
        merged: false,
        error: message,
      });
      return json<ActionResponse>({ ok: false, error: message }, { status: 502 });
    }
  }

  if (op === "turn") {
    const conversationId = String(form.get("conversationId") ?? "").trim();
    const message = String(form.get("message") ?? "").trim();
    // Three mutually-exclusive attachment shapes — the composer's
    // discriminated union maps onto exactly one engine field. Only
    // one of these will be non-empty in practice.
    //
    // image_data: data URL from FileReader — base64 is whitespace-
    // sensitive so we don't trim.
    const rawImage = form.get("imageData");
    const imageData =
      typeof rawImage === "string" && rawImage.startsWith("data:")
        ? rawImage
        : "";
    const wardrobeItemId = String(form.get("wardrobeItemId") ?? "").trim();
    const wishlistProductId = String(form.get("wishlistProductId") ?? "").trim();
    const hasAttachment = !!(imageData || wardrobeItemId || wishlistProductId);

    if (!conversationId || !message) {
      return json<ActionResponse>(
        { ok: false, error: "Missing conversationId or message" },
        { status: 400 },
      );
    }

    // Pairing-anchor enforcement. The engine's
    // _message_requests_pairing (orchestrator.py:1221) only flips
    // intent to PAIRING_REQUEST — and only then injects the attached
    // garment as the outfit's anchor — when the user's prose contains
    // a recognized pairing phrase ("what goes with this", "build an
    // outfit around", "pair this", etc.). Customers don't naturally
    // type those phrases.
    //
    // Append an explicit pairing trigger whenever ANY attachment is
    // present (image upload OR wardrobe selection OR wishlist
    // selection — same intent on the engine side). "Build an outfit
    // around this attached piece" matches the wardrobe_pairing_phrases
    // branch unconditionally so the override fires every time. The
    // user's bubble in the UI still shows their original text — we
    // return ``message`` (not engineMessage) below so the augmentation
    // is invisible.
    const engineMessage = hasAttachment
      ? `${message} Build an outfit around this attached piece.`
      : message;

    // Log the pairing-rewrite event explicitly so we can answer "did
    // the silent message augmentation fire?" without scraping the
    // engine's prompt logs. attachment_kind enables a per-source split
    // (image upload vs wardrobe pick vs wishlist pick). Log even when
    // no rewrite happened so the per-turn rate is computable.
    const attachmentKind: "image" | "wardrobe" | "wishlist" | "none" = imageData
      ? "image"
      : wardrobeItemId
        ? "wardrobe"
        : wishlistProductId
          ? "wishlist"
          : "none";
    logInfo("vibe_turn_pairing_rewrite", {
      session_id: sessionId,
      conversation_id: conversationId,
      rewrite_applied: hasAttachment,
      attachment_kind: attachmentKind,
      original_message_length: message.length,
    });

    const turn = await startTurn({
      conversationId,
      userId: sessionId,
      message: engineMessage,
      imageData: imageData || undefined,
      wardrobeItemId: wardrobeItemId || undefined,
      wishlistProductId: wishlistProductId || undefined,
      shopDomain,
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
    case "height-waist":
      return "Measurements saved";
  }
}

function skippedSummary(kind: OnboardingMessageKind): string {
  switch (kind) {
    case "photos":
      return "Photos skipped";
    case "gender-dob":
      return "Basics skipped";
    case "height-waist":
      return "Measurements skipped";
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

// Steps the seed effect treats as "the customer is still in the
// initial parallel onboarding phase" — photos + gender-DOB rendered
// side-by-side. Anything past this and the customer has either
// completed one of the initial cards or moved on to the height-waist
// follow-up card.
const INITIAL_PHASE: ReadonlySet<OnboardingStep> = new Set<OnboardingStep>([
  "welcome",
  "photos",
  "gender-dob",
]);

// Templated prompt the assistant sends right after onboarding wraps
// (and analysis completes, if the customer uploaded photos). Carries
// a concrete example so the customer knows what to type next.
const WHAT_LOOKING_FOR_PROMPT =
  "All set — I've taken a read on your style. What would you like to wear? Try something like \"Dress me for a dinner date\" or \"I need an outfit for a work presentation\".";

export default function ConversationPage() {
  const {
    mockMode,
    loggedInCustomerId,
    hasProfile: hasProfileFromLoader,
    themeOverrides,
  } = useLoaderData<typeof loader>();
  const [sessionId, setSessionId] = useState("");
  const [conversationId, setConversationId] = useState("");
  // Engine's photo-presence snapshot at session init. The seed effect
  // uses this to re-inject the PhotosCard when the customer's
  // onboarding-step localStorage says "past photos" but the engine
  // has no full_body row on file (volume rebuild / manual delete / etc).
  // `null` while the init request is in flight — distinguishes from
  // "loaded and empty".
  const [imagesUploaded, setImagesUploaded] = useState<string[] | null>(null);
  // Authoritative hasProfile snapshot from the init action. Mirrors
  // the loader's shopify-only check, but works for anonymous
  // customers too (the loader has no access to the localStorage
  // sessionId, but the init action does). `null` while the init
  // request is in flight.
  const [hasProfileFromInit, setHasProfileFromInit] = useState<boolean | null>(
    null,
  );
  // Effective hasProfile used by the seed effect: prefer init when
  // it's landed (most accurate, fires for both anonymous and Shopify
  // identities); fall back to the loader hint (Shopify-only) for the
  // brief window before init responds.
  const hasProfile = hasProfileFromInit ?? hasProfileFromLoader;
  const [initError, setInitError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  // Short-lived error from the composer's attach button (file too big,
  // wrong type, unreadable). Distinct from initError, which signals a
  // hard session-setup failure the customer can't recover from.
  const [attachError, setAttachError] = useState<string | null>(null);
  // Post-onboarding profile analysis state. The engine kicks off
  // analysis automatically when the customer uploads each photo
  // (handleOnboardingPhotoUploaded fires phase1/phase2). We poll the
  // status endpoint once all onboarding cards have resolved so the
  // chat can render an "Analyzing your style…" indicator and then
  // emit the next-action prompt when the engine is done.
  //   idle      → onboarding still in flight (cards active, or not
  //              yet completed). No indicator, no follow-up.
  //   running   → all cards resolved + photos were uploaded. Show
  //              the analyzing indicator; poll until done.
  //   complete  → analysis returned a terminal status (or photos
  //              were skipped, so analysis can't run). Emit the
  //              templated follow-up prompt and stop here.
  const [analysisPhase, setAnalysisPhase] = useState<
    "idle" | "running" | "complete"
  >("idle");
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
      setImagesUploaded(data.imagesUploaded ?? []);
      setHasProfileFromInit(Boolean(data.hasProfile));
      setInitError(null);
    } else if (!data.ok) {
      setInitError(data.error || "Couldn't start a conversation.");
    }
  }, [initFetcher.state, initFetcher.data]);

  // Seed the feed once per page life. Three shapes:
  //
  //   hasProfile = true, photos on file
  //     → welcome-back message only. Step advances to "done".
  //
  //   hasProfile = true, photos missing on engine
  //     → welcome-back + PhotosCard. Engine reported no full_body
  //       row (volume rebuild / manual delete) so we override
  //       localStorage's "past photos" pointer and re-emit the card.
  //       Step rolls back to "photos" so onAdvance promotes correctly.
  //
  //   hasProfile = false
  //     → existing new-customer flow (welcome + photos + gender-DOB
  //       stacked, or resume mid-flow from persisted step).
  //
  // Waits until imagesUploaded is non-null — the init response hasn't
  // landed yet otherwise and we'd seed against a stale guess. seededRef
  // prevents double-seeding when sessionId/conversationId/imagesUploaded
  // settle on different ticks.
  useEffect(() => {
    if (!sessionId || !conversationId) return;
    if (imagesUploaded === null) return;
    if (seededRef.current) return;
    seededRef.current = true;

    const needsPhotos = !imagesUploaded.includes("full_body");

    // If the engine reports the photo missing, clear any stale
    // "photos" resolution from localStorage so the seed branches
    // below re-emit the card. Otherwise resolved.has("photos") would
    // suppress the new-customer-path emission below.
    if (needsPhotos) {
      unmarkKindResolved("photos");
    }

    if (hasProfile) {
      const seeded: ChatMessage[] = [
        { role: "assistant", text: WELCOME_RETURNING },
      ];
      if (needsPhotos) {
        seeded.push({ role: "onboarding", kind: "photos", status: "active" });
        onboardingStepRef.current = "photos";
        writeOnboardingStep("photos");
      } else {
        onboardingStepRef.current = "done";
        writeOnboardingStep("done");
      }
      setMessages(seeded);
      return;
    }

    // New-customer path. Two layers of persistence:
    //   - vibe_onboarding_step: the furthest *sequence position* the
    //     customer has reached. Drives where the next card slots in
    //     once the initial parallel pair clears.
    //   - vibe_onboarding_resolved_kinds: explicit list of cards
    //     already saved/skipped. A reload during the parallel
    //     photos+gender-DOB phase consults this so a completed
    //     photos card doesn't re-emit (unless the engine just told
    //     us the photo went missing — handled above).
    let persisted = readOnboardingStep();
    // If the engine reports photos missing but localStorage already
    // advanced past them, roll the cursor back so the initial-phase
    // branch fires and emits the card.
    if (needsPhotos && !INITIAL_PHASE.has(persisted)) {
      persisted = "photos";
      writeOnboardingStep(persisted);
    }
    const resolved = readResolvedKinds();
    const isInitialPhase = INITIAL_PHASE.has(persisted);

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
  }, [sessionId, conversationId, hasProfile, imagesUploaded]);

  // Detect "onboarding has wrapped up" and arm the analysis-watching
  // state machine. Triggers exactly once per page life when:
  //   - there's at least one onboarding card in the feed (i.e. the
  //     customer entered the flow on this session)
  //   - none of those cards are still active
  //   - the analysis state is still "idle"
  //
  // If the customer completed the PhotosCard (status === "completed"
  // for the photos kind), we poll for analysis. If they skipped
  // photos, analysis can't run, so we jump straight to "complete"
  // and emit the follow-up prompt.
  useEffect(() => {
    if (analysisPhase !== "idle") return;
    const onbMessages = messages.filter((m) => m.role === "onboarding");
    if (onbMessages.length === 0) return;
    if (onbMessages.some((m) => m.status === "active")) return;
    // Short-circuit: if the templated follow-up is already somewhere
    // in the history, skip polling. Defensive against future paths
    // where seeded messages might rehydrate a completed prompt — and
    // saves a round-trip on returning sessions.
    if (
      messages.some(
        (m) => m.role === "assistant" && m.text === WHAT_LOOKING_FOR_PROMPT,
      )
    ) {
      setAnalysisPhase("complete");
      return;
    }
    const photosCompleted = onbMessages.some(
      (m) => m.kind === "photos" && m.status === "completed",
    );
    setAnalysisPhase(photosCompleted ? "running" : "complete");
  }, [messages, analysisPhase]);

  // Poll the engine's analysis status until it terminates.
  // 2s interval — analysis typically completes in 10-20s, so a
  // handful of polls is plenty. Bails on unmount or phase change.
  useEffect(() => {
    if (analysisPhase !== "running") return;
    if (!sessionId) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const resp = await fetch(
          `/apps/vibe/api/onboarding/analysis-status?sessionId=${encodeURIComponent(sessionId)}`,
        );
        if (cancelled) return;
        const data = (await resp.json()) as {
          ok: boolean;
          status?: string;
        };
        if (
          data.ok &&
          (data.status === "completed" || data.status === "failed")
        ) {
          setAnalysisPhase("complete");
          return;
        }
      } catch {
        // Transient failure — try again on the next tick.
      }
      if (!cancelled) setTimeout(tick, 2000);
    };
    // First poll fires after a short delay so the indicator gets a
    // moment to render rather than blinking on/off on a cache hit.
    const timer = setTimeout(tick, 600);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [analysisPhase, sessionId]);

  // When analysis completes (or is skipped), emit the templated
  // follow-up prompt. Idempotency check scans the WHOLE history,
  // not just the last message — a customer who sent a turn after
  // onboarding (assistant prompt → user message → reload) would
  // otherwise see the prompt appended again.
  useEffect(() => {
    if (analysisPhase !== "complete") return;
    setMessages((prev) => {
      const alreadyEmitted = prev.some(
        (m) => m.role === "assistant" && m.text === WHAT_LOOKING_FOR_PROMPT,
      );
      if (alreadyEmitted) return prev;
      return [
        ...prev,
        { role: "assistant", text: WHAT_LOOKING_FOR_PROMPT },
      ];
    });
  }, [analysisPhase]);

  // Auto-scroll to bottom when messages or pending state changes.
  useEffect(() => {
    const el = feedRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, pending]);

  // When the submit action returns, start polling. The user message
  // bubble was already appended optimistically in handleSubmit — we
  // only need the job id here to arm the poll loop.
  useEffect(() => {
    if (submitFetcher.state !== "idle") return;
    const data = submitFetcher.data;
    if (!data) return;
    // Action failed: append an assistant error so the conversation
    // doesn't dead-end on a lone user bubble.
    if (!data.ok) {
      if (consumedTurnIdRef.current === `err:${data.error}`) return;
      consumedTurnIdRef.current = `err:${data.error}`;
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: data.error || "Couldn't send that — try again." },
      ]);
      return;
    }
    if (data.op !== "turn") return;
    if (consumedTurnIdRef.current === data.jobId) return;
    consumedTurnIdRef.current = data.jobId;

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
    // Route the attachment to the right engine field by kind. The
    // server-side action passes one of three mutually-exclusive
    // anchors to startTurn — image_data / wardrobe_item_id /
    // wishlist_product_id — exactly matching the engine's CreateTurnRequest.
    if (attachment) {
      if (attachment.kind === "image") {
        form.set("imageData", attachment.dataUrl);
      } else if (attachment.kind === "wardrobe") {
        form.set("wardrobeItemId", attachment.itemId);
      } else if (attachment.kind === "wishlist") {
        form.set("wishlistProductId", attachment.productId);
      }
    }
    // Clear the consumed-turn marker so the next action response — be
    // it a jobId or an error — gets picked up by the effect below.
    // Without this, two submissions in a row that produce the same
    // stable response (e.g. same error twice) would silently skip the
    // second one because the ref still matches.
    consumedTurnIdRef.current = null;
    submitFetcher.submit(form, { method: "post", encType: "multipart/form-data" });

    // Optimistic user-message append. We render the customer's bubble
    // (with attached-image thumbnail, if any) as soon as they hit send,
    // BEFORE the action returns the job id. Reads more responsively
    // than waiting on the round-trip, and surfaces what was sent even
    // if the engine errors. The success effect below only sets pending
    // state — no second append, no duplicate bubble.
    //
    // The thumbnail source depends on attachment kind: image uploads
    // carry a data URL; wardrobe / wishlist selections carry an
    // engine-side image URL (already routed through the proxy if it
    // was a local /v1/onboarding/images/local path).
    const imagePreview =
      attachment?.kind === "image"
        ? attachment.dataUrl
        : attachment?.imageUrl;
    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        text: message,
        imagePreview,
      },
    ]);

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
      // Returning customer (hasProfile=true) only sees onboarding
      // cards in the recovery path — e.g. PhotosCard re-injected
      // because the engine lost the photo. Their gender / DOB /
      // measurements are already on the engine; promoting through
      // the full new-customer ladder would force them to re-enter
      // basics they've already saved. Jump straight to "done" after
      // they resolve the recovery card.
      if (hasProfile) {
        return next;
      }
      // New-customer flow: advance to the next sequential card.
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
    // Mirror transformAdvance's hasProfile branch: when a returning
    // customer has resolved the last active onboarding card (the
    // recovery PhotosCard, typically), persist step as "done" rather
    // than chaining to the next sequential step.
    const step: OnboardingStep = anyActive
      ? (lastOnb.kind as OnboardingStep)
      : hasProfile
        ? "done"
        : nextStep(lastOnb.kind as OnboardingStep);
    if (onboardingStepRef.current !== step) {
      onboardingStepRef.current = step;
      writeOnboardingStep(step);
    }
  }, [messages, hasProfile]);

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
      <ThemeOverridesStyle overrides={themeOverrides} />
      {/* PR #480: replicated merchant header replaces the AURA-branded
          conv-header. The customer should never feel they left the
          store — the header reads as the merchant's, with "Find your
          Vibe" / "Your Vibes" appearing as menu items that PR 4
          injects into their main-menu. Mock-mode + sign-in pill were
          dropped from this surface; Shopify handles login via the
          merchant's own nav, and mock-mode is a developer affordance
          surfaced in console / engine.server.ts already. */}
      <MerchantHeader overrides={themeOverrides} />

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
        {/* Post-onboarding analysis indicator. Renders while we poll
            the engine for the photo-analysis run to finish; replaced
            by the WHAT_LOOKING_FOR_PROMPT assistant message once the
            status flips to "completed". */}
        {analysisPhase === "running" && (
          <div className="conv-stage">Analyzing your style…</div>
        )}
      </div>

      <Composer
        sessionId={sessionId}
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
