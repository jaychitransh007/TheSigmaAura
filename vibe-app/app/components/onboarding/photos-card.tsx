// Onboarding photo card — 2-up upload (full body + headshot).
//
// Each side independently uploads to /apps/vibe/api/onboarding/image
// when the customer picks a file. Both have their own progress state.
// Skip dismisses without uploading.
//
// Once both photos land OR the customer hits Continue / Skip, the
// parent's onAdvance() fires and the page emits the next onboarding
// card. The card itself stays mounted only while active — when the
// step advances it's replaced by a static "Photos saved" / "Photos
// skipped" line (rendered by message.tsx), not by this component.

import { useState } from "react";

import type { OnboardingImageCategory } from "../../lib/engine.server";

type SideState =
  | { phase: "idle" }
  | { phase: "uploading"; pct: number }
  | { phase: "done"; previewUrl: string }
  | { phase: "error"; message: string };

const GUIDELINES = [
  "Plain background, good lighting",
  "Fitted clothing (not loose or baggy)",
  "One person, looking at the camera",
];

const HEADSHOT_HINT = "Face only, hair away from face";
const FULL_BODY_HINT = "Head to feet, arms relaxed at sides";

export function PhotosCard({
  sessionId,
  onAdvance,
  onUploaded,
}: {
  sessionId: string;
  onAdvance: (mode: "completed" | "skipped") => void;
  /** Fires per successful upload — lets the page trigger analysis phases. */
  onUploaded?: (category: OnboardingImageCategory) => void;
}) {
  const [fullBody, setFullBody] = useState<SideState>({ phase: "idle" });
  const [headshot, setHeadshot] = useState<SideState>({ phase: "idle" });

  const uploadSide = async (
    category: OnboardingImageCategory,
    file: File,
    setSide: (s: SideState) => void,
  ) => {
    // Cheap client-side guardrail — engine caps at 10MB.
    if (file.size > 10 * 1024 * 1024) {
      setSide({ phase: "error", message: "Image must be under 10MB." });
      return;
    }
    setSide({ phase: "uploading", pct: 0 });
    const form = new FormData();
    form.set("sessionId", sessionId);
    form.set("category", category);
    form.set("file", file);

    try {
      const resp = await fetch("/apps/vibe/api/onboarding/image", {
        method: "POST",
        body: form,
      });
      const data = (await resp.json()) as
        | { ok: true; saved: boolean }
        | { ok: false; error: string };
      if (!resp.ok || !data.ok) {
        const msg =
          "error" in data && data.error ? data.error : `Upload failed (${resp.status})`;
        setSide({ phase: "error", message: msg });
        return;
      }
      // The engine response doesn't include a viewable URL (images are
      // stored encrypted by the engine). Use the local object URL for
      // the thumbnail preview — it'll get revoked when the card
      // unmounts in the parent's advance step.
      setSide({ phase: "done", previewUrl: URL.createObjectURL(file) });
      onUploaded?.(category);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Upload failed.";
      setSide({ phase: "error", message: msg });
    }
  };

  const bothDone = fullBody.phase === "done" && headshot.phase === "done";
  const anyInFlight =
    fullBody.phase === "uploading" || headshot.phase === "uploading";

  return (
    <div className="onb-card">
      <header className="onb-card__header">
        <h3>Let's see what works on you</h3>
        <p>
          Two quick photos help me get your colours and proportions right.
          Skip if you'd rather not — we can still chat.
        </p>
      </header>

      <ul className="onb-card__guidelines">
        {GUIDELINES.map((g) => (
          <li key={g}>{g}</li>
        ))}
      </ul>

      <div className="onb-photos">
        <PhotoTile
          label="Full body"
          hint={FULL_BODY_HINT}
          state={fullBody}
          onPick={(f) => uploadSide("full_body", f, setFullBody)}
        />
        <PhotoTile
          label="Headshot"
          hint={HEADSHOT_HINT}
          state={headshot}
          onPick={(f) => uploadSide("headshot", f, setHeadshot)}
        />
      </div>

      <div className="onb-card__actions">
        <button
          type="button"
          className="onb-card__skip"
          onClick={() => onAdvance("skipped")}
          disabled={anyInFlight}
        >
          Skip
        </button>
        <button
          type="button"
          className="onb-card__primary"
          onClick={() => onAdvance("completed")}
          // Continue is available once at least one side is uploaded;
          // both lit when both done. Disabled while uploads run so we
          // don't advance mid-flight.
          disabled={
            anyInFlight ||
            (fullBody.phase !== "done" && headshot.phase !== "done")
          }
        >
          {bothDone ? "Continue" : "Continue with what I've got"}
        </button>
      </div>
    </div>
  );
}

function PhotoTile({
  label,
  hint,
  state,
  onPick,
}: {
  label: string;
  hint: string;
  state: SideState;
  onPick: (f: File) => void;
}) {
  const inputId = `onb-photo-${label.toLowerCase().replace(/\s+/g, "-")}`;

  return (
    <label className={`onb-photo onb-photo--${state.phase}`} htmlFor={inputId}>
      <div className="onb-photo__inner">
        {state.phase === "done" ? (
          <img src={state.previewUrl} alt={label} className="onb-photo__preview" />
        ) : (
          <>
            <div className="onb-photo__label">{label}</div>
            <div className="onb-photo__hint">{hint}</div>
            {state.phase === "uploading" && (
              <div className="onb-photo__uploading">Uploading…</div>
            )}
            {state.phase === "error" && (
              <div className="onb-photo__error">{state.message}</div>
            )}
            {state.phase === "idle" && (
              <div className="onb-photo__cta">Choose file</div>
            )}
          </>
        )}
      </div>
      <input
        id={inputId}
        type="file"
        accept="image/*"
        className="onb-photo__input"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onPick(file);
        }}
        disabled={state.phase === "uploading"}
      />
    </label>
  );
}
