// Shared page frame for the customer-facing Vibe pages outside of the
// Conversation surface (Wardrobe, Looks, Outfit Check). Renders the
// brand header with cross-page nav and centers the body content.
//
// The Conversation page has its own header/composer/layout machinery
// and doesn't use this — keeping it separate avoids forcing the chat
// surface into a generic page frame.

import type { ReactNode } from "react";
import { Link, useLocation } from "@remix-run/react";

const NAV_ITEMS: ReadonlyArray<{ to: string; label: string }> = [
  { to: "/apps/vibe/style", label: "Chat" },
  { to: "/apps/vibe/wardrobe", label: "Wardrobe" },
  { to: "/apps/vibe/looks", label: "Looks" },
  { to: "/apps/vibe/check", label: "Outfit Check" },
];

export function VibePageShell({
  title,
  children,
  headerExtras,
}: {
  title: string;
  children: ReactNode;
  headerExtras?: ReactNode;
}) {
  const location = useLocation();

  return (
    <div className="vibe-page">
      <header className="vibe-page-header">
        <h1>{title}</h1>
        <nav className="vibe-page-nav" aria-label="Vibe sections">
          {NAV_ITEMS.map((item) => {
            const isActive = location.pathname.startsWith(item.to);
            return (
              <Link
                key={item.to}
                to={item.to}
                className={isActive ? "is-active" : undefined}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        {headerExtras}
      </header>
      <main className="vibe-page-body">{children}</main>
    </div>
  );
}
