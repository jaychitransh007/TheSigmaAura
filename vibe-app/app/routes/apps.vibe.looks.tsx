// Looks page — recommendation history grouped by theme.
//
// Mirrors the legacy `platform_core/ui.py` § Outfits tab. Each theme
// (e.g. "Office & Professional", "Weekend & Everyday") renders as a
// block with:
//   - italic-serif title + faint accent rule
//   - one PDP carousel containing every outfit recommended within
//     that theme, with the originating user prompt shown above each
//     slide and a "N / total" counter + prev/next arrows on the right
//
// No Saved / Recent / Try-ons tabs, no "Your Vibes" header — just the
// recommendation history surfaced in the same shape Aura's standalone
// customer surface uses, so the experience reads identically across
// the two products.

import { useEffect, useState } from "react";
import type { LinksFunction, LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";

import looksStyles from "../components/looks/styles.css?url";
import conversationStyles from "../components/conversation/styles.css?url";
import { OutfitCarousel } from "../components/conversation/outfit-carousel";
import { VibePageShell } from "../components/vibe-page-shell";
import { loadCustomerHeaderData } from "../lib/customer-loader.server";
import type { IntentHistoryTheme } from "../lib/engine.server";
import {
  getOrCreateClientSessionId,
  readMergedCustomerId,
} from "../lib/session.client";
import { authenticate } from "../shopify.server";

export const links: LinksFunction = () => [
  // Reuse the conversation stylesheet so OutfitCard / OutfitCarousel
  // pick up their visual tokens. Theme-block layout layered on top
  // via looks/styles.css.
  { rel: "stylesheet", href: conversationStyles },
  { rel: "stylesheet", href: looksStyles },
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

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; themes: IntentHistoryTheme[]; hasBodyPhoto: boolean }
  | { kind: "error"; message: string };

export default function LooksPage() {
  const { themeOverrides, isAuthenticated } = useLoaderData<typeof loader>();
  const [sessionId, setSessionId] = useState("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    const merged = readMergedCustomerId();
    const sid = merged ? `shopify:${merged}` : getOrCreateClientSessionId();
    setSessionId(sid);
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    setState({ kind: "loading" });
    (async () => {
      try {
        const params = new URLSearchParams({ sessionId });
        const resp = await fetch(`/apps/vibe/api/looks?${params.toString()}`);
        const body = (await resp.json()) as
          | { ok: true; themes: IntentHistoryTheme[]; hasBodyPhoto?: boolean }
          | { ok: false; error: string };
        if (cancelled) return;
        if (!resp.ok || !body.ok) {
          setState({
            kind: "error",
            message: body.ok ? "Failed to load looks" : body.error,
          });
          return;
        }
        setState({
          kind: "ready",
          themes: body.themes,
          hasBodyPhoto: Boolean(body.hasBodyPhoto),
        });
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "Network error";
        setState({ kind: "error", message });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  return (
    <VibePageShell
      themeOverrides={themeOverrides}
      isAuthenticated={isAuthenticated}
    >
      <div className="looks-page">
        {state.kind === "loading" && (
          <p className="looks-loading">Loading your styled looks…</p>
        )}
        {state.kind === "error" && (
          <p className="looks-error">{state.message}</p>
        )}
        {state.kind === "ready" && state.themes.length === 0 && (
          <p className="looks-empty">
            Nothing styled yet. Start a chat to see your looks appear here.
          </p>
        )}
        {state.kind === "ready" &&
          state.themes.map((theme) => (
            <section
              key={theme.theme_key}
              className="looks-theme-block"
              aria-label={theme.theme_label}
            >
              <h2 className="looks-theme-title">{theme.theme_label}</h2>
              <hr className="looks-theme-rule" />
              <OutfitCarousel
                outfits={theme.outfits}
                contextLabelForIndex={(idx) =>
                  theme.outfits[idx]?.user_message ?? ""
                }
                alwaysShowHeader
                hasBodyPhoto={state.hasBodyPhoto}
              />
            </section>
          ))}
      </div>
    </VibePageShell>
  );
}
