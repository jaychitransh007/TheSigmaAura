// Resource route — kick off an onboarding analysis phase.
//
// URL via App Proxy: thesigmavibe.shop/apps/vibe/api/onboarding/analysis
// Method: POST
//
// Form fields:
//   sessionId  — customer's localStorage session id (= engine user_id)
//   phase      — "phase1" (color from headshot+gender)
//              | "phase2" (other details from both images + DOB)
//
// The engine's two phase endpoints have prerequisites — if not met the
// engine returns 400 with detail and we surface that to the UI so the
// caller can decide whether to wait / nudge / ignore. The full analysis
// endpoint (POST /analysis/start) requires onboarding_complete=true,
// which Vibe customers never set, so it's intentionally not exposed.

import type { ActionFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import {
  EngineError,
  startOnboardingAnalysis,
} from "../lib/engine.server";
import { authenticate } from "../shopify.server";

const ALLOWED_PHASES = new Set(["phase1", "phase2"] as const);

export const action = async ({ request }: ActionFunctionArgs) => {
  await authenticate.public.appProxy(request);

  const form = await request.formData();
  const sessionId = String(form.get("sessionId") ?? "").trim();
  const phaseRaw = String(form.get("phase") ?? "").trim();

  if (!sessionId) {
    return json({ ok: false, error: "Missing sessionId" }, { status: 400 });
  }
  if (!ALLOWED_PHASES.has(phaseRaw as "phase1" | "phase2")) {
    return json(
      { ok: false, error: `Invalid phase: ${phaseRaw}` },
      { status: 400 },
    );
  }
  const phase = phaseRaw as "phase1" | "phase2";

  try {
    const result = await startOnboardingAnalysis({
      userId: sessionId,
      phase,
    });
    return json({ ok: true, ...result });
  } catch (err) {
    // Always JSON — see image.tsx for the rationale.
    if (err instanceof EngineError) {
      return json(
        { ok: false, error: err.message },
        { status: err.status || 502 },
      );
    }
    const message = err instanceof Error ? err.message : "Analysis trigger failed";
    return json({ ok: false, error: message }, { status: 500 });
  }
};
