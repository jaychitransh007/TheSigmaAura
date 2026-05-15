// Typed client for the Vibe Engine API (today's `platform_core`
// FastAPI server). Three endpoints in the v1 turn loop:
//
//   1. POST /v1/conversations/resolve     {user_id}        → conversation
//   2. POST /v1/conversations/{id}/turns/start {message}   → job_id
//   3. GET  /v1/conversations/{id}/turns/{jobId}/status    → stages + result
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
// ─────────────────────────────────────────────────────────────────────

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${ENGINE_API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`Engine ${path} → ${resp.status}: ${text.slice(0, 200)}`);
  }
  return (await resp.json()) as T;
}

async function getJson<T>(path: string): Promise<T> {
  const resp = await fetch(`${ENGINE_API_URL}${path}`);
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`Engine ${path} → ${resp.status}: ${text.slice(0, 200)}`);
  }
  return (await resp.json()) as T;
}

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

export async function startTurn(args: {
  conversationId: string;
  message: string;
  imageUrl?: string;
}): Promise<StartTurnResponse> {
  if (USE_MOCK) {
    return {
      conversation_id: args.conversationId,
      job_id: `mock-job-${Date.now()}`,
      status: "running",
    };
  }
  return postJson<StartTurnResponse>(
    `/v1/conversations/${encodeURIComponent(args.conversationId)}/turns/start`,
    { message: args.message, image_url: args.imageUrl },
  );
}

export async function pollTurn(args: {
  conversationId: string;
  jobId: string;
}): Promise<TurnStatusResponse> {
  if (USE_MOCK) {
    return mockTurnResult(args);
  }
  return getJson<TurnStatusResponse>(
    `/v1/conversations/${encodeURIComponent(args.conversationId)}/turns/${encodeURIComponent(args.jobId)}/status`,
  );
}

// ─────────────────────────────────────────────────────────────────────
// Mock turn — minimal but realistic enough to wire the UI against.
// Returns a "succeeded" status with one stylist-flavored outfit and a
// few follow-up chips. Refined further when the real engine lands.
// ─────────────────────────────────────────────────────────────────────

function mockTurnResult(args: { conversationId: string; jobId: string }): TurnStatusResponse {
  const now = new Date().toISOString();
  return {
    conversation_id: args.conversationId,
    job_id: args.jobId,
    status: "succeeded",
    stages: [
      { timestamp: now, stage: "planner_complete", message: "Read your style" },
      { timestamp: now, stage: "architect_complete", message: "Built the outfit shape" },
      { timestamp: now, stage: "composer_complete", message: "Composed the look" },
      { timestamp: now, stage: "rater_complete", message: "Checked the fit" },
      { timestamp: now, stage: "tryon_complete", message: "Rendered try-on" },
    ],
    error: "",
    result: {
      turn_id: `mock-turn-${args.jobId.slice(-6)}`,
      message: "Here's a look that should work for a relaxed evening out — a fluid silk dress paired with low-heel mules. Easy to dress up or down depending on the spot.",
      outfits: [
        {
          outfit_id: "mock-outfit-1",
          name: "Champagne Drift",
          reasoning: "Soft drape carries the evening light, warm tones flatter your palette, the silhouette stays clean without effort.",
          fashion_score: 87,
          items: [
            {
              garment_id: "mock-garment-1",
              title: "Champagne Silk Slip Dress",
              brand: "Nicobar",
              price: 4188,
              product_url: "https://thesigmavibe.shop/products/champagne-silk-slip-dress-mock",
            },
            {
              garment_id: "mock-garment-2",
              title: "Tan Leather Mules",
              brand: "Off Duty",
              price: 2388,
              product_url: "https://thesigmavibe.shop/products/tan-leather-mules-mock",
            },
          ],
        },
      ],
      follow_ups: [
        { label: "Show me something edgier", prompt: "show me something edgier", group: "Show Alternatives" },
        { label: "What if it rains?", prompt: "what if it rains", group: "Improve It" },
        { label: "Add a jacket", prompt: "add a jacket to this look", group: "Shop The Gap" },
      ],
    },
  };
}
