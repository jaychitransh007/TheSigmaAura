// Server-side auth / identity helpers shared across Vibe resource
// routes. Lives here (vs inline per-route) because identity checks
// are security-critical and the cost of any single route drifting
// out of sync with the others is an IDOR bug.

/**
 * Reject an incoming request when the customer's session id claims to
 * be a Shopify Customer Account (`shopify:{id}`) but the App Proxy
 * URL didn't carry a matching, signed `logged_in_customer_id`.
 *
 * Background: every storefront-origin request to `/apps/vibe/*` is
 * routed through Shopify's App Proxy. The proxy:
 *   1. Auto-appends `logged_in_customer_id=<n>` whenever a Customer
 *      Account is signed in via Shopify's classic / new accounts flow.
 *   2. HMAC-signs the full URL (query string + path) so the signed
 *      param can't be tampered with after the fact.
 *
 * Anonymous (UUID-shaped) session ids are unguessable per-browser
 * identifiers — they don't need an extra verification step. But the
 * `shopify:{customer_id}` shape is enumerable, so we MUST verify a
 * caller claiming that identity really has the matching signed
 * customer id on the request URL.
 *
 * Importantly: **the request body is NOT signed**. App Proxy only
 * signs query parameters. Accepting a body-supplied "customer id"
 * as a fallback would silently bypass the check.
 *
 * Returns `true` when the request should be rejected with HTTP 403.
 */
export function identityMismatch(url: URL, sessionId: string): boolean {
  if (!sessionId.startsWith("shopify:")) return false;
  const expected = url.searchParams.get("logged_in_customer_id")?.trim() || "";
  return !expected || sessionId !== `shopify:${expected}`;
}
