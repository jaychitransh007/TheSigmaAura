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
  // PR #480 additions for MerchantHeader replication.
  shop_name: string;
  main_menu: Array<{ title: string; url: string }>;
};

const EMPTY: ShopifyThemeOverrides = {
  font_body: "",
  color_primary: "",
  color_background: "",
  color_text: "",
  logo_url: "",
  shop_name: "",
  main_menu: [],
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

type ShopAndMenuQueryResult = {
  data?: {
    shop?: { name?: string };
    menu?: {
      title?: string;
      items?: Array<{
        title?: string;
        url?: string;
        items?: Array<{ title?: string; url?: string }>;
      }>;
    };
  };
};

/**
 * Fetch theme settings + shop name + main menu in a single Admin
 * GraphQL round-trip. Returns an all-empty object on any failure so
 * the caller can safely PATCH it to the engine (engine treats empty
 * strings as "not provided" and stores NULL).
 *
 * The combined fetch is intentional — vibe-app PATCHes the whole
 * `theme_overrides` payload at once, so reading both in one query
 * avoids a second round-trip and keeps everything consistent at
 * write time. Logo URL is left empty in this MVP; the MerchantHeader
 * falls back to the shop's name as a text logo.
 */
export async function readMerchantThemeOverrides(
  admin: AdminGraphqlClient,
): Promise<ShopifyThemeOverrides> {
  // Two independent queries because the `themes` query and `menu`
  // query don't compose well in a single document (menu uses a
  // handle, themes uses a role filter). Run sequentially; a failure
  // on the first short-circuits the rest of the probe — Confident
  // Luxe defaults take over.
  let themeContent = "";
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
    if (resp.ok) {
      const gql = (await resp.json()) as ThemeFileQueryResult;
      themeContent =
        gql.data?.themes?.edges?.[0]?.node?.files?.edges?.[0]?.node?.body
          ?.content ?? "";
    }
  } catch {
    // Continue — we'll still try the menu probe.
  }

  let shopName = "";
  let menuItems: Array<{ title: string; url: string }> = [];
  try {
    const resp = await admin.graphql(
      `#graphql
      query VibeShopAndMenu {
        shop { name }
        menu(handle: "main-menu") {
          title
          items {
            title
            url
            items { title url }
          }
        }
      }`,
    );
    if (resp.ok) {
      const gql = (await resp.json()) as ShopAndMenuQueryResult;
      shopName = String(gql.data?.shop?.name ?? "").trim();
      const items = gql.data?.menu?.items ?? [];
      for (const it of items) {
        const title = String(it.title ?? "").trim();
        const url = String(it.url ?? "").trim();
        if (title && url) menuItems.push({ title, url });
      }
    }
  } catch {
    // Continue — partial probe is still useful.
  }

  const themeProbed = themeContent ? probeThemeSettings(themeContent) : EMPTY;
  return {
    ...themeProbed,
    shop_name: shopName,
    main_menu: menuItems,
  };
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
    // shop_name + main_menu live outside settings_data.json — they're
    // populated separately by `readMerchantThemeOverrides` via a
    // second GraphQL query. probeThemeSettings returns empty for
    // these so the merged result still type-checks.
    shop_name: "",
    main_menu: [],
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
