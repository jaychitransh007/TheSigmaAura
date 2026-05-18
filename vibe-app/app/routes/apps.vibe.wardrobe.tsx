// Wardrobe page — customer-facing CRUD + filters for their saved
// garments. Vibe styles outfits around what the customer already owns,
// so this surface is the source of truth for "what's in my closet".
//
// Reads live from /apps/vibe/api/wardrobe (the same loader powering the
// conversation `+` picker), so an item the customer added mid-chat
// appears here without a refresh on the next mount.
//
// Identity: localStorage session id, threaded explicitly through every
// fetch (cookies don't survive Shopify's App Proxy round-trip — see
// session.client.ts).

import { useEffect, useMemo, useState } from "react";
import type { LinksFunction, LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";

import { ConfirmDialog, type ConfirmRequest } from "../components/ui/confirm-dialog";
import { ToastsProvider, useToasts } from "../components/ui/toast";
import { VibePageShell } from "../components/vibe-page-shell";
import wardrobeStyles from "../components/wardrobe/styles.css?url";
import { loadCustomerHeaderData } from "../lib/customer-loader.server";
import type { WardrobeItem } from "../lib/engine.server";
import {
  getOrCreateClientSessionId,
  readMergedCustomerId,
} from "../lib/session.client";
import { authenticate } from "../shopify.server";

export const links: LinksFunction = () => [
  { rel: "stylesheet", href: wardrobeStyles },
  { rel: "preconnect", href: "https://fonts.googleapis.com" },
  { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
  {
    rel: "stylesheet",
    href: "https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,600;1,400&display=swap",
  },
];

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.public.appProxy(request);
  // Pull tenant theme overrides + auth flag for the merchant header.
  const headerData = await loadCustomerHeaderData(request);
  return json(headerData);
};

// Category vocab matches the engine's GarmentCategory enum (top,
// bottom, dress, outerwear, footwear, accessory). The customer never
// has to know which bucket Vibe assigned — empty option means
// "Vibe figures it out from the photo" which is the right default.
const CATEGORY_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "", label: "Let Vibe decide" },
  { value: "top", label: "Top" },
  { value: "bottom", label: "Bottom" },
  { value: "dress", label: "Dress / Set" },
  { value: "outerwear", label: "Outerwear" },
  { value: "footwear", label: "Footwear" },
  { value: "accessory", label: "Accessory" },
];

// Filter chips show only categories that actually have items. "All"
// is always present.
const FILTER_ALL = "__all__";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; items: WardrobeItem[] }
  | { kind: "error"; message: string };

export default function WardrobePage() {
  return (
    <ToastsProvider>
      <WardrobePageInner />
    </ToastsProvider>
  );
}

function WardrobePageInner() {
  const { themeOverrides, isAuthenticated } = useLoaderData<typeof loader>();
  const toasts = useToasts();
  const [sessionId, setSessionId] = useState("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [filter, setFilter] = useState<string>(FILTER_ALL);
  const [addOpen, setAddOpen] = useState(false);
  const [busyDeleteId, setBusyDeleteId] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<ConfirmRequest | null>(null);

  // Resolve the session id on mount. Prefer the Shopify-customer-keyed
  // id if the customer has merged (D.S.3b); fall back to the anonymous
  // localStorage UUID otherwise. Mirrors the conversation page.
  useEffect(() => {
    const merged = readMergedCustomerId();
    const sid = merged ? `shopify:${merged}` : getOrCreateClientSessionId();
    setSessionId(sid);
  }, []);

  const loadItems = useMemo(
    () => async (sid: string) => {
      if (!sid) return;
      setState({ kind: "loading" });
      try {
        const params = new URLSearchParams({ sessionId: sid });
        const resp = await fetch(`/apps/vibe/api/wardrobe?${params.toString()}`);
        const body = (await resp.json()) as
          | { ok: true; items: WardrobeItem[] }
          | { ok: false; error: string };
        if (!resp.ok || !body.ok) {
          setState({
            kind: "error",
            message: body.ok ? "Failed to load wardrobe" : body.error,
          });
          return;
        }
        setState({ kind: "ready", items: body.items });
      } catch (err) {
        const message = err instanceof Error ? err.message : "Network error";
        setState({ kind: "error", message });
      }
    },
    [],
  );

  useEffect(() => {
    if (sessionId) void loadItems(sessionId);
  }, [sessionId, loadItems]);

  const items = state.kind === "ready" ? state.items : [];

  // Compute filter chips from the items we actually have. Saves
  // showing empty buckets to the customer.
  const filterChips = useMemo(() => {
    const seen = new Set<string>();
    for (const it of items) {
      const cat = it.garment_category.trim().toLowerCase();
      if (cat) seen.add(cat);
    }
    return Array.from(seen).sort();
  }, [items]);

  const visibleItems = useMemo(() => {
    if (filter === FILTER_ALL) return items;
    return items.filter(
      (it) => it.garment_category.trim().toLowerCase() === filter,
    );
  }, [items, filter]);

  function handleDelete(item: WardrobeItem) {
    if (!sessionId || !item.id) return;
    setConfirm({
      title: "Remove this piece?",
      message: `"${item.title}" will be removed from your wardrobe. Outfits already built around it stay in your Looks.`,
      confirmLabel: "Remove",
      destructive: true,
      onConfirm: () => deleteWardrobeItem(item),
    });
  }

  async function deleteWardrobeItem(item: WardrobeItem) {
    if (!sessionId || !item.id) return;
    setBusyDeleteId(item.id);
    try {
      const form = new FormData();
      form.set("sessionId", sessionId);
      form.set("wardrobeItemId", item.id);
      const resp = await fetch("/apps/vibe/api/wardrobe", {
        method: "DELETE",
        body: form,
      });
      const body = (await resp.json()) as { ok: boolean; error?: string };
      if (!resp.ok || !body.ok) {
        toasts.push({
          kind: "error",
          message:
            body.error || "Couldn't remove that piece — try again in a sec.",
        });
        return;
      }
      // Optimistic refresh — drop the item locally, no full reload.
      setState((prev) =>
        prev.kind === "ready"
          ? { kind: "ready", items: prev.items.filter((x) => x.id !== item.id) }
          : prev,
      );
      toasts.push({ kind: "success", message: `Removed "${item.title}".` });
    } finally {
      setBusyDeleteId(null);
    }
  }

  async function handleAdded(item: WardrobeItem) {
    setAddOpen(false);
    // Engine returns the row; splice it into the head of the list so
    // the customer sees their new piece without a round-trip.
    setState((prev) =>
      prev.kind === "ready"
        ? { kind: "ready", items: [item, ...prev.items] }
        : { kind: "ready", items: [item] },
    );
  }

  return (
    <VibePageShell
      title="Wardrobe"
      themeOverrides={themeOverrides}
      isAuthenticated={isAuthenticated}
      headerExtras={
        <button
          type="button"
          className="vibe-primary-btn"
          onClick={() => setAddOpen(true)}
          disabled={!sessionId}
        >
          Add a piece
        </button>
      }
    >
      <p className="vibe-page-intro">
        Pieces you already own. Vibe styles around these first, then fills the
        gaps from the store. Add a photo of anything you wear regularly — a
        favourite shirt, your everyday jeans, the dress you keep coming back
        to.
      </p>

      {state.kind === "error" ? (
        <div className="vibe-error-banner">
          Couldn't load your wardrobe: {state.message}
        </div>
      ) : null}

      {state.kind === "ready" && items.length === 0 ? (
        <div className="vibe-empty">
          <h2>Your closet is empty</h2>
          <p>
            Add a few pieces and Vibe will start styling outfits around them.
          </p>
          <button
            type="button"
            className="vibe-primary-btn"
            onClick={() => setAddOpen(true)}
            disabled={!sessionId}
          >
            Add your first piece
          </button>
        </div>
      ) : null}

      {items.length > 0 ? (
        <>
          <div className="vibe-filter-row">
            <button
              type="button"
              className={
                "vibe-filter-chip" +
                (filter === FILTER_ALL ? " is-active" : "")
              }
              onClick={() => setFilter(FILTER_ALL)}
            >
              All
            </button>
            {filterChips.map((cat) => (
              <button
                key={cat}
                type="button"
                className={
                  "vibe-filter-chip" + (filter === cat ? " is-active" : "")
                }
                onClick={() => setFilter(cat)}
              >
                {prettifyCategory(cat)}
              </button>
            ))}
            <span className="vibe-filter-count">
              {visibleItems.length} of {items.length}
            </span>
          </div>

          <div className="vibe-tile-grid">
            {visibleItems.map((item) => (
              <WardrobeTile
                key={item.id}
                item={item}
                disabled={busyDeleteId === item.id}
                onDelete={() => handleDelete(item)}
              />
            ))}
          </div>
        </>
      ) : null}

      {addOpen ? (
        <AddPieceDialog
          sessionId={sessionId}
          onClose={() => setAddOpen(false)}
          onAdded={handleAdded}
        />
      ) : null}

      {confirm ? (
        <ConfirmDialog {...confirm} onClose={() => setConfirm(null)} />
      ) : null}
    </VibePageShell>
  );
}

function WardrobeTile({
  item,
  disabled,
  onDelete,
}: {
  item: WardrobeItem;
  disabled: boolean;
  onDelete: () => void;
}) {
  const meta = [item.garment_subtype, item.primary_color]
    .map((s) => s.trim())
    .filter(Boolean)
    .map(prettifyCategory)
    .join(" · ");

  return (
    <div className="vibe-tile">
      <div className="vibe-tile-image">
        {item.image_url ? (
          <img src={item.image_url} alt={item.title} loading="lazy" />
        ) : (
          <div className="vibe-tile-image-placeholder">No image</div>
        )}
      </div>
      <div className="vibe-tile-actions">
        <button
          type="button"
          className="vibe-tile-icon-btn"
          aria-label={`Remove ${item.title}`}
          onClick={onDelete}
          disabled={disabled}
          title="Remove from wardrobe"
        >
          ×
        </button>
      </div>
      <div className="vibe-tile-body">
        <p className="vibe-tile-title" title={item.title}>
          {item.title || "Untitled"}
        </p>
        {meta ? <p className="vibe-tile-meta">{meta}</p> : null}
      </div>
    </div>
  );
}

// Modal — file picker + optional title/category. Renders a preview the
// moment a file is chosen so the customer can confirm before uploading.
function AddPieceDialog({
  sessionId,
  onClose,
  onAdded,
}: {
  sessionId: string;
  onClose: () => void;
  onAdded: (item: WardrobeItem) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  // Escape to close — matches platform expectation for modal dialogs.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !sessionId) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.set("sessionId", sessionId);
      if (title.trim()) form.set("title", title.trim());
      if (category) form.set("garmentCategory", category);
      form.set("file", file, file.name || "wardrobe.jpg");
      const resp = await fetch("/apps/vibe/api/wardrobe", {
        method: "POST",
        body: form,
      });
      const body = (await resp.json()) as
        | { ok: true; item: WardrobeItem }
        | { ok: false; error: string };
      if (!resp.ok || !body.ok) {
        setError(body.ok ? "Upload failed" : body.error);
        return;
      }
      onAdded(body.item);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="vibe-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="vibe-add-piece-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <form className="vibe-modal" onSubmit={handleSubmit}>
        <h2 id="vibe-add-piece-title">Add a piece</h2>
        <p className="vibe-modal-intro">
          Snap a clean photo against a plain background — Vibe reads colour,
          cut, and fabric so the more honest the shot, the better the styling.
        </p>

        <label className="vibe-modal-file" htmlFor="vibe-add-piece-file">
          <input
            id="vibe-add-piece-file"
            type="file"
            accept="image/*"
            onChange={(e) => setFile(e.currentTarget.files?.[0] ?? null)}
          />
          {previewUrl ? (
            <img
              src={previewUrl}
              alt="Preview"
              className="vibe-modal-file-preview"
            />
          ) : (
            <span>Click to choose a photo</span>
          )}
        </label>

        <label htmlFor="vibe-add-piece-name">Name (optional)</label>
        <input
          id="vibe-add-piece-name"
          type="text"
          placeholder="e.g. Black linen shirt"
          value={title}
          onChange={(e) => setTitle(e.currentTarget.value)}
          maxLength={120}
        />

        <label htmlFor="vibe-add-piece-category">Category</label>
        <select
          id="vibe-add-piece-category"
          value={category}
          onChange={(e) => setCategory(e.currentTarget.value)}
        >
          {CATEGORY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        {error ? <div className="vibe-error-banner">{error}</div> : null}

        <div className="vibe-modal-actions">
          <button
            type="button"
            className="vibe-ghost-btn"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="vibe-primary-btn"
            disabled={!file || busy}
          >
            {busy ? "Saving…" : "Save piece"}
          </button>
        </div>
      </form>
    </div>
  );
}

function prettifyCategory(raw: string): string {
  if (!raw) return "";
  return raw
    .split("_")
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
}
