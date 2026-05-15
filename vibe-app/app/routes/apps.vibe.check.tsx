// Outfit Check page placeholder. Real upload + feedback flow lands in
// D.C.5 — customer uploads an outfit photo, engine returns honest
// styling feedback.

import type { LoaderFunctionArgs } from "@remix-run/node";

import { VibeShell } from "../components/vibe-shell";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.public.appProxy(request);
  return null;
};

export default function CheckPage() {
  return (
    <VibeShell title="Outfit Check" subtitle="Coming in D.C.5">
      <p>
        Upload an outfit photo. Get honest, stylist-voiced feedback before
        you walk out the door.
      </p>
    </VibeShell>
  );
}
