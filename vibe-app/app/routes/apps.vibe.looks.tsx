// Looks page — saved outfits + recent recommendation history.
//
// Two tabs:
//   Saved   — outfits the customer hearted via the conversation card.
//             Removable; clicking a tile takes them back to the
//             conversation it came from.
//   Recent  — the most recent N styled turns. Read-only history; same
//             tile click jumps back to the conversation.
//
// Replaces a third-party wishlist app — D.C.8 will mirror the saved set
// onto the Shopify customer-account page via a Theme App Extension.

import { useEffect, useMemo, useState } from "react";
import type { LinksFunction, LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";

import { ConfirmDialog, type ConfirmRequest } from "../components/ui/confirm-dialog";
import { ToastsProvider, useToasts } from "../components/ui/toast";
import { VibePageShell } from "../components/vibe-page-shell";
import wardrobeStyles from "../components/wardrobe/styles.css?url";
import type {
  PastLookSummary,
  SavedLookSummary,
  TryonGalleryEntry,
} from "../lib/engine.server";
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
  // No identity threading from server → client: Shopify's App Proxy
  // auto-appends `logged_in_customer_id` to every storefront-origin
  // request to /apps/vibe/* and HMAC-signs the result, so subsequent
  // resource-route fetches are independently identity-checked by the
  // server side without the page echoing anything.
  return json({});
};

type Tab = "saved" | "recent" | "tryons";

type LoadState =
  | { kind: "loading" }
  | {
      kind: "ready";
      saved: SavedLookSummary[];
      past: PastLookSummary[];
      tryons: TryonGalleryEntry[];
      warnings: string[];
    }
  | { kind: "error"; message: string };

export default function LooksPage() {
  return (
    <ToastsProvider>
      <LooksPageInner />
    </ToastsProvider>
  );
}

function LooksPageInner() {
  useLoaderData<typeof loader>();
  const toasts = useToasts();
  const [sessionId, setSessionId] = useState("");
  const [tab, setTab] = useState<Tab>("saved");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [busyDeleteId, setBusyDeleteId] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<ConfirmRequest | null>(null);

  useEffect(() => {
    const merged = readMergedCustomerId();
    const sid = merged ? `shopify:${merged}` : getOrCreateClientSessionId();
    setSessionId(sid);
  }, []);

  const loadLooks = useMemo(
    () => async (sid: string) => {
      if (!sid) return;
      setState({ kind: "loading" });
      try {
        const params = new URLSearchParams({ sessionId: sid });
        const resp = await fetch(`/apps/vibe/api/looks?${params.toString()}`);
        const body = (await resp.json()) as
          | {
              ok: true;
              savedLooks: SavedLookSummary[];
              pastLooks: PastLookSummary[];
              tryonGallery: TryonGalleryEntry[];
              errors: string[];
            }
          | { ok: false; error: string };
        if (!resp.ok || !body.ok) {
          setState({
            kind: "error",
            message: body.ok ? "Failed to load looks" : body.error,
          });
          return;
        }
        setState({
          kind: "ready",
          saved: body.savedLooks,
          past: body.pastLooks,
          tryons: body.tryonGallery,
          warnings: body.errors,
        });
      } catch (err) {
        const message = err instanceof Error ? err.message : "Network error";
        setState({ kind: "error", message });
      }
    },
    [],
  );

  useEffect(() => {
    if (sessionId) void loadLooks(sessionId);
  }, [sessionId, loadLooks]);

  function handleDeleteSaved(item: SavedLookSummary) {
    if (!sessionId || !item.saved_look_id) return;
    setConfirm({
      title: "Remove this saved look?",
      message: `"${item.title}" won't appear in Saved any more. The original conversation stays in Recent.`,
      confirmLabel: "Remove",
      destructive: true,
      onConfirm: () => deleteSavedLookRow(item),
    });
  }

  async function deleteSavedLookRow(item: SavedLookSummary) {
    if (!sessionId || !item.saved_look_id) return;
    setBusyDeleteId(item.saved_look_id);
    try {
      const form = new FormData();
      form.set("sessionId", sessionId);
      form.set("savedLookId", item.saved_look_id);
      const resp = await fetch("/apps/vibe/api/looks", {
        method: "DELETE",
        body: form,
      });
      const body = (await resp.json()) as { ok: boolean; error?: string };
      if (!resp.ok || !body.ok) {
        toasts.push({
          kind: "error",
          message:
            body.error || "Couldn't remove that look — try again in a sec.",
        });
        return;
      }
      setState((prev) =>
        prev.kind === "ready"
          ? {
              ...prev,
              saved: prev.saved.filter(
                (x) => x.saved_look_id !== item.saved_look_id,
              ),
            }
          : prev,
      );
      toasts.push({
        kind: "success",
        message: `Removed "${item.title}" from saved.`,
      });
    } finally {
      setBusyDeleteId(null);
    }
  }

  const savedList = state.kind === "ready" ? state.saved : [];
  const pastList = state.kind === "ready" ? state.past : [];
  const tryonList = state.kind === "ready" ? state.tryons : [];

  return (
    <VibePageShell title="Looks">
      <p className="vibe-page-intro">
        Outfits Vibe has built for you. Save the ones worth coming back to —
        the rest stay in your history for a few weeks so you can pick up where
        a conversation left off.
      </p>

      <div className="vibe-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "saved"}
          className={"vibe-tab" + (tab === "saved" ? " is-active" : "")}
          onClick={() => setTab("saved")}
        >
          Saved {state.kind === "ready" ? `(${savedList.length})` : ""}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "recent"}
          className={"vibe-tab" + (tab === "recent" ? " is-active" : "")}
          onClick={() => setTab("recent")}
        >
          Recent {state.kind === "ready" ? `(${pastList.length})` : ""}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "tryons"}
          className={"vibe-tab" + (tab === "tryons" ? " is-active" : "")}
          onClick={() => setTab("tryons")}
        >
          Try-ons {state.kind === "ready" ? `(${tryonList.length})` : ""}
        </button>
      </div>

      {state.kind === "error" ? (
        <div className="vibe-error-banner">
          Couldn't load your looks: {state.message}
        </div>
      ) : null}

      {state.kind === "ready" && state.warnings.length > 0 ? (
        <div className="vibe-error-banner">
          Partial load — {state.warnings.join("; ")}
        </div>
      ) : null}

      {tab === "saved" ? (
        <SavedTab
          items={savedList}
          loading={state.kind === "loading"}
          busyDeleteId={busyDeleteId}
          onDelete={handleDeleteSaved}
        />
      ) : tab === "recent" ? (
        <RecentTab items={pastList} loading={state.kind === "loading"} />
      ) : (
        <TryonsTab items={tryonList} loading={state.kind === "loading"} />
      )}

      {confirm ? (
        <ConfirmDialog {...confirm} onClose={() => setConfirm(null)} />
      ) : null}
    </VibePageShell>
  );
}

function SavedTab({
  items,
  loading,
  busyDeleteId,
  onDelete,
}: {
  items: SavedLookSummary[];
  loading: boolean;
  busyDeleteId: string | null;
  onDelete: (item: SavedLookSummary) => void;
}) {
  if (loading && items.length === 0) {
    return <p className="vibe-page-intro">Loading your saved looks…</p>;
  }
  if (items.length === 0) {
    return (
      <div className="vibe-empty">
        <h2>Nothing saved yet</h2>
        <p>
          Tap the heart on an outfit card in chat to keep it here. Vibe will
          remember the original conversation so you can pick it back up.
        </p>
        <a className="vibe-primary-btn" href="/apps/vibe/style">
          Start a conversation
        </a>
      </div>
    );
  }

  return (
    <div className="vibe-tile-grid">
      {items.map((item) => (
        <div className="vibe-tile" key={item.saved_look_id}>
          <a
            className="vibe-tile-image"
            href={lookConversationUrl(item.conversation_id, item.turn_id)}
            aria-label={`Open conversation for ${item.title}`}
          >
            {item.preview_image_url ? (
              <img
                src={item.preview_image_url}
                alt={item.title}
                loading="lazy"
              />
            ) : (
              <div className="vibe-tile-image-placeholder">No preview</div>
            )}
          </a>
          <div className="vibe-tile-actions">
            <button
              type="button"
              className="vibe-tile-icon-btn"
              aria-label={`Remove ${item.title}`}
              title="Remove from saved"
              onClick={() => onDelete(item)}
              disabled={busyDeleteId === item.saved_look_id}
            >
              ×
            </button>
          </div>
          <div className="vibe-tile-body">
            <p className="vibe-tile-title" title={item.title}>
              {item.title}
            </p>
            <p className="vibe-tile-meta">
              {item.item_count > 0
                ? `${item.item_count} piece${item.item_count === 1 ? "" : "s"}`
                : "Saved look"}
              {item.created_at ? ` · ${formatRelative(item.created_at)}` : ""}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function RecentTab({
  items,
  loading,
}: {
  items: PastLookSummary[];
  loading: boolean;
}) {
  if (loading && items.length === 0) {
    return <p className="vibe-page-intro">Loading your recent looks…</p>;
  }
  if (items.length === 0) {
    return (
      <div className="vibe-empty">
        <h2>No conversations yet</h2>
        <p>Ask Vibe for an outfit and it'll show up here.</p>
        <a className="vibe-primary-btn" href="/apps/vibe/style">
          Start a conversation
        </a>
      </div>
    );
  }

  return (
    <div className="vibe-tile-grid">
      {items.map((item) => {
        const caption =
          item.user_message ||
          item.assistant_message ||
          item.occasion ||
          "Styled look";
        return (
          <a
            key={item.turn_id}
            className="vibe-tile vibe-look-tile"
            href={lookConversationUrl(item.conversation_id, item.turn_id)}
            aria-label={`Open conversation: ${caption}`}
          >
            <div className="vibe-tile-image">
              {item.preview_image_url ? (
                <img src={item.preview_image_url} alt="" loading="lazy" />
              ) : (
                <div className="vibe-tile-image-placeholder">No preview</div>
              )}
            </div>
            <div className="vibe-tile-body">
              <p className="vibe-tile-title" title={caption}>
                {caption}
              </p>
              <p className="vibe-tile-meta">
                {item.outfit_count > 0
                  ? `${item.outfit_count} outfit${item.outfit_count === 1 ? "" : "s"}`
                  : "1 outfit"}
                {item.created_at ? ` · ${formatRelative(item.created_at)}` : ""}
              </p>
            </div>
          </a>
        );
      })}
    </div>
  );
}

// Try-on gallery tab (D.C.6). Engine accumulates one render per outfit
// recommendation; this surface lets the customer scroll back through
// them. Read-only — try-on renders aren't individually deletable
// today (they expire when the underlying conversation row archives).
function TryonsTab({
  items,
  loading,
}: {
  items: TryonGalleryEntry[];
  loading: boolean;
}) {
  if (loading && items.length === 0) {
    return <p className="vibe-page-intro">Loading your try-ons…</p>;
  }
  if (items.length === 0) {
    return (
      <div className="vibe-empty">
        <h2>No try-ons yet</h2>
        <p>
          Every outfit Vibe builds for you comes with a try-on render. They'll
          start appearing here once you've had a styling conversation.
        </p>
        <a className="vibe-primary-btn" href="/apps/vibe/style">
          Start a conversation
        </a>
      </div>
    );
  }

  return (
    <div className="vibe-tile-grid">
      {items.map((entry) => {
        const sourceLabel =
          entry.garment_source === "wardrobe"
            ? "From your wardrobe"
            : entry.garment_source === "catalog"
              ? "From the store"
              : "";
        return (
          <div className="vibe-tile" key={entry.id}>
            <div className="vibe-tile-image">
              {entry.image_url ? (
                <img
                  src={entry.image_url}
                  alt="Try-on render"
                  loading="lazy"
                />
              ) : (
                <div className="vibe-tile-image-placeholder">No preview</div>
              )}
            </div>
            <div className="vibe-tile-body">
              <p className="vibe-tile-title">
                {entry.garment_ids.length > 0
                  ? `${entry.garment_ids.length} piece${entry.garment_ids.length === 1 ? "" : "s"}`
                  : "Try-on"}
              </p>
              <p className="vibe-tile-meta">
                {[sourceLabel, formatRelative(entry.created_at)]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Conversation deep-link. Today /apps/vibe/style doesn't read these
// params yet — the chat page resolves the active conversation from
// localStorage on mount. The query string is preserved as a hook for
// when D.C.4-next wires "jump to this turn" scroll-restoration.
function lookConversationUrl(conversationId: string, turnId: string): string {
  const params = new URLSearchParams();
  if (conversationId) params.set("conversation", conversationId);
  if (turnId) params.set("turn", turnId);
  const qs = params.toString();
  return `/apps/vibe/style${qs ? `?${qs}` : ""}`;
}

// Compact relative time — keeps tiles readable. Anything older than a
// week falls back to MMM D so the customer sees an absolute date.
function formatRelative(iso: string): string {
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "";
  const diffMs = Date.now() - t;
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diffMs < hour) {
    const m = Math.max(1, Math.round(diffMs / minute));
    return `${m}m ago`;
  }
  if (diffMs < day) {
    const h = Math.round(diffMs / hour);
    return `${h}h ago`;
  }
  if (diffMs < 7 * day) {
    const d = Math.round(diffMs / day);
    return `${d}d ago`;
  }
  const dt = new Date(t);
  return dt.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
