// Replicate-the-merchant's-header (PR #480).
//
// Customer-facing Vibe pages used to render a separate AURA-branded
// header — "HOME OUTFITS CHECKS WARDROBE SAVED". User feedback was
// that the customer should never feel like they left the store. The
// fix isn't to make the merchant's header literally wrap our pages
// (that's a multi-week Liquid-rendering refactor), it's to render a
// React header that LOOKS like theirs: their shop name on the left,
// their main-menu items in the center, and the merchant's primary
// color + body font (PR #478) bleeding through via CSS variables.
//
// The Vibe-owned destinations ("Find your Vibe" → /apps/vibe/style,
// "Your Vibes" → /apps/vibe/looks) get an active underline when the
// customer is on that page; everything else is a plain link to the
// merchant's storefront.

import { Link, useLocation } from "@remix-run/react";
import type { TenantThemeOverrides } from "../lib/engine.server";

const VIBE_PATHS_ACTIVE_MARKERS: ReadonlyArray<{
  match: (pathname: string) => boolean;
  /** URL the merchant put in their main menu, lowercase-compared. */
  matchesUrl: (urlLower: string) => boolean;
}> = [
  {
    match: (p) => p.startsWith("/apps/vibe/style"),
    matchesUrl: (u) => u.includes("/apps/vibe/style"),
  },
  {
    match: (p) => p.startsWith("/apps/vibe/looks"),
    matchesUrl: (u) => u.includes("/apps/vibe/looks"),
  },
];

export function MerchantHeader({
  overrides,
}: {
  overrides?: TenantThemeOverrides | null;
}) {
  const location = useLocation();
  const shopName = (overrides?.shop_name || "").trim();
  const menuItems = overrides?.main_menu ?? [];

  return (
    <header className="merchant-header" data-testid="merchant-header">
      <div className="merchant-header-inner">
        <div className="merchant-header-brand">
          {/* Text logo as the cheapest reliable inheritance — merchant
              logo images live in the theme assets, not in the settings
              we probed (PR #478 left logo_url empty by design).
              MerchantHeader's logo can grow into a real <img> when the
              probe captures it. */}
          {shopName ? (
            <a href="/" className="merchant-header-logo">
              {shopName}
            </a>
          ) : (
            <span className="merchant-header-logo merchant-header-logo--placeholder">
              Vibe
            </span>
          )}
        </div>
        <nav className="merchant-header-nav" aria-label="Store navigation">
          {menuItems.map((item) => {
            const urlLower = item.url.toLowerCase();
            const isVibeActive = VIBE_PATHS_ACTIVE_MARKERS.some(
              (m) =>
                m.matchesUrl(urlLower) && m.match(location.pathname),
            );
            return (
              <a
                key={item.url + item.title}
                href={item.url}
                className={
                  isVibeActive
                    ? "merchant-header-nav-link is-active"
                    : "merchant-header-nav-link"
                }
              >
                {item.title}
              </a>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
