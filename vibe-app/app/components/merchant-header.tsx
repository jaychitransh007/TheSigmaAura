// Replicate the merchant's storefront header on customer-facing Vibe
// pages so the customer never feels they left the store. Not a Liquid
// wrap of theme.liquid — that's a multi-week refactor — but a React
// header that consumes the merchant's shop name + main-menu items
// from theme_overrides, plus the --theme-color-primary +
// --theme-font-body CSS variables. End result: same visual feel as
// the host store without leaving the React/Remix stack.
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
  isAuthenticated,
}: {
  overrides?: TenantThemeOverrides | null;
  /** When false, render a "Sign in" affordance linking to Shopify's
   *  Customer Account login flow. Needed because some merchant menus
   *  don't carry an Account link of their own; anonymous customers
   *  landing on a Vibe page would otherwise have no way to log in. */
  isAuthenticated?: boolean;
}) {
  const location = useLocation();
  const shopName = (overrides?.shop_name || "").trim();
  const menuItems = overrides?.main_menu ?? [];

  return (
    <header className="merchant-header" data-testid="merchant-header">
      <div className="merchant-header-inner">
        <div className="merchant-header-brand">
          {/* Text logo as the cheapest reliable inheritance — merchant
              logo images live in theme assets, not in the
              settings_data.json we probe. Can grow into a real <img>
              once we capture the asset URL too. */}
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
          {menuItems.map((item, idx) => {
            const urlLower = item.url.toLowerCase();
            const isVibeActive = VIBE_PATHS_ACTIVE_MARKERS.some(
              (m) =>
                m.matchesUrl(urlLower) && m.match(location.pathname),
            );
            return (
              <a
                key={`${idx}-${item.url}`}
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
        <div className="merchant-header-account">
          {isAuthenticated ? (
            <span className="merchant-header-account-pill" aria-label="Signed in">
              Account
            </span>
          ) : (
            <a
              className="merchant-header-account-pill merchant-header-account-pill--signin"
              href="/account/login"
            >
              Sign in
            </a>
          )}
        </div>
      </div>
    </header>
  );
}
