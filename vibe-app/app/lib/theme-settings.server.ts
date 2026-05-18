// Read the merchant's active Shopify theme settings + probe out the
// handful of values Vibe uses to bias its visual presentation toward
// the host store (font, primary color, logo URL).
//
// Approach: Admin GraphQL to fetch the MAIN theme's
// `config/settings_data.json`. That file is JSON written by the
// merchant via the theme editor; the schema varies wildly per theme
// (Dawn vs Studio vs Refresh vs a custom theme), so we probe a
// fallback chain for each value and gracefully give up — Vibe falls
// back to Confident Luxe defaults whenever a key isn't found.
//
// Required scope: `read_themes` (granted at F.1 — already in the
// app's scope set).

// Minimal structural type for the Admin GraphQL client. We only need
// the `graphql` method on it; pulling in `AdminApiContext` from the
// SDK trips the package's typing surface (the export's shape differs
// between Shopify SDK versions).
type AdminGraphqlClient = {
  graphql(query: string, options?: unknown): Promise<Response>;
};

export type ShopifyThemeOverrides = {
  font_body: string;
  color_primary: string;
  color_background: string;
  color_text: string;
  logo_url: string;
};

const EMPTY: ShopifyThemeOverrides = {
  font_body: "",
  color_primary: "",
  color_background: "",
  color_text: "",
  logo_url: "",
};

// Theme settings file body GraphQL response shape (Admin API).
type ThemeFileQueryResult = {
  data?: {
    themes?: {
      edges?: Array<{
        node?: {
          id?: string;
          files?: {
            edges?: Array<{
              node?: {
                body?: {
                  content?: string;
                };
              };
            }>;
          };
        };
      }>;
    };
  };
};

/**
 * Fetch the merchant's active theme settings and probe out the Vibe-
 * relevant overrides. Returns an all-empty object on any failure so
 * the caller can safely PATCH it to the engine (engine treats empty
 * strings as "not provided" and stores NULL).
 */
export async function readMerchantThemeOverrides(
  admin: AdminGraphqlClient,
): Promise<ShopifyThemeOverrides> {
  try {
    const resp = await admin.graphql(
      `#graphql
      query VibeThemeSettings {
        themes(first: 1, roles: [MAIN]) {
          edges {
            node {
              id
              files(filenames: ["config/settings_data.json"]) {
                edges {
                  node {
                    body {
                      ... on OnlineStoreThemeFileBodyText {
                        content
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }`,
    );
    if (!resp.ok) return EMPTY;
    const gql = (await resp.json()) as ThemeFileQueryResult;
    const content =
      gql.data?.themes?.edges?.[0]?.node?.files?.edges?.[0]?.node?.body?.content;
    if (!content) return EMPTY;
    return probeThemeSettings(content);
  } catch {
    // GraphQL failure, JSON parse failure, missing scope — all silent.
    // The CSS layer falls back to Confident Luxe defaults; nothing
    // about the storefront breaks because a probe didn't work.
    return EMPTY;
  }
}

/**
 * Parse `config/settings_data.json` and pick the merchant's chosen
 * font + colors. Exposed for tests; called by `readMerchantThemeOverrides`.
 *
 * Theme settings JSON has a `current` key with the live theme
 * configuration (or `"presets"` referencing one). Different themes
 * use different setting names — Dawn uses `type_body_font` and
 * `colors_accent_1`; Studio uses `font_body` and `color_primary`;
 * Refresh uses yet another set. We probe a fallback chain ordered
 * most-common-first and give up gracefully when nothing matches.
 */
export function probeThemeSettings(rawJson: string): ShopifyThemeOverrides {
  let parsed: unknown;
  try {
    parsed = JSON.parse(rawJson);
  } catch {
    return EMPTY;
  }
  if (!parsed || typeof parsed !== "object") return EMPTY;
  const root = parsed as Record<string, unknown>;
  // `current` is the live theme settings; falls back to the first
  // preset if `current` is just a preset name (string).
  let settings: Record<string, unknown> = {};
  const cur = root.current;
  if (cur && typeof cur === "object") {
    settings = cur as Record<string, unknown>;
  } else if (typeof cur === "string") {
    const presets = root.presets as Record<string, unknown> | undefined;
    if (presets && presets[cur] && typeof presets[cur] === "object") {
      settings = presets[cur] as Record<string, unknown>;
    }
  }
  // Newer Shopify themes nest under `current.settings` instead of
  // putting fields at the top level. Probe both.
  const nestedSettings = (settings.settings || settings) as Record<
    string,
    unknown
  >;

  return {
    font_body: pickFont(nestedSettings, [
      "type_body_font",       // Dawn, Sense, others derived from Dawn
      "font_body",            // Studio, Refresh
      "body_font",
      "main_body_font",
    ]),
    color_primary: pickColor(nestedSettings, [
      "colors_accent_1",      // Dawn
      "color_primary",        // Studio
      "accent_color",
      "primary_color",
      "button_color",
      "color_button_background",
    ]),
    color_background: pickColor(nestedSettings, [
      "colors_background_1",  // Dawn
      "color_background",
      "background_color",
    ]),
    color_text: pickColor(nestedSettings, [
      "colors_text",          // Dawn
      "color_text",
      "text_color",
    ]),
    // Header logo isn't typically in settings_data.json — it lives in
    // a section's settings or as a file under `assets/`. Skipping for
    // MVP; vibe-app can fall back to the shop's name as a text logo.
    logo_url: "",
  };
}

function pickFont(
  settings: Record<string, unknown>,
  candidates: string[],
): string {
  for (const key of candidates) {
    const raw = settings[key];
    if (typeof raw !== "string") continue;
    const value = raw.trim();
    if (!value) continue;
    // Shopify font_picker values look like `assistant_n4` or
    // `inter_n5` — family name + weight + variant. Strip the weight
    // suffix to get a usable Google Fonts family name. Best-effort:
    // some custom themes store the full CSS font-family string here
    // and we pass that through unchanged.
    const cleaned = value.replace(/_n\d.*$/i, "").replace(/_/g, " ");
    return titleCase(cleaned);
  }
  return "";
}

function pickColor(
  settings: Record<string, unknown>,
  candidates: string[],
): string {
  for (const key of candidates) {
    const raw = settings[key];
    if (typeof raw !== "string") continue;
    const value = raw.trim();
    if (!value) continue;
    // Accept hex (#RRGGBB or #RGB), rgb(), or rgba() — pass through
    // verbatim. Anything else (theme variable names like `gradient`,
    // empty CSS expressions) gets skipped.
    if (/^#[0-9a-f]{3,8}$/i.test(value)) return value;
    if (/^rgba?\(/i.test(value)) return value;
  }
  return "";
}

function titleCase(s: string): string {
  return s
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}
