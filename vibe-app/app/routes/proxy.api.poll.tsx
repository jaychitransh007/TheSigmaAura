// Resource route — no React component, just a GET loader returning
// JSON. Client-side code on /apps/vibe/style polls this every second
// while a turn is running.
//
// URL after Shopify App Proxy: thesigmavibe.shop/apps/vibe/api/poll
//
// Query params:
//   conv  — conversation id
//   job   — turn job id
//
// Returns the engine's status payload as JSON. HMAC signature on the
// request is validated by authenticate.public.appProxy() — unsigned
// requests get 401.

import type { LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import { pollTurn } from "../lib/engine.server";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.public.appProxy(request);

  const url = new URL(request.url);
  const conversationId = url.searchParams.get("conv");
  const jobId = url.searchParams.get("job");

  if (!conversationId || !jobId) {
    return json({ error: "Missing conv or job param" }, { status: 400 });
  }

  const status = await pollTurn({ conversationId, jobId });
  return json(status);
};
