// Tiny helpers for client-side fetch calls against our App Proxy
// resource routes.
//
// Why this exists: every onboarding interaction (image upload,
// profile field save, analysis trigger) talks to a backend route
// that returns JSON like `{ ok: true, ... }` or `{ ok: false,
// error: "..." }`. Things go wrong in the wild — some intermediary
// (most often Shopify App Proxy on this stack) can strip or rewrite
// the response's Content-Type header, and on outright server errors
// Vercel serves an HTML page. A naive `await resp.json()` then
// crashes with "Unexpected token '<', '<!doctype '..." and the
// SyntaxError surfaces to the customer instead of a friendly
// message.
//
// parseActionJson always returns one of the two response shapes
// (ok/fail), regardless of whether the body was actually JSON. The
// caller can switch on `data.ok` and ignore parsing concerns.

export type OkPayload<T extends object> = { ok: true } & T;
export type FailPayload = { ok: false; error: string };
export type ActionPayload<T extends object> = OkPayload<T> | FailPayload;

export async function parseActionJson<T extends object>(
  resp: Response,
): Promise<ActionPayload<T>> {
  try {
    return (await resp.json()) as ActionPayload<T>;
  } catch {
    return {
      ok: false,
      error: resp.ok
        ? "The server returned an unreadable response."
        : `Request failed (HTTP ${resp.status})`,
    };
  }
}
