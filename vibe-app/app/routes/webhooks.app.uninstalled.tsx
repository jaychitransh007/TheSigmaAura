import type { ActionFunctionArgs } from "@remix-run/node";
import { authenticate, unauthenticated } from "../shopify.server";
import db from "../db.server";
import { removeVibeMenuItems } from "../lib/navigation.server";

export const action = async ({ request }: ActionFunctionArgs) => {
  const { shop, session, topic } = await authenticate.webhook(request);

  console.log(`Received ${topic} webhook for ${shop}`);

  // PR #481: best-effort cleanup of the "Find your Vibe" + "Your
  // Vibes" menu items we injected at install. Shopify usually revokes
  // the access token before delivering this webhook, so the admin
  // client may not be reachable — silent failure is fine; the
  // merchant can remove leftover items from Online Store → Navigation.
  // Run BEFORE deleting the session so unauthenticated.admin can
  // still see it briefly.
  if (session) {
    try {
      const { admin } = await unauthenticated.admin(shop);
      const result = await removeVibeMenuItems(admin);
      console.log(
        `[vibe] uninstall menu cleanup for ${shop}: removed=${result.removed}` +
          (result.skipped ? ` skipped=${result.skipped}` : ""),
      );
    } catch (err) {
      console.warn(
        `[vibe] uninstall menu cleanup failed for ${shop}:`,
        err instanceof Error ? err.message : err,
      );
    }
  }

  // Webhook requests can trigger multiple times and after an app has already been uninstalled.
  // If this webhook already ran, the session may have been deleted previously.
  if (session) {
    await db.session.deleteMany({ where: { shop } });
  }

  return new Response();
};
