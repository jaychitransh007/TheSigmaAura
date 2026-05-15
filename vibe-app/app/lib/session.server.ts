// Anonymous customer session for Vibe's App Proxy pages.
//
// Every customer visiting thesigmavibe.shop/apps/vibe/* gets a stable
// session cookie that doubles as their engine `user_id`. Used to:
//   - resolve a long-lived conversation across visits
//   - tie wardrobe / liked outfits / try-on cache to the same identity
//
// Anonymous-only for v1. D.S.3 layers Shopify Customer Account on top
// (when a customer logs in, we'll merge their anonymous data into
// their authenticated profile).
//
// Storage: HttpOnly cookie, signed via Remix's `createCookie`. Not
// rotated unless the cookie expires or is cleared.

import { createCookie } from "@remix-run/node";
import { randomUUID } from "node:crypto";

const COOKIE_NAME = "vibe_session_id";
const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

const sessionCookie = createCookie(COOKIE_NAME, {
  httpOnly: true,
  secure: true,
  sameSite: "lax",
  path: "/",
  maxAge: ONE_YEAR_SECONDS,
});

export type SessionResult = {
  /** The customer's stable session id (UUID v4 string). */
  sessionId: string;
  /** Whether this request created a fresh session (response needs Set-Cookie). */
  isNew: boolean;
  /** Set-Cookie value to attach to the response if isNew. */
  setCookie: string | null;
};

/**
 * Read the customer's session id from the cookie, or mint a new one.
 * Caller must attach `setCookie` to the response when `isNew === true`.
 */
export async function getOrCreateSession(request: Request): Promise<SessionResult> {
  const existing: string | null = await sessionCookie.parse(request.headers.get("Cookie"));
  if (existing && typeof existing === "string" && existing.length > 0) {
    return { sessionId: existing, isNew: false, setCookie: null };
  }

  const fresh = randomUUID();
  const cookieHeader = await sessionCookie.serialize(fresh);
  return { sessionId: fresh, isNew: true, setCookie: cookieHeader };
}
