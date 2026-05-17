# Privacy Policy

> ⚠️ **TEMPLATE — LEGAL REVIEW REQUIRED.** Replace `{{ ... }}` placeholders. See [README.md](README.md).
>
> This template is drafted against the **Digital Personal Data Protection Act 2023 (DPDPA)**, the **Information Technology Act 2000** + **IT (Reasonable Security Practices) Rules 2011**, and **IT (Intermediary Guidelines) Rules 2021**. Specific cross-checks counsel should make:
>
> - DPDPA Data Protection Officer (DPO) appointment trigger thresholds
> - "Significant Data Fiduciary" classification (currently unclear for this scale)
> - DPDPA notice requirements (Section 5) — content, language, and form
> - Children's data handling (Section 9) — verifiable parental consent
> - Cross-border data transfer language re: Shopify (Canada), Razorpay (India), OpenAI (US, for the Vibe stylist), Google (US, for Gemini try-on), Supabase (US, for engine data)

*Effective: {{ EFFECTIVE_DATE }}*

---

## 1. Who we are

{{ COMPANY_NAME }} ("**TheSigmaVibe**", "**we**", "**us**", "**our**") operates the storefront at [thesigmavibe.shop](https://thesigmavibe.shop) and the **Vibe** AI stylist available at [thesigmavibe.shop/apps/vibe](https://thesigmavibe.shop/apps/vibe). We are the **Data Fiduciary** under the **Digital Personal Data Protection Act 2023 (DPDPA)** for personal data collected through these surfaces.

**Registered office:** {{ REGISTERED_ADDRESS }}
**GSTIN:** `{{ GSTIN }}`
**Contact:** [{{ SUPPORT_EMAIL }}](mailto:{{ SUPPORT_EMAIL }})

## 2. What this notice covers

How we collect, use, store, share, and protect your personal data when you:

- Browse [thesigmavibe.shop](https://thesigmavibe.shop)
- Create a customer account
- Place an order
- Use the Vibe AI stylist
- Sign up for marketing communications
- Contact us for support

## 3. What we collect

### 3.1 Information you give us directly

| Category | Examples | Why |
|---|---|---|
| Account & contact | Name, email, phone, delivery address | Order fulfillment, communications |
| Payment | Card / UPI / netbanking via Razorpay | Process payments (we never see the full card; Razorpay tokenizes) |
| Identity | Gender, date of birth (optional, in the Vibe stylist) | Style recommendations, age-appropriate fits |
| Body & style data (Vibe) | Height, waist, full-body photo, headshot, garment photos you upload | Generate outfit recommendations, virtual try-on |
| Preferences | Hearted items, saved looks, wardrobe pieces | Style memory across sessions |
| Communications | Emails, support messages, chat conversations with Vibe | Resolve queries, improve service |

### 3.2 Information we collect automatically

| Category | Examples |
|---|---|
| Device & log | IP address, browser, device type, OS, referrer URL |
| Usage | Pages viewed, time on page, search queries, click paths |
| Cookies & similar | First-party + Shopify session cookies; see Section 9 |

### 3.3 Photos and biometric-adjacent data

The Vibe stylist asks for an **optional** full-body photo and headshot to power body-type analysis and virtual try-on. These photos are:

- **Optional** — you can use Vibe without uploading them
- Stored encrypted at rest on our infrastructure
- Not shared with third parties except as required to deliver the service (e.g. Google Gemini for try-on rendering)
- Deletable on request via [{{ DPO_CONTACT }}](mailto:{{ DPO_CONTACT }})

Photos uploaded for **Outfit Check** are processed in-memory by our AI stylist and may be retained alongside your conversation history for up to **{{ PHOTO_RETENTION_DAYS }} days**.

## 4. Lawful basis & purpose

We process your personal data on the following bases (DPDPA Section 6 / 7):

| Basis | What it covers |
|---|---|
| Consent | Marketing communications, optional Vibe stylist photos, cookies beyond strictly-necessary |
| Performance of contract | Order processing, fulfillment, payments, returns, customer support |
| Legal obligation | GST invoicing, IT Rules record-keeping, tax filings |
| Legitimate uses (DPDPA s.7) | Fraud prevention, network/IT security, internal analytics on de-identified data |

## 5. Who we share with

We don't sell or rent your personal data. We share with:

| Recipient | Purpose | Where they process |
|---|---|---|
| **Shopify, Inc.** | Storefront hosting, order management, customer accounts | Canada / US |
| **Razorpay Software Pvt. Ltd.** | Payment processing | India |
| **The original brand / retailer** | Order fulfillment (sharing only delivery name, address, contact, items) | India |
| **Courier partners** | Delivery (Delhivery, Bluedart, etc.) | India |
| **OpenAI** | The Vibe AI stylist's language model (text only, anonymized session id) | US |
| **Google LLC** | Gemini virtual try-on rendering (your photo + chosen garment images) | US |
| **Supabase, Inc.** | Engine database hosting (encrypted at rest) | US |
| **Fly.io, Inc.** | Engine compute (Mumbai region, but Fly is US-based) | India compute, US org |
| **Vercel, Inc.** | Vibe app hosting (Mumbai region) | India compute, US org |
| **Vibe (in-house AI stylist)** | Style analysis, outfit recommendations | India (Mumbai) compute |

**Cross-border transfers:** processed under DPDPA Section 16 (currently India does not restrict transfers to most jurisdictions; we monitor for any Central Government notification restricting specific countries).

We may also disclose personal data when **legally required** (court order, regulatory inquiry, lawful government request), or to protect rights, property, or safety.

## 6. How long we keep your data

| Category | Retention |
|---|---|
| Account & order records | **8 years** (GST + IT Act record-keeping requirements) |
| Vibe stylist conversations | **{{ CONVERSATION_RETENTION_DAYS }} days** active; archived for **2 years** then deleted |
| Photos uploaded to Vibe | Deletable on request at any time; otherwise retained while account is active |
| Marketing data | Until you unsubscribe + 30 days |
| Logs | **{{ LOG_RETENTION_DAYS }} days** rolling |

## 7. Your rights under DPDPA

You have the right to:

1. **Access** the personal data we hold about you
2. **Correct** inaccurate or incomplete data
3. **Erase** data we no longer have a lawful basis to retain
4. **Withdraw consent** at any time (for processing based on consent)
5. **Nominate** another individual to exercise these rights in your stead
6. **Grievance redressal** — escalate concerns to our Data Protection Officer

To exercise any of these rights, write to [{{ DPO_CONTACT }}](mailto:{{ DPO_CONTACT }}). We respond within **30 days** (or sooner where the law requires).

If you're not satisfied with our response, you may escalate to the **Data Protection Board of India** (once operational under DPDPA).

## 8. Security

We follow reasonable security practices per **IT Act + IT (Reasonable Security Practices) Rules 2011** and the DPDPA:

- HTTPS / TLS in transit
- Encryption at rest for personal data on our infrastructure
- Access controls (least-privilege, MFA on admin systems)
- Regular security reviews of code touching personal data
- Incident response plan with **72-hour breach notification** per DPDPA s.8(6)

No system is perfectly secure, but if we become aware of a breach affecting your data, we'll notify you and the Data Protection Board as required.

## 9. Cookies and similar technologies

We use cookies for:

| Type | Purpose | Consent? |
|---|---|---|
| Strictly necessary | Cart, session, login, anti-fraud | No (legal basis: legitimate use) |
| Performance | Aggregated analytics on what's working | Yes |
| Marketing | Retargeting, conversion measurement | Yes |

You can manage cookie preferences via the cookie banner on first visit and the "Cookie settings" link in the footer (or your browser settings).

## 10. Children

Our storefront is not intended for users under **18**. The Vibe stylist's analytical features (body-type, color analysis) are not designed for or marketed to children. We do not knowingly collect personal data from anyone under 18 without **verifiable parental consent** per DPDPA s.9.

If you believe we have collected data from a child without proper consent, contact [{{ DPO_CONTACT }}](mailto:{{ DPO_CONTACT }}) — we'll delete it promptly.

## 11. Changes to this policy

We'll post material changes here with a new "Effective" date at the top. If the changes are significant, we'll email registered customers + put a banner on the storefront.

## 12. Contact

| Role | Contact |
|---|---|
| General data questions | [{{ SUPPORT_EMAIL }}](mailto:{{ SUPPORT_EMAIL }}) |
| Data Protection Officer (DPDPA) | [{{ DPO_CONTACT }}](mailto:{{ DPO_CONTACT }}) |
| Grievance Officer (IT Rules / Consumer Protection) | {{ GRIEVANCE_OFFICER_NAME }} — [{{ GRIEVANCE_OFFICER_EMAIL }}](mailto:{{ GRIEVANCE_OFFICER_EMAIL }}) |

Postal: {{ COMPANY_NAME }}, {{ REGISTERED_ADDRESS }}
