// Outfit Check page (D.C.5).
// URL: thesigmavibe.shop/apps/vibe/check
//
// Single-shot flow: customer uploads a photo of an outfit they're
// wearing → engine returns stylist commentary in the assistant_message
// + alternative outfit cards "or try this instead". Reuses the engine
// turn machinery (resolve → start → poll); the dispatcher action lives
// at /apps/vibe/api/check so the server-side outfit-check prompt
// stays canonical (see apps.vibe.api.check.tsx).
//
// State machine:
//   idle     — empty, file picker dominant
//   selected — file chosen, preview + "Get feedback" button
//   running  — poll loop active, stage indicator shown
//   result   — verdict + alternatives, "Check another outfit" CTA
//   error    — banner over preview, retry by re-clicking "Get feedback"

import { useEffect, useMemo, useRef, useState } from "react";
import type { LinksFunction, LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import { OutfitCard } from "../components/conversation/outfit-card";
import { VibePageShell } from "../components/vibe-page-shell";
import checkStyles from "../components/check/styles.css?url";
import wardrobeStyles from "../components/wardrobe/styles.css?url";
import type { Outfit, TurnStatusResponse } from "../lib/engine.server";
import {
  getOrCreateClientSessionId,
  readMergedCustomerId,
} from "../lib/session.client";
import { authenticate } from "../shopify.server";

export const links: LinksFunction = () => [
  { rel: "stylesheet", href: wardrobeStyles },
  { rel: "stylesheet", href: checkStyles },
  { rel: "preconnect", href: "https://fonts.googleapis.com" },
  { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
  {
    rel: "stylesheet",
    href: "https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,600;1,400&display=swap",
  },
];

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.public.appProxy(request);
  return json({});
};

type CheckState =
  | { kind: "idle" }
  | { kind: "selected"; file: File; previewUrl: string }
  | {
      kind: "running";
      previewUrl: string;
      stage: string;
      conversationId: string;
      jobId: string;
    }
  | {
      kind: "result";
      previewUrl: string;
      message: string;
      outfits: Outfit[];
    }
  | { kind: "error"; previewUrl: string | null; message: string };

// Match the engine's stage events to friendlier copy. Same vocabulary
// the conversation StageIndicator uses, trimmed to the stages this
// page actually surfaces.
const STAGE_LABELS: Record<string, string> = {
  planner_complete: "Reading the look…",
  architect_complete: "Mapping the silhouette…",
  composer_complete: "Lining up alternatives…",
  rater_complete: "Cross-checking the fit…",
  tryon_complete: "Almost there…",
};

const POLL_INTERVAL_MS = 1500;
// Reasonable ceiling on the polling loop. Engine turns are 30–60s on a
// warm path; this caps wall-clock at 2 min to keep the UI from spinning
// forever on a stuck job. Customer can just retry.
const MAX_POLL_ATTEMPTS = 80;

export default function CheckPage() {
  useLoaderData();
  const [sessionId, setSessionId] = useState("");
  const [state, setState] = useState<CheckState>({ kind: "idle" });
  const [dragOver, setDragOver] = useState(false);
  const pollAbortRef = useRef<{ aborted: boolean } | null>(null);

  // Resolve identity once on mount. Same pattern as the wardrobe /
  // looks pages — prefer the merged shopify:{id}, fall back to the
  // anonymous localStorage UUID.
  useEffect(() => {
    const merged = readMergedCustomerId();
    setSessionId(merged ? `shopify:${merged}` : getOrCreateClientSessionId());
  }, []);

  // Tear down preview blob URLs when the state changes; otherwise
  // each new upload leaks a blob URL into the page.
  useEffect(() => {
    if (state.kind === "selected") {
      const url = state.previewUrl;
      return () => URL.revokeObjectURL(url);
    }
  }, [state]);

  // Cancel any in-flight poll on unmount.
  useEffect(() => {
    return () => {
      if (pollAbortRef.current) pollAbortRef.current.aborted = true;
    };
  }, []);

  function pickFile(file: File | null | undefined) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setState({
        kind: "error",
        previewUrl: null,
        message: "That doesn't look like an image — pick a JPG or PNG.",
      });
      return;
    }
    // Vercel rejects >4.5MB request bodies before the handler runs;
    // surface the limit as a friendly error here instead of a generic
    // 500 from the upstream.
    if (file.size > 4 * 1024 * 1024) {
      setState({
        kind: "error",
        previewUrl: null,
        message:
          "That photo is over 4MB — try a smaller one, or take the shot at a lower resolution.",
      });
      return;
    }
    const previewUrl = URL.createObjectURL(file);
    setState({ kind: "selected", file, previewUrl });
  }

  async function fileToDataUrl(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(reader.error ?? new Error("Read failed"));
      reader.onload = () => {
        const result = reader.result;
        if (typeof result !== "string") {
          reject(new Error("Unexpected reader result"));
          return;
        }
        resolve(result);
      };
      reader.readAsDataURL(file);
    });
  }

  async function submitCheck() {
    if (state.kind !== "selected" || !sessionId) return;
    const { file, previewUrl } = state;
    let dataUrl: string;
    try {
      dataUrl = await fileToDataUrl(file);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Couldn't read that photo.";
      setState({ kind: "error", previewUrl, message });
      return;
    }

    setState({
      kind: "running",
      previewUrl,
      stage: "Reading the look…",
      conversationId: "",
      jobId: "",
    });

    let conversationId = "";
    let jobId = "";
    try {
      const form = new FormData();
      form.set("sessionId", sessionId);
      form.set("imageData", dataUrl);
      const resp = await fetch("/apps/vibe/api/check", {
        method: "POST",
        body: form,
      });
      const body = (await resp.json()) as
        | { ok: true; conversationId: string; jobId: string }
        | { ok: false; error: string };
      if (!resp.ok || !body.ok) {
        setState({
          kind: "error",
          previewUrl,
          message: body.ok ? "Couldn't start the check." : body.error,
        });
        return;
      }
      conversationId = body.conversationId;
      jobId = body.jobId;
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Network error starting the check.";
      setState({ kind: "error", previewUrl, message });
      return;
    }

    // Poll loop. Pure setTimeout / fetch — no AbortController in the
    // hot path because Vercel's serverless functions don't expose
    // useful cancellation, and re-entry guard via `aborted` flag is
    // enough to prevent double-runs on fast remounts.
    const ticket = { aborted: false };
    pollAbortRef.current = ticket;

    setState({
      kind: "running",
      previewUrl,
      stage: "Reading the look…",
      conversationId,
      jobId,
    });

    let attempts = 0;
    const poll = async () => {
      if (ticket.aborted) return;
      attempts += 1;
      if (attempts > MAX_POLL_ATTEMPTS) {
        setState({
          kind: "error",
          previewUrl,
          message:
            "The engine took longer than expected. Try again in a moment.",
        });
        return;
      }
      try {
        const resp = await fetch(
          `/apps/vibe/api/poll?conv=${encodeURIComponent(conversationId)}` +
            `&job=${encodeURIComponent(jobId)}`,
        );
        const status = (await resp.json()) as TurnStatusResponse;
        if (ticket.aborted) return;

        const latestStage = (status.stages ?? [])[status.stages.length - 1];
        const stageLabel = latestStage
          ? STAGE_LABELS[latestStage.stage] ||
            latestStage.message ||
            "Working on it…"
          : "Reading the look…";
        setState((prev) =>
          prev.kind === "running" ? { ...prev, stage: stageLabel } : prev,
        );

        if (status.status === "succeeded" && status.result) {
          setState({
            kind: "result",
            previewUrl,
            message: status.result.message,
            outfits: status.result.outfits,
          });
          return;
        }
        if (status.status === "failed") {
          setState({
            kind: "error",
            previewUrl,
            message: status.error || "The check failed. Try again.",
          });
          return;
        }
        setTimeout(poll, POLL_INTERVAL_MS);
      } catch (err) {
        if (ticket.aborted) return;
        const message = err instanceof Error ? err.message : "Poll failed";
        setState({ kind: "error", previewUrl, message });
      }
    };
    setTimeout(poll, POLL_INTERVAL_MS);
  }

  function reset() {
    if (pollAbortRef.current) pollAbortRef.current.aborted = true;
    pollAbortRef.current = null;
    setState({ kind: "idle" });
  }

  return (
    <VibePageShell title="Outfit Check">
      <p className="vibe-check-intro">
        Upload a photo of what you're wearing. Vibe gives you an honest read —
        what's working, what isn't, and a couple of alternatives if you'd
        change something.
      </p>

      {state.kind === "idle" ? (
        <PickerCard
          dragOver={dragOver}
          onDragOver={setDragOver}
          onPick={pickFile}
        />
      ) : null}

      {state.kind === "error" ? (
        <div className="vibe-error-banner" style={{ marginBottom: "1rem" }}>
          {state.message}
        </div>
      ) : null}

      {(state.kind === "selected" ||
        state.kind === "running" ||
        state.kind === "result" ||
        (state.kind === "error" && state.previewUrl)) ? (
        <PreviewCard
          previewUrl={
            state.kind === "error"
              ? state.previewUrl!
              : state.previewUrl
          }
          state={state}
          onSubmit={submitCheck}
          onReset={reset}
          canSubmit={!!sessionId}
        />
      ) : null}

      {state.kind === "running" ? (
        <div className="vibe-check-stage" role="status" aria-live="polite">
          <span className="vibe-check-stage-dot" aria-hidden="true" />
          <span>{state.stage}</span>
        </div>
      ) : null}

      {state.kind === "result" ? (
        <ResultPanel
          message={state.message}
          outfits={state.outfits}
          onReset={reset}
        />
      ) : null}
    </VibePageShell>
  );
}

// Local stub for useLoaderData since the page only needs to assert the
// loader's signature without consuming any of its keys.
function useLoaderData() {
  return undefined;
}

function PickerCard({
  dragOver,
  onDragOver,
  onPick,
}: {
  dragOver: boolean;
  onDragOver: (v: boolean) => void;
  onPick: (file: File | null) => void;
}) {
  return (
    <label
      className={
        "vibe-check-picker" + (dragOver ? " vibe-check-picker--dragover" : "")
      }
      htmlFor="vibe-check-file"
      onDragOver={(e) => {
        e.preventDefault();
        onDragOver(true);
      }}
      onDragLeave={() => onDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        onDragOver(false);
        onPick(e.dataTransfer.files?.[0] ?? null);
      }}
    >
      <input
        id="vibe-check-file"
        type="file"
        accept="image/*"
        onChange={(e) => onPick(e.currentTarget.files?.[0] ?? null)}
      />
      <svg
        className="vibe-check-picker-icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        aria-hidden="true"
      >
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <circle cx="9" cy="11" r="2" />
        <path d="M21 17l-5-5-4 4-3-3-6 6" />
      </svg>
      <p className="vibe-check-picker-title">Drop a photo, or click to upload</p>
      <p className="vibe-check-picker-help">
        Full-length shot works best. Under 4MB.
      </p>
    </label>
  );
}

function PreviewCard({
  previewUrl,
  state,
  onSubmit,
  onReset,
  canSubmit,
}: {
  previewUrl: string;
  state: CheckState;
  onSubmit: () => void;
  onReset: () => void;
  canSubmit: boolean;
}) {
  const isRunning = state.kind === "running";
  const isResult = state.kind === "result";
  return (
    <div className="vibe-check-preview">
      <div className="vibe-check-preview-image">
        <img src={previewUrl} alt="Your outfit" />
      </div>
      <div className="vibe-check-preview-actions">
        <h2>
          {isResult
            ? "Here's the read"
            : isRunning
              ? "Working on it…"
              : "Ready for an honest take?"}
        </h2>
        <p>
          {isResult
            ? "Scroll down for the verdict and a couple of alternatives Vibe pulled together."
            : isRunning
              ? "Engine pass takes 30–60 seconds. You can leave this page open."
              : "Vibe will tell you what's working, what isn't, and pull a couple of alternatives if you'd change something."}
        </p>
        <div className="vibe-check-button-row">
          {state.kind === "selected" || state.kind === "error" ? (
            <button
              type="button"
              className="vibe-primary-btn"
              onClick={onSubmit}
              disabled={!canSubmit}
            >
              Get feedback
            </button>
          ) : null}
          {(state.kind === "selected" ||
            state.kind === "result" ||
            state.kind === "error") ? (
            <button
              type="button"
              className="vibe-ghost-btn"
              onClick={onReset}
            >
              {isResult ? "Check another outfit" : "Pick a different photo"}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function ResultPanel({
  message,
  outfits,
  onReset,
}: {
  message: string;
  outfits: Outfit[];
  onReset: () => void;
}) {
  // Split the engine's prose on blank lines so paragraph breaks survive
  // through to the rendered output without us having to dangerously
  // set innerHTML.
  const paragraphs = useMemo(
    () =>
      message
        .split(/\n{2,}/)
        .map((p) => p.trim())
        .filter(Boolean),
    [message],
  );

  return (
    <>
      <div className="vibe-check-verdict">
        <h2>Honest take</h2>
        {paragraphs.length > 0 ? (
          paragraphs.map((p, i) => <p key={i}>{p}</p>)
        ) : (
          <p>
            Vibe didn't return commentary on this one — try a different angle
            or a clearer shot.
          </p>
        )}
      </div>

      {outfits.length > 0 ? (
        <div className="vibe-check-alternatives">
          <p className="vibe-check-alternatives-title">
            Or try one of these instead
          </p>
          <div className="vibe-check-alternatives-rail">
            {outfits.map((outfit) => (
              <OutfitCard key={outfit.outfit_id} outfit={outfit} />
            ))}
          </div>
        </div>
      ) : null}

      <div className="vibe-check-footer">
        <button type="button" className="vibe-primary-btn" onClick={onReset}>
          Check another outfit
        </button>
      </div>
    </>
  );
}
