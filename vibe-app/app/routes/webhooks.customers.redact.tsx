// Mandatory GDPR / Shopify privacy-compliance webhook.
//
// Shopify fires `customers/redact` 10 days after a customer-deletion
// request is filed with the merchant (or immediately when the
// merchant uninstalls Vibe for a shop that had customer data). We
// have **30 days from receipt** to delete (or fully anonymize) the
// customer's personal data from our systems.
//
// This handler:
//   1. Validates HMAC via authenticate.webhook.
//   2. Logs a `vibe_gdpr_customers_redact` event with the external
//      user id the engine indexes by.
//   3. Returns 200 within Shopify's 5s budget.
//
// Why no engine call: the redact spans ~20 tables across two
// services (platform_core + user). Doing that synchronously here
// risks Vercel's function timeout AND leaves us with a half-deleted
// state if any single table errors. The pipeline that performs the
// erase across all tables transactionally lives behind a follow-up
// engine endpoint (see "GDPR data pipeline" in OPEN_TASKS.md).
//
// Until that ships, redact requests are surfaced as
// `event=vibe_gdpr_customers_redact` in Vercel Log Drain and
// processed manually within the 30-day SLA.

import type { ActionFunctionArgs } from "@remix-run/node";

import { logInfo } from "../lib/logger.server";
import { authenticate } from "../shopify.server";

type CustomersRedactPayload = {
  shop_id?: number;
  shop_domain?: string;
  customer?: {
    id?: number;
    email?: string;
    phone?: string;
  };
  orders_to_redact?: number[];
};

export const action = async ({ request }: ActionFunctionArgs) => {
  const { shop, topic, payload } = await authenticate.webhook(request);

  const body = (payload ?? {}) as CustomersRedactPayload;
  const customer = body.customer ?? {};
  const externalUserId =
    typeof customer.id === "number" ? `shopify:${customer.id}` : null;

  logInfo("vibe_gdpr_customers_redact", {
    topic,
    shop,
    shop_id: body.shop_id ?? null,
    shop_domain: body.shop_domain ?? null,
    external_user_id: externalUserId,
    customer_email_present: !!customer.email,
    customer_phone_present: !!customer.phone,
    orders_to_redact_count: Array.isArray(body.orders_to_redact)
      ? body.orders_to_redact.length
      : 0,
  });

  return new Response();
};
