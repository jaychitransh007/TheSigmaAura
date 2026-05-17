// Toast notifications — drop-in replacement for window.alert.
//
// Two pieces:
//   - `<ToastHost>` renders the toast stack in a fixed-position
//     container at the bottom-right of the viewport. Mount once per
//     page (typically inside the VibePageShell consumer).
//   - `useToasts()` returns `{ push }` — call `push({ kind, message })`
//     from anywhere in the same component subtree to enqueue a toast.
//
// Toasts auto-dismiss after 4 seconds. Customers can click the X
// inside the toast to dismiss earlier. Multiple toasts stack
// vertically; oldest on top.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type ToastKind = "success" | "error" | "info";

type Toast = {
  id: number;
  kind: ToastKind;
  message: string;
};

type ToastsCtx = {
  push: (toast: { kind: ToastKind; message: string }) => void;
};

const Ctx = createContext<ToastsCtx | null>(null);

const AUTO_DISMISS_MS = 4000;

export function ToastsProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const push = useCallback((toast: { kind: ToastKind; message: string }) => {
    setToasts((prev) => [
      ...prev,
      { id: Date.now() + Math.random(), kind: toast.kind, message: toast.message },
    ]);
  }, []);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Auto-dismiss every toast 4s after it's enqueued. Effect re-runs
  // whenever the list changes; each toast gets its own timer keyed by id.
  useEffect(() => {
    if (toasts.length === 0) return;
    const timers = toasts.map((t) =>
      window.setTimeout(() => dismiss(t.id), AUTO_DISMISS_MS),
    );
    return () => {
      for (const t of timers) window.clearTimeout(t);
    };
  }, [toasts, dismiss]);

  const value = useMemo(() => ({ push }), [push]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <ToastHost toasts={toasts} onDismiss={dismiss} />
    </Ctx.Provider>
  );
}

export function useToasts(): ToastsCtx {
  const ctx = useContext(Ctx);
  if (!ctx) {
    // Defensive — components calling useToasts must be wrapped in
    // <ToastsProvider>. Failing loud helps catch misuse early.
    throw new Error("useToasts must be used inside <ToastsProvider>");
  }
  return ctx;
}

function ToastHost({
  toasts,
  onDismiss,
}: {
  toasts: Toast[];
  onDismiss: (id: number) => void;
}) {
  if (toasts.length === 0) return null;
  return (
    <div
      className="vibe-toast-host"
      role="status"
      aria-live="polite"
      aria-atomic="false"
    >
      {toasts.map((t) => (
        <div key={t.id} className={`vibe-toast vibe-toast--${t.kind}`}>
          <span className="vibe-toast-message">{t.message}</span>
          <button
            type="button"
            className="vibe-toast-close"
            onClick={() => onDismiss(t.id)}
            aria-label="Dismiss notification"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
