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
    const fresh = crypto.randomUUID();
    window.localStorage.setItem(STORAGE_KEY, fresh);
    return fresh;
  } catch {
    // localStorage can throw in private browsing or when disabled.
    // Fall back to an in-memory id for this page session — conversation
    // won't persist across reloads but the chat loop still works.
    return crypto.randomUUID();
  }
}
