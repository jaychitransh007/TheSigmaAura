// Looks page placeholder. Saved + past outfit recommendations land in
// D.C.4. Becomes the native equivalent of a wishlist — that's why
// we're not installing a third-party wishlist app.

import type { LoaderFunctionArgs } from "@remix-run/node";

import { VibeShell } from "../components/vibe-shell";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.public.appProxy(request);
  return null;
};

export default function LooksPage() {
  return (
    <VibeShell title="Looks" subtitle="Coming in D.C.4">
      <p>
        Outfits Vibe has built for you, plus pieces you've saved. Returns to
        the carousel of past recommendations and likes.
      </p>
    </VibeShell>
  );
}
