# TheSigmaVibe storefront — legal page templates

This directory holds **draft** content for the six mandatory storefront pages required before the launch of `thesigmavibe.shop` (task **B.4** in [docs/OPEN_TASKS.md](../../OPEN_TASKS.md)).

> ⚠️ **LEGAL REVIEW REQUIRED — do not paste into Shopify as-is.**
>
> These templates are written from publicly-known facts about TheSigmaVibe's setup (India-only, INR, Razorpay, GST, manual fulfillment from original retailers, Vibe AI stylist app). They reference the **Indian Consumer Protection Act 2019**, **Consumer Protection (E-Commerce) Rules 2020**, **Information Technology Act 2000 + IT Rules 2011/2021**, **Digital Personal Data Protection Act 2023 (DPDPA)**, and **Shopify Partner Program / Razorpay merchant terms**.
>
> None of it has been reviewed by counsel. Specifics that *will* need lawyer input before publishing:
>
> 1. **Business entity name + registered address** — the templates use `{{ COMPANY_NAME }}` and `{{ REGISTERED_ADDRESS }}` placeholders that must be replaced with the actual GST-registered entity.
> 2. **Returns window + restocking** — currently drafted at **7 days from delivery** for unworn/unwashed items with original tags. Adjust based on what's commercially viable given the manual-fulfillment model.
> 3. **Shipping SLA** — drafted as `5–10 business days, India only`. Real lead-time depends on how quickly source retailers ship.
> 4. **Privacy specifics** — DPDPA requires named Data Protection Officer (DPO) once thresholds are met; templates flag this with a `{{ DPO_CONTACT }}` placeholder.
> 5. **Pricing + tax** — GST inclusion language assumes the entity is GST-registered. Templates use "all prices inclusive of GST" which is a common pattern but may not fit every entity structure.
> 6. **Razorpay / Shopify branding** — Razorpay's merchant terms restrict how their name can appear on the storefront's policy pages. The drafted Terms references "Razorpay" generically — review against Razorpay's current brand guidelines before publishing.

## Files

| Page | Template | Shopify admin path |
|---|---|---|
| About | [about.md](about.md) | Online Store → Pages → Add page (handle: `about`) |
| Contact | [contact.md](contact.md) | Online Store → Pages → Add page (handle: `contact`) |
| Shipping Policy | [shipping_policy.md](shipping_policy.md) | Settings → Policies → Shipping policy |
| Returns / Refund Policy | [returns_refund_policy.md](returns_refund_policy.md) | Settings → Policies → Return policy + Refund policy |
| Privacy Policy | [privacy_policy.md](privacy_policy.md) | Settings → Policies → Privacy policy |
| Terms of Service | [terms_of_service.md](terms_of_service.md) | Settings → Policies → Terms of service |

Shopify's **Settings → Policies** UI auto-links the four policy pages from the storefront footer; About + Contact need to be added to the footer menu manually under **Online Store → Navigation → Footer menu**.

## Placeholders to replace before publishing

Every template uses these placeholder tokens. Find-and-replace before pasting into Shopify admin:

| Token | Replace with | Notes |
|---|---|---|
| `{{ COMPANY_NAME }}` | Registered entity name | e.g. "TheSigmaVibe Private Limited" |
| `{{ REGISTERED_ADDRESS }}` | Full GST-registered address | India-side address required for any cross-border claims |
| `{{ GSTIN }}` | GSTIN | Required on invoices; surfaced on storefront for B2B buyer confidence |
| `{{ SUPPORT_EMAIL }}` | Public support inbox | Currently `hellosigmascience+partner@gmail.com` — should switch to a `@thesigmavibe.shop` mailbox before launch |
| `{{ SUPPORT_PHONE }}` | Public support phone | DPDPA / Consumer Protection Rules effectively require a contact phone |
| `{{ DPO_CONTACT }}` | DPDPA Data Protection Officer | Name + email; required when applicable thresholds are met |
| `{{ EFFECTIVE_DATE }}` | Date page goes live | ISO date (e.g. `2026-05-17`) |

## Post-launch tracking

Once these are published, update [docs/OPEN_TASKS.md](../../OPEN_TASKS.md) marking **B.4** as done and noting which counsel reviewed the final copy.
