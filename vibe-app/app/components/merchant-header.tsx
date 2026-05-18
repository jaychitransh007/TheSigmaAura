// Replicate the merchant's storefront header on customer-facing Vibe
// pages so the customer never feels they left the store. Not a Liquid
// wrap of theme.liquid — that's a multi-week refactor — but a React
// header that consumes the merchant's shop name + main-menu items
// from theme_overrides and renders the same affordances every Shopify
// storefront carries (search, account, cart with live item count).
// End result: same chrome the customer expects, regardless of theme.
//
// The Vibe-owned destinations ("Find your Vibe" → /apps/vibe/style,
// "Your Vibes" → /apps/vibe/looks) get an active underline when the
// customer is on that page; everything else is a plain link to the
// merchant's storefront.

import { useEffect, useState } from "react";
import { useLocation } from "@remix-run/react";
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
  /** True when the App Proxy carried a logged_in_customer_id —
   *  HMAC-validated by Shopify. Drives the account-icon target
   *  (`/account` vs `/account/login`). */
  isAuthenticated?: boolean;
}) {
  const location = useLocation();
  const shopName = (overrides?.shop_name || "").trim();
  const menuItems = overrides?.main_menu ?? [];
  const cartCount = useCartCount();
  const accountHref = isAuthenticated ? "/account" : "/account/login";
  const accountLabel = isAuthenticated ? "Account" : "Sign in";

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
        <div
          className="merchant-header-utils"
          role="group"
          aria-label="Search, account, and cart"
        >
          <a
            href="/search"
            className="merchant-header-util"
            aria-label="Search"
          >
            <SearchIcon />
          </a>
          <a
            href={accountHref}
            className="merchant-header-util"
            aria-label={accountLabel}
          >
            <AccountIcon />
          </a>
          <a
            href="/cart"
            className="merchant-header-util merchant-header-util--cart"
            aria-label={cartCount > 0 ? `Cart (${cartCount})` : "Cart"}
          >
            <CartIcon />
            {cartCount > 0 ? (
              <span className="merchant-header-cart-badge" aria-hidden="true">
                {cartCount}
              </span>
            ) : null}
          </a>
        </div>
      </div>
    </header>
  );
}

/**
 * Read the customer's live cart count from Shopify's Ajax Cart endpoint
 * (`/cart.js`). Same-origin under the App Proxy, so cookies flow and
 * the response reflects the current cart for this browser session.
 * Returns 0 on any failure — the badge just hides.
 */
function useCartCount(): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let cancelled = false;
    fetch("/cart.js", { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (cancelled || !data) return;
        const c = (data as { item_count?: number }).item_count;
        if (typeof c === "number" && c >= 0) setCount(c);
      })
      .catch(() => {
        // Network / parse failure → leave at 0. The badge just hides;
        // the cart link still works.
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return count;
}

function SearchIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

function AccountIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20c0-4 4-6 8-6s8 2 8 6" />
    </svg>
  );
}

function CartIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M6 7h12l-1.2 11a2 2 0 0 1-2 1.8H9.2a2 2 0 0 1-2-1.8L6 7z" />
      <path d="M9 7V5a3 3 0 0 1 6 0v2" />
    </svg>
  );
}
