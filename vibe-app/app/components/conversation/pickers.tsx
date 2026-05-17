// Wardrobe + wishlist picker modals — the "From wardrobe" / "From saved"
// options on the composer's + popover open these. Modal grid layout with
// a search input + click-outside-to-close, mirroring the legacy ui.py
// modal-overlay pattern.
//
// Each picker fetches its list from the corresponding resource route on
// mount (sessionId comes from the parent). Loading / empty / error
// states render inline so the customer always sees what's happening
// rather than a silently-blank grid.

import { useEffect, useMemo, useRef, useState } from "react";

import type { WardrobeItem, WishlistItem } from "../../lib/engine.server";

type FetchState<T> =
  | { phase: "loading" }
  | { phase: "ready"; items: T[] }
  | { phase: "error"; message: string };

function useFetchOnMount<T>(url: string): FetchState<T> {
  const [state, setState] = useState<FetchState<T>>({ phase: "loading" });
  useEffect(() => {
    // Reset to `loading` on every URL change so the picker doesn't
    // briefly show stale items from a previous identity. The common
    // case (sessionId stable for the life of the session) is
    // unaffected; the load-bearing case is a Shopify-merge mid-
    // session, where the canonical id swaps and the URL recomputes —
    // without this reset we'd render the anonymous user's wardrobe
    // until the canonical-user fetch returned.
    setState({ phase: "loading" });
    // AbortController, not a captured `cancelled` flag — the latter
    // would suppress state updates after unmount but still let the
    // network request finish, wasting bandwidth when the customer
    // closes the picker quickly. AbortController kills the request
    // at the transport layer.
    const controller = new AbortController();
    fetch(url, { credentials: "same-origin", signal: controller.signal })
      .then(async (resp) => {
        const body = (await resp.json().catch(() => null)) as
          | { ok: true; items: T[] }
          | { ok: false; error?: string }
          | null;
        if (controller.signal.aborted) return;
        if (!resp.ok || !body || body.ok === false) {
          const msg =
            (body && "error" in body && body.error) ||
            `Failed (${resp.status})`;
          setState({ phase: "error", message: msg });
          return;
        }
        setState({ phase: "ready", items: body.items });
      })
      .catch((err) => {
        // AbortError is the expected outcome on unmount — don't
        // surface it as a real error. Other failures (network down,
        // 5xx, etc.) still flow through.
        if (err && (err.name === "AbortError" || controller.signal.aborted)) {
          return;
        }
        setState({
          phase: "error",
          message: err instanceof Error ? err.message : "Fetch failed",
        });
      });
    return () => controller.abort();
  }, [url]);
  return state;
}

// Backdrop + container — Escape to close, click-outside-to-close.
function PickerModal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const overlayRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);

    // Lock body scroll so the picker grid scrolls independently of
    // the feed behind it. Setting overflow:hidden on its own makes
    // the vertical scrollbar disappear, which on most desktop
    // browsers visibly shifts the underlying page content rightward
    // by ~15px. Pad the body by the scrollbar width to keep
    // everything pinned in place; restore the original inline values
    // on cleanup so we don't leak styles for any code that touched
    // them elsewhere.
    const scrollbarWidth =
      window.innerWidth - document.documentElement.clientWidth;
    const prevOverflow = document.body.style.overflow;
    const prevPaddingRight = document.body.style.paddingRight;
    document.body.style.overflow = "hidden";
    if (scrollbarWidth > 0) {
      document.body.style.paddingRight = `${scrollbarWidth}px`;
    }
    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = prevOverflow;
      document.body.style.paddingRight = prevPaddingRight;
    };
  }, [onClose]);

  return (
    <div
      ref={overlayRef}
      className="conv-picker-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onMouseDown={(e) => {
        // Only dismiss when the click started on the overlay itself
        // (not a child). Without this, dragging from inside the box
        // out to the overlay would close the picker on mouseup.
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div className="conv-picker-box">
        <header className="conv-picker-header">
          <h2 className="conv-picker-title">{title}</h2>
          <button
            type="button"
            className="conv-picker-close"
            onClick={onClose}
            aria-label="Close picker"
            title="Close"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path
                d="M18 6L6 18M6 6l12 12"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}

function PickerSearch({
  query,
  onChange,
  placeholder,
}: {
  query: string;
  onChange: (next: string) => void;
  placeholder: string;
}) {
  return (
    <input
      type="search"
      className="conv-picker-search"
      placeholder={placeholder}
      value={query}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function PickerEmpty({ message }: { message: string }) {
  return <div className="conv-picker-empty">{message}</div>;
}

export function WardrobePicker({
  sessionId,
  onClose,
  onPick,
}: {
  sessionId: string;
  onClose: () => void;
  onPick: (item: WardrobeItem) => void;
}) {
  const state = useFetchOnMount<WardrobeItem>(
    `/apps/vibe/api/wardrobe?sessionId=${encodeURIComponent(sessionId)}`,
  );
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    if (state.phase !== "ready") return [];
    const q = query.trim().toLowerCase();
    if (!q) return state.items;
    return state.items.filter((it) => {
      const hay = `${it.title} ${it.garment_category} ${it.garment_subtype} ${it.primary_color}`.toLowerCase();
      return hay.includes(q);
    });
  }, [state, query]);

  return (
    <PickerModal title="From wardrobe" onClose={onClose}>
      {state.phase === "ready" && state.items.length > 0 && (
        <PickerSearch
          query={query}
          onChange={setQuery}
          placeholder="Search your closet…"
        />
      )}
      {state.phase === "loading" && <PickerEmpty message="Loading your closet…" />}
      {state.phase === "error" && (
        <PickerEmpty message={`Couldn't load wardrobe — ${state.message}`} />
      )}
      {state.phase === "ready" && state.items.length === 0 && (
        <PickerEmpty message="Your closet is empty. Upload a photo of an item to add it." />
      )}
      {state.phase === "ready" && state.items.length > 0 && filtered.length === 0 && (
        <PickerEmpty message={`No items match "${query.trim()}"`} />
      )}
      {state.phase === "ready" && filtered.length > 0 && (
        <ul className="conv-picker-grid">
          {filtered.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className="conv-picker-tile"
                onClick={() => onPick(item)}
                aria-label={`Use ${item.title} as anchor`}
              >
                {item.image_url ? (
                  <img src={item.image_url} alt="" loading="lazy" />
                ) : (
                  <div className="conv-picker-tile-empty">No image</div>
                )}
                <span className="conv-picker-tile-title">{item.title}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </PickerModal>
  );
}

export function WishlistPicker({
  sessionId,
  onClose,
  onPick,
}: {
  sessionId: string;
  onClose: () => void;
  onPick: (item: WishlistItem) => void;
}) {
  const state = useFetchOnMount<WishlistItem>(
    `/apps/vibe/api/wishlist?sessionId=${encodeURIComponent(sessionId)}`,
  );
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    if (state.phase !== "ready") return [];
    const q = query.trim().toLowerCase();
    if (!q) return state.items;
    return state.items.filter((it) => {
      const hay = `${it.title} ${it.brand}`.toLowerCase();
      return hay.includes(q);
    });
  }, [state, query]);

  return (
    <PickerModal title="From saved" onClose={onClose}>
      {state.phase === "ready" && state.items.length > 0 && (
        <PickerSearch
          query={query}
          onChange={setQuery}
          placeholder="Search saved items…"
        />
      )}
      {state.phase === "loading" && <PickerEmpty message="Loading saved items…" />}
      {state.phase === "error" && (
        <PickerEmpty message={`Couldn't load wishlist — ${state.message}`} />
      )}
      {state.phase === "ready" && state.items.length === 0 && (
        <PickerEmpty message="Nothing saved yet. Tap the heart on an outfit card to save items." />
      )}
      {state.phase === "ready" && state.items.length > 0 && filtered.length === 0 && (
        <PickerEmpty message={`No items match "${query.trim()}"`} />
      )}
      {state.phase === "ready" && filtered.length > 0 && (
        <ul className="conv-picker-grid">
          {filtered.map((item) => (
            <li key={item.product_id}>
              <button
                type="button"
                className="conv-picker-tile"
                onClick={() => onPick(item)}
                aria-label={`Use ${item.title} as anchor`}
              >
                {item.image_url ? (
                  <img src={item.image_url} alt="" loading="lazy" />
                ) : (
                  <div className="conv-picker-tile-empty">No image</div>
                )}
                <span className="conv-picker-tile-title">{item.title}</span>
                {item.brand && (
                  <span className="conv-picker-tile-brand">{item.brand}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </PickerModal>
  );
}
