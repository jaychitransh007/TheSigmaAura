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
  // Upload succeeded but the browser can't render the source (HEIC
  // that heic2any couldn't transcode). Engine still got the file, so
  // we don't block the customer — just skip the preview/zoom UI.
  | { phase: "done-no-preview" }
  | { phase: "error"; message: string };

const HEADSHOT_HINT = "Face only, hair away from face";
const FULL_BODY_HINT = "Head to feet, arms relaxed at sides";

const ZOOM_MIN = 1;
const ZOOM_MAX = 3;
const ZOOM_STEP = 0.2;

function isHeic(file: File): boolean {
  const type = file.type.toLowerCase();
  // startsWith catches `image/heic-sequence` / `image/heif-sequence`
  // emitted for iPhone burst / Live Photos in addition to plain
  // `image/heic` / `image/heif`.
  if (type.startsWith("image/heic") || type.startsWith("image/heif")) {
    return true;
  }
  // Some browsers (and older Chromes) leave file.type empty for
  // iPhone HEIC; fall back to the extension. Regex covers the
  // sequence-variant extensions too (.heics / .heifs).
  return /\.(heic|heif|heics|heifs)$/i.test(file.name);
}

type TranscodeOutcome =
  | { ok: true; file: File; previewable: true }
  | { ok: true; file: File; previewable: false };

/**
 * Prepare a file for upload. Non-HEIC files pass through unchanged
 * (previewable: true — browser can render the bytes directly).
 *
 * HEIC inputs: try to transcode to JPEG via heic2any so the preview
 * renders AND the upload payload is smaller. If conversion fails
 * (encrypted HEIC, multi-frame Live Photo, unsupported variant,
 * corrupt file), fall back to uploading the original HEIC — the
 * engine's Pillow handling will pick it up server-side. In that case
 * previewable=false so the UI can show a "Photo uploaded —
 * preview unavailable" tile instead of a broken-image glyph.
 *
 * heic2any is dynamically imported so non-HEIC uploads pay zero
 * bundle cost.
 */
async function prepareUpload(file: File): Promise<TranscodeOutcome> {
  if (!isHeic(file)) {
    return { ok: true, file, previewable: true };
  }
  try {
    const { default: heic2any } = await import("heic2any");
    const out = await heic2any({
      blob: file,
      toType: "image/jpeg",
      quality: 0.85,
    });
    const blob = Array.isArray(out) ? out[0] : out;
    // Strip any HEIF-family extension, then unconditionally append .jpg.
    // Covers the case where isHeic matched via MIME type but the file
    // had a generic name like "blob" with no extension to swap.
    const newName =
      file.name.replace(/\.(heic|heif|heics|heifs)$/i, "") + ".jpg";
    return {
      ok: true,
      file: new File([blob], newName, { type: "image/jpeg" }),
      previewable: true,
    };
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn("HEIC client-side transcode failed; uploading original:", err);
    return { ok: true, file, previewable: false };
  }
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

    const prepared = await prepareUpload(rawFile);
    const file = prepared.file;

    const form = new FormData();
    form.set("sessionId", sessionId);
    form.set("category", category);
    form.set("file", file);

    try {
      const resp = await fetch("/apps/vibe/api/onboarding/image", {
        method: "POST",
        body: form,
      });
      // Don't gate on Content-Type — some intermediaries (App Proxy,
      // Vercel edge, etc.) can strip or rewrite the header even when
      // the body is valid JSON. Just try to parse; if parse throws
      // (e.g. body is HTML), fall back to a friendly status-keyed
      // error string instead of letting "Unexpected token '<'"
      // bubble to the customer.
      let data:
        | { ok: true; saved: boolean }
        | { ok: false; error: string };
      try {
        data = await resp.json();
      } catch {
        data = resp.ok
          ? { ok: false, error: "Upload returned an unreadable response." }
          : { ok: false, error: `Upload failed (HTTP ${resp.status})` };
      }
      if (!resp.ok || !data.ok) {
        const msg =
          "error" in data && data.error ? data.error : `Upload failed (${resp.status})`;
        setSide({ phase: "error", message: msg });
        return;
      }
      // Upload succeeded. If the file isn't previewable (HEIC that
      // heic2any couldn't transcode), show the "uploaded but no
      // preview" tile instead of a broken-image glyph. Otherwise mint
      // an object URL for the cover-fitted preview the customer can
      // zoom + pan.
      if (prepared.previewable) {
        setSide({
          phase: "done",
          previewUrl: URL.createObjectURL(file),
          zoom: 1,
          offsetX: 0,
          offsetY: 0,
        });
      } else {
        setSide({ phase: "done-no-preview" });
      }
      onUploaded?.(category);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Upload failed.";
      setSide({ phase: "error", message: msg });
    }
  };

  // "done-no-preview" counts as done for the purpose of advancing —
  // the customer's photo IS uploaded, the preview just can't render.
  const isSideDone = (s: SideState): boolean =>
    s.phase === "done" || s.phase === "done-no-preview";
  const bothDone = isSideDone(fullBody) && isSideDone(headshot);
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
            anyInFlight || (!isSideDone(fullBody) && !isSideDone(headshot))
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

  // Uploaded but the browser can't render this file (HEIC that
  // heic2any couldn't transcode). Show a static "saved" tile with a
  // Change button so the customer can retry with a different photo.
  if (state.phase === "done-no-preview") {
    return (
      <div className="onb-photo onb-photo--done-no-preview">
        <div className="onb-photo__inner">
          <div className="onb-photo__label">{label}</div>
          <div className="onb-photo__hint">
            ✓ Saved · preview unavailable
          </div>
          <button
            type="button"
            className="onb-photo__cta onb-photo__cta--button"
            onClick={() => inputRef.current?.click()}
          >
            Change
          </button>
        </div>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept="image/*"
          className="onb-photo__input"
          onChange={handleFile}
        />
      </div>
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
