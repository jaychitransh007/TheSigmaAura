// Mandatory GDPR / Shopify privacy-compliance webhook.
//
// Shopify fires `customers/data_request` when a customer asks the
// merchant for a copy of the data the merchant (and its apps) hold
// about them. We have **30 days** to compile + deliver that export.
//
// This handler:
//   1. Validates the HMAC via authenticate.webhook (Shopify rejects
//      forged requests at the framework level — invalid signature
//      yields a 401 before our code runs).
//   2. Logs a `vibe_gdpr_data_request` event with the relevant
//      identifiers so the actual compilation can run async.
//   3. Returns 200 immediately so Shopify counts the webhook as
//      acknowledged within its 5s budget.
//
// The actual data export touches ~20 engine tables (onboarding_*,
// users, conversations, conversation_turns, user_wardrobe_items,
// saved_looks, virtual_tryon_images, catalog_interaction_history,
// confidence_history, …). That work is **deliberately not done in
// this handler** — see "GDPR data pipeline" in docs/OPEN_TASKS.md
// for the follow-up task that builds the engine-side export endpoint
// and an email/portal delivery step.
//
// Until that pipeline ships, requests show up in Vercel Log Drain as
// `event=vibe_gdpr_data_request` and are processed manually within
// the 30-day SLA.

import type { ActionFunctionArgs } from "@remix-run/node";

import { logInfo } from "../lib/logger.server";
import { authenticate } from "../shopify.server";

type CustomersDataRequestPayload = {
  shop_id?: number;
  shop_domain?: string;
  orders_requested?: number[];
  customer?: {
    id?: number;
    email?: string;
    phone?: string;
  };
  data_request?: {
    id?: number;
  };
};

export const action = async ({ request }: ActionFunctionArgs) => {
  const { shop, topic, payload } = await authenticate.webhook(request);

  const body = (payload ?? {}) as CustomersDataRequestPayload;
  const customer = body.customer ?? {};
  // Vibe keys customer identity as `shopify:{customer.id}` (D.S.3b
  // merge). Log it explicitly so the manual processor can grep for
  // exactly the external_user_id the engine indexes by.
  const externalUserId =
    typeof customer.id === "number" ? `shopify:${customer.id}` : null;

  logInfo("vibe_gdpr_data_request", {
    topic,
    shop,
    shop_id: body.shop_id ?? null,
    shop_domain: body.shop_domain ?? null,
    external_user_id: externalUserId,
    customer_email_present: !!customer.email,
    customer_phone_present: !!customer.phone,
    orders_requested_count: Array.isArray(body.orders_requested)
      ? body.orders_requested.length
      : 0,
    data_request_id: body.data_request?.id ?? null,
  });

  return new Response();
};
