// Combined height + waist onboarding card.
//
// Mirrors GenderDobCard's shape: two fieldsets side by side, segmented
// numeric inputs (feet / inches) for each, single Save button that
// fires parallel POSTs to /apps/vibe/api/onboarding/profile (one per
// field). The customer can fill either or both before saving — at
// least one must be present for Save to enable.
//
// Engine still stores height_cm / waist_cm as decimal centimeters
// (pydantic ge/le constrained), so we convert ft+in → cm on save.

import { useRef, useState } from "react";

import { parseActionJson } from "../../lib/fetch.client";

type SaveState =
  | { phase: "idle" }
  | { phase: "saving" }
  | { phase: "error"; message: string };

const FT_PER_CM = 30.48;
const IN_PER_CM = 2.54;

// Reasonable bounds — anything outside these is a typo. Engine has
// its own ge/le constraints; these match so the client rejects
// nonsense before round-tripping.
const HEIGHT_FT_MIN = 1;
const HEIGHT_FT_MAX = 9;
const WAIST_FT_MIN = 0;
const WAIST_FT_MAX = 5;
const IN_MIN = 0;
const IN_MAX = 11;

type Measurement = { ft: string; in: string };

function isValidMeasurement(
  m: Measurement,
  ftMin: number,
  ftMax: number,
): boolean {
  if (!m.ft && !m.in) return false;
  const ft = m.ft === "" ? 0 : Number(m.ft);
  const inches = m.in === "" ? 0 : Number(m.in);
  if (!Number.isFinite(ft) || !Number.isFinite(inches)) return false;
  if (ft < ftMin || ft > ftMax) return false;
  if (inches < IN_MIN || inches > IN_MAX) return false;
  // Reject all-zero
  return ft + inches > 0;
}

function toCm(m: Measurement): number {
  const ft = m.ft === "" ? 0 : Number(m.ft);
  const inches = m.in === "" ? 0 : Number(m.in);
  return Math.round((ft * FT_PER_CM + inches * IN_PER_CM) * 10) / 10;
}

export function HeightWaistCard({
  sessionId,
  onAdvance,
}: {
  sessionId: string;
  onAdvance: (mode: "completed" | "skipped") => void;
}) {
  const [height, setHeight] = useState<Measurement>({ ft: "", in: "" });
  const [waist, setWaist] = useState<Measurement>({ ft: "", in: "" });
  const [state, setState] = useState<SaveState>({ phase: "idle" });
  const savingRef = useRef(false);

  // Auto-advance focus across the four segments (height ft → height in
  // → waist ft → waist in) once the customer fills each.
  const heightInRef = useRef<HTMLInputElement>(null);
  const waistFtRef = useRef<HTMLInputElement>(null);
  const waistInRef = useRef<HTMLInputElement>(null);

  const heightValid = isValidMeasurement(height, HEIGHT_FT_MIN, HEIGHT_FT_MAX);
  const heightPartial =
    (height.ft !== "" || height.in !== "") && !heightValid;
  const waistValid = isValidMeasurement(waist, WAIST_FT_MIN, WAIST_FT_MAX);
  const waistPartial = (waist.ft !== "" || waist.in !== "") && !waistValid;

  // Customer must have at least one valid measurement AND no
  // partially-filled-or-invalid measurement sitting in the form.
  const canSubmit =
    (heightValid || waistValid) && !heightPartial && !waistPartial;

  const saving = state.phase === "saving";

  const postField = (
    field: "height_cm" | "waist_cm",
    value: number,
  ): Promise<Response> => {
    const form = new FormData();
    form.set("sessionId", sessionId);
    form.set("field", field);
    form.set("value", String(value));
    return fetch("/apps/vibe/api/onboarding/profile", {
      method: "POST",
      body: form,
    });
  };

  const handleSave = async () => {
    if (!canSubmit) return;
    if (savingRef.current) return;
    savingRef.current = true;
    setState({ phase: "saving" });

    const saves: Promise<Response>[] = [];
    if (heightValid) saves.push(postField("height_cm", toCm(height)));
    if (waistValid) saves.push(postField("waist_cm", toCm(waist)));

    try {
      const resps = await Promise.all(saves);
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
      savingRef.current = false;
    }
  };

  const handleSkip = () => {
    if (saving) return;
    onAdvance("skipped");
  };

  const onSegKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && canSubmit && !saving) {
      e.preventDefault();
      handleSave();
    }
  };

  return (
    <div className="onb-card">
      <header className="onb-card__header">
        <h3>A couple of measurements</h3>
        <p>Optional — helps me read proportions for fit and silhouette.</p>
      </header>

      <div className="onb-measurements">
        <fieldset className="onb-fieldset" aria-labelledby="onb-height-label">
          <legend id="onb-height-label" className="onb-fieldset__legend">
            Height
          </legend>
          <div className="onb-measurement">
            <input
              type="number"
              inputMode="numeric"
              placeholder="5"
              className="onb-measurement__seg"
              min={HEIGHT_FT_MIN}
              max={HEIGHT_FT_MAX}
              value={height.ft}
              onChange={(e) => {
                const v = e.target.value.replace(/\D/g, "").slice(0, 1);
                setHeight((h) => ({ ...h, ft: v }));
                if (v.length === 1) heightInRef.current?.focus();
              }}
              onKeyDown={onSegKeyDown}
              disabled={saving}
              aria-label="Height feet"
            />
            <span className="onb-measurement__unit">ft</span>
            <input
              ref={heightInRef}
              type="number"
              inputMode="numeric"
              placeholder="6"
              className="onb-measurement__seg"
              min={IN_MIN}
              max={IN_MAX}
              value={height.in}
              onChange={(e) => {
                const v = e.target.value.replace(/\D/g, "").slice(0, 2);
                setHeight((h) => ({ ...h, in: v }));
                if (v.length === 2) waistFtRef.current?.focus();
              }}
              onKeyDown={onSegKeyDown}
              disabled={saving}
              aria-label="Height inches"
            />
            <span className="onb-measurement__unit">in</span>
          </div>
        </fieldset>

        <fieldset className="onb-fieldset" aria-labelledby="onb-waist-label">
          <legend id="onb-waist-label" className="onb-fieldset__legend">
            Waist
          </legend>
          <div className="onb-measurement">
            <input
              ref={waistFtRef}
              type="number"
              inputMode="numeric"
              placeholder="2"
              className="onb-measurement__seg"
              min={WAIST_FT_MIN}
              max={WAIST_FT_MAX}
              value={waist.ft}
              onChange={(e) => {
                const v = e.target.value.replace(/\D/g, "").slice(0, 1);
                setWaist((w) => ({ ...w, ft: v }));
                if (v.length === 1) waistInRef.current?.focus();
              }}
              onKeyDown={onSegKeyDown}
              disabled={saving}
              aria-label="Waist feet"
            />
            <span className="onb-measurement__unit">ft</span>
            <input
              ref={waistInRef}
              type="number"
              inputMode="numeric"
              placeholder="6"
              className="onb-measurement__seg"
              min={IN_MIN}
              max={IN_MAX}
              value={waist.in}
              onChange={(e) => {
                const v = e.target.value.replace(/\D/g, "").slice(0, 2);
                setWaist((w) => ({ ...w, in: v }));
              }}
              onKeyDown={onSegKeyDown}
              disabled={saving}
              aria-label="Waist inches"
            />
            <span className="onb-measurement__unit">in</span>
          </div>
        </fieldset>
      </div>

      {state.phase === "error" && (
        <div className="onb-field__error">{state.message}</div>
      )}

      <div className="onb-card__actions">
        <button
          type="button"
          className="onb-card__skip"
          onClick={handleSkip}
          disabled={saving}
        >
          Skip
        </button>
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
