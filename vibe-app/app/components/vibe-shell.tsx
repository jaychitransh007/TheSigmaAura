// Shared visual frame for every Vibe customer page rendered via the
// App Proxy. Applies the Confident Luxe brand surface (warm cream
// canvas, clay-terracotta accent, Fraunces display + Inter body) so
// the storefront feels consistent across Conversation / Wardrobe /
// Looks / Outfit Check.
//
// Kept minimal here — full responsive layout, header chrome, and
// composer come together in D.C.2d when the Conversation UI lands.

import type { ReactNode } from "react";

export function VibeShell({
  title,
  subtitle,
  children,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div
      style={{
        fontFamily: '-apple-system, BlinkMacSystemFont, "Inter", sans-serif',
        background: "#faf5ee",
        color: "#2d1b14",
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem",
      }}
    >
      <style>{`
        .vibe-card {
          max-width: 520px;
          width: 100%;
          background: #ffffff;
          border-radius: 16px;
          padding: 2.5rem;
          box-shadow: 0 8px 24px rgba(180, 100, 60, 0.08);
        }
        .vibe-card h1 {
          font-family: "Playfair Display", Georgia, serif;
          font-size: 2rem;
          color: #b45a3c;
          margin: 0 0 0.5rem;
        }
        .vibe-card .vibe-subtitle {
          color: #806050;
          margin: 0 0 1.5rem;
          font-size: 0.95rem;
        }
        .vibe-card p {
          margin: 0.5rem 0;
          line-height: 1.6;
        }
        .vibe-card code {
          background: #f5ebe0;
          padding: 0.1rem 0.4rem;
          border-radius: 4px;
          font-size: 0.9em;
        }
        .vibe-card .vibe-meta {
          margin-top: 1.5rem;
          padding-top: 1.5rem;
          border-top: 1px solid #f0e0d0;
          font-size: 0.85rem;
          color: #806050;
        }
        .vibe-mock-badge {
          display: inline-block;
          background: #f5ebe0;
          color: #806050;
          font-size: 0.7rem;
          font-weight: 600;
          letter-spacing: 0.05em;
          text-transform: uppercase;
          padding: 0.15rem 0.5rem;
          border-radius: 999px;
          margin-left: 0.5rem;
          vertical-align: middle;
        }
      `}</style>
      <div className="vibe-card">
        {title && <h1>{title}</h1>}
        {subtitle && <p className="vibe-subtitle">{subtitle}</p>}
        {children}
      </div>
    </div>
  );
}
