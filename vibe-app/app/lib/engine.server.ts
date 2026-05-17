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
  /** Stylist-voice description authored by the composer (LLM) or
   *  attribute-synthesized fallback. Used for the outfit-level
   *  reasoning paragraph; per-garment PDP prefers catalog_description. */
  description?: string;
  /** Raw product description sourced from the Shopify catalog row
   *  (catalog_enriched.description). The per-garment PDP renders this
   *  in preference to the LLM description so customers see the store's
   *  own copy. Empty for wardrobe items — GarmentDetail falls back to
   *  description in that case. */
  catalog_description?: string;
  /** True when this item is the customer's own wardrobe garment that
   *  the engine anchored the outfit around. Drives item ordering
   *  (anchor first) and the "From wardrobe" pill in the listing. */
  is_anchor?: boolean;
  /** "wardrobe" for customer-owned items, "catalog" for store products. */
  source?: string;
  /** Shopify product gid (gid://shopify/Product/<n>). Useful for deep
   *  linking + analytics; cart adds key on the variant id below. */
  shopify_product_id?: string;
  /** Per-size variant gids. Indexes the catalog row for Add-to-Cart
   *  wiring (D.C.7). Undefined when B.8 hasn't mapped this product. */
  shopify_variant_ids?: Record<string, string>;
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

export const ENGINE_HTTP_TIMEOUT_MS = 8_000;

// Caller-channel tag — appended as `?channel=vibe_storefront` to every
// engine call that supports it. The engine's onboarding endpoints
// accept a `channel` query parameter (default "web") which they pass
// to `observe_onboarding_endpoint(...)` so dashboards can slice
// Vibe-app traffic from agentic-app / direct-engine traffic. The
// existing `startTurn` already carries a channel field in the JSON
// body — this constant is for the GET/POST/PATCH onboarding routes
// that don't have a body-level channel field.
const ENGINE_CHANNEL = "vibe_storefront";

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
 * Snapshot of the engine's onboarding_profiles row. Fields are
 * intentionally loose — we only consume a few for the welcome-message
 * decision today; the engine returns ~15 columns total. Empty
 * strings are the engine's "not set" representation for text fields.
 */
export type OnboardingStatus = {
  user_id: string;
  name: string;
  date_of_birth: string;
  gender: string;
  profile_complete: boolean;
  onboarding_complete: boolean;
  /** Engine-side list of onboarding photo categories that have rows in
   *  `onboarding_images`. The seed effect uses this to detect customers
   *  whose photo records vanished from the DB (e.g. a Fly volume
   *  rebuild) — those should see the PhotosCard re-injected even
   *  though their localStorage step is past "photos". Values are
   *  "full_body" / "headshot". Empty array if no photos uploaded. */
  images_uploaded: string[];
};

/**
 * Read the engine's onboarding-profile snapshot for a user. Three
 * distinct outcomes — the caller needs to tell them apart because the
 * safe fallback is opposite-signed for the "no row" vs "engine error"
 * cases:
 *
 *   - OnboardingStatus → 2xx with a body. Trust the fields (they may
 *     all be empty if the row exists but no onboarding has happened
 *     yet).
 *   - null              → 404. The user has no onboarding_profiles row
 *                         yet. This is a new customer — render the
 *                         onboarding cards.
 *   - undefined         → engine error (5xx, network, timeout, parse
 *                         failure). The customer's onboarding state is
 *                         unknown. Callers should apply a safe-default
 *                         that doesn't re-prompt an already-onboarded
 *                         returning customer (i.e. assume hasProfile
 *                         under uncertainty).
 *
 * Conflating null and undefined was the cause of #432's review thread:
 * a brand-new customer (404) and a customer hitting transient engine
 * trouble (5xx) were indistinguishable, so we had to pick one fallback
 * for both. The undefined-on-error split lets the init action apply
 * its hasProfile=true safety net only when the answer is genuinely
 * unknown, while still propagating "this is a new user" honestly.
 *
 * Default `timeoutMs` is 1500 because this helper is also called
 * from the page loader on every Shopify-authenticated request, and
 * the loader blocks SSR — an 8s ceiling there would turn into long
 * blank screens on engine wobble. Callers with a more relaxed time
 * budget (e.g. the init action's Promise.allSettled fan-out) pass
 * `ENGINE_HTTP_TIMEOUT_MS` explicitly to avoid the false-negative
 * that caused the May 17 returning-customer re-onboarding bug.
 */
export async function getOnboardingStatus(
  userId: string,
  timeoutMs: number = 1500,
): Promise<OnboardingStatus | null | undefined> {
  if (USE_MOCK) {
    // Simulate a returning customer in mock mode — `gender` is the
    // hasProfile signal, so a non-empty value keeps the welcome-back
    // path live without ENGINE_API_URL being set. Pre-#434 this helper
    // returned null in mock mode, which under the old two-way semantics
    // mapped to hasProfile=true via the action's old fallback rule. The
    // three-way return introduced in #434 changed null to mean
    // "confirmed new customer", so returning a populated status here is
    // what preserves the previous mock UX. Matches the populated-mock
    // pattern in getAnalysisStatus / getWardrobeItems / startTurn.
    return {
      user_id: userId,
      name: "",
      date_of_birth: "1995-01-01",
      gender: "female",
      profile_complete: true,
      onboarding_complete: true,
      images_uploaded: ["full_body", "headshot"],
    };
  }
  let resp: Response;
  try {
    resp = await fetch(
      `${ENGINE_API_URL}/v1/onboarding/status/${encodeURIComponent(userId)}?channel=${ENGINE_CHANNEL}`,
      { signal: AbortSignal.timeout(timeoutMs) },
    );
  } catch {
    // Network / timeout / abort — state is unknown, signal error.
    return undefined;
  }
  // 404 specifically means "no onboarding_profiles row for this user"
  // — a confirmed new customer, not an engine problem. Everything else
  // non-2xx is an error condition the caller should fall back on.
  if (resp.status === 404) return null;
  if (!resp.ok) return undefined;
  let parsed: unknown;
  try {
    parsed = await resp.json();
  } catch {
    return undefined;
  }
  // `resp.json()` can yield primitives, arrays, or literal `null` — all
  // valid JSON. Guard against everything that isn't a plain object
  // before accessing fields, otherwise the property dereference below
  // would throw a TypeError that bubbles out of the helper as an
  // unhandled rejection (the SSR loader awaits this without try/catch,
  // so any throw turns into a 500 on the storefront).
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return undefined;
  }
  const raw = parsed as Partial<OnboardingStatus>;
  // images_uploaded is a real engine field but normalize defensively so
  // downstream consumers can always trust `Array.isArray(status.images_uploaded)`.
  return {
    user_id: raw.user_id ?? "",
    name: raw.name ?? "",
    date_of_birth: raw.date_of_birth ?? "",
    gender: raw.gender ?? "",
    profile_complete: Boolean(raw.profile_complete),
    onboarding_complete: Boolean(raw.onboarding_complete),
    images_uploaded: Array.isArray(raw.images_uploaded)
      ? raw.images_uploaded.filter((c): c is string => typeof c === "string")
      : [],
  };
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
    `/v1/onboarding/profile/ensure?channel=${ENGINE_CHANNEL}`,
    { user_id: userId },
  );
}

/**
 * Merge an anonymous identity into an authenticated one. Called by the
 * Vibe app when a customer signs in via Shopify Customer Account — the
 * App Proxy starts forwarding logged_in_customer_id and we reattribute
 * the anonymous localStorage UUID's conversations / history rows to
 * the Shopify-customer-keyed identity. Idempotent: canonical == alias
 * short-circuits on the engine side.
 */
export async function mergeUserIdentity(args: {
  canonicalExternalUserId: string;
  aliasExternalUserId: string;
}): Promise<{ canonical_external_user_id: string; merged: boolean; message: string }> {
  if (USE_MOCK) {
    return {
      canonical_external_user_id: args.canonicalExternalUserId,
      merged: args.canonicalExternalUserId !== args.aliasExternalUserId,
      message: "mock merged",
    };
  }
  return postJson("/v1/users/merge", {
    canonical_external_user_id: args.canonicalExternalUserId,
    alias_external_user_id: args.aliasExternalUserId,
  });
}

export async function startTurn(args: {
  conversationId: string;
  userId: string;
  message: string;
  imageData?: string;
  /** Picked from the customer's wardrobe via the + popover. Engine's
   *  CreateTurnRequest looks this up against user_wardrobe_items and
   *  uses it as the pairing anchor in lieu of an uploaded photo. */
  wardrobeItemId?: string;
  /** Picked from the customer's wishlist (saved catalog products).
   *  Engine resolves to a catalog row and anchors on it. */
  wishlistProductId?: string;
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
      // the engine's CreateTurnRequest defaults each attachment field
      // to "" via pydantic. Avoids shipping empty strings for fields
      // the caller didn't set. The three attachment fields are
      // mutually exclusive on the engine side — only one anchor per
      // turn — so callers should pass exactly one (or none).
      image_data: args.imageData,
      wardrobe_item_id: args.wardrobeItemId,
      wishlist_product_id: args.wishlistProductId,
    },
  );
}

// ─────────────────────────────────────────────────────────────────────
// Wardrobe + wishlist listings — power the + popover's pickers.
//
// These hit the engine's existing GET endpoints (no body, just the
// user_id in the path). Both surfaces are read-only here; the customer
// adds to wardrobe via image upload (engine persists asynchronously
// on every pairing-intent turn — see PR #403) and adds to wishlist via
// the per-product heart button on outfit cards.
// ─────────────────────────────────────────────────────────────────────

export type WardrobeItem = {
  id: string;
  title: string;
  image_url: string;
  garment_category: string;
  garment_subtype: string;
  primary_color: string;
};

export type WishlistItem = {
  product_id: string;
  title: string;
  image_url: string;
  brand: string;
  price: number | null;
};

type RawWardrobeListResponse = {
  user_id: string;
  items?: Array<{
    id?: string;
    title?: string;
    image_url?: string;
    image_path?: string;
    garment_category?: string;
    garment_subtype?: string;
    primary_color?: string;
  }>;
};

type RawWishlistListResponse = {
  user_id: string;
  items?: Array<{
    product_id?: string;
    title?: string;
    image_url?: string;
    brand?: string;
    price?: string | number | null;
  }>;
};

export async function getWardrobeItems(userId: string): Promise<WardrobeItem[]> {
  if (USE_MOCK) {
    return [
      {
        id: "mock-wardrobe-1",
        title: "Black Linen Shirt",
        image_url: "https://picsum.photos/seed/vibe-wardrobe-1/300/400",
        garment_category: "top",
        garment_subtype: "shirt",
        primary_color: "black",
      },
      {
        id: "mock-wardrobe-2",
        title: "Indigo Wide-Leg Jeans",
        image_url: "https://picsum.photos/seed/vibe-wardrobe-2/300/400",
        garment_category: "bottom",
        garment_subtype: "jeans",
        primary_color: "blue",
      },
    ];
  }
  const raw = await getJson<RawWardrobeListResponse>(
    `/v1/onboarding/wardrobe/${encodeURIComponent(userId)}?channel=${ENGINE_CHANNEL}`,
  );
  return (raw.items ?? []).map((it) => ({
    id: String(it.id ?? ""),
    title: String(it.title ?? "").trim() || "Untitled",
    // Local engine paths (data/wardrobe/images/...) → proxy through
    // the App Proxy tryon-image route just like try-on renders.
    image_url: rewriteEngineImageUrl(it.image_url || it.image_path) || "",
    garment_category: String(it.garment_category ?? ""),
    garment_subtype: String(it.garment_subtype ?? ""),
    primary_color: String(it.primary_color ?? ""),
  })).filter((it) => it.id !== "");
}

// Wardrobe write operations (D.C.3). Upload mirrors the onboarding
// image upload — multipart, no AbortSignal because phone photos over
// mobile are routinely 5-10 MB. Delete is a quick DELETE with user_id
// in the query string (engine checks ownership before archiving the
// row).

export type SaveWardrobeItemArgs = {
  userId: string;
  file: Blob;
  filename: string;
  title?: string;
  garmentCategory?: string;
  brand?: string;
};

export async function saveWardrobeItem(
  args: SaveWardrobeItemArgs,
): Promise<WardrobeItem> {
  if (USE_MOCK) {
    return {
      id: `mock-wardrobe-${Date.now()}`,
      title: args.title?.trim() || "Untitled piece",
      image_url: "https://picsum.photos/seed/vibe-new-wardrobe/300/400",
      garment_category: args.garmentCategory || "",
      garment_subtype: "",
      primary_color: "",
    };
  }
  const form = new FormData();
  form.append("user_id", args.userId);
  form.append("file", args.file, args.filename);
  if (args.title) form.append("title", args.title);
  if (args.garmentCategory) form.append("garment_category", args.garmentCategory);
  if (args.brand) form.append("brand", args.brand);

  let resp: Response;
  try {
    resp = await fetch(
      `${ENGINE_API_URL}/v1/onboarding/wardrobe/items?channel=${ENGINE_CHANNEL}`,
      { method: "POST", body: form },
    );
  } catch (e) {
    const reason = e instanceof Error ? e.message : String(e);
    throw new EngineError(0, `Engine wardrobe upload unreachable: ${reason}`);
  }
  if (!resp.ok) {
    throw new EngineError(
      resp.status,
      `Engine wardrobe upload → ${resp.status}: ${await readErrorBody(resp)}`,
    );
  }
  const raw = (await resp.json()) as {
    id?: string;
    title?: string;
    image_url?: string;
    image_path?: string;
    garment_category?: string;
    garment_subtype?: string;
    primary_color?: string;
  };
  return {
    id: String(raw.id ?? ""),
    title: String(raw.title ?? "").trim() || "Untitled",
    image_url: rewriteEngineImageUrl(raw.image_url || raw.image_path) || "",
    garment_category: String(raw.garment_category ?? ""),
    garment_subtype: String(raw.garment_subtype ?? ""),
    primary_color: String(raw.primary_color ?? ""),
  };
}

export async function deleteWardrobeItem(args: {
  userId: string;
  wardrobeItemId: string;
}): Promise<void> {
  if (USE_MOCK) return;
  let resp: Response;
  const url =
    `${ENGINE_API_URL}/v1/onboarding/wardrobe/items/${encodeURIComponent(args.wardrobeItemId)}` +
    `?user_id=${encodeURIComponent(args.userId)}&channel=${ENGINE_CHANNEL}`;
  try {
    resp = await fetch(url, { method: "DELETE", signal: fetchTimeout() });
  } catch (e) {
    const reason = e instanceof Error ? e.message : String(e);
    throw new EngineError(0, `Engine wardrobe delete unreachable: ${reason}`);
  }
  if (!resp.ok) {
    throw new EngineError(
      resp.status,
      `Engine wardrobe delete → ${resp.status}: ${await readErrorBody(resp)}`,
    );
  }
}

export async function getWishlistItems(userId: string): Promise<WishlistItem[]> {
  if (USE_MOCK) {
    return [
      {
        product_id: "mock-wishlist-1",
        title: "Champagne Silk Slip Dress",
        image_url: "https://picsum.photos/seed/vibe-wishlist-1/300/400",
        brand: "Nicobar",
        price: 4188,
      },
    ];
  }
  const raw = await getJson<RawWishlistListResponse>(
    `/v1/users/${encodeURIComponent(userId)}/wishlist`,
  );
  return (raw.items ?? []).map((it) => {
    const priceNum =
      typeof it.price === "number"
        ? it.price
        : typeof it.price === "string"
          ? Number.parseFloat(it.price)
          : NaN;
    return {
      product_id: String(it.product_id ?? ""),
      title: String(it.title ?? "").trim() || "Untitled",
      image_url: rewriteEngineImageUrl(it.image_url) || "",
      brand: String(it.brand ?? ""),
      price: Number.isFinite(priceNum) ? priceNum : null,
    };
  }).filter((it) => it.product_id !== "");
}

// Looks page (D.C.4) — saved outfits + recent recommendation history.
//
// Saved looks live in saved_looks rows the customer explicitly hearted.
// snapshot_json carries the full outfit object as it appeared at save
// time so the tile can render without re-fetching the conversation.
//
// Results live in turns the customer received; the engine summarizes
// each into a ResultListItem with a single preview image (try-on first,
// first garment fallback).

export type SavedLookSummary = {
  saved_look_id: string;
  title: string;
  preview_image_url: string;
  turn_id: string;
  conversation_id: string;
  item_count: number;
  created_at: string;
};

export type PastLookSummary = {
  turn_id: string;
  conversation_id: string;
  user_message: string;
  assistant_message: string;
  occasion: string;
  outfit_count: number;
  preview_image_url: string;
  created_at: string;
};

export type TryonGalleryEntry = {
  id: string;
  image_url: string;
  garment_ids: string[];
  garment_source: string;
  created_at: string;
};

type RawSavedLookRow = {
  id?: string;
  title?: string;
  item_ids?: string[];
  snapshot_json?: Record<string, unknown>;
  turn_id?: string;
  conversation_id?: string;
  created_at?: string;
};

type RawSavedLooksResponse = {
  user_id: string;
  saved_looks?: RawSavedLookRow[];
};

type RawResultsResponse = {
  user_id: string;
  results?: Array<{
    turn_id?: string;
    conversation_id?: string;
    user_message?: string;
    assistant_message?: string;
    occasion?: string;
    intent?: string;
    source?: string;
    outfit_count?: number;
    first_outfit_image?: string;
    created_at?: string;
  }>;
};

function previewFromSnapshot(snap: Record<string, unknown> | undefined): string {
  if (!snap || typeof snap !== "object") return "";
  // Snapshot shape isn't strict — historical saves carry varying keys.
  // Probe the obvious places: top-level tryon_image, items[0].image_url,
  // outfit.items[0].image_url.
  const direct = readString(snap, "tryon_image") || readString(snap, "image_url");
  if (direct) return direct;
  const items = Array.isArray(snap.items) ? snap.items : [];
  for (const it of items) {
    if (it && typeof it === "object") {
      const img = readString(it as Record<string, unknown>, "image_url");
      if (img) return img;
    }
  }
  const outfit = snap.outfit as Record<string, unknown> | undefined;
  if (outfit && typeof outfit === "object") {
    const tryon = readString(outfit, "tryon_image");
    if (tryon) return tryon;
    const oitems = Array.isArray(outfit.items) ? outfit.items : [];
    for (const it of oitems) {
      if (it && typeof it === "object") {
        const img = readString(it as Record<string, unknown>, "image_url");
        if (img) return img;
      }
    }
  }
  return "";
}

function readString(obj: Record<string, unknown>, key: string): string {
  const v = obj[key];
  return typeof v === "string" ? v.trim() : "";
}

export async function getSavedLooks(userId: string): Promise<SavedLookSummary[]> {
  if (USE_MOCK) {
    return [
      {
        saved_look_id: "mock-saved-1",
        title: "Champagne Drift",
        preview_image_url: "https://picsum.photos/seed/vibe-saved-1/400/533",
        turn_id: "mock-turn-1",
        conversation_id: "mock-conv-1",
        item_count: 2,
        created_at: new Date(Date.now() - 86400000).toISOString(),
      },
    ];
  }
  const raw = await getJson<RawSavedLooksResponse>(
    `/v1/users/${encodeURIComponent(userId)}/saved-looks`,
  );
  return (raw.saved_looks ?? []).map((row) => {
    const snap = (row.snapshot_json ?? {}) as Record<string, unknown>;
    const itemCount = Array.isArray(row.item_ids)
      ? row.item_ids.length
      : Array.isArray(snap.items)
        ? (snap.items as unknown[]).length
        : 0;
    return {
      saved_look_id: String(row.id ?? ""),
      title: String(row.title ?? "").trim() || "Saved look",
      preview_image_url: rewriteEngineImageUrl(previewFromSnapshot(snap)) || "",
      turn_id: String(row.turn_id ?? ""),
      conversation_id: String(row.conversation_id ?? ""),
      item_count: itemCount,
      created_at: String(row.created_at ?? ""),
    };
  }).filter((it) => it.saved_look_id !== "");
}

export async function deleteSavedLook(args: {
  userId: string;
  savedLookId: string;
}): Promise<void> {
  if (USE_MOCK) return;
  let resp: Response;
  const url = `${ENGINE_API_URL}/v1/users/${encodeURIComponent(args.userId)}/saved-looks/${encodeURIComponent(args.savedLookId)}`;
  try {
    resp = await fetch(url, { method: "DELETE", signal: fetchTimeout() });
  } catch (e) {
    const reason = e instanceof Error ? e.message : String(e);
    throw new EngineError(0, `Engine saved-look delete unreachable: ${reason}`);
  }
  if (!resp.ok) {
    throw new EngineError(
      resp.status,
      `Engine saved-look delete → ${resp.status}: ${await readErrorBody(resp)}`,
    );
  }
}

// Try-on gallery (D.C.6). Engine's `/v1/users/{user_id}/tryon-gallery`
// returns every try-on render the customer has accumulated — Gemini
// produces one per outfit recommendation, and they persist on the
// engine's disk + an entry per render in `virtual_tryon_images`.
//
// image_url comes back as either an absolute URL or a `/v1/onboarding/
// images/local?path=…` reference; rewriteEngineImageUrl normalises
// both into the App Proxy passthrough.
type RawTryonGalleryResponse = {
  user_id: string;
  items?: Array<{
    id?: string;
    image_url?: string;
    garment_ids?: string[];
    garment_source?: string;
    created_at?: string;
  }>;
};

export async function getTryonGallery(userId: string): Promise<TryonGalleryEntry[]> {
  if (USE_MOCK) {
    return [
      {
        id: "mock-tryon-1",
        image_url: "https://picsum.photos/seed/vibe-tryon-mock-1/400/533",
        garment_ids: ["mock-garment-1", "mock-garment-2"],
        garment_source: "catalog",
        created_at: new Date(Date.now() - 86400000).toISOString(),
      },
      {
        id: "mock-tryon-2",
        image_url: "https://picsum.photos/seed/vibe-tryon-mock-2/400/533",
        garment_ids: ["mock-garment-3"],
        garment_source: "wardrobe",
        created_at: new Date(Date.now() - 3 * 86400000).toISOString(),
      },
    ];
  }
  const raw = await getJson<RawTryonGalleryResponse>(
    `/v1/users/${encodeURIComponent(userId)}/tryon-gallery`,
  );
  return (raw.items ?? []).map((row) => ({
    id: String(row.id ?? ""),
    image_url: rewriteEngineImageUrl(row.image_url) || "",
    garment_ids: Array.isArray(row.garment_ids)
      ? row.garment_ids.filter((s): s is string => typeof s === "string")
      : [],
    garment_source: String(row.garment_source ?? ""),
    created_at: String(row.created_at ?? ""),
  })).filter((it) => it.id !== "");
}

export async function getPastLooks(userId: string): Promise<PastLookSummary[]> {
  if (USE_MOCK) {
    return [
      {
        turn_id: "mock-turn-past-1",
        conversation_id: "mock-conv-past-1",
        user_message: "what should I wear to a wedding?",
        assistant_message:
          "A bias-cut silk slip in warm champagne keeps it elegant without trying too hard.",
        occasion: "wedding",
        outfit_count: 2,
        preview_image_url: "https://picsum.photos/seed/vibe-past-1/400/533",
        created_at: new Date(Date.now() - 3 * 86400000).toISOString(),
      },
      {
        turn_id: "mock-turn-past-2",
        conversation_id: "mock-conv-past-2",
        user_message: "rainy day outfit",
        assistant_message: "Layered neutrals with a waterproof outer.",
        occasion: "everyday",
        outfit_count: 1,
        preview_image_url: "https://picsum.photos/seed/vibe-past-2/400/533",
        created_at: new Date(Date.now() - 7 * 86400000).toISOString(),
      },
    ];
  }
  const raw = await getJson<RawResultsResponse>(
    `/v1/users/${encodeURIComponent(userId)}/results`,
  );
  return (raw.results ?? []).map((row) => ({
    turn_id: String(row.turn_id ?? ""),
    conversation_id: String(row.conversation_id ?? ""),
    user_message: String(row.user_message ?? "").trim(),
    assistant_message: String(row.assistant_message ?? "").trim(),
    occasion: String(row.occasion ?? "").trim(),
    outfit_count: Number(row.outfit_count ?? 0),
    preview_image_url: rewriteEngineImageUrl(row.first_outfit_image) || "",
    created_at: String(row.created_at ?? ""),
  })).filter((it) => it.turn_id !== "");
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

  // No AbortSignal on uploads. Two reasons:
  //   1. Phone photos over mobile are routinely 5-10 MB and 8s is
  //      way too short to ship + ingest one. We don't want to abort
  //      a happy-path request just because the customer is on 4G.
  //   2. AbortSignal.timeout interacts badly with @remix-run/web-fetch
  //      when the request body is a multipart stream — when the timer
  //      fires mid-upload it tries to cancel a stream that already
  //      has an active reader (web-streams-polyfill error) which
  //      crashes the lambda with an unhandled rejection. Vercel then
  //      serves a generic 500 HTML page, the client tries to parse it
  //      as JSON, and we get "Unexpected token '<', '<!doctype '...".
  // Vercel's 60s Hobby-plan function ceiling and Fly's idle timeout
  // are the outer bounds; that's plenty for a single image upload.
  let resp: Response;
  try {
    resp = await fetch(
      `${ENGINE_API_URL}/v1/onboarding/images/${encodeURIComponent(args.category)}?channel=${ENGINE_CHANNEL}`,
      { method: "POST", body: form },
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
    resp = await fetch(`${ENGINE_API_URL}/v1/onboarding/profile/partial?channel=${ENGINE_CHANNEL}`, {
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
      ? `/v1/onboarding/analysis/start-phase1?channel=${ENGINE_CHANNEL}`
      : `/v1/onboarding/analysis/start-phase2?channel=${ENGINE_CHANNEL}`;
  return postJson<OnboardingAnalysisResponse>(path, { user_id: args.userId });
}

export type OnboardingAnalysisStatus = {
  user_id: string;
  analysis_run_id: string;
  /** Engine values: "not_started" | "in_progress" | "running" |
   *  "completed" | "failed" | "queued". Treat anything but
   *  "completed" / "failed" as "still working". */
  status: string;
  error_message: string;
};

/**
 * Read the engine's current onboarding-analysis status. The Vibe app
 * polls this after photo uploads complete so it can flip the
 * "Analyzing your style…" stage indicator off and emit the next
 * conversation prompt once the analysis is done.
 *
 * Short timeout (1.5s) so the poll loop doesn't pile up on a slow
 * engine — a missed poll just retries on the next interval.
 */
export async function getAnalysisStatus(
  userId: string,
  timeoutMs: number = 1500,
): Promise<OnboardingAnalysisStatus | null> {
  if (USE_MOCK) {
    return {
      user_id: userId,
      analysis_run_id: "mock-run",
      status: "completed",
      error_message: "",
    };
  }
  try {
    const resp = await fetch(
      `${ENGINE_API_URL}/v1/onboarding/analysis/${encodeURIComponent(userId)}?channel=${ENGINE_CHANNEL}`,
      { signal: AbortSignal.timeout(timeoutMs) },
    );
    if (!resp.ok) return null;
    const raw = (await resp.json()) as Partial<OnboardingAnalysisStatus>;
    return {
      user_id: raw.user_id ?? userId,
      analysis_run_id: raw.analysis_run_id ?? "",
      status: raw.status ?? "not_started",
      error_message: raw.error_message ?? "",
    };
  } catch {
    return null;
  }
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
  description?: string;
  catalog_description?: string;
  is_anchor?: boolean;
  source?: string;
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
  // Sort so the customer's own piece (wardrobe / uploaded anchor)
  // reads first in the per-item listing AND the thumbnail rail —
  // they're looking at "their" thing first, then the recommended
  // pairings. Engine returns items in role order (top, bottom,
  // outerwear...) which doesn't always put the anchor first. Stable
  // sort: items keep their original relative order within each group.
  const sortedItems = (card.items ?? [])
    .map((it, i) => ({ it, i }))
    .sort((a, b) => {
      const aAnchor = isAnchorRaw(a.it) ? 0 : 1;
      const bAnchor = isAnchorRaw(b.it) ? 0 : 1;
      if (aAnchor !== bAnchor) return aAnchor - bAnchor;
      return a.i - b.i;
    })
    .map(({ it }) => normalizeItem(it));
  return {
    outfit_id: `outfit-${id}`,
    name: card.title ?? "",
    reasoning: card.reasoning ?? "",
    fashion_score: card.fashion_score_pct ?? 0,
    tryon_image_url: rewriteEngineImageUrl(card.tryon_image) || undefined,
    items: sortedItems,
  };
}

// Anchor detection on the raw item shape (pre-normalize). True for
// items explicitly flagged is_anchor by the engine OR items the engine
// tagged with source="wardrobe" (the user's own piece either way).
function isAnchorRaw(item: RawEngineOutfitItem): boolean {
  return item.is_anchor === true || (item.source ?? "").toLowerCase() === "wardrobe";
}

// Engine emits image references in three shapes:
//   1. Absolute http(s):// URLs — Shopify CDN, catalog products. Use
//      as-is.
//   2. /v1/onboarding/images/local?path=<...> — try-on renders + some
//      historical wardrobe paths. Route through the App Proxy
//      passthrough so the engine origin stays hidden and CORS stays
//      moot.
//   3. Raw filesystem paths like `data/onboarding/images/wardrobe/
//      <hash>.jpg` — the wardrobe + (some) onboarding endpoints
//      return these directly because the engine's response model
//      (user/schemas.WardrobeItemResponse) carries the raw path in
//      `image_path` without prefixing the serving route. Wrap them
//      in the proxy URL so the browser can fetch them; the engine's
//      _resolve_local_image_file allowlists data/onboarding/images
//      and data/tryon/images, both of which we forward.
//
// Without case 3 the wardrobe picker tiles render with broken-image
// icons (browser hits thesigmavibe.shop/data/onboarding/images/... → 404).
function rewriteEngineImageUrl(raw: string | undefined): string {
  const url = String(raw ?? "").trim();
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  if (url.startsWith("data:")) return url;
  const prefix = "/v1/onboarding/images/local?path=";
  if (url.startsWith(prefix)) {
    return "/apps/vibe/api/tryon-image?path=" + url.slice(prefix.length);
  }
  // Raw filesystem path served by the engine — must wrap in the
  // proxy + URL-encode the path so slashes round-trip cleanly through
  // the searchParams reader on the receiving side.
  if (url.startsWith("data/")) {
    return "/apps/vibe/api/tryon-image?path=" + encodeURIComponent(url);
  }
  return url;
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
    image_url: rewriteEngineImageUrl(item.image_url) || undefined,
    description: item.description?.trim() || undefined,
    catalog_description: item.catalog_description?.trim() || undefined,
    is_anchor: item.is_anchor || undefined,
    source: item.source || undefined,
    shopify_product_id: item.shopify_product_id || undefined,
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
            description:
              "A bias-cut slip in warm champagne silk. The drape catches evening light without shouting; the spaghetti straps keep the neckline open enough for a long chain or layered pendants.",
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
            description:
              "Square-toe leather mules in a soft tan that reads warmer than camel. The slim heel keeps the silhouette long without committing to a stiletto.",
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
