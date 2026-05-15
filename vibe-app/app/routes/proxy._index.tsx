// /apps/vibe → redirects customers to /apps/vibe/style.
//
// The Conversation page is Vibe's primary surface; the bare `/apps/vibe`
// URL exists so a customer can land on the app without remembering the
// exact path. Shopify's App Proxy forwards `/apps/vibe` here as `/proxy`,
// which Remix matches against this file.

import type { LoaderFunctionArgs } from "@remix-run/node";
import { redirect } from "@remix-run/node";

import { authenticate } from "../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  // Validate the App Proxy signature even on the redirect — rejecting
  // unsigned/tampered requests at the door rather than letting them
  // bounce through to the destination page.
  await authenticate.public.appProxy(request);

  // Preserve the original query string (Shopify's signed params + any
  // future customer-side params).
  const url = new URL(request.url);
  return redirect(`/proxy/style${url.search}`);
};
