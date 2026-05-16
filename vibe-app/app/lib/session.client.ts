// Customer session ID stored in localStorage on the customer's browser.
//
// We can't use HttpOnly cookies for the Vibe conversation page: Shopify
// App Proxy proxies requests from the storefront origin to the app
// backend, but Set-Cookie headers from the backend don't reliably
// round-trip back to the browser through the proxy (and even when they
// do, subsequent storefront requests don't always include them in the
// proxied call). The symptom: each request looks like a fresh customer
// to the engine, so the user/conversation get re-created every call.
//
// localStorage is the canonical workaround: the customer mints (or
// reads) a UUID on first page load and sends it explicitly with every
// request to the backend. Identity is per-browser, persists across
// reloads, scoped to the storefront origin.
//
// D.S.3 (Shopify Customer Account) will layer over the top — when a
// customer logs in we'll merge their anonymous localStorage session
// into their authenticated profile.

const STORAGE_KEY = "vibe_session_id";

/**
 * Mint a UUID v4. Prefers `crypto.randomUUID` (Web Crypto, secure
 * contexts only) and falls back to a Math.random-based RFC 4122 v4
 * string when it's unavailable. Shopify storefronts are always HTTPS
 * so the native path is the norm; the fallback is a safety net for
 * dev / HTTP / older browsers and the inner catch below.
 */
function mintUuid(): string {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
  } catch {
    // Fall through to the Math.random path.
  }
  // RFC 4122 v4 — sufficient for client-side session identity (not
  // cryptographic; engine treats this as an opaque external_user_id).
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Read the customer's session id from localStorage, or mint a fresh
 * UUID v4 and persist it. Returns "" during SSR (window undefined).
 *
 * Caller must invoke from a useEffect / client-only path — server-side
 * Remix loaders/actions cannot read localStorage and must accept the
 * session id explicitly via form/query.
 */
export function getOrCreateClientSessionId(): string {
  if (typeof window === "undefined") return "";
  try {
    const existing = window.localStorage.getItem(STORAGE_KEY);
    if (existing && existing.length > 0) return existing;
    const fresh = mintUuid();
    window.localStorage.setItem(STORAGE_KEY, fresh);
    return fresh;
  } catch {
    // localStorage can throw in private browsing or when disabled.
    // Fall back to an in-memory id for this page session — conversation
    // won't persist across reloads but the chat loop still works.
    return mintUuid();
  }
}
