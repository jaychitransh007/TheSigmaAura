// Onboarding state machine — runs client-side on the conversation page.
//
// The customer's progress through the in-chat onboarding (welcome →
// photos → name → DOB → gender → height → waist → done) is persisted
// in localStorage so a page reload resumes mid-flow. Identity is
// keyed off the vibe_session_id (D.S.3a) — when that's deleted (e.g.
// the customer clears site data) the onboarding resets too, which is
// the correct behaviour for an anonymous shopper.
//
// Skipping advances the step without saving. Completing advances the
// step AFTER the backend confirms the save (so a transient network
// failure doesn't lose the answer).
//
// D.O.3.

const STEP_KEY = "vibe_onboarding_step";

export type OnboardingStep =
  | "welcome"
  | "photos"
  | "name"
  | "dob"
  | "gender"
  | "height"
  | "waist"
  | "done";

const ORDER: readonly OnboardingStep[] = [
  "welcome",
  "photos",
  "name",
  "dob",
  "gender",
  "height",
  "waist",
  "done",
] as const;

export function readOnboardingStep(): OnboardingStep {
  if (typeof window === "undefined") return "welcome";
  try {
    const raw = window.localStorage.getItem(STEP_KEY);
    if (raw && (ORDER as readonly string[]).includes(raw)) {
      return raw as OnboardingStep;
    }
  } catch {
    // localStorage unavailable (private browsing); fall through.
  }
  return "welcome";
}

export function writeOnboardingStep(step: OnboardingStep): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STEP_KEY, step);
  } catch {
    // Best-effort — if localStorage is locked the user just re-does
    // the flow on next visit.
  }
}

export function nextStep(current: OnboardingStep): OnboardingStep {
  const idx = ORDER.indexOf(current);
  if (idx < 0) return "done";
  return ORDER[Math.min(idx + 1, ORDER.length - 1)];
}

/** True iff this step renders an interactive card in the feed. */
export function isCardStep(step: OnboardingStep): boolean {
  return step !== "welcome" && step !== "done";
}
