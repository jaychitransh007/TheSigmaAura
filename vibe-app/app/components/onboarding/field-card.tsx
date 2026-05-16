// Onboarding field card — one question per card (name / DOB / gender /
// height / waist). Each card has a single input, a Save button, and a
// Skip button. On save the value is POSTed to
// /apps/vibe/api/onboarding/profile (one field per call); on skip we
// advance without writing.
//
// The render variant comes from the `kind` prop. The page picks which
// kind to render based on the current onboarding step.

import { useState } from "react";

import type { OnboardingProfileField } from "../../lib/engine.server";

export type FieldKind = "name" | "dob" | "gender" | "height" | "waist";

const KIND_CONFIG: Record<
  FieldKind,
  {
    field: OnboardingProfileField;
    title: string;
    blurb: string;
    placeholder: string;
    inputType: "text" | "date" | "number" | "select";
    options?: { value: string; label: string }[];
    min?: number;
    max?: number;
    step?: number;
  }
> = {
  name: {
    field: "name",
    title: "What should I call you?",
    blurb: "Just a first name is fine.",
    placeholder: "Your name",
    inputType: "text",
  },
  dob: {
    field: "date_of_birth",
    title: "When were you born?",
    blurb: "Helps me read age-aware proportions.",
    placeholder: "",
    inputType: "date",
  },
  gender: {
    field: "gender",
    title: "How do you dress?",
    blurb: "Steers the lookbook I build for you.",
    placeholder: "",
    inputType: "select",
    options: [
      { value: "female", label: "Feminine" },
      { value: "male", label: "Masculine" },
      { value: "non_binary", label: "Mix it up" },
      { value: "prefer_not_to_say", label: "Prefer not to say" },
    ],
  },
  height: {
    field: "height_cm",
    title: "How tall are you?",
    blurb: "Centimetres — fit suggestions get sharper.",
    placeholder: "165",
    inputType: "number",
    min: 50,
    max: 300,
    step: 0.5,
  },
  waist: {
    field: "waist_cm",
    title: "Waist measurement?",
    blurb: "Centimetres. Skip if you'd rather not measure.",
    placeholder: "70",
    inputType: "number",
    min: 30,
    max: 200,
    step: 0.5,
  },
};

type SaveState =
  | { phase: "idle" }
  | { phase: "saving" }
  | { phase: "error"; message: string };

export function FieldCard({
  kind,
  sessionId,
  onAdvance,
}: {
  kind: FieldKind;
  sessionId: string;
  onAdvance: (mode: "completed" | "skipped") => void;
}) {
  const cfg = KIND_CONFIG[kind];
  const [value, setValue] = useState<string>("");
  const [state, setState] = useState<SaveState>({ phase: "idle" });

  const handleSave = async () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setState({ phase: "saving" });

    const form = new FormData();
    form.set("sessionId", sessionId);
    form.set("field", cfg.field);
    form.set("value", trimmed);

    try {
      const resp = await fetch("/apps/vibe/api/onboarding/profile", {
        method: "POST",
        body: form,
      });
      const data = (await resp.json()) as
        | { ok: true; saved: boolean }
        | { ok: false; error: string };
      if (!resp.ok || !data.ok) {
        const msg =
          "error" in data && data.error
            ? data.error
            : `Save failed (${resp.status})`;
        setState({ phase: "error", message: msg });
        return;
      }
      onAdvance("completed");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Save failed.";
      setState({ phase: "error", message: msg });
    }
  };

  const saving = state.phase === "saving";
  // The card's <h3> is the visual question; wire it as the input's
  // accessible label so screen readers announce "What should I call
  // you? — edit text" instead of "edit text" alone.
  const labelId = `onb-label-${kind}`;

  return (
    <div className="onb-card">
      <header className="onb-card__header">
        <h3 id={labelId}>{cfg.title}</h3>
        <p>{cfg.blurb}</p>
      </header>

      <div className="onb-field">
        {cfg.inputType === "select" ? (
          <select
            aria-labelledby={labelId}
            className="onb-field__input"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            disabled={saving}
          >
            <option value="">Choose…</option>
            {cfg.options?.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            aria-labelledby={labelId}
            type={cfg.inputType}
            className="onb-field__input"
            placeholder={cfg.placeholder}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            min={cfg.min}
            max={cfg.max}
            step={cfg.step}
            disabled={saving}
            // Pressing Enter submits the single field.
            onKeyDown={(e) => {
              if (e.key === "Enter" && value.trim()) {
                e.preventDefault();
                handleSave();
              }
            }}
          />
        )}
      </div>

      {state.phase === "error" && (
        <div className="onb-field__error">{state.message}</div>
      )}

      <div className="onb-card__actions">
        <button
          type="button"
          className="onb-card__skip"
          onClick={() => onAdvance("skipped")}
          disabled={saving}
        >
          Skip
        </button>
        <button
          type="button"
          className="onb-card__primary"
          onClick={handleSave}
          disabled={saving || !value.trim()}
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
