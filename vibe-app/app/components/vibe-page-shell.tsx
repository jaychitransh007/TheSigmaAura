// Shared page frame for the customer-facing Vibe pages outside of the
// Conversation surface (Wardrobe, Looks, Outfit Check).
//
// The MerchantHeader replicates the merchant's storefront header. The
// in-app section nav (Chat / Wardrobe / Looks / Outfit Check) was
// dropped — only Conversation + Looks remain in the header navigation
// via the menu items injected into the merchant's main-menu ("Find
// your Vibe" + "Your Vibes"). Wardrobe + Outfit Check are reached
// from within the Conversation flow (+ popover, check-image upload)
// rather than from a dedicated tab.

import type { ReactNode } from "react";
import type { TenantThemeOverrides } from "../lib/engine.server";
import { MerchantHeader } from "./merchant-header";
import { ThemeOverridesStyle } from "./theme-overrides";
import "./merchant-header.css";

export function VibePageShell({
  title,
  children,
  themeOverrides,
  isAuthenticated,
  headerExtras,
}: {
  title: string;
  children: ReactNode;
  themeOverrides?: TenantThemeOverrides | null;
  /** Forwarded to MerchantHeader's account pill — "Sign in" when
   *  false / undefined, "Account" pill when true. */
  isAuthenticated?: boolean;
  /**
   * Page-specific CTA shown in the title row (e.g. wardrobe's "Add a
   * piece" button). Rendered to the right of the page title, below
   * the merchant header — keeps the per-page action close to where
   * the customer expects it without polluting the merchant header.
   */
  headerExtras?: ReactNode;
}) {
  return (
    <div className="vibe-page">
      <ThemeOverridesStyle overrides={themeOverrides} />
      <MerchantHeader
        overrides={themeOverrides}
        isAuthenticated={isAuthenticated}
      />
      <div className="vibe-page-title">
        <h1>{title}</h1>
        {headerExtras ? (
          <div className="vibe-page-title-extras">{headerExtras}</div>
        ) : null}
      </div>
      <main className="vibe-page-body">{children}</main>
    </div>
  );
}
