// Onboarding state machine — runs client-side on the conversation page.
//
// The customer's progress through the in-chat onboarding (welcome →
// photos → gender-DOB → height-waist → done) is persisted in
// localStorage so a page reload resumes mid-flow. Identity is keyed
// off the vibe_session_id (D.S.3a) — when that's deleted (e.g. the
// customer clears site data) the onboarding resets too, which is the
// correct behaviour for an anonymous shopper.
//
// Skipping advances the step without saving. Completing advances the
// step AFTER the backend confirms the save (so a transient network
// failure doesn't lose the answer).
//
// D.O.3.

const STEP_KEY = "vibe_onboarding_step";
// Set of onboarding-card kinds the customer has already resolved
// (completed OR skipped). Stored as a JSON array of strings.
// Consulted by the seed effect so a mid-flow reload doesn't re-emit
// resolved cards as active. Without this, a customer who completes
// the photos card and reloads sees the photos card re-appear,
// effectively losing the resolution.
const RESOLVED_KEY = "vibe_onboarding_resolved_kinds";

export type OnboardingStep =
  | "welcome"
  | "photos"
  // Combined gender + DOB card. Gender is chip-style (Male / Female /
  // Non-binary), DOB is a DD/MM/YYYY segmented numeric input.
  | "gender-dob"
  // Combined height + waist card. Each measurement is ft + in
  // segmented numeric inputs, converted to cm before save.
  | "height-waist"
  | "done";

const ORDER: readonly OnboardingStep[] = [
  "welcome",
  "photos",
  "gender-dob",
  "height-waist",
  "done",
] as const;

// Migration map for customers whose persisted step references a
// kind no longer in the flow.
//   - dob / gender → gender-dob (the combined card)
//   - name → the next sensible step (now height-waist; previously
//     "height" but that card was rolled into height-waist)
//   - height / waist → the combined height-waist card
const LEGACY_STEP_ALIASES: Readonly<Record<string, OnboardingStep>> = {
  dob: "gender-dob",
  gender: "gender-dob",
  name: "height-waist",
  height: "height-waist",
  waist: "height-waist",
};

export function readOnboardingStep(): OnboardingStep {
  if (typeof window === "undefined") return "welcome";
  try {
    const raw = window.localStorage.getItem(STEP_KEY);
    if (!raw) return "welcome";
    if (raw in LEGACY_STEP_ALIASES) {
      const next = LEGACY_STEP_ALIASES[raw];
      // Repair localStorage so subsequent reads avoid the legacy
      // branch entirely.
      window.localStorage.setItem(STEP_KEY, next);
      return next;
    }
    if ((ORDER as readonly string[]).includes(raw)) {
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

/**
 * Read the set of onboarding-card kinds that have already been
 * resolved (saved or skipped) in a prior session. Used by the seed
 * effect to skip re-emitting them on reload.
 */
export function readResolvedKinds(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage.getItem(RESOLVED_KEY);
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((v) => typeof v === "string"));
  } catch {
    return new Set();
  }
}

export function markKindResolved(kind: string): void {
  if (typeof window === "undefined") return;
  try {
    const current = readResolvedKinds();
    current.add(kind);
    window.localStorage.setItem(RESOLVED_KEY, JSON.stringify([...current]));
  } catch {
    // Best-effort.
  }
}

/**
 * Clear a single resolved-kind entry. Used when the engine reports
 * that a previously-resolved card is invalid again (e.g. the photo
 * file vanished server-side); the seed effect needs to re-emit the
 * card and shouldn't be blocked by the historical resolution.
 */
export function unmarkKindResolved(kind: string): void {
  if (typeof window === "undefined") return;
  try {
    const current = readResolvedKinds();
    if (!current.delete(kind)) return;
    window.localStorage.setItem(RESOLVED_KEY, JSON.stringify([...current]));
  } catch {
    // Best-effort.
  }
}
