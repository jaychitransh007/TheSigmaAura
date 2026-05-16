// Resource route — save a single onboarding profile field.
//
// URL via App Proxy: thesigmavibe.shop/apps/vibe/api/onboarding/profile
// Method: POST (application/x-www-form-urlencoded)
//
// Form fields:
//   sessionId  — customer's localStorage session id (= engine user_id)
//   field      — one of: name, date_of_birth, gender, height_cm, waist_cm
//   value      — the field value (string; height/waist parsed to number)
//
// Forwards to engine PATCH /v1/onboarding/profile/partial. One field at
// a time so the UI can save each answer the customer commits.

import type { ActionFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import {
  EngineError,
  patchOnboardingProfile,
  type OnboardingProfileField,
} from "../lib/engine.server";
import { authenticate } from "../shopify.server";

const ALLOWED_FIELDS: ReadonlySet<OnboardingProfileField> = new Set([
  "name",
  "date_of_birth",
  "gender",
  "height_cm",
  "waist_cm",
]);

const NUMERIC_FIELDS: ReadonlySet<OnboardingProfileField> = new Set([
  "height_cm",
  "waist_cm",
]);

export const action = async ({ request }: ActionFunctionArgs) => {
  await authenticate.public.appProxy(request);

  const form = await request.formData();
  const sessionId = String(form.get("sessionId") ?? "").trim();
  const field = String(form.get("field") ?? "").trim() as OnboardingProfileField;
  const rawValue = String(form.get("value") ?? "").trim();

  if (!sessionId) {
    return json({ ok: false, error: "Missing sessionId" }, { status: 400 });
  }
  if (!ALLOWED_FIELDS.has(field)) {
    return json({ ok: false, error: `Invalid field: ${field}` }, { status: 400 });
  }
  if (!rawValue) {
    return json({ ok: false, error: "Missing value" }, { status: 400 });
  }

  // height_cm / waist_cm need to ship as numbers — pydantic's ge/le
  // constraints reject string-coerced numbers in some edge cases. Parse
  // here so a malformed value 400s before we hit the engine.
  let value: string | number = rawValue;
  if (NUMERIC_FIELDS.has(field)) {
    const n = Number.parseFloat(rawValue);
    if (!Number.isFinite(n)) {
      return json(
        { ok: false, error: `${field} must be a number` },
        { status: 400 },
      );
    }
    value = n;
  }

  try {
    const result = await patchOnboardingProfile({
      userId: sessionId,
      field,
      value,
    });
    return json({ ok: true, ...result });
  } catch (err) {
    // Always JSON — see image.tsx for the rationale (avoid Vercel HTML
    // error pages breaking the client's response.json() parse).
    if (err instanceof EngineError) {
      return json(
        { ok: false, error: err.message },
        { status: err.status || 502 },
      );
    }
    const message = err instanceof Error ? err.message : "Save failed";
    return json({ ok: false, error: message }, { status: 500 });
  }
};
