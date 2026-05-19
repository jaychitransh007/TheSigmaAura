// Onboarding state machine — runs client-side on the conversation page.
//
// Sequential flow (D.O.5, 2026-05-20):
//
//   welcome → photos card
//       photos skipped     → done (no gender-DOB, jump to chat)
//       photos completed   → gender-dob card
//           gender-dob *   → done (analysis fires if gender-dob completed)
//
// Persistence keys:
//   - vibe_onboarding_step:            sequence position, drives seed
//   - vibe_onboarding_resolved_kinds:  Set of kinds the customer has
//                                      already saved or skipped
//   - vibe_onboarding_resolved_modes:  JSON map of kind → "completed" |
//                                      "skipped", so the seed effect can
//                                      tell the customer's intent on
//                                      reload (skipping photos has a
//                                      different downstream effect than
//                                      completing them — it bypasses
//                                      gender-DOB entirely).
//
// Identity is keyed off vibe_session_id (D.S.3a) — when that's deleted
// (e.g. the customer clears site data) the onboarding resets too,
// which is the correct behaviour for an anonymous shopper.

const STEP_KEY = "vibe_onboarding_step";
const RESOLVED_KEY = "vibe_onboarding_resolved_kinds";
const RESOLVED_MODES_KEY = "vibe_onboarding_resolved_modes";

export type OnboardingStep =
  | "welcome"
  | "photos"
  // Combined gender + DOB card. Gender is chip-style (Male / Female /
  // Non-binary), DOB is a DD/MM/YYYY segmented numeric input. Skip is
  // now exposed too (D.O.5) — a customer who doesn't want to share
  // demographics can still chat, they just don't get the analysis-
  // driven personalization.
  | "gender-dob"
  | "done";

export type OnboardingResolutionMode = "completed" | "skipped";

const ORDER: readonly OnboardingStep[] = [
  "welcome",
  "photos",
  "gender-dob",
  "done",
] as const;

// Migration map for customers whose persisted step references a
// kind no longer in the flow.
//   - dob / gender → gender-dob (the combined card)
//   - height / waist / height-waist / name → done (D.O.5 dropped the
//     measurements card from the in-chat onboarding flow; the customer
//     can fill those later via a profile edit surface)
const LEGACY_STEP_ALIASES: Readonly<Record<string, OnboardingStep>> = {
  dob: "gender-dob",
  gender: "gender-dob",
  name: "done",
  height: "done",
  waist: "done",
  "height-waist": "done",
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

/** Read the kind → mode map of how each resolved card was completed. */
export function readResolvedModes(): Record<string, OnboardingResolutionMode> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(RESOLVED_MODES_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {};
    }
    const out: Record<string, OnboardingResolutionMode> = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (v === "completed" || v === "skipped") {
        out[k] = v;
      }
    }
    return out;
  } catch {
    return {};
  }
}

/** Convenience accessor — returns the mode for one kind, or null. */
export function getResolvedMode(
  kind: string,
): OnboardingResolutionMode | null {
  const modes = readResolvedModes();
  return modes[kind] ?? null;
}

export function markKindResolved(
  kind: string,
  mode: OnboardingResolutionMode = "completed",
): void {
  if (typeof window === "undefined") return;
  try {
    const current = readResolvedKinds();
    current.add(kind);
    window.localStorage.setItem(RESOLVED_KEY, JSON.stringify([...current]));
    const modes = readResolvedModes();
    modes[kind] = mode;
    window.localStorage.setItem(RESOLVED_MODES_KEY, JSON.stringify(modes));
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
    if (current.delete(kind)) {
      window.localStorage.setItem(RESOLVED_KEY, JSON.stringify([...current]));
    }
    const modes = readResolvedModes();
    if (modes[kind] !== undefined) {
      delete modes[kind];
      window.localStorage.setItem(RESOLVED_MODES_KEY, JSON.stringify(modes));
    }
  } catch {
    // Best-effort.
  }
}
