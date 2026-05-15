// /apps/vibe → redirects customers to /apps/vibe/style.
//
// The Conversation page is Vibe's primary surface; the bare `/apps/vibe`
// URL exists so a customer can land on the app without remembering the
// exact path. Shopify's App Proxy forwards `/apps/vibe` to this server
// at the same path so server and browser stay URL-aligned for hydration.

import type { LoaderFunctionArgs } from "@remix-run/node";
import { redirect } from "@remix-run/node";

import { authenticate } from "../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.public.appProxy(request);

  const url = new URL(request.url);
  return redirect(`/apps/vibe/style${url.search}`);
};
