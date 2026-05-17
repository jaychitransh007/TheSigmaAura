// Combined gender + date-of-birth onboarding card.
//
// Two reasons it's a single card instead of two FieldCards:
//   1. Customer-facing: pairs naturally — "basics" — and cuts one
//      back-and-forth from the onboarding sequence.
//   2. Brand: gender deserves chip-style choice (one click, visible
//      options) rather than a dropdown; DOB deserves a polished
//      segmented input rather than the native date control. Once each
//      had its own non-FieldCard treatment, sharing a card was the
//      natural shape.
//
// Save flow: parallel POSTs to the existing single-field profile
// endpoint via Promise.all. No skip — gender/DOB are the only two
// signals the planner can't infer from anything else, so the card
// stays put until the customer commits at least one (canSubmit
// gates the Save button until then).

import { useRef, useState } from "react";

import { parseActionJson } from "../../lib/fetch.client";

type SaveState =
  | { phase: "idle" }
  | { phase: "saving" }
  | { phase: "error"; message: string };

// Engine schema accepts these four values for gender; we surface the
// first three as chips and treat skip as "prefer_not_to_say".
type Gender = "male" | "female" | "non_binary";

const GENDER_CHIPS: { value: Gender; label: string }[] = [
  { value: "male", label: "Male" },
  { value: "female", label: "Female" },
  { value: "non_binary", label: "Non-binary" },
];

const CURRENT_YEAR = new Date().getFullYear();

function isValidDob(day: string, month: string, year: string): boolean {
  if (!day || !month || !year) return false;
  const d = Number(day);
  const m = Number(month);
  const y = Number(year);
  if (!Number.isFinite(d) || !Number.isFinite(m) || !Number.isFinite(y)) return false;
  if (m < 1 || m > 12) return false;
  if (d < 1 || d > 31) return false;
  // Reject impossible-future / implausibly-old dates without being
  // pedantic about leap years — engine validates on save anyway.
  if (y < 1900 || y > CURRENT_YEAR) return false;
  // Quick day-per-month sanity check so a customer can't submit
  // 31 / 02 / 2000.
  const daysInMonth = new Date(y, m, 0).getDate();
  return d <= daysInMonth;
}

function toIsoDate(day: string, month: string, year: string): string {
  const dd = day.padStart(2, "0");
  const mm = month.padStart(2, "0");
  return `${year}-${mm}-${dd}`;
}

export function GenderDobCard({
  sessionId,
  onAdvance,
}: {
  sessionId: string;
  onAdvance: (mode: "completed" | "skipped") => void;
}) {
  const [gender, setGender] = useState<Gender | null>(null);
  const [day, setDay] = useState<string>("");
  const [month, setMonth] = useState<string>("");
  const [year, setYear] = useState<string>("");
  const [state, setState] = useState<SaveState>({ phase: "idle" });

  // Refs let us auto-advance focus DD → MM → YYYY as the customer
  // fills out segments. Pleasant on desktop, essential on mobile
  // where typing one segment + reaching for the next is fiddly.
  const monthRef = useRef<HTMLInputElement>(null);
  const yearRef = useRef<HTMLInputElement>(null);
  // Synchronous in-flight guard. React state updates are async — two
  // rapid Enter presses can both observe `saving === false` before
  // the component re-renders, and both trigger handleSave. The ref
  // closes that window: flip it true at the start of the save and
  // bail any concurrent call.
  const savingRef = useRef(false);

  const dobValid = isValidDob(day, month, year);
  const dobPartial = (day !== "" || month !== "" || year !== "") && !dobValid;
  // Customer must either:
  //   - pick at least one signal (gender or a valid DOB), AND
  //   - not have a partially-filled-or-invalid DOB sitting in the
  //     form. Without the second clause, "gender chosen but day=32"
  //     would silently drop the DOB on save — the customer thinks
  //     they filled both, we'd advance with only gender saved.
  const canSubmit = (gender !== null || dobValid) && !dobPartial;

  const handleSave = async () => {
    if (!canSubmit) return;
    if (savingRef.current) return;
    savingRef.current = true;
    setState({ phase: "saving" });

    // Build the parallel save list. Only include fields the customer
    // actually filled in — saving a half-empty DOB or null gender
    // would 422 the engine.
    const saves: Promise<Response>[] = [];
    if (gender) {
      const form = new FormData();
      form.set("sessionId", sessionId);
      form.set("field", "gender");
      form.set("value", gender);
      saves.push(
        fetch("/apps/vibe/api/onboarding/profile", {
          method: "POST",
          body: form,
        }),
      );
    }
    if (dobValid) {
      const form = new FormData();
      form.set("sessionId", sessionId);
      form.set("field", "date_of_birth");
      form.set("value", toIsoDate(day, month, year));
      saves.push(
        fetch("/apps/vibe/api/onboarding/profile", {
          method: "POST",
          body: form,
        }),
      );
    }

    try {
      const resps = await Promise.all(saves);
      // Surface the first non-ok response we see — better than
      // silently advancing with one half saved. parseActionJson never
      // throws; safe to await in sequence.
      for (const resp of resps) {
        const data = await parseActionJson<{ saved: boolean }>(resp);
        if (!resp.ok || !data.ok) {
          const msg =
            "error" in data && data.error
              ? data.error
              : `Save failed (${resp.status})`;
          setState({ phase: "error", message: msg });
          return;
        }
      }
      onAdvance("completed");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Save failed.";
      setState({ phase: "error", message: msg });
    } finally {
      // Release the in-flight guard regardless of how we exit. Success
      // → card unmounts shortly, error → customer can retry.
      savingRef.current = false;
    }
  };

  const saving = state.phase === "saving";

  // Enter on any DOB segment submits — same pattern as FieldCard's
  // single-input cards. Guard on canSubmit so a half-filled DOB
  // doesn't bypass the validation gate, AND on !saving so a fast
  // double-press during the disabled-attribute propagation window
  // can't queue a second submit.
  const onSegKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && canSubmit && !saving) {
      e.preventDefault();
      handleSave();
    }
  };

  return (
    <div className="onb-card">
      <header className="onb-card__header">
        <h3>Let us learn more about you!</h3>
      </header>

      <fieldset className="onb-fieldset" aria-labelledby="onb-gender-label">
        <legend id="onb-gender-label" className="onb-fieldset__legend">
          Who do you identify as?
        </legend>
        <div className="onb-chips onb-chips--stacked" role="radiogroup" aria-labelledby="onb-gender-label">
          {GENDER_CHIPS.map((g) => (
            <button
              key={g.value}
              type="button"
              role="radio"
              aria-checked={gender === g.value}
              className={`onb-chip ${gender === g.value ? "onb-chip--on" : ""}`}
              onClick={() => setGender(g.value)}
              disabled={saving}
            >
              {g.label}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset className="onb-fieldset" aria-labelledby="onb-dob-label">
        <legend id="onb-dob-label" className="onb-fieldset__legend">
          Date of birth
        </legend>
        <div className="onb-dob">
          <input
            type="number"
            inputMode="numeric"
            placeholder="DD"
            className="onb-dob__seg onb-dob__seg--dd"
            min={1}
            max={31}
            value={day}
            onChange={(e) => {
              const v = e.target.value.replace(/\D/g, "").slice(0, 2);
              setDay(v);
              if (v.length === 2) monthRef.current?.focus();
            }}
            onKeyDown={onSegKeyDown}
            disabled={saving}
            aria-label="Day"
          />
          <span className="onb-dob__sep">/</span>
          <input
            ref={monthRef}
            type="number"
            inputMode="numeric"
            placeholder="MM"
            className="onb-dob__seg onb-dob__seg--mm"
            min={1}
            max={12}
            value={month}
            onChange={(e) => {
              const v = e.target.value.replace(/\D/g, "").slice(0, 2);
              setMonth(v);
              if (v.length === 2) yearRef.current?.focus();
            }}
            onKeyDown={onSegKeyDown}
            disabled={saving}
            aria-label="Month"
          />
          <span className="onb-dob__sep">/</span>
          <input
            ref={yearRef}
            type="number"
            inputMode="numeric"
            placeholder="YYYY"
            className="onb-dob__seg onb-dob__seg--yyyy"
            min={1900}
            max={CURRENT_YEAR}
            value={year}
            onChange={(e) => {
              const v = e.target.value.replace(/\D/g, "").slice(0, 4);
              setYear(v);
            }}
            onKeyDown={onSegKeyDown}
            disabled={saving}
            aria-label="Year"
          />
        </div>
      </fieldset>

      {state.phase === "error" && (
        <div className="onb-field__error">{state.message}</div>
      )}

      <div className="onb-card__actions">
        {/* No Skip button — gender + DOB are the only two
            confidence-load-bearing fields in onboarding. canSubmit
            gates the Save button until the customer commits at least
            one of them. */}
        <button
          type="button"
          className="onb-card__primary"
          onClick={handleSave}
          disabled={saving || !canSubmit}
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
