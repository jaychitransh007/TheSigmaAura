// Wardrobe page placeholder. Real CRUD + filters land in D.C.3 once
// Shopify Customer Account auth is wired in D.S.3 (we tie wardrobe
// items to the customer's identity, not just the anonymous session).

import type { LoaderFunctionArgs } from "@remix-run/node";

import { VibeShell } from "../components/vibe-shell";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.public.appProxy(request);
  return null;
};

export default function WardrobePage() {
  return (
    <VibeShell title="Wardrobe" subtitle="Coming in D.C.3 — needs customer auth (D.S.3)">
      <p>
        Your closet will live here. Add pieces you already own and Vibe will
        style around them — wardrobe-first, catalog-as-gap-filler.
      </p>
    </VibeShell>
  );
}
