# E.1 — Manual fulfillment SOP

Standard operating procedure for fulfilling a customer order on `thesigmavibe.shop`.

TheSigmaVibe doesn't hold inventory. When a customer places an order, we coordinate with the **source retailer** (the brand or marketplace whose product is in our catalog) to ship to the customer, then mark the Shopify order fulfilled with the tracking link.

This runbook is the canonical procedure. Follow it for every order until the volume justifies an internal dashboard (see [`E.2`](../OPEN_TASKS.md) below).

---

## When a new order arrives

You'll get an **email from Shopify** ("New order #1042 from …") and the order shows up in **Shopify admin → Orders**. Aim to start within **2 business hours** so the source-retailer order can ship same-day.

## Step 1 — Open the order

1. Sign in to [admin.shopify.com/store/q8pery-95/orders](https://admin.shopify.com/store/q8pery-95/orders).
2. Click the new order. You'll see:
   - Customer name + delivery address (right sidebar)
   - Phone number (right sidebar; collected at checkout)
   - Line items with the variant size + quantity
   - Payment status (should be **Paid** before you proceed — Razorpay's webhook lands within seconds of checkout)

> ⚠️ **Do not start sourcing if payment status is `Pending` or `Authorized`.** Wait for `Paid` — refunds are messy if sourcing started against an unconfirmed transaction.

## Step 2 — Read the source URL for each line item

Each catalog product carries a `vibe.source_product_url` metafield set at import time (see `scripts/seed_thesigmavibe_catalog/build_shopify_csv.py`). Pull it for every line item:

1. Click the product name in the order line item — opens the product detail page.
2. Scroll to the bottom of the product page → **Metafields** section → look for `vibe.source_product_url`.
3. Copy the URL. This is the source retailer's PDP for the exact piece.

> 💡 **Time-saver:** open every line item's source URL in a new tab before you start placing orders. Avoids context-switching between Shopify and the retailers mid-checkout.

## Step 3 — Place the order at the source retailer

For each line item:

1. Open the source URL in a new tab.
2. Verify on the source retailer's page:
   - Same product
   - **Size matches** the Shopify line item's variant (XS / S / M / L / XL)
   - In stock
3. Add to cart on the source retailer.
4. Check out. Shipping address: **the Shopify customer's address** from Step 1.
5. Billing: use the TheSigmaVibe operating card. Save the receipt.
6. Note the source-retailer's **order number** + **tracking link** when it arrives (usually by email within 24h).

> ⚠️ **If a piece is out of stock on the source retailer:** email the customer (template in Step 6 below) and refund that line item in Shopify admin (Orders → … → Refund → select line item → Refund). Continue with the rest of the order.

## Step 4 — Wait for tracking from the source retailer

Source retailers usually email a tracking link within **24 hours of ordering**. Keep an eye on the inbox associated with the operating card.

When the tracking link lands:
- Confirm courier + tracking number
- Verify the destination address on the courier site matches the Shopify customer's address (typo check — common Hindi/English transliteration issues)

## Step 5 — Mark the Shopify order fulfilled

1. Back in Shopify admin → the order page.
2. **Fulfill items** button (top-right of the line-items panel).
3. Paste the **tracking number** + select the courier from the dropdown. If the courier isn't listed, paste the courier's **tracking URL** into the "Tracking URL" field.
4. Leave "Send shipment details to your customer now" checked — Shopify emails them the tracking link.
5. Click **Fulfill items**.

The order's status flips from `Unfulfilled` → `Fulfilled`, and the customer gets:
- Email: "Your order is on the way" with the tracking link
- (Eventually) Email: "Your order has been delivered" from Shopify when the courier marks delivered

## Step 6 — Customer comms (if needed)

### Out-of-stock at source

```
Subject: Update on your order #1042 from TheSigmaVibe

Hi {{ first_name }},

Quick heads-up — the {{ product_name }} you ordered is out of stock
at our source for the size you picked. The rest of your order is on
its way.

I've refunded ₹{{ amount }} for that piece to your original payment
method (usually shows up in 3–7 business days, depending on your bank).

Want a similar piece in your size? Reply and I'll dig something out
of the catalog.

Sorry for the friction!
— {{ your_name }} at TheSigmaVibe
```

### Address looks wrong / unreachable

```
Subject: Quick check on order #1042

Hi {{ first_name }},

Before we ship, just want to confirm your delivery address:

  {{ address_line_1 }}
  {{ address_line_2 }}
  {{ city }}, {{ state }} {{ pincode }}

Reply with the corrected address if anything's off — we'll hold the
order until we hear from you.

— {{ your_name }} at TheSigmaVibe
```

### Significant delay (>3 business days past estimate)

```
Subject: Your order #1042 is taking longer than expected

Hi {{ first_name }},

Apologies — your order is running behind. The source retailer is
{{ reason: "moving slower than usual" / "backlogged" / "shipping in
batches due to <holiday/strike>" }}. Latest estimate: {{ new_eta }}.

If you'd rather not wait, reply and we'll refund the order.

Tracking: {{ tracking_link }}
— {{ your_name }} at TheSigmaVibe
```

## Step 7 — Filing

For every fulfilled order, save in your operating-card receipt folder:

| Save | Where |
|---|---|
| Shopify order PDF (admin → … → Print order) | `orders/{YYYY}/{shopify_order_id}.pdf` |
| Source-retailer order confirmation emails | Same folder, named `source_{retailer}_{their_order_id}.eml` |
| Source-retailer invoices | Same folder, named `invoice_{retailer}_{their_order_id}.pdf` |

These are the audit trail for GST returns + cost-of-goods reconciliation. **Don't skip.**

## Step 8 — Returns

If a customer initiates a return per the [Returns / Refund Policy](../storefront/legal_pages/returns_refund_policy.md):

1. Customer emails support → you arrange reverse pickup with the courier.
2. When the piece arrives back, inspect:
   - Tags attached ✓
   - No visible wear / wash ✓
   - Matches the line item shipped ✓
3. **If accepted:** Shopify admin → order → Refund → select line item → Refund. Customer is refunded to original payment method within 3–7 business days.
4. **If rejected** (worn / tags missing / different item): photograph the issue + email the customer with the photos. Refund denied, piece returned to customer at their cost.
5. We **eat the source retailer's cost** on accepted returns — the return value of the SKU at the source isn't recoverable. Factor this into pricing.

## Tooling notes

- **Email templates**: keep in a notes app you can copy-paste from. The samples in Step 6 are the canonical text — don't drift.
- **Card disputes**: if the operating card sees a chargeback, the Shopify order PDF + source-retailer invoice from Step 7 is enough to win it back. File the dispute the same day.
- **Bulk fulfillment**: Shopify lets you batch-fulfill multiple orders. Useful past ~5 orders/day. Not needed at current volume.

---

## When to graduate this runbook

Triggers to revisit:

- **>10 orders/day** for two weeks straight — at that point, **E.2** (internal dashboard listing open orders + their source URLs in one screen) starts paying for itself.
- **>2 source retailers per typical order** — the tab-juggling becomes the bottleneck; a script that pre-opens source URLs would save real time.
- **Returns rate >15%** — the SOP needs a clearer pre-purchase fit-guidance loop (Vibe stylist should be steering customers harder on size).

Until then, this runbook + a spreadsheet of source-retailer logins is sufficient.
