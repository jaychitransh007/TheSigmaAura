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

function isHeic(file: File): boolean {
  const type = file.type.toLowerCase();
  if (type === "image/heic" || type === "image/heif") return true;
  // Some browsers (and older Chromes) leave file.type empty for
  // iPhone HEIC; fall back to the extension.
  const name = file.name.toLowerCase();
  return name.endsWith(".heic") || name.endsWith(".heif");
}

/**
 * Browsers can't render HEIC in an <img> tag (Apple's format; only
 * Safari handles it natively and even then unreliably). For HEIC
 * uploads we transcode to JPEG client-side via heic2any so the
 * preview renders AND the engine receives a smaller, universally
 * decodable file. heic2any is dynamically imported so non-HEIC
 * uploads pay zero bundle cost.
 *
 * Returns the original File untouched for non-HEIC inputs.
 */
async function transcodeIfHeic(file: File): Promise<File> {
  if (!isHeic(file)) return file;
  const { default: heic2any } = await import("heic2any");
  const out = await heic2any({
    blob: file,
    toType: "image/jpeg",
    quality: 0.85,
  });
  const blob = Array.isArray(out) ? out[0] : out;
  const newName = file.name.replace(/\.(heic|heif)$/i, ".jpg");
  return new File([blob], newName, { type: "image/jpeg" });
}

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

  // Revoke each side's object URL when:
  //   (a) the URL itself changes — the customer picked a new file, so
  //       the prior object URL is no longer referenced and can go,
  //   (b) the card unmounts.
  //
  // Crucially, NOT on every state change. Zoom / pan / offset updates
  // produce a new SideState object but the same previewUrl. If the
  // effect dep is the whole state object, the cleanup captured during
  // the prior render revokes that same still-displayed URL — the img
  // breaks the moment the customer clicks `+` to zoom in. Depending
  // on the URL string itself avoids that.
  const fullBodyUrl =
    fullBody.phase === "done" ? fullBody.previewUrl : null;
  const headshotUrl =
    headshot.phase === "done" ? headshot.previewUrl : null;

  useEffect(() => {
    if (!fullBodyUrl) return;
    return () => URL.revokeObjectURL(fullBodyUrl);
  }, [fullBodyUrl]);

  useEffect(() => {
    if (!headshotUrl) return;
    return () => URL.revokeObjectURL(headshotUrl);
  }, [headshotUrl]);

  const uploadSide = async (
    category: OnboardingImageCategory,
    rawFile: File,
    setSide: (s: SideState) => void,
  ) => {
    // Cheap client-side guardrail — engine caps at 10MB. Check the
    // ORIGINAL file: HEIC->JPEG transcoding usually shrinks but we
    // don't want to spend ~3s on a heic2any decode just to learn the
    // source was 50MB.
    if (rawFile.size > 10 * 1024 * 1024) {
      setSide({ phase: "error", message: "Image must be under 10MB." });
      return;
    }
    setSide({ phase: "uploading", pct: 0 });

    let file: File;
    try {
      file = await transcodeIfHeic(rawFile);
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Couldn't read that photo format.";
      setSide({ phase: "error", message: msg });
      return;
    }

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
  // Pan drag is local-only while the gesture is in flight. We surface
  // the in-progress offset via a local state slot (so this tile
  // re-renders smoothly without re-running the whole PhotosCard), and
  // commit the final offset to the parent SideState on pointerup.
  // Without this every pointermove would call onTransform → setSide
  // in the parent → PhotosCard re-renders → both PhotoTiles re-render
  // 60+ times a second. The img transform read uses dragOffset when
  // active, falls back to the committed state.{offsetX,offsetY}.
  const dragStart = useRef<{
    x: number;
    y: number;
    baseX: number;
    baseY: number;
  } | null>(null);
  const [dragOffset, setDragOffset] = useState<{ x: number; y: number } | null>(
    null,
  );

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
    // currentTarget is the frame we attached the listener to; .target
    // can resolve to a child if event bubbling kicks in. Capture on
    // currentTarget so we keep receiving moves even if the pointer
    // leaves the frame mid-drag.
    e.currentTarget.setPointerCapture?.(e.pointerId);
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
    setDragOffset({
      x: dragStart.current.baseX + dx,
      y: dragStart.current.baseY + dy,
    });
  };
  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.releasePointerCapture?.(e.pointerId);
    // Compute the final offset from the pointerup event itself, not
    // from dragOffset state. React state updates are async — on a
    // fast lift right after pointermove, the most recent setDragOffset
    // may not have flushed yet, so dragOffset would carry a value
    // from one frame earlier. The dragStart ref + e.clientX/Y give us
    // the exact lift position.
    if (dragStart.current) {
      const dx = e.clientX - dragStart.current.x;
      const dy = e.clientY - dragStart.current.y;
      // Skip the commit when the gesture didn't materially move —
      // a click-down-and-up with no pan would otherwise call
      // onTransform → setSide → re-render PhotosCard (both tiles)
      // for no UI change. 0.5px threshold catches sub-pixel jitter
      // on high-DPI / touch devices where a tap can emit non-zero
      // deltas even when the customer didn't drag.
      if (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5) {
        onTransform({
          ...state,
          offsetX: dragStart.current.baseX + dx,
          offsetY: dragStart.current.baseY + dy,
        });
      }
      setDragOffset(null);
    }
    dragStart.current = null;
  };

  const effOffsetX = dragOffset ? dragOffset.x : state.offsetX;
  const effOffsetY = dragOffset ? dragOffset.y : state.offsetY;
  const transform = `translate3d(${effOffsetX}px, ${effOffsetY}px, 0) scale(${state.zoom})`;
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
