// Catchall fallback for unknown /apps/vibe/* paths.
// Specific routes (apps.vibe._index, apps.vibe.style, apps.vibe.wardrobe,
// apps.vibe.looks, apps.vibe.check) take precedence; anything else
// lands here.
//
// We still validate the App Proxy signature even on the 404 — refuse
// to render anything for unsigned requests.

import type { LoaderFunctionArgs } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";

import { VibeShell } from "../components/vibe-shell";
import { authenticate } from "../shopify.server";

export const loader = async ({ request, params }: LoaderFunctionArgs) => {
  await authenticate.public.appProxy(request);
  return { path: params["*"] ?? "" };
};

export default function VibeProxyNotFound() {
  const { path } = useLoaderData<typeof loader>();

  return (
    <VibeShell title="Not here" subtitle="That page isn't part of Vibe yet">
      <p>
        Try <a href="/apps/vibe/style">Conversation</a>,{" "}
        <a href="/apps/vibe/wardrobe">Wardrobe</a>,{" "}
        <a href="/apps/vibe/looks">Looks</a>, or{" "}
        <a href="/apps/vibe/check">Outfit Check</a>.
      </p>
      <div className="vibe-meta">
        <p>
          Requested path: <code>{path || "(root)"}</code>
        </p>
      </div>
    </VibeShell>
  );
}
