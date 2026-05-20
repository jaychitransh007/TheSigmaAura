// Per-turn Shopify body_html hydration.
//
// The engine returns OutfitItems with `catalog_description` sourced
// from `catalog_enriched.description`. For the 14k legacy rows
// imported via CSV that field carries the pre-Shopify-import ugly
// serialized blob ("title: X product_type: Y body_html: <html>…").
// What customers want to see on the Vibe PDP card is the *Shopify*
// `body_html` — the clean
//
//     <p>Lede.</p>
//     <p><strong>The vibe:</strong></p>
//     <ul><li><strong>Fit:</strong> Regular</li>…</ul>
//
// format build_shopify_csv.py generated and the storefront PDP
// renders. The bulk CSV import doesn't fire products/create
// webhooks, so the engine-side description was never refreshed.
//
// This helper fetches body_html in one batched Admin REST call per
// turn (up to 250 products per call via `?ids=…`). Single tenant
// for now (TheSigmaVibe); multi-tenant comes when we onboard more
// stores — at which point the token will move from a single
// env var to a per-tenant lookup against the `tenants` table.

const SHOPIFY_API_VERSION = "2026-04";

// Generous timeout: Admin REST is 200-400ms typical, with 1s p99.
// Vercel function ceiling is 60s — this is well inside.
const FETCH_TIMEOUT_MS = 4000;

/** Extract numeric Shopify product id from a GraphQL GID string.
 *
 *   "gid://shopify/Product/8049768562806" → "8049768562806"
 *
 * Returns "" for already-numeric input (so we tolerate either
 * representation upstream) and "" for unparseable strings. */
export function shopifyNumericIdFromGid(gid: string): string {
  if (!gid) return "";
  const trimmed = gid.trim();
  if (/^\d+$/.test(trimmed)) return trimmed;
  const match = trimmed.match(/Product\/(\d+)$/);
  return match ? match[1] : "";
}

/** Fetch `body_html` for a batch of Shopify products via the Admin
 *  REST API.
 *
 *  Returns a Map keyed by NUMERIC product id (string) → body_html.
 *  Missing / unauthorized / errored products are simply omitted —
 *  the caller falls back to the engine-provided catalog_description
 *  for any product not in the returned map. No partial failure
 *  surfaces to the customer; descriptions just don't upgrade for
 *  those rows.
 *
 *  Single-tenant: reads `SHOPIFY_ADMIN_TOKEN` from env, uses the
 *  shop domain passed in. When SHOPIFY_ADMIN_TOKEN is unset (e.g.
 *  local dev without the env var), returns an empty map and the
 *  customer sees the engine's (sanitized but plain-text)
 *  catalog_description — same as before this hydrator existed. */
export async function fetchShopifyBodyHtmlBatch(args: {
  shopDomain: string;
  numericProductIds: string[];
}): Promise<Map<string, string>> {
  const out = new Map<string, string>();
  const adminToken = process.env.SHOPIFY_ADMIN_TOKEN?.trim();
  if (!adminToken) return out;
  if (!args.shopDomain.trim()) return out;
  const uniqueIds = Array.from(
    new Set(args.numericProductIds.map((id) => id.trim()).filter(Boolean)),
  );
  if (uniqueIds.length === 0) return out;

  // Admin REST allows up to 250 ids per call. Recommendation turns
  // top out at ~15 items so a single call is always enough today,
  // but chunk defensively in case a multi-outfit turn grows.
  const CHUNK = 250;
  const chunks: string[][] = [];
  for (let i = 0; i < uniqueIds.length; i += CHUNK) {
    chunks.push(uniqueIds.slice(i, i + CHUNK));
  }

  await Promise.all(
    chunks.map(async (chunk) => {
      const url =
        `https://${args.shopDomain.trim()}/admin/api/${SHOPIFY_API_VERSION}/products.json` +
        `?ids=${chunk.join(",")}&fields=id,body_html`;
      let resp: Response;
      try {
        resp = await fetch(url, {
          headers: {
            "X-Shopify-Access-Token": adminToken,
            "Accept": "application/json",
          },
          signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
        });
      } catch {
        // Network / timeout — swallow, fall back to engine
        // description for these ids. Don't break the turn for a
        // description-upgrade hiccup.
        return;
      }
      if (!resp.ok) return;
      let body: { products?: Array<{ id?: number | string; body_html?: string }> };
      try {
        body = (await resp.json()) as typeof body;
      } catch {
        return;
      }
      for (const p of body.products ?? []) {
        const id = String(p.id ?? "").trim();
        const html = String(p.body_html ?? "").trim();
        if (id && html) out.set(id, html);
      }
    }),
  );

  return out;
}
