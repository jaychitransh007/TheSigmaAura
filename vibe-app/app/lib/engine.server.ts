// Typed client for the Vibe Engine API (today's `platform_core`
// FastAPI server). Three endpoints in the v1 turn loop:
//
//   1. POST /v1/conversations/resolve            {user_id}                → conversation
//   2. POST /v1/conversations/{id}/turns/start   {user_id, message, ...}  → job_id
//   3. GET  /v1/conversations/{id}/turns/{jobId}/status                   → stages + result
//
// Both POST bodies require `user_id` — the engine's CreateTurnRequest
// pydantic model has it as a min-length-1 string. Omitting it 422s.
//
// Mock mode is on when ENGINE_API_URL is unset OR VIBE_USE_MOCK=true.
// Lets the Vibe app UI be built and shipped against canned responses
// before the engine is deployed to Fly.io (Mumbai `bom`). Swap to the
// real URL via Vercel env vars in D.C.2g — no code change needed.

// ─────────────────────────────────────────────────────────────────────
// Response shapes (loose for now; tighten when engine is reachable)
// ─────────────────────────────────────────────────────────────────────

export type ResolveConversationResponse = {
  conversation_id: string;
  user_id: string;
  is_new: boolean;
};

export type StartTurnResponse = {
  conversation_id: string;
  job_id: string;
  status: "running" | "succeeded" | "failed";
};

export type TurnStage = {
  timestamp: string;
  stage: string;
  detail?: string;
  message?: string;
};

export type TurnStatusResponse = {
  conversation_id: string;
  job_id: string;
  status: "running" | "succeeded" | "failed";
  stages: TurnStage[];
  /** Final turn result (only present when status === "succeeded"). */
  result: TurnResult | null;
  /** Error message (only present when status === "failed"). */
  error: string;
};

export type OutfitItem = {
  garment_id: string;
  title: string;
  brand?: string;
  price?: number;
  product_url?: string;
  image_url?: string;
  /** Indexes the catalog row for downstream Add-to-Cart wiring (D.C.7). */
  shopify_variant_ids?: Record<string, string>; // size → variant gid
};

export type Outfit = {
  outfit_id: string;
  name?: string;
  reasoning?: string;
  fashion_score?: number;
  items: OutfitItem[];
  tryon_image_url?: string;
};

export type TurnResult = {
  turn_id: string;
  message: string;
  outfits: Outfit[];
  follow_ups?: { label: string; prompt: string; group?: string }[];
};

// ─────────────────────────────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────────────────────────────

const ENGINE_API_URL = process.env.ENGINE_API_URL?.trim() ?? "";
const FORCE_MOCK = process.env.VIBE_USE_MOCK === "true";
const USE_MOCK = FORCE_MOCK || ENGINE_API_URL.length === 0;

/** Exposed so route loaders can render a small "Mock mode" badge in dev. */
export const ENGINE_MOCK_ACTIVE = USE_MOCK;

// ─────────────────────────────────────────────────────────────────────
// Real HTTP client
//
// Timeouts (D.C.2g): every engine call uses AbortSignal.timeout to
// cap the wait. Hobby Vercel functions have a 60s ceiling — we set
// internal timeouts well below that so a hung engine doesn't burn
// the function's full budget.
//
// Engine endpoints in practice:
//   - resolve / start-turn / poll-status: short (≪ 1s) — 8s cap is
//     generous, fails fast if engine is unreachable.
// Long-running work (the 30-60s turn pipeline) lives behind the
// async job pattern; we never block on it in a single HTTP call.
// ─────────────────────────────────────────────────────────────────────

const ENGINE_HTTP_TIMEOUT_MS = 8_000;

class EngineError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "EngineError";
  }
}

function fetchTimeout(): AbortSignal {
  // AbortSignal.timeout is available in Node 18+ / Edge runtimes.
  return AbortSignal.timeout(ENGINE_HTTP_TIMEOUT_MS);
}

async function readErrorBody(resp: Response): Promise<string> {
  try {
    const text = await resp.text();
    return text.slice(0, 200);
  } catch {
    return "";
  }
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${ENGINE_API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: fetchTimeout(),
    });
  } catch (e) {
    const reason = e instanceof Error ? e.message : String(e);
    throw new EngineError(0, `Engine ${path} unreachable: ${reason}`);
  }
  if (!resp.ok) {
    throw new EngineError(resp.status, `Engine ${path} → ${resp.status}: ${await readErrorBody(resp)}`);
  }
  return (await resp.json()) as T;
}

async function getJson<T>(path: string): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${ENGINE_API_URL}${path}`, { signal: fetchTimeout() });
  } catch (e) {
    const reason = e instanceof Error ? e.message : String(e);
    throw new EngineError(0, `Engine ${path} unreachable: ${reason}`);
  }
  if (!resp.ok) {
    throw new EngineError(resp.status, `Engine ${path} → ${resp.status}: ${await readErrorBody(resp)}`);
  }
  return (await resp.json()) as T;
}

export { EngineError };

// ─────────────────────────────────────────────────────────────────────
// Public API
// ─────────────────────────────────────────────────────────────────────

export async function resolveConversation(userId: string): Promise<ResolveConversationResponse> {
  if (USE_MOCK) {
    return {
      conversation_id: `mock-conv-${userId.slice(0, 8)}`,
      user_id: userId,
      is_new: true,
    };
  }
  return postJson<ResolveConversationResponse>("/v1/conversations/resolve", { user_id: userId });
}

/**
 * Idempotently ensure an onboarding_profiles row exists for this user.
 * Vibe customers never go through OTP, so the engine's image upload /
 * profile patch routes would 404 ("User not found") on the very first
 * onboarding-card interaction without this. Safe to call repeatedly.
 */
export async function ensureOnboardingProfile(userId: string): Promise<void> {
  if (USE_MOCK) return;
  await postJson<{ user_id: string; saved: boolean }>(
    "/v1/onboarding/profile/ensure",
    { user_id: userId },
  );
}

export async function startTurn(args: {
  conversationId: string;
  userId: string;
  message: string;
  imageData?: string;
}): Promise<StartTurnResponse> {
  if (USE_MOCK) {
    // Encode start timestamp into the job_id so pollTurn can compute
    // elapsed-time-based stage progression without server-side state.
    return {
      conversation_id: args.conversationId,
      job_id: `mock-job-${Date.now()}`,
      status: "running",
    };
  }
  return postJson<StartTurnResponse>(
    `/v1/conversations/${encodeURIComponent(args.conversationId)}/turns/start`,
    {
      user_id: args.userId,
      message: args.message,
      // "vibe_storefront" tells the engine to bypass the onboarding
      // gate and the minimum-profile validator. Customers can chat
      // with any combination of skipped onboarding fields; quality
      // degrades gracefully (architect runs in "minimal" richness,
      // rater drops body_harmony, etc.).
      channel: "vibe_storefront",
      // Omit when undefined — JSON.stringify drops undefined keys, and
      // the engine's CreateTurnRequest defaults image_data to "" via
      // pydantic. Avoids shipping empty strings for fields the caller
      // didn't set.
      image_data: args.imageData,
    },
  );
}

export async function pollTurn(args: {
  conversationId: string;
  jobId: string;
}): Promise<TurnStatusResponse> {
  if (USE_MOCK) {
    return mockTurnResult(args);
  }
  const raw = await getJson<RawEngineStatusResponse>(
    `/v1/conversations/${encodeURIComponent(args.conversationId)}/turns/${encodeURIComponent(args.jobId)}/status`,
  );
  return normalizeStatus(raw);
}

// ─────────────────────────────────────────────────────────────────────
// In-chat onboarding helpers (D.O.2)
//
// Vibe customers can save profile fields and upload photos one-at-a-time
// from inside the chat. Each helper is a thin pass-through to the
// existing platform_core onboarding endpoints. Identity is the
// localStorage session id (D.S.3a), threaded through as user_id.
//
// Mock mode is intentionally lax — returns optimistic success so the
// UI flow can be built / tested before ENGINE_API_URL is set.
// ─────────────────────────────────────────────────────────────────────

export type OnboardingImageCategory = "full_body" | "headshot";
export type OnboardingProfileField =
  | "name"
  | "date_of_birth"
  | "gender"
  | "height_cm"
  | "waist_cm";

export type OnboardingImageUploadResponse = {
  user_id: string;
  category: OnboardingImageCategory;
  saved: boolean;
  encrypted_filename?: string;
  file_path?: string;
};

export type OnboardingProfileResponse = {
  user_id: string;
  saved: boolean;
  message?: string;
};

export type OnboardingAnalysisResponse = {
  user_id: string;
  analysis_run_id?: string;
  status: string;
  message?: string;
};

export async function uploadOnboardingImage(args: {
  userId: string;
  category: OnboardingImageCategory;
  file: Blob;
  filename: string;
}): Promise<OnboardingImageUploadResponse> {
  if (USE_MOCK) {
    return {
      user_id: args.userId,
      category: args.category,
      saved: true,
      encrypted_filename: `mock-${args.category}-${Date.now()}.jpg`,
      file_path: `mock://${args.userId}/${args.category}`,
    };
  }
  const form = new FormData();
  form.append("user_id", args.userId);
  form.append("file", args.file, args.filename);

  let resp: Response;
  try {
    resp = await fetch(
      `${ENGINE_API_URL}/v1/onboarding/images/${encodeURIComponent(args.category)}`,
      { method: "POST", body: form, signal: fetchTimeout() },
    );
  } catch (e) {
    const reason = e instanceof Error ? e.message : String(e);
    throw new EngineError(0, `Engine onboarding image upload unreachable: ${reason}`);
  }
  if (!resp.ok) {
    throw new EngineError(
      resp.status,
      `Engine onboarding image upload → ${resp.status}: ${await readErrorBody(resp)}`,
    );
  }
  return (await resp.json()) as OnboardingImageUploadResponse;
}

export async function patchOnboardingProfile(args: {
  userId: string;
  field: OnboardingProfileField;
  value: string | number;
}): Promise<OnboardingProfileResponse> {
  if (USE_MOCK) {
    return { user_id: args.userId, saved: true, message: "mock saved" };
  }
  // platform_core's PATCH /onboarding/profile/partial accepts a partial
  // body with any subset of the profile fields. We send exactly one
  // field per call so the UI can save incrementally as the customer
  // answers each card.
  const body: Record<string, unknown> = { user_id: args.userId };
  body[args.field] = args.value;
  let resp: Response;
  try {
    resp = await fetch(`${ENGINE_API_URL}/v1/onboarding/profile/partial`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: fetchTimeout(),
    });
  } catch (e) {
    const reason = e instanceof Error ? e.message : String(e);
    throw new EngineError(0, `Engine profile patch unreachable: ${reason}`);
  }
  if (!resp.ok) {
    throw new EngineError(
      resp.status,
      `Engine profile patch → ${resp.status}: ${await readErrorBody(resp)}`,
    );
  }
  return (await resp.json()) as OnboardingProfileResponse;
}

/**
 * Trigger an analysis phase against whatever profile data has been
 * saved so far. The engine's two phase endpoints have prerequisites
 * (phase1: gender + headshot, phase2: gender + DOB + both photos);
 * if the prereq isn't met, the engine 400s and we surface that.
 * "full" requires onboarding_complete=true which Vibe never sets, so
 * we don't expose it here.
 */
export async function startOnboardingAnalysis(args: {
  userId: string;
  phase: "phase1" | "phase2";
}): Promise<OnboardingAnalysisResponse> {
  if (USE_MOCK) {
    return {
      user_id: args.userId,
      analysis_run_id: `mock-run-${Date.now()}`,
      status: `${args.phase}_started`,
      message: "mock analysis started",
    };
  }
  const path =
    args.phase === "phase1"
      ? "/v1/onboarding/analysis/start-phase1"
      : "/v1/onboarding/analysis/start-phase2";
  return postJson<OnboardingAnalysisResponse>(path, { user_id: args.userId });
}

// ─────────────────────────────────────────────────────────────────────
// Engine ↔ Vibe response shape normalization
//
// The engine (platform_core.api_schemas) returns:
//   status: "running" | "completed" | "failed"
//   result.assistant_message
//   result.outfits: [{ rank, title, reasoning, fashion_score_pct,
//                      tryon_image, items: [...] }]
//   result.follow_up_suggestions: string[]
//
// The Vibe app's TurnStatusResponse / Outfit / OutfitItem shapes were
// designed for the customer chat UI (different field names, numeric
// fashion_score, follow-ups as chips). Normalize at this boundary so
// route code only ever sees the Vibe shape.
//
// shopify_variant_ids is populated by B.8's capture_shopify_gids.py
// backfill. The engine carries shopify_product_id + shopify_variant_ids
// (keyed by size) through OutfitItem; we surface them on Vibe's
// Outfit.items[] so cart.client.ts can resolve a chosen size to a
// real variant gid. Items missing the mapping arrive with an empty
// object and Vibe's UI surfaces a disabled CTA — same behaviour as
// mock-prefixed dev variants.
// ─────────────────────────────────────────────────────────────────────

type RawEngineStatusResponse = {
  conversation_id: string;
  job_id: string;
  status: string;
  stages?: TurnStage[];
  error?: string;
  result?: RawEngineTurnResult | null;
};

type RawEngineTurnResult = {
  turn_id?: string;
  assistant_message?: string;
  outfits?: RawEngineOutfit[];
  follow_up_suggestions?: string[];
};

type RawEngineOutfit = {
  rank?: number;
  title?: string;
  reasoning?: string;
  fashion_score_pct?: number;
  tryon_image?: string;
  items?: RawEngineOutfitItem[];
};

type RawEngineOutfitItem = {
  product_id?: string;
  title?: string;
  image_url?: string;
  price?: string;
  product_url?: string;
  shopify_product_id?: string;
  shopify_variant_ids?: Record<string, string>;
};

function normalizeStatus(raw: RawEngineStatusResponse): TurnStatusResponse {
  // Engine emits "completed" today; accept "succeeded" too so a future
  // engine-side rename to align with our vocabulary won't silently fall
  // back to "running" and hang the polling loop.
  const status: TurnStatusResponse["status"] =
    raw.status === "completed" || raw.status === "succeeded"
      ? "succeeded"
      : raw.status === "failed"
        ? "failed"
        : "running";
  return {
    conversation_id: raw.conversation_id,
    job_id: raw.job_id,
    status,
    stages: raw.stages ?? [],
    error: raw.error ?? "",
    result: raw.result ? normalizeResult(raw.result) : null,
  };
}

function normalizeResult(raw: RawEngineTurnResult): TurnResult {
  return {
    turn_id: raw.turn_id ?? "",
    message: raw.assistant_message ?? "",
    outfits: (raw.outfits ?? []).map((card, idx) => normalizeOutfit(card, idx)),
    follow_ups: (raw.follow_up_suggestions ?? []).map((s) => ({
      label: s,
      prompt: s,
    })),
  };
}

function normalizeOutfit(card: RawEngineOutfit, idx: number): Outfit {
  // Prefer the engine's rank; fall back to array index. Prefix each
  // path with a namespace (r/i) so a ranked outfit at rank N can't
  // collide with an unranked outfit at index N — e.g. `outfit-r1` vs
  // `outfit-i1`.
  const hasRank = typeof card.rank === "number" && card.rank > 0;
  const id = hasRank ? `r${card.rank}` : `i${idx}`;
  return {
    outfit_id: `outfit-${id}`,
    name: card.title ?? "",
    reasoning: card.reasoning ?? "",
    fashion_score: card.fashion_score_pct ?? 0,
    tryon_image_url: card.tryon_image || undefined,
    items: (card.items ?? []).map(normalizeItem),
  };
}

function normalizeItem(item: RawEngineOutfitItem): OutfitItem {
  // engine price is a string ("1234") → number for the UI to format.
  // Falsy parse → undefined so the card omits the price row instead of
  // showing 0.
  const priceNum = item.price ? Number.parseFloat(item.price) : NaN;
  // shopify_variant_ids is optional — empty when B.8 hasn't mapped
  // this product yet. Pass through only if non-empty so the cart-CTA
  // detection (cart.client.ts) can distinguish "real cart available"
  // from "no mapping" by presence of the field.
  const variantIds = item.shopify_variant_ids ?? {};
  return {
    garment_id: item.product_id ?? "",
    title: item.title ?? "",
    price: Number.isFinite(priceNum) ? priceNum : undefined,
    product_url: item.product_url || undefined,
    image_url: item.image_url || undefined,
    shopify_variant_ids:
      Object.keys(variantIds).length > 0 ? variantIds : undefined,
  };
}

// ─────────────────────────────────────────────────────────────────────
// Mock turn — minimal but realistic enough to wire the UI against.
// Returns a "succeeded" status with one stylist-flavored outfit and a
// few follow-up chips. Refined further when the real engine lands.
// ─────────────────────────────────────────────────────────────────────

// Mock turn — simulates a ~5s engine turn with progressive stage events.
// Each call decodes the start time embedded in the job_id and returns
// the stages that "would have completed" by now. After ~5s elapsed,
// returns status="succeeded" with a realistic outfit response.
//
// 5s is short enough to not annoy in dev but long enough to demo the
// StageIndicator and exercise the polling loop. Real engine turns are
// 30-60s; UI behaves identically — only the wall-clock differs.

const MOCK_STAGE_SCHEDULE: Array<{ atMs: number; stage: string; message: string }> = [
  { atMs: 800, stage: "planner_complete", message: "Reading your style…" },
  { atMs: 1800, stage: "architect_complete", message: "Building the outfit shape…" },
  { atMs: 3000, stage: "composer_complete", message: "Composing the look…" },
  { atMs: 4000, stage: "rater_complete", message: "Checking the fit…" },
  { atMs: 5000, stage: "tryon_complete", message: "Rendering try-on…" },
];

function mockTurnResult(args: { conversationId: string; jobId: string }): TurnStatusResponse {
  // job_id format: `mock-job-{timestamp_ms}`
  const startedAt = Number.parseInt(args.jobId.split("-").pop() ?? "0", 10) || Date.now();
  const elapsed = Math.max(0, Date.now() - startedAt);

  const stages = MOCK_STAGE_SCHEDULE
    .filter((s) => elapsed >= s.atMs)
    .map((s) => ({
      timestamp: new Date(startedAt + s.atMs).toISOString(),
      stage: s.stage,
      message: s.message,
    }));

  const done = elapsed >= MOCK_STAGE_SCHEDULE[MOCK_STAGE_SCHEDULE.length - 1].atMs;

  return {
    conversation_id: args.conversationId,
    job_id: args.jobId,
    status: done ? "succeeded" : "running",
    stages,
    error: "",
    result: done ? mockResultBody(args.jobId) : null,
  };
}

function mockResultBody(jobId: string): TurnResult {
  // Placeholder images from picsum (deterministic per seed) so the
  // outfit card has something to render. Swapped for real catalog
  // images when ENGINE_API_URL is set.
  const pic = (seed: string, w = 400, h = 533) =>
    `https://picsum.photos/seed/${seed}/${w}/${h}`;

  return {
    turn_id: `mock-turn-${jobId.slice(-6)}`,
    message:
      "Here's a look that should work for a relaxed evening out — a fluid silk dress paired with low-heel mules. Easy to dress up or down depending on the spot.",
    outfits: [
      {
        outfit_id: "mock-outfit-1",
        name: "Champagne Drift",
        reasoning:
          "Soft drape carries the evening light, warm tones flatter your palette, the silhouette stays clean without effort.",
        fashion_score: 87,
        tryon_image_url: pic("vibe-tryon-1", 600, 800),
        items: [
          {
            garment_id: "mock-garment-1",
            title: "Champagne Silk Slip Dress",
            brand: "Nicobar",
            price: 4188,
            product_url: "https://thesigmavibe.shop/products/champagne-silk-slip-dress-mock",
            image_url: pic("vibe-dress-1"),
            // Mock variant gids — cart.client.ts detects "mock-" and
            // refuses the add (real engine response will have proper
            // gid://shopify/ProductVariant/<numeric> values).
            shopify_variant_ids: {
              XS: "gid://shopify/ProductVariant/mock-1-xs",
              S: "gid://shopify/ProductVariant/mock-1-s",
              M: "gid://shopify/ProductVariant/mock-1-m",
              L: "gid://shopify/ProductVariant/mock-1-l",
              XL: "gid://shopify/ProductVariant/mock-1-xl",
            },
          },
          {
            garment_id: "mock-garment-2",
            title: "Tan Leather Mules",
            brand: "Off Duty",
            price: 2388,
            product_url: "https://thesigmavibe.shop/products/tan-leather-mules-mock",
            image_url: pic("vibe-mules-1"),
            shopify_variant_ids: {
              XS: "gid://shopify/ProductVariant/mock-2-xs",
              S: "gid://shopify/ProductVariant/mock-2-s",
              M: "gid://shopify/ProductVariant/mock-2-m",
              L: "gid://shopify/ProductVariant/mock-2-l",
              XL: "gid://shopify/ProductVariant/mock-2-xl",
            },
          },
        ],
      },
    ],
    follow_ups: [
      { label: "Show me something edgier", prompt: "show me something edgier", group: "Show Alternatives" },
      { label: "What if it rains?", prompt: "what if it rains", group: "Improve It" },
      { label: "Add a jacket", prompt: "add a jacket to this look", group: "Shop The Gap" },
    ],
  };
}
