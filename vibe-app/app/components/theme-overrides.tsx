// Inject merchant-theme overrides as CSS variables on customer-facing
// Vibe pages.
//
// The Confident Luxe brand stays the structural design system; the
// merchant's body font + primary accent color override two specific
// variables when present. Existing CSS uses `var(--accent)` /
// `font-family: Inter, ...` patterns; this component sets
// `--theme-color-primary` + `--theme-font-body` at the page root and
// the styles read them via `var(--theme-color-primary, var(--accent))`
// fallback chains.
//
// Rendered as a <style> tag rather than inline style on a wrapping div
// so the variables apply at :root scope without forcing a new
// stacking context. The component is safe to render with empty
// overrides — emits no <style> at all so the page falls back to
// Confident Luxe.

import type { TenantThemeOverrides } from "../lib/engine.server";

/**
 * Renders a <style> block setting CSS variables for merchant theme
 * inheritance. Empty / null overrides → render nothing (Vibe falls
 * back to Confident Luxe defaults).
 *
 * Font names get URL-encoded into a Google Fonts <link> in case the
 * theme picks a family Vibe doesn't currently load. The browser falls
 * through to the system-font stack if the link fails.
 */
export function ThemeOverridesStyle({
  overrides,
}: {
  overrides?: TenantThemeOverrides | null;
}) {
  if (!overrides) return null;
  const fontBody = (overrides.font_body || "").trim();
  const colorPrimary = (overrides.color_primary || "").trim();
  if (!fontBody && !colorPrimary) return null;

  // Compose the CSS variable declarations at :root so they cascade
  // across both .conv-page and .vibe-page surfaces.
  const declarations: string[] = [];
  if (fontBody) {
    declarations.push(`--theme-font-body: ${cssQuote(fontBody)};`);
  }
  if (colorPrimary) {
    declarations.push(`--theme-color-primary: ${colorPrimary};`);
  }
  const css = `:root { ${declarations.join(" ")} }`;

  // Best-effort Google Fonts preload for the body font. If the theme
  // names a custom / non-Google font, the link 404s harmlessly and
  // the CSS variable falls back to whatever weight the browser can
  // resolve from the family stack.
  const fontHref = fontBody
    ? `https://fonts.googleapis.com/css2?family=${encodeURIComponent(fontBody).replace(/%20/g, "+")}:wght@400;500;600&display=swap`
    : null;

  return (
    <>
      {fontHref ? (
        <>
          <link rel="preconnect" href="https://fonts.googleapis.com" />
          <link
            rel="preconnect"
            href="https://fonts.gstatic.com"
            crossOrigin="anonymous"
          />
          <link rel="stylesheet" href={fontHref} />
        </>
      ) : null}
      <style dangerouslySetInnerHTML={{ __html: css }} />
    </>
  );
}

// Quote a font-family name for CSS — multi-word names need quoting so
// "Source Sans Pro" doesn't get parsed as three families.
function cssQuote(name: string): string {
  // Already quoted → pass through.
  if (/^['"].*['"]$/.test(name)) return name;
  // Single-word non-keyword → no quoting needed.
  if (/^[A-Za-z][A-Za-z0-9-]*$/.test(name)) return name;
  return `"${name.replace(/"/g, '\\"')}"`;
}
