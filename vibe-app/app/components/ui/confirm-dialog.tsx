// Branded confirm dialog — drop-in replacement for window.confirm.
//
// Native browser confirm dialogs are unstyled, block the main thread,
// and clash with the rest of the Vibe surface (Confident Luxe palette
// + Fraunces italic headlines). This component matches the wardrobe
// "Add a piece" modal's look so customers get a consistent visual
// register across destructive actions.
//
// Usage:
//   const [confirm, setConfirm] = useState<ConfirmRequest | null>(null);
//   ...
//   onClick={() => setConfirm({
//     title: "Remove this piece?",
//     message: `"${item.title}" will be removed from your wardrobe.`,
//     confirmLabel: "Remove",
//     destructive: true,
//     onConfirm: () => handleDelete(item),
//   })}
//   ...
//   {confirm && <ConfirmDialog {...confirm} onClose={() => setConfirm(null)} />}

import { useEffect, useRef, useState } from "react";

export type ConfirmRequest = {
  title: string;
  message: string;
  /** Confirm-button label. Default "Confirm". */
  confirmLabel?: string;
  /** Cancel-button label. Default "Cancel". */
  cancelLabel?: string;
  /** When true, the confirm button uses a destructive red colour.
   *  Default false — confirm uses the brand accent. */
  destructive?: boolean;
  /** Callback fired on confirm. Sync or async — the dialog disables
   *  buttons while a returned Promise is pending so the customer
   *  can't double-tap. */
  onConfirm: () => void | Promise<void>;
};

export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  onConfirm,
  onClose,
}: ConfirmRequest & { onClose: () => void }) {
  const [busy, setBusy] = useState(false);
  const confirmRef = useRef<HTMLButtonElement>(null);

  // Auto-focus the confirm button on mount so keyboard users land
  // inside the dialog. Escape closes (handled below).
  useEffect(() => {
    confirmRef.current?.focus();
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  async function handleConfirm() {
    if (busy) return;
    setBusy(true);
    try {
      await onConfirm();
      onClose();
    } catch {
      // Caller is responsible for surfacing the failure (typically
      // via a Toast). We re-enable the dialog so the customer can
      // either cancel or retry.
      setBusy(false);
    }
  }

  return (
    <div
      className="vibe-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="vibe-confirm-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <div className="vibe-modal vibe-confirm">
        <h2 id="vibe-confirm-title">{title}</h2>
        <p className="vibe-modal-intro">{message}</p>
        <div className="vibe-modal-actions">
          <button
            type="button"
            className="vibe-ghost-btn"
            onClick={onClose}
            disabled={busy}
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            className={
              destructive ? "vibe-primary-btn vibe-primary-btn--danger" : "vibe-primary-btn"
            }
            onClick={handleConfirm}
            disabled={busy}
          >
            {busy ? "…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
