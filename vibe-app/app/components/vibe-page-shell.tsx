// Shared page frame for the customer-facing Vibe pages outside of the
// Conversation surface (Wardrobe, Looks, Outfit Check).
//
// PR #480: the page's AURA-branded header was replaced by the
// MerchantHeader (replicates the merchant's storefront header). The
// in-app section nav (Chat / Wardrobe / Looks / Outfit Check) was
// dropped — only Conversation + Looks remain in the header navigation
// via the menu items the merchant added (PR 4 injects "Find your Vibe"
// + "Your Vibes"). Wardrobe + Outfit Check are reached from within
// the Conversation flow (+ popover, check-image upload) rather than
// from a dedicated tab.

import type { ReactNode } from "react";
import type { TenantThemeOverrides } from "../lib/engine.server";
import { MerchantHeader } from "./merchant-header";
import { ThemeOverridesStyle } from "./theme-overrides";
import "./merchant-header.css";

export function VibePageShell({
  title,
  children,
  themeOverrides,
  headerExtras,
}: {
  title: string;
  children: ReactNode;
  themeOverrides?: TenantThemeOverrides | null;
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
      <MerchantHeader overrides={themeOverrides} />
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
