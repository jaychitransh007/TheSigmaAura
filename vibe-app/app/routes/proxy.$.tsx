// App Proxy handler. Shopify forwards requests from
// thesigmavibe.shop/apps/vibe/<path> here as /proxy/<path>.
//
// Authentication: every request carries a Shopify HMAC signature in the
// query string. authenticate.public.appProxy() validates it and rejects
// unsigned or tampered requests with a 401. The returned context tells
// us which shop (and, if logged in, which customer) the request belongs
// to — that's how Vibe knows whose data to load.
//
// This is the D.S.1 placeholder. The four real customer pages
// (Conversation / Wardrobe / Looks / Outfit Check) replace its rendered
// content in D.C.2-D.C.5 by branching on the splat path.

import type { LoaderFunctionArgs } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";

import { authenticate } from "../shopify.server";

export const loader = async ({ request, params }: LoaderFunctionArgs) => {
  const { session, liquid: _liquid } = await authenticate.public.appProxy(request);

  // params["*"] is the splat — everything after /proxy/.
  // E.g. /proxy/style/v2 → "style/v2".
  const path = params["*"] ?? "";

  return {
    ok: true,
    path,
    shop: session?.shop ?? null,
  };
};

export default function VibeAppProxy() {
  const { path, shop } = useLoaderData<typeof loader>();

  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <title>Vibe</title>
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <style>{`
          body {
            font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif;
            background: #faf5ee;
            color: #2d1b14;
            margin: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 2rem;
          }
          .card {
            max-width: 480px;
            background: #ffffff;
            border-radius: 16px;
            padding: 2.5rem;
            box-shadow: 0 8px 24px rgba(180, 100, 60, 0.08);
          }
          h1 {
            font-family: "Playfair Display", Georgia, serif;
            font-size: 2rem;
            color: #b45a3c;
            margin: 0 0 0.5rem;
          }
          p {
            margin: 0.5rem 0;
            line-height: 1.6;
          }
          code {
            background: #f5ebe0;
            padding: 0.1rem 0.4rem;
            border-radius: 4px;
            font-size: 0.9em;
          }
          .meta {
            margin-top: 1.5rem;
            padding-top: 1.5rem;
            border-top: 1px solid #f0e0d0;
            font-size: 0.85rem;
            color: #806050;
          }
        `}</style>
      </head>
      <body>
        <div className="card">
          <h1>Hello from Vibe.</h1>
          <p>App proxy is wired up correctly. This page was rendered by Vibe's Remix backend after Shopify validated the signed request.</p>
          <p>Real customer pages — Conversation, Wardrobe, Looks, Outfit Check — replace this placeholder in upcoming work.</p>
          <div className="meta">
            <p>Requested path: <code>{path || "(root)"}</code></p>
            <p>Shop: <code>{shop ?? "(none)"}</code></p>
          </div>
        </div>
      </body>
    </html>
  );
}
