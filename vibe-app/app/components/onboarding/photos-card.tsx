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

import { useEffect, useRef, useState } from "react";

import type { OnboardingImageCategory } from "../../lib/engine.server";

type SideState =
  | { phase: "idle" }
  | { phase: "uploading"; pct: number }
  | {
      phase: "done";
      previewUrl: string;
      // Per-side framing controls. Customer can zoom in and pan to
      // pick which part of the image fills the card frame. Image is
      // still sent to the engine full-size — these transforms are
      // cosmetic, just so the customer's preview looks right.
      zoom: number;
      offsetX: number;
      offsetY: number;
    }
  | { phase: "error"; message: string };

const HEADSHOT_HINT = "Face only, hair away from face";
const FULL_BODY_HINT = "Head to feet, arms relaxed at sides";

const ZOOM_MIN = 1;
const ZOOM_MAX = 3;
const ZOOM_STEP = 0.2;

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

  // Revoke each side's object URL independently when that side
  // changes OR the card unmounts. Without this the browser keeps the
  // file's bytes in memory for the page's lifetime — fine in dev, but
  // accumulates if a customer re-picks a photo.
  //
  // The effects MUST be split per-side. A single effect with
  // [fullBody, headshot] in its deps would fire on every change to
  // EITHER, and its cleanup (captured at the previous render) would
  // revoke the other side's URL by accident — e.g. headshot upload
  // completes → effect re-runs → cleanup revokes the still-displayed
  // fullBody preview because that's what was in the closure. Each
  // effect now keys only on its own state and revokes only its own
  // URL.
  useEffect(() => {
    return () => {
      if (fullBody.phase === "done") URL.revokeObjectURL(fullBody.previewUrl);
    };
  }, [fullBody]);

  useEffect(() => {
    return () => {
      if (headshot.phase === "done") URL.revokeObjectURL(headshot.previewUrl);
    };
  }, [headshot]);

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
      // Response.json() throws "Unexpected token '<'..." when the
      // route ate a 500 and Vercel served an HTML error page. Sniff
      // the content-type and surface a friendly message instead of
      // bubbling the SyntaxError to the customer.
      const isJson = (resp.headers.get("content-type") ?? "").includes(
        "application/json",
      );
      const data = isJson
        ? ((await resp.json()) as
            | { ok: true; saved: boolean }
            | { ok: false; error: string })
        : { ok: false as const, error: `Upload failed (HTTP ${resp.status})` };
      if (!resp.ok || !data.ok) {
        const msg =
          "error" in data && data.error ? data.error : `Upload failed (${resp.status})`;
        setSide({ phase: "error", message: msg });
        return;
      }
      // The engine response doesn't include a viewable URL (images are
      // stored encrypted by the engine). Use the local object URL for
      // the thumbnail preview — it'll get revoked when the card
      // unmounts in the parent's advance step. zoom=1 + offset 0
      // start the customer with the cover-fitted frame; they can
      // zoom + pan from here to pick a tighter crop for their preview.
      setSide({
        phase: "done",
        previewUrl: URL.createObjectURL(file),
        zoom: 1,
        offsetX: 0,
        offsetY: 0,
      });
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

      <div className="onb-photos">
        <PhotoTile
          label="Full body"
          hint={FULL_BODY_HINT}
          state={fullBody}
          onPick={(f) => uploadSide("full_body", f, setFullBody)}
          onTransform={(next) => setFullBody(next)}
        />
        <PhotoTile
          label="Headshot"
          hint={HEADSHOT_HINT}
          state={headshot}
          onPick={(f) => uploadSide("headshot", f, setHeadshot)}
          onTransform={(next) => setHeadshot(next)}
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
  onTransform,
}: {
  label: string;
  hint: string;
  state: SideState;
  onPick: (f: File) => void;
  onTransform: (next: SideState) => void;
}) {
  const inputId = `onb-photo-${label.toLowerCase().replace(/\s+/g, "-")}`;
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) onPick(file);
    // Reset the input so picking the same file twice re-fires onChange
    // (otherwise a customer who picks a photo, switches to another,
    // then back to the first would silently no-op).
    e.target.value = "";
  };

  // Done state gets its own subtree with zoom + pan + change-photo.
  // The non-done states keep the original label-as-clickable affordance
  // because clicking anywhere on the empty tile to open the picker is
  // the right shortcut.
  if (state.phase === "done") {
    return (
      <PhotoTilePreview
        label={label}
        state={state}
        inputId={inputId}
        inputRef={inputRef}
        onTransform={onTransform}
      >
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept="image/*"
          className="onb-photo__input"
          onChange={handleFile}
        />
      </PhotoTilePreview>
    );
  }

  return (
    <label className={`onb-photo onb-photo--${state.phase}`} htmlFor={inputId}>
      <div className="onb-photo__inner">
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
      </div>
      <input
        id={inputId}
        type="file"
        accept="image/*"
        className="onb-photo__input"
        onChange={handleFile}
        disabled={state.phase === "uploading"}
      />
    </label>
  );
}

function PhotoTilePreview({
  label,
  state,
  inputId,
  inputRef,
  onTransform,
  children,
}: {
  label: string;
  state: Extract<SideState, { phase: "done" }>;
  inputId: string;
  inputRef: React.RefObject<HTMLInputElement>;
  onTransform: (next: SideState) => void;
  children: React.ReactNode;
}) {
  // Pan drag state — kept local because it's mid-gesture; on
  // pointerup we commit the final offset back to SideState so it
  // persists across re-renders.
  const dragStart = useRef<{
    x: number;
    y: number;
    baseX: number;
    baseY: number;
  } | null>(null);

  const setZoom = (next: number) => {
    onTransform({ ...state, zoom: Math.min(Math.max(next, ZOOM_MIN), ZOOM_MAX) });
  };
  const reset = () => {
    onTransform({ ...state, zoom: 1, offsetX: 0, offsetY: 0 });
  };
  const changePhoto = () => {
    inputRef.current?.click();
  };

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    // Don't pan with zoom = 1 — there's nothing outside the frame.
    if (state.zoom <= ZOOM_MIN) return;
    (e.target as Element).setPointerCapture?.(e.pointerId);
    dragStart.current = {
      x: e.clientX,
      y: e.clientY,
      baseX: state.offsetX,
      baseY: state.offsetY,
    };
  };
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragStart.current) return;
    const dx = e.clientX - dragStart.current.x;
    const dy = e.clientY - dragStart.current.y;
    onTransform({
      ...state,
      offsetX: dragStart.current.baseX + dx,
      offsetY: dragStart.current.baseY + dy,
    });
  };
  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    (e.target as Element).releasePointerCapture?.(e.pointerId);
    dragStart.current = null;
  };

  const transform = `translate3d(${state.offsetX}px, ${state.offsetY}px, 0) scale(${state.zoom})`;
  const grabCursor = state.zoom > ZOOM_MIN ? "grab" : "default";

  return (
    <div className="onb-photo onb-photo--done">
      <div
        className="onb-photo__frame"
        style={{ cursor: grabCursor }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <img
          src={state.previewUrl}
          alt={label}
          className="onb-photo__preview"
          style={{ transform }}
          draggable={false}
        />
      </div>
      <div className="onb-photo__controls">
        <button
          type="button"
          className="onb-photo__ctrl"
          onClick={() => setZoom(state.zoom - ZOOM_STEP)}
          disabled={state.zoom <= ZOOM_MIN}
          aria-label="Zoom out"
        >
          −
        </button>
        <button
          type="button"
          className="onb-photo__ctrl"
          onClick={() => setZoom(state.zoom + ZOOM_STEP)}
          disabled={state.zoom >= ZOOM_MAX}
          aria-label="Zoom in"
        >
          +
        </button>
        <button
          type="button"
          className="onb-photo__ctrl onb-photo__ctrl--text"
          onClick={reset}
          aria-label="Reset zoom and position"
        >
          Reset
        </button>
        <button
          type="button"
          className="onb-photo__ctrl onb-photo__ctrl--text"
          onClick={changePhoto}
          aria-label="Choose a different photo"
        >
          Change
        </button>
      </div>
      {children}
    </div>
  );
}
